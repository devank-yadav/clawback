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

Stand-in (no QBO keys yet): answers with the same shapes and ids starting "sim-". It's never recorded as a
fixture, and every ledger post it backs says it was simulated.
"""

from __future__ import annotations

import itertools
import os
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

    def _find(self, entity: str, where: str) -> dict:
        found = self._call("GET", "/query", params={"query": f"select * from {entity} where {where}"})
        rows = found.get("QueryResponse", {}).get(entity, [])
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
        body = {"CustomerRef": invoice["CustomerRef"], "TotalAmt": 0,
                "Line": [{"Amount": _money(amount), "LinkedTxn": [{"TxnId": invoice["Id"], "TxnType": "Invoice"}]},
                         {"Amount": _money(amount), "LinkedTxn": [{"TxnId": credit_memo_id, "TxnType": "CreditMemo"}]}]}
        made = self._call("POST", "/payment", body=body, request_id=request_id)["Payment"]
        return Posted("Payment", made["Id"], Decimal(amount), False)

    def note_open_balance(self, request_id: str, invoice_no: str, note: str, disputed: Decimal) -> Posted:
        invoice = self._find("Invoice", f"DocNumber = '{invoice_no}'")
        body = {"Id": invoice["Id"], "SyncToken": invoice["SyncToken"], "sparse": True, "PrivateNote": note}
        made = self._call("POST", "/invoice", body=body, request_id=request_id)["Invoice"]
        return Posted("Invoice", made["Id"], Decimal(disputed), False)


class StandInBooks:
    """No QuickBooks keys yet: the same answers, clearly fake. Keeps what it 'posted' for tests and the log."""

    simulated = True

    def __init__(self):
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
        if all(os.getenv(k) for k in KEYS):
            _books = LiveBooks(os.environ["QBO_REALM_ID"], _refreshing_token())
        else:
            _books = StandInBooks()
    return _books


def reset() -> None:
    global _books
    _books = None
