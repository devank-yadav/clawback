"""Capital One Nessie (F15): a distributor's short payment arrives as a deposit, and that starts its account's run.

Calls follow scripts/nessie_deposit.py (base URL, ?key= on every call, POST /accounts/{id}/deposits per Nessie's
official SDK). Listing an account's deposits uses GET on the same path; Nessie's reference couldn't be checked
(its docs answer 403), so verify it once NESSIE_* keys are set. If it fails, the poller logs and keeps trying,
and the "Northmart pays" button (POST /payments/{account}) still starts the run.

Every account's deposit lands on the one NESSIE_ACCOUNT_ID; its description says whose it is (account.yaml
nessie_description, api/accounts.for_deposit): Peak Bar Co.'s four distributors are "Northmart remittance INV-3102",
"KeHE Distributors remittance PBK-2603", "Walmart remittance PBW-2603" and "Five Below remittance PBF-2603", each for
its invoice's received amount. A deposit that names no account is history, not a trigger. Each look and each new
deposit (with the account and the run it started) is noted for the Connections page (api/sources.py, "bank").

The poller checks every 5 seconds. Deposits already on the account when it starts are history, not triggers (so
the test deposit Manasv posted while setting up never starts a run).
It's off in DEMO_MODE, without keys, or with NESSIE_POLL=off; the button covers those.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx

from api import sources

log = logging.getLogger("clawback.nessie")

DEFAULT_BASE = "https://api.nessieisreal.com"  # the live API is HTTPS only
TIMEOUT_S = 10
POLL_S = 5.0
AMOUNT = Decimal("41350.00")  # Peak Bar's (data/CLAUDE.md): the short remittance for INV-3102
DESCRIPTION = "Northmart remittance INV-3102"  # Peak Bar's nessie_description


class NessieError(RuntimeError):
    pass


@dataclass(frozen=True)
class Deposit:
    id: str
    amount: Decimal
    description: str
    transaction_date: str | None


def configured() -> bool:
    return bool(os.getenv("NESSIE_API_KEY") and os.getenv("NESSIE_ACCOUNT_ID"))


def account_of(d: Deposit):
    """The account this deposit pays (an api.accounts.Account), or None: it isn't a trigger."""
    from api import accounts

    return accounts.for_deposit(d.description)


class Nessie:
    def __init__(self, key: str, account_id: str, http: httpx.Client | None = None):
        self.account_id = account_id
        self.http = http or httpx.Client(base_url=os.getenv("NESSIE_BASE_URL") or DEFAULT_BASE, timeout=TIMEOUT_S)
        self._key = key

    def _call(self, method: str, path: str, **kw):
        """One request with a timeout and one retry on a network error or 5xx (like the script)."""
        for attempt in (1, 2):
            try:
                r = self.http.request(method, path, params={"key": self._key}, **kw)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise NessieError(f"Nessie {method} {path} failed: {type(e).__name__}") from e
                continue
            if r.status_code >= 500 and attempt == 1:
                continue
            if r.status_code >= 400:
                raise NessieError(f"Nessie {method} {path} returned {r.status_code}")
            return r.json()

    def deposits(self) -> list[Deposit]:
        rows = self._call("GET", f"/accounts/{self.account_id}/deposits")
        return [Deposit(str(d["_id"]), Decimal(str(d.get("amount", 0))), d.get("description") or "",
                        d.get("transaction_date")) for d in rows]

    def post_deposit(self, amount: Decimal = AMOUNT, description: str = DESCRIPTION) -> Deposit:
        # status is required by the live API (400 without it); "pending" as in scripts/nessie_deposit.py
        body = {"medium": "balance", "transaction_date": date.today().isoformat(), "status": "pending",
                "amount": float(amount), "description": description}
        made = (self._call("POST", f"/accounts/{self.account_id}/deposits", json=body) or {}).get("objectCreated") or {}
        if "_id" not in made:
            raise NessieError("Nessie didn't return the new deposit's id")
        return Deposit(str(made["_id"]), amount, description, body["transaction_date"])


def client() -> Nessie | None:
    return Nessie(os.environ["NESSIE_API_KEY"], os.environ["NESSIE_ACCOUNT_ID"]) if configured() else None


def describe(d: Deposit) -> str:
    return f"Deposit {d.id} of ${d.amount:,.2f}" + (f" (“{d.description}”)" if d.description else "")


def note(d: Deposit, account_id: str, run: object) -> None:
    """The Connections page's line for a deposit that started (or matched) its account's run."""
    run_id, dep = getattr(run, "id", None), getattr(run, "deposit", None)
    matched = dep is not None and not (getattr(dep, "source", "nessie") == "nessie" and dep.id == d.id)
    sources.saw("bank", f"{describe(d)}: " + (f"the same payment as run {run_id}" if matched
                                             else f"started run {run_id}" if run_id else "the run is starting"),
                account_id, run_id)


class Poller:
    """Every POLL_S seconds, look for a new deposit that pays an account and hand it to `on_deposit` (once per
    deposit; pipeline.start_for_deposit finds the account again from the description)."""

    def __init__(self, nessie: Nessie, on_deposit: Callable[[Deposit], object], interval: float = POLL_S):
        self.nessie, self.on_deposit, self.interval = nessie, on_deposit, interval
        self.seen: set[str] | None = None  # filled on the first successful look: those deposits are history
        self.errors = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> list[Deposit]:
        """One look. Returns the deposits that started (or matched) a run. What it saw goes to the Connections page
        (api/sources.py): when it looked, and each new deposit with the account and run it belongs to."""
        try:
            found = self.nessie.deposits()
        except NessieError as e:
            self.errors += 1
            log.warning("nessie poll failed (%s); trying again", e)
            sources.checked("bank", error=str(e))
            return []
        sources.checked("bank")
        if self.seen is None:
            self.seen = {d.id for d in found}
            if found:
                sources.saw("bank", f"{len(found)} deposit{'s' if len(found) != 1 else ''} already on the account when "
                            "the agents started watching: history, not new payments")
            return []
        started = []
        for d in found:
            if d.id in self.seen:
                continue
            self.seen.add(d.id)
            if (account := account_of(d)) is None:
                sources.saw("bank", f"{describe(d)}: it names no distributor's invoice, so it isn't a payment to check")
                continue
            log.info("nessie: %s deposit %s of $%s arrived", account.id, d.id, d.amount)
            try:
                run = self.on_deposit(d)
            except Exception as e:  # noqa: BLE001 - one deposit that can't start a run never stops the poller
                log.exception("nessie: deposit %s couldn't start %s's run", d.id, account.id)
                sources.saw("bank", f"{describe(d)}: couldn't start the run ({type(e).__name__})", account.id)
                continue
            note(d, account.id, run)
            started.append(d)
        return started

    def start(self) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:  # noqa: BLE001 - the poller keeps looking
                    log.exception("nessie poll crashed; trying again")
                self._stop.wait(self.interval)

        self._thread = threading.Thread(target=loop, daemon=True, name="nessie-poller")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())


poller: Poller | None = None
