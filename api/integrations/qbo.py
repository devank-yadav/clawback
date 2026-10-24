"""QuickBooks Online writes for approved credit memos (F10). Only this code writes to the books, and only after
the controller (or the owner's policy, for memos of $1,000 or less) has said yes.

Live (QBO_* keys set): the sandbox REST API. The base URL, minorversion and the query / create / get calls
follow scripts/seed_quickbooks.py, which created customer Northmart, the "Promotional Allowance" item and
INV-3102. Each write carries `requestid` (Intuit: a repeat with the same id gets the first response back, not a
duplicate; at most 50 characters), built from the approval id. Every call goes through replay.call_outside, so
DEMO_MODE replays recorded responses.
- The credit memo is applied with a $0 Payment whose lines link INV-3102 and the credit memo (Intuit's Payment
  reference). Verify in the sandbox UI that the invoice's balance drops by the memo amount.
- The open-balance note is a sparse update (Id, SyncToken, "sparse": true) of the invoice's PrivateNote.
- POST /demo/reset undoes all of it (undo_demo_writes): every credit memo and payment Clawback writes has a
  PrivateNote starting "Clawback ", so the reset finds them, deletes them and clears the invoice note.

Stand-in (no QBO keys yet, or DEMO_MODE): answers with the same shapes and ids starting "sim-". It's never
recorded as a fixture, and every ledger post it backs says it was simulated and why. DEMO_MODE uses it even with the
keys set: every write carries the run's approval id and today's date, so a recorded response could never match a
new run's request, and the books would fail with Wi-Fi off.
"""

from __future__ import annotations

import itertools
import os
import re
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
CUSTOMER = "Northmart"
ALLOWANCE_ITEM = "Promotional Allowance"
KEYS = ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN")
MARK = "Clawback "  # how every credit memo and payment Clawback writes starts its PrivateNote
OPEN_NOTE = re.compile(rf"Open \$[\d,]+\.\d\d disputed with {CUSTOMER}:")  # pipeline._post_books' invoice note


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
              request_id: str | None = None) -> dict:
        q = {"minorversion": MINOR, **(params or {}), **({"requestid": request_id} if request_id else {})}
        request = {"method": method, "path": path, "params": q, "body": body}  # no token: it's never recorded

        def live(req: dict, timeout: float) -> dict:
            r = self.http.request(req["method"], req["path"], params=req["params"], json=req["body"], timeout=timeout,
                                  headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"})
            if r.status_code >= 400:
                raise BooksError(f"QuickBooks {method} {path} returned {r.status_code}: {r.text[:300]}")
            return r.json()

        try:
            return replay.call_outside("qbo", request, live).response
        except replay.OutsideCallFailed as e:
            raise BooksError(str(e)) from e

    def _query(self, entity: str, where: str) -> list[dict]:
        found = self._call("GET", "/query", params={"query": f"select * from {entity} where {where}"})
        return found.get("QueryResponse", {}).get(entity, [])

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

    def post_credit_memo(self, request_id: str, lines: Sequence[Line], memo: str) -> Posted:
        item = self._id("Item", f"Name = '{ALLOWANCE_ITEM}'")
        body = {"CustomerRef": {"value": self._id("Customer", f"DisplayName = '{CUSTOMER}'")},
                "TxnDate": date.today().isoformat(), "PrivateNote": memo,
                "Line": [{"Amount": _money(ln.amount), "DetailType": "SalesItemLineDetail", "Description": ln.description,
                          "SalesItemLineDetail": {"ItemRef": {"value": item}, "Qty": 1, "UnitPrice": _money(ln.amount)}}
                         for ln in lines]}
        made = self._call("POST", "/creditmemo", body=body, request_id=request_id)["CreditMemo"]
        return Posted("CreditMemo", made["Id"], Decimal(str(made["TotalAmt"])), False)

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

    def undo_demo_writes(self) -> list[Undone]:
        """Delete every payment and credit memo Clawback wrote for Northmart and clear its note from their invoices,
        so the sandbox is back to the seed: INV-3102 with $6,850 open. Payments go first, so no memo is still applied
        when it's deleted. A $0 payment from before payments carried the note is found by the Clawback memo it links.
        Running it again finds nothing and changes nothing.

        Delete, not void (a void keeps the record with its amounts zeroed), per Intuit's QuickBooks Online Accounting
        API reference, "Delete a payment" and "Delete a credit memo": POST /{entity}?operation=delete with the Id and
        the latest SyncToken.
        https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/payment
        https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/creditmemo
        Intuit's SDKs send the same request: QuickBooks-V3-Java-SDK DataService.prepareDelete and
        QuickBooks-V3-PHP-SDK DataService::Delete."""
        customer = self._id("Customer", f"DisplayName = '{CUSTOMER}'")
        where = f"CustomerRef = '{customer}' MAXRESULTS 1000"
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

    def post_credit_memo(self, request_id: str, lines: Sequence[Line], memo: str) -> Posted:
        return self._post(request_id, "CreditMemo", sum((ln.amount for ln in lines), Decimal(0)), {"memo": memo, "lines": lines})

    def apply_to_invoice(self, request_id: str, invoice_no: str, credit_memo_id: str, amount: Decimal) -> Posted:
        return self._post(request_id, "Payment", amount, {"invoice": invoice_no, "credit_memo": credit_memo_id})

    def note_open_balance(self, request_id: str, invoice_no: str, note: str, disputed: Decimal) -> Posted:
        return self._post(request_id, "Invoice", disputed, {"invoice": invoice_no, "note": note})

    def undo_demo_writes(self) -> list[Undone]:
        """Clears what it 'posted', in LiveBooks' order: payments, credit memos, then each invoice's note once."""
        posted = [(entity, self._seen[rid].id, rid, detail) for entity, rid, detail in self.calls]
        undone = [Undone(entity, sim_id, "deleted", detail.get("memo", f"{MARK}{rid}"), True)
                  for kind in ("Payment", "CreditMemo") for entity, sim_id, rid, detail in posted if entity == kind]
        notes = {detail["invoice"]: Undone("Invoice", sim_id, "note cleared", detail["note"], True)
                 for entity, sim_id, _, detail in posted if entity == "Invoice"}
        self.calls.clear(), self._seen.clear()
        return undone + list(notes.values())


_books: LiveBooks | StandInBooks | None = None


def _refreshing_token() -> Callable[[], str]:
    """An access token from the refresh token; the newest refresh token goes back to .env (they rotate)."""
    from dotenv import set_key
    from intuitlib.client import AuthClient

    cache: dict[str, str] = {}

    def token() -> str:
        if "access" not in cache:
            current = os.environ["QBO_REFRESH_TOKEN"]
            auth = AuthClient(os.environ["QBO_CLIENT_ID"], os.environ["QBO_CLIENT_SECRET"], REDIRECT_URI, "sandbox",
                              refresh_token=current, realm_id=os.environ["QBO_REALM_ID"])
            auth.refresh()
            if auth.refresh_token != current:
                os.environ["QBO_REFRESH_TOKEN"] = auth.refresh_token
                if ENV.exists():
                    set_key(str(ENV), "QBO_REFRESH_TOKEN", auth.refresh_token)
            cache["access"] = auth.access_token
        return cache["access"]

    return token


def books() -> LiveBooks | StandInBooks:
    global _books
    if _books is None:
        if not all(os.getenv(k) for k in KEYS):
            _books = StandInBooks()
        elif replay.demo_mode():
            _books = StandInBooks("DEMO_MODE is on, so nothing reaches QuickBooks")
        else:
            _books = LiveBooks(os.environ["QBO_REALM_ID"], _refreshing_token())
    return _books


def reset() -> None:
    global _books
    _books = None
