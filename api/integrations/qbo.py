"""QuickBooks Online writes for approved credit memos (F10). Only this code writes to the books, and only after
the admin (or the owner's policy: memos of $1,000 or less, or under the admin's auto-post limit) has said yes.

Live (QBO_* keys set): the sandbox REST API. The base URL, minorversion and the query / create / get calls
follow scripts/seed_quickbooks.py, which created each account's customer (Peak Bar's: Northmart) and invoice
(INV-3102) and the shared "Promotional Allowance" item in the one sandbox company. Each write carries `requestid`
(Intuit: a repeat with the same id gets the first response back, not a duplicate; at most 50 characters), built from
the approval id. Every call goes through replay.call_outside, so DEMO_MODE replays recorded responses.
- The credit memo is applied with a $0 Payment whose lines link INV-3102 and the credit memo (Intuit's Payment
  reference). Verify in the sandbox UI that the invoice's balance drops by the memo amount.
- The open-balance note is a sparse update (Id, SyncToken, "sparse": true) of the invoice's PrivateNote.
- POST /demo/reset undoes all of it (undo_demo_writes), for every account's customer: every credit memo and
  payment Clawback writes has a PrivateNote starting "Clawback ", so the reset finds them, deletes them and clears
  the invoice note.

The read side (invoice, customer_payments, record_payment, delete_payment) is for api/integrations/qbo_source.py,
which watches for payments recorded against each account's invoice and starts its run; those calls are never
recorded as fixtures.

Stand-in (no QBO keys yet, or DEMO_MODE): answers with the same shapes and ids starting "sim-". It's never
recorded as a fixture, and every ledger post it backs says it was simulated and why. DEMO_MODE uses it even with the
keys set: every write carries the run's approval id and today's date, so a recorded response could never match a
new run's request, and the books would fail with Wi-Fi off.
"""

from __future__ import annotations

import itertools
import logging
import os
import re
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from api.integrations import replay

BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"
MINOR = "75"
REDIRECT_URI = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"  # unused by a refresh
ENV = Path(__file__).resolve().parents[2] / ".env"
log = logging.getLogger("clawback.qbo")
CUSTOMER = "Northmart"  # Peak Bar's; every account names its own (account.yaml qbo.customer)
ALLOWANCE_ITEM = "Promotional Allowance"
KEYS = ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN")
MARK = "Clawback "  # how every credit memo and payment Clawback writes starts its PrivateNote
OPEN_NOTE = re.compile(r"Open \$[\d,]+\.\d\d disputed with [^:]+:")  # pipeline._post_books' invoice note


class BooksError(RuntimeError):
    pass


@dataclass(frozen=True)
class Line:
    charge_id: str | None
    description: str
    amount: Decimal


@dataclass(frozen=True)
class Posted:
    entity: str  # CreditMemo, Payment, Invoice
    id: str
    amount: Decimal
    simulated: bool


@dataclass(frozen=True)
class Undone:
    entity: str  # Payment, CreditMemo, Invoice
    id: str
    action: str  # deleted · note cleared
    note: str  # the PrivateNote that marked it as Clawback's
    simulated: bool


def _money(v: Decimal) -> float:
    return float(Decimal(v).quantize(Decimal("0.01")))


class LiveBooks:
    simulated = False

    def __init__(self, realm: str, token: Callable[[], str], http: httpx.Client | None = None):
        self.realm, self._token = realm, token
        self.http = http or httpx.Client(base_url=f"{BASE}/{realm}")
        self._ids: dict[str, str] = {}

    def _call(self, method: str, path: str, *, params: dict | None = None, body: Any = None,
              request_id: str | None = None, record: bool | None = None) -> dict:
        q = {"minorversion": MINOR, **(params or {}), **({"requestid": request_id} if request_id else {})}
        request = {"method": method, "path": path, "params": q, "body": body}  # no token: it's never recorded

        def send(req: dict, timeout: float) -> httpx.Response:
            return self.http.request(req["method"], req["path"], params=req["params"], json=req["body"],
                                     timeout=timeout,
                                     headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"})

        def live(req: dict, timeout: float) -> dict:
            r = send(req, timeout)
            if r.status_code == 401 and hasattr(self._token, "expire"):  # the hour-long access token ran out
                self._token.expire()
                r = send(req, timeout)
            if r.status_code >= 400:
                raise BooksError(f"QuickBooks {method} {path} returned {r.status_code}: {r.text[:300]}")
            return r.json()

        try:
            return replay.call_outside("qbo", request, live, record=record).response
        except replay.OutsideCallFailed as e:
            raise BooksError(str(e)) from e

    def _query(self, entity: str, where: str, record: bool | None = None) -> list[dict]:
        found = self._call("GET", "/query", params={"query": f"select * from {entity} where {where}"}, record=record)
        return found.get("QueryResponse", {}).get(entity, [])

    # ---- the read side (api/integrations/qbo_source.py): never recorded as fixtures, so polling while `make record`
    # runs writes nothing to data/fixtures/

    def invoice(self, invoice_no: str) -> dict | None:
        """The invoice with this DocNumber (its Id, CustomerRef, Balance), or None if the sandbox has none."""
        rows = self._query("Invoice", f"DocNumber = '{_quoted(invoice_no)}'", record=False)
        return rows[0] if rows else None

    def customer_payments(self, customer_id: str) -> list[dict]:
        """Every payment recorded for this customer: the same query the reset uses (CustomerRef, MAXRESULTS 1000)."""
        return self._query("Payment", f"CustomerRef = '{_quoted(customer_id)}' MAXRESULTS 1000", record=False)

    def record_payment(self, request_id: str, invoice: dict, amount: Decimal, note: str) -> dict:
        """A customer payment applied to the invoice, as scripts/seed_quickbooks.py records the seed's (the demo's
        "the distributor paid" in QuickBooks: python -m api.integrations.qbo_source pay <account>)."""
        body = {"CustomerRef": invoice["CustomerRef"], "TotalAmt": _money(amount), "TxnDate": date.today().isoformat(),
                "PrivateNote": note,
                "Line": [{"Amount": _money(amount), "LinkedTxn": [{"TxnId": invoice["Id"], "TxnType": "Invoice"}]}]}
        return self._call("POST", "/payment", body=body, request_id=request_id, record=False)["Payment"]

    def delete_payment(self, payment: dict) -> None:
        """Intuit's delete operation (POST /payment?operation=delete with Id and SyncToken), as undo_demo_writes."""
        self._call("POST", "/payment", params={"operation": "delete"},
                   body={"Id": payment["Id"], "SyncToken": payment["SyncToken"]},
                   request_id=f"undo-payment-{payment['Id']}-{payment['SyncToken']}", record=False)

    def _find(self, entity: str, where: str) -> dict:
        rows = self._query(entity, where)
        if not rows:
            raise BooksError(f"QuickBooks has no {entity} where {where}; run scripts/seed_quickbooks.py")
        return rows[0]

    def _id(self, entity: str, where: str) -> str:
        key = f"{entity}:{where}"
        if key not in self._ids:
            self._ids[key] = self._find(entity, where)["Id"]
        return self._ids[key]

    def post_credit_memo(self, request_id: str, lines: Sequence[Line], memo: str, customer: str = CUSTOMER) -> Posted:
        item = self._id("Item", f"Name = '{ALLOWANCE_ITEM}'")
        body = {"CustomerRef": {"value": self._id("Customer", f"DisplayName = '{_quoted(customer)}'")},
                "TxnDate": date.today().isoformat(), "PrivateNote": memo,
                "Line": [{"Amount": _money(ln.amount), "DetailType": "SalesItemLineDetail", "Description": ln.description,
                          "SalesItemLineDetail": {"ItemRef": {"value": item}, "Qty": 1, "UnitPrice": _money(ln.amount)}}
                         for ln in lines]}
        made = self._call("POST", "/creditmemo", body=body, request_id=request_id)["CreditMemo"]
        return Posted("CreditMemo", made["Id"], Decimal(str(made["TotalAmt"])), False)

    def open_balance(self, invoice_no: str) -> Decimal | None:
        """What's still open on the invoice (None if QuickBooks didn't say)."""
        balance = self._find("Invoice", f"DocNumber = '{invoice_no}'").get("Balance")
        return None if balance is None else Decimal(str(balance))

    def apply_to_invoice(self, request_id: str, invoice_no: str, credit_memo_id: str, amount: Decimal) -> Posted:
        invoice = self._find("Invoice", f"DocNumber = '{invoice_no}'")
        body = {"CustomerRef": invoice["CustomerRef"], "TotalAmt": 0, "PrivateNote": f"{MARK}{request_id}",
                "Line": [{"Amount": _money(amount), "LinkedTxn": [{"TxnId": invoice["Id"], "TxnType": "Invoice"}]},
                         {"Amount": _money(amount), "LinkedTxn": [{"TxnId": credit_memo_id, "TxnType": "CreditMemo"}]}]}
        made = self._call("POST", "/payment", body=body, request_id=request_id)["Payment"]
        return Posted("Payment", made["Id"], Decimal(amount), False)

    def note_open_balance(self, request_id: str, invoice_no: str, note: str, disputed: Decimal) -> Posted:
        invoice = self._find("Invoice", f"DocNumber = '{invoice_no}'")
        body = {"Id": invoice["Id"], "SyncToken": invoice["SyncToken"], "sparse": True, "PrivateNote": note}
        made = self._call("POST", "/invoice", body=body, request_id=request_id)["Invoice"]
        return Posted("Invoice", made["Id"], Decimal(disputed), False)

    def undo_demo_writes(self, customers: Sequence[str] | None = None) -> list[Undone]:
        """Delete every payment and credit memo Clawback wrote for these customers (every account's, by default) and
        clear its note from their invoices, so the sandbox is back to the seed: INV-3102 with $6,850 open, and each
        other account's invoice with its own short payment open. Payments go first, so no memo is still applied
        when it's deleted. A $0 payment from before payments carried the note is found by the Clawback memo it links.
        Running it again finds nothing and changes nothing.

        Delete, not void (a void keeps the record with its amounts zeroed), per Intuit's QuickBooks Online Accounting
        API reference, "Delete a payment" and "Delete a credit memo": POST /{entity}?operation=delete with the Id and
        the latest SyncToken.
        https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/payment
        https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/creditmemo
        Intuit's SDKs send the same request: QuickBooks-V3-Java-SDK DataService.prepareDelete and
        QuickBooks-V3-PHP-SDK DataService::Delete."""
        undone: list[Undone] = []
        for name in dict.fromkeys(customers if customers is not None else account_customers()):
            undone += self._undo_customer(name)
        return undone

    def _undo_customer(self, name: str) -> list[Undone]:
        named = f"DisplayName = '{_quoted(name)}'"
        if f"Customer:{named}" not in self._ids:  # _id(), except that a customer not seeded yet has nothing to undo
            found = self._query("Customer", named)
            if not found:
                return []
            self._ids[f"Customer:{named}"] = found[0]["Id"]
        where = f"CustomerRef = '{self._ids[f'Customer:{named}']}' MAXRESULTS 1000"
        memos = [m for m in self._query("CreditMemo", where) if m.get("PrivateNote", "").startswith(MARK)]
        ours = {m["Id"] for m in memos}
        payments = [p for p in self._query("Payment", where) if p.get("PrivateNote", "").startswith(MARK) or any(
            lt.get("TxnType") == "CreditMemo" and lt.get("TxnId") in ours
            for ln in p.get("Line", []) for lt in ln.get("LinkedTxn", []))]
        undone: list[Undone] = []
        for entity, rows in (("Payment", payments), ("CreditMemo", memos)):
            for row in rows:
                self._call("POST", f"/{entity.lower()}", params={"operation": "delete"},
                           body={"Id": row["Id"], "SyncToken": row["SyncToken"]},
                           request_id=f"undo-{entity.lower()}-{row['Id']}")
                undone.append(Undone(entity, row["Id"], "deleted", row.get("PrivateNote", ""), False))
        for invoice in self._query("Invoice", where):
            if OPEN_NOTE.match(invoice.get("PrivateNote", "")):
                body = {"Id": invoice["Id"], "SyncToken": invoice["SyncToken"], "sparse": True, "PrivateNote": ""}
                # the SyncToken keeps each reset's request id new: a repeated id would get the first answer back
                self._call("POST", "/invoice", body=body,
                           request_id=f"undo-note-{invoice['Id']}-{invoice['SyncToken']}")
                undone.append(Undone("Invoice", invoice["Id"], "note cleared", invoice["PrivateNote"], False))
        return undone


class StandInBooks:
    """No QuickBooks keys yet, or DEMO_MODE: the same answers, clearly fake. Keeps what it 'posted' for tests and the
    log; `why` says which it is."""

    simulated = True

    def __init__(self, why: str = "QuickBooks keys aren't set yet"):
        self.why = why
        self.calls: list[tuple[str, str, Any]] = []
        self._seq = itertools.count(1)
        self._seen: dict[str, Posted] = {}

    def _post(self, request_id: str, entity: str, amount: Decimal, detail: Any) -> Posted:
        if request_id in self._seen:  # same request id, same answer: like Intuit's requestid
            return self._seen[request_id]
        posted = Posted(entity, f"sim-{entity.lower()}-{next(self._seq)}", Decimal(amount), True)
        self._seen[request_id] = posted
        self.calls.append((entity, request_id, detail))
        return posted

    def post_credit_memo(self, request_id: str, lines: Sequence[Line], memo: str, customer: str = CUSTOMER) -> Posted:
        return self._post(request_id, "CreditMemo", sum((ln.amount for ln in lines), Decimal(0)),
                          {"memo": memo, "lines": lines, "customer": customer})

    def apply_to_invoice(self, request_id: str, invoice_no: str, credit_memo_id: str, amount: Decimal) -> Posted:
        return self._post(request_id, "Payment", amount, {"invoice": invoice_no, "credit_memo": credit_memo_id})

    def note_open_balance(self, request_id: str, invoice_no: str, note: str, disputed: Decimal) -> Posted:
        return self._post(request_id, "Invoice", disputed, {"invoice": invoice_no, "note": note})

    def open_balance(self, invoice_no: str) -> Decimal | None:
        return None  # the stand-in keeps no invoice

    def undo_demo_writes(self, customers: Sequence[str] | None = None) -> list[Undone]:
        """Clears what it 'posted' (for every customer), in LiveBooks' order: payments, credit memos, then each
        invoice's note once."""
        posted = [(entity, self._seen[rid].id, rid, detail) for entity, rid, detail in self.calls]
        undone = [Undone(entity, sim_id, "deleted", detail.get("memo", f"{MARK}{rid}"), True)
                  for kind in ("Payment", "CreditMemo") for entity, sim_id, rid, detail in posted if entity == kind]
        notes = {detail["invoice"]: Undone("Invoice", sim_id, "note cleared", detail["note"], True)
                 for entity, sim_id, _, detail in posted if entity == "Invoice"}
        self.calls.clear(), self._seen.clear()
        return undone + list(notes.values())


_books: LiveBooks | StandInBooks | None = None


def account_customers() -> list[str]:
    """Every account's QuickBooks customer (data/accounts/<id>/account.yaml qbo.customer)."""
    from api import accounts

    return [a.config.qbo.customer for a in accounts.every()]


def _quoted(name: str) -> str:
    """A name inside a QuickBooks query string: a single quote is escaped with a backslash."""
    return name.replace("'", "\\'")


def _token_file() -> Path | None:
    """Where the VM keeps the newest refresh token: QBO_TOKEN_FILE, a file in the mounted state/ folder that outlives
    the container (compose sets it). Laptops have none and keep the token in the repo's .env."""
    return Path(os.environ["QBO_TOKEN_FILE"]) if os.getenv("QBO_TOKEN_FILE") else None


def _keep_refresh_token(kept: Path | None, value: str) -> None:
    """Refresh tokens rotate, and Intuit stops taking the old one a day later: save the new one where the next start
    reads it. A failed save is logged, never raised (the write in hand still has its access token)."""
    from dotenv import set_key

    try:
        if kept:
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.touch(mode=0o600, exist_ok=True)
            set_key(str(kept), "QBO_REFRESH_TOKEN", value)
        elif ENV.exists():
            set_key(str(ENV), "QBO_REFRESH_TOKEN", value)
    except OSError as e:
        log.warning("couldn't save the rotated QuickBooks refresh token (%s); it lasts until this process stops", e)


def _refreshing_token() -> Callable[[], str]:
    """An access token from the newest refresh token: QBO_TOKEN_FILE's when it has one, else QBO_REFRESH_TOKEN.
    A rotated refresh token is saved back (_keep_refresh_token)."""
    from dotenv import dotenv_values
    from intuitlib.client import AuthClient

    cache: dict[str, str] = {}
    lock = threading.Lock()  # the payments poller and a write can both need one: refresh (and rotate) only once

    def token() -> str:
        with lock:
            return _fresh()

    def _fresh() -> str:
        if "access" not in cache:
            kept = _token_file()
            saved = dotenv_values(kept).get("QBO_REFRESH_TOKEN") if kept and kept.exists() else None
            current = saved or os.environ["QBO_REFRESH_TOKEN"]
            auth = AuthClient(os.environ["QBO_CLIENT_ID"], os.environ["QBO_CLIENT_SECRET"], REDIRECT_URI, "sandbox",
                              refresh_token=current, realm_id=os.environ["QBO_REALM_ID"])
            auth.refresh()
            if auth.refresh_token != current:
                os.environ["QBO_REFRESH_TOKEN"] = auth.refresh_token
                _keep_refresh_token(kept, auth.refresh_token)
            cache["access"] = auth.access_token
        return cache["access"]

    token.expire = lambda: cache.pop("access", None)  # Intuit's access tokens last an hour; a 401 calls this
    return token


_history_books: StandInBooks | None = None


def books() -> LiveBooks | StandInBooks:
    global _books, _history_books
    if replay.forced():  # the replayed history (api/story.py): its own stand-in, never the live books' cache
        if _history_books is None:
            _history_books = StandInBooks("part of the history replayed before this payment, not written to QuickBooks")
        return _history_books
    if _books is None:
        if not all(os.getenv(k) for k in KEYS):
            _books = StandInBooks()
        elif replay.demo_mode():
            _books = StandInBooks("DEMO_MODE is on, so nothing reaches QuickBooks")
        else:
            _books = LiveBooks(os.environ["QBO_REALM_ID"], _refreshing_token())
    return _books


def reset() -> None:
    global _books, _history_books
    _books = _history_books = None
