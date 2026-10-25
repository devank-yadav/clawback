"""QuickBooks as a source: a payment recorded against an account's invoice starts that account's run, as a Nessie
deposit does (api/integrations/nessie.py). The write side (credit memos after the admin's yes) is api/integrations/qbo.py.

Every QBO_POLL_S seconds, with the QBO_* keys set and not in DEMO_MODE (and QBO_POLL not "off"):
1. each account's invoice is looked up once by its DocNumber (account.yaml qbo.invoice_no, unique across accounts in
   the one sandbox company): its Id and its CustomerRef;
2. each of those customers' payments is listed: `select * from Payment where CustomerRef = '<id>' MAXRESULTS 1000`,
   the query undo_demo_writes already runs against the sandbox (Intuit's query reference: GET /v3/company/<realm>/query
   ?query=<select statement>; CustomerRef filters, MAXRESULTS at most 1,000). Customers can be shared by several
   accounts (KeHE Distributors pays Peak Bar and Lantern Hill), so a payment belongs to the account whose invoice it
   pays: a Line whose LinkedTxn has TxnType "Invoice" and that invoice's TxnId (Payment.Line.LinkedTxn in Intuit's
   Payment entity; field names as in Intuit's QuickBooks-V3-Java-SDK Payment / Transaction / Line / LinkedTxn);
3. a payment not seen before starts the account's run for the amount its lines apply to that invoice, once:
   pipeline.start_for_deposit keys it by "quickbooks:<Payment Id>", and a run the bank's deposit of the same payment
   started in the last half hour is matched instead of a second one.

A payment that can't start its run (the run raised) is tried once more, RETRY_AFTER_S later, then left to a person.
Each account's invoice is looked up again every REFRESH_INVOICES_S, and at once after POST /demo/reset
(forget_invoices), so a reseeded invoice with a new Id is watched without a restart; the payments already on it are
history, as on a newly seeded one.

Payments already there on the first look are history (the seed's $41,350 on INV-3102 never starts a run), and so are
Clawback's own: the $0 payment that applies a credit memo (TotalAmt 0, PrivateNote "Clawback ..."). The access token
comes from qbo.books() (one LiveBooks, so the refresh token rotates in one place and is saved, qbo._refreshing_token).
Reads go through replay.call_outside (timeout, one retry, the DEMO_MODE fixture fallback) but are never recorded.
A failed look is noted and tried again next time. Without the keys, or in DEMO_MODE, nothing polls: the Connections
page says QuickBooks isn't connected and postings stay with the stand-in (qbo.StandInBooks), saying so.

Demo: with the server running, `python -m api.integrations.qbo_source pay peak-bar` records Northmart's $41,350
payment on INV-3102 in the sandbox (as a bookkeeper would), and the poller starts the run. INV-3102 already has the
seed's payment, so `--replace` deletes that one first (Intuit's delete operation, as the reset uses).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from api import accounts, sources
from api.integrations import qbo, replay

log = logging.getLogger("clawback.qbo_source")

POLL_S = 15.0  # one query per customer per look: well inside Intuit's per-company request limits
RETRY_MISSING_S = 60.0  # an invoice the sandbox doesn't have yet is looked up again this often
REFRESH_INVOICES_S = 120.0  # a found invoice is looked up again this often: a reseed gives it a new Id
RETRY_AFTER_S = 60.0  # a payment that couldn't start its run is tried once more, this long after
FAILED = object()  # what _start returns when the run couldn't start (on_payment itself may return None)
DEMO_NOTE = "Recorded for the Clawback demo: the distributor's payment"  # never starts with qbo.MARK


@dataclass(frozen=True)
class Payment:
    """A payment recorded in QuickBooks against an account's invoice: what pipeline.start_for_deposit takes."""

    id: str  # QuickBooks' Payment Id
    amount: Decimal  # what its lines apply to the account's invoice
    description: str  # "Northmart payment on INV-3102"
    account_id: str
    total: Decimal  # the payment's TotalAmt
    txn_date: str | None
    source: str = "quickbooks"


def configured() -> bool:
    return all(os.getenv(k) for k in qbo.KEYS)


def should_poll() -> bool:
    return configured() and not replay.demo_mode() and os.getenv("QBO_POLL", "on").lower() != "off"


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def ours(p: dict) -> bool:
    """Clawback's own writes: the $0 payment applying a credit memo (and anything else it notes as its own)."""
    return p.get("PrivateNote", "").startswith(qbo.MARK) or _money(p.get("TotalAmt")) == 0


def applied(p: dict, invoice_id: str) -> Decimal:
    """What the payment's lines apply to this invoice."""
    return sum((_money(ln.get("Amount")) for ln in p.get("Line", [])
                if any(lt.get("TxnType") == "Invoice" and str(lt.get("TxnId")) == invoice_id
                       for lt in ln.get("LinkedTxn", []))), Decimal("0.00"))


class Poller:
    """Look for new payments against every account's invoice; hand each to `on_payment` once."""

    def __init__(self, books: qbo.LiveBooks, on_payment: Callable[[Payment], object], interval: float = POLL_S,
                 every: Callable[[], list[accounts.Account]] = accounts.every, retry_after: float = RETRY_AFTER_S,
                 clock: Callable[[], float] = time.monotonic):
        self.books, self.on_payment, self.interval, self.every = books, on_payment, interval, every
        self.retry_after, self.clock = retry_after, clock
        self._retry: dict[str, tuple[Payment, str, float]] = {}  # "<payment>:<account>" -> (payment, words, when)
        self._found_at: dict[str, float] = {}  # account id -> when its invoice was last looked up and found
        self.seen: set[str] | None = None  # Payment Ids; filled on the first successful look: those are history
        self.customers: set[str] = set()  # customer Ids watched so far; a newly watched one's payments are history
        self.watched: set[str] = set()  # invoice Ids watched so far; payments already on a newly watched one are too
        self.invoices: dict[str, dict] = {}  # account id -> its invoice in the sandbox (Id, CustomerRef)
        self._missing: dict[str, float] = {}  # account id -> when its invoice was last not found
        self.errors = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _invoice(self, a: accounts.Account) -> dict | None:
        now = self.clock()
        cached = self.invoices.get(a.id)  # .get: POST /demo/reset may clear it from another thread
        if cached is not None and now - self._found_at.get(a.id, now) < REFRESH_INVOICES_S:
            return cached
        if cached is None and now - self._missing.get(a.id, -RETRY_MISSING_S) < RETRY_MISSING_S:
            return None
        found = self.books.invoice(a.config.qbo.invoice_no)
        if found is None:
            self.invoices.pop(a.id, None)  # deleted since (a reset or a reseed in progress): nothing to watch
            self._missing[a.id] = now  # not seeded (scripts/seed_quickbooks.py): nothing to watch yet
            return None
        self.invoices[a.id], self._found_at[a.id] = found, now
        return found

    def forget_invoices(self) -> None:
        """Look every invoice up again on the next look (POST /demo/reset calls it): a reseeded invoice has a new Id."""
        self.invoices.clear()
        self._found_at.clear()
        self._missing.clear()

    def _start(self, payment: Payment, what: str, a: accounts.Account, again: bool) -> object:
        """Hand one payment to on_payment. A first failure is tried once more later; a second one is left to a person."""
        try:
            return self.on_payment(payment)
        except Exception as e:  # noqa: BLE001 - one payment that can't start a run never stops the poller
            log.exception("quickbooks: payment %s couldn't start %s's run", payment.id, a.id)
            if again:
                sources.saw("quickbooks", f"{what}: still couldn't start the run ({type(e).__name__}); start it from "
                            "Agents or upload the remittance", a.id)
            else:
                self._retry[f"{payment.id}:{a.id}"] = (payment, what, self.clock() + self.retry_after)
                sources.saw("quickbooks", f"{what}: couldn't start the run ({type(e).__name__}); trying once more in "
                            f"{self.retry_after:.0f} s", a.id)
            return FAILED

    def _noted(self, payment: Payment, what: str, a: accounts.Account, run: object) -> None:
        run_id, dep = getattr(run, "id", None), getattr(run, "deposit", None)
        matched = dep is not None and not (getattr(dep, "source", "nessie") == "quickbooks" and dep.id == payment.id)
        sources.saw("quickbooks", f"{what}: " + (f"the same payment as run {run_id}" if matched
                                                 else f"started run {run_id}"), a.id, run_id)

    def _retry_due(self, targets: dict[str, accounts.Account]) -> list[Payment]:
        """The payments whose one retry is due: started now, or left to a person."""
        now, done = self.clock(), []
        by_id = {a.id: a for a in targets.values()}
        for key, (payment, what, when) in list(self._retry.items()):
            if now < when:
                continue
            del self._retry[key]
            a = by_id.get(payment.account_id) or accounts.get(payment.account_id)
            run = self._start(payment, what, a, again=True)
            if run is not FAILED:
                self._noted(payment, what, a, run)
                done.append(payment)
        return done

    def look(self) -> tuple[dict[str, accounts.Account], dict[str, list[dict]]]:
        """The watched invoices (sandbox Id -> account) and each of their customers' payments (customer Id -> them)."""
        targets: dict[str, accounts.Account] = {}
        customers: dict[str, None] = {}
        for a in self.every():
            inv = self._invoice(a)
            if inv is not None:
                targets[str(inv["Id"])] = a
                customers[str(inv["CustomerRef"]["value"])] = None
        return targets, {c: self.books.customer_payments(c) for c in customers}

    def tick(self) -> list[Payment]:
        """One look. Returns the payments that started (or matched) a run."""
        try:
            targets, by_customer = self.look()
        except qbo.BooksError as e:
            self.errors += 1
            log.warning("quickbooks poll failed (%s); trying again", e)
            sources.checked("quickbooks", error=str(e)[:300])
            return []
        sources.checked("quickbooks")
        # What was already there when it started being watched is history: every payment on the first look, and later
        # a newly watched customer's payments or ones already applied to a newly watched invoice (seeded since).
        found = [p for ps in by_customer.values() for p in ps]
        new_invoices = set(targets) - self.watched
        fresh = [p for c, ps in by_customer.items() if c not in self.customers for p in ps] + \
            [p for p in found if any(applied(p, i) > 0 for i in new_invoices)]
        self.customers |= set(by_customer)
        self.watched |= set(targets)
        first = self.seen is None
        self.seen = (self.seen or set()) | {str(p["Id"]) for p in (found if first else fresh)}
        if first:
            if found:
                sources.saw("quickbooks", f"{len(found)} payment{'s' if len(found) != 1 else ''} already recorded "
                            "when the agents started watching: history, not new payments")
            return []
        started = []
        for p in found:
            pid = str(p["Id"])
            if pid in self.seen:
                continue
            self.seen.add(pid)
            if ours(p):
                continue  # Clawback's own credit memo application
            for inv_id, a in targets.items():
                amount = applied(p, inv_id)
                if amount <= 0:
                    continue
                payment = Payment(id=pid, amount=amount, account_id=a.id, total=_money(p.get("TotalAmt")),
                                  txn_date=p.get("TxnDate"),
                                  description=f"{a.distributor.name} payment on {a.config.qbo.invoice_no}")
                what = f"Payment {pid} of ${amount:,.2f} on {a.config.qbo.invoice_no} ({a.distributor.name})"
                log.info("quickbooks: %s", what)
                run = self._start(payment, what, a, again=False)
                if run is FAILED:
                    continue
                self._noted(payment, what, a, run)
                started.append(payment)
            if not any(applied(p, i) > 0 for i in targets):
                sources.saw("quickbooks", f"Payment {pid} of ${_money(p.get('TotalAmt')):,.2f} isn't against an invoice "
                            "the agents check")
        return started + self._retry_due(targets)

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:  # noqa: BLE001 - the poller keeps looking
                    log.exception("quickbooks poll crashed; trying again")
                self._stop.wait(self.interval)

        self._thread = threading.Thread(target=loop, daemon=True, name="qbo-poller")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())


poller: Poller | None = None


def start_poller(on_payment: Callable[[Payment], object]) -> Poller | None:
    """Start polling when it can run (keys set, not DEMO_MODE, QBO_POLL not "off"); api/main.py's startup calls it."""
    global poller
    books = qbo.books()
    if not should_poll() or not isinstance(books, qbo.LiveBooks):
        return None
    poller = Poller(books, on_payment)
    poller.start()
    return poller


# ---------------------------------------------------------------- the demo: record the distributor's payment

def pay(account_id: str, replace: bool = False, books: qbo.LiveBooks | None = None) -> dict:
    """Record the account's short payment (invoice.received) against its invoice in the sandbox. Raises BooksError."""
    a = accounts.get(account_id)
    books = books or qbo.books()
    if not isinstance(books, qbo.LiveBooks):
        raise qbo.BooksError(f"QuickBooks isn't live here ({books.why})")
    invoice = books.invoice(a.config.qbo.invoice_no)
    if invoice is None:
        raise qbo.BooksError(f"the sandbox has no invoice {a.config.qbo.invoice_no}; run scripts/seed_quickbooks.py")
    amount = Decimal(a.invoice.received)
    balance = _money(invoice.get("Balance"))
    if balance < amount:
        earlier = [p for p in books.customer_payments(str(invoice["CustomerRef"]["value"]))
                   if not ours(p) and applied(p, str(invoice["Id"])) == amount]
        if not replace or not earlier:
            raise qbo.BooksError(
                f"{a.config.qbo.invoice_no} has ${balance:,.2f} open, less than the ${amount:,.2f} payment: it's already "
                f"recorded (payment {', '.join(p['Id'] for p in earlier) or 'unknown'}). Run with --replace to delete "
                "that payment and record it again, so the poller sees a new one")
        for p in earlier:
            books.delete_payment(p)
        invoice = books.invoice(a.config.qbo.invoice_no) or invoice
    return books.record_payment(f"demo-pay-{uuid.uuid4().hex[:12]}", invoice, amount, DEMO_NOTE)


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    if len(argv) < 2 or argv[0] != "pay":
        print("usage: python -m api.integrations.qbo_source pay <account> [--replace]")
        return 2
    try:
        made = pay(argv[1], replace="--replace" in argv[2:])
    except (qbo.BooksError, accounts.UnknownAccount) as e:
        print(f"Not recorded: {e}")
        return 1
    print(f"Recorded payment {made['Id']} of ${Decimal(str(made['TotalAmt'])):,.2f} for {argv[1]}; the server's "
          f"poller starts the run within {POLL_S:.0f} seconds.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
