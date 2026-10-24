"""Seed the QuickBooks Online sandbox for the demo. Idempotent: a second run creates nothing new.

Run: python scripts/seed_quickbooks.py
Keys (.env): QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REALM_ID, QBO_REFRESH_TOKEN.

Creates (only if missing): customer Northmart; items Peak Bar Original / Chocolate / Mint; account
"Promotional Allowances" and service item "Promotional Allowance"; invoice INV-3102 for $48,200; a $41,350
payment applied to it. Refresh tokens rotate, so the newest one is written back to .env after every refresh.
API: https://sandbox-quickbooks.api.intuit.com/v3/company/{realm}/..., minorversion 75.
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key
from intuitlib.client import AuthClient
from intuitlib.exceptions import AuthClientError

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
TIMEOUT = 30
BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"
MINOR = "75"
# Only used by the authorization-code flow; a refresh doesn't redirect anywhere.
REDIRECT_URI = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"

CUSTOMER = "Northmart"
INVOICE_NO = "INV-3102"
INVOICE_DATE = "2026-03-31"
PAYMENT_DATE = "2026-04-20"
INVOICED = 48200.00
PAID = 41350.00
# March shipment lines on INV-3102; they sum to $48,200.00
LINES = [
    ("Peak Bar Original", 9000, 2.40),   # 21,600.00
    ("Peak Bar Chocolate", 8000, 2.40),  # 19,200.00
    ("Peak Bar Mint", 3700, 2.00),       #  7,400.00
]
ALLOWANCE_ACCOUNT = "Promotional Allowances"
ALLOWANCE_ITEM = "Promotional Allowance"


def require(*names):
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    return [os.environ[n] for n in names]


def refresh_tokens(client_id, secret, realm, refresh_token):
    auth = AuthClient(client_id, secret, REDIRECT_URI, "sandbox", refresh_token=refresh_token, realm_id=realm)
    try:
        auth.refresh()
    except AuthClientError as e:
        hint = " (refresh token expired or already used: get a new one from the OAuth Playground)" \
            if "invalid_grant" in str(e.content) else ""
        sys.exit(f"QuickBooks token refresh failed: {e.status_code}{hint}")
    if auth.refresh_token != refresh_token:
        set_key(ENV, "QBO_REFRESH_TOKEN", auth.refresh_token)
        print("Saved the new QBO_REFRESH_TOKEN to .env")
    return auth.access_token


class QBO:
    def __init__(self, realm, access_token):
        self.http = httpx.Client(base_url=f"{BASE}/{realm}", timeout=TIMEOUT, params={"minorversion": MINOR},
                                 headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})

    def _call(self, method, path, **kw):
        """One request with a timeout and one retry on network errors or 5xx."""
        for attempt in (1, 2):
            try:
                r = self.http.request(method, path, **kw)
            except httpx.HTTPError as e:
                if attempt == 2:
                    sys.exit(f"QuickBooks {method} {path} failed: {e}")
                continue
            if r.status_code >= 500 and attempt == 1:
                continue
            if r.status_code >= 400:
                sys.exit(f"QuickBooks {method} {path} returned {r.status_code}: {r.text[:500]}")
            return r.json()

    def query(self, entity, where):
        resp = self._call("GET", "/query", params={"query": f"select * from {entity} where {where}"})
        return resp.get("QueryResponse", {}).get(entity, [])

    def create(self, entity, body):
        return self._call("POST", f"/{entity.lower()}", json=body)[entity]

    def get(self, entity, entity_id):
        return self._call("GET", f"/{entity.lower()}/{entity_id}")[entity]


def ensure(qbo, entity, where, body, label):
    found = qbo.query(entity, where)
    if found:
        print(f"Exists:  {entity} {label} (id {found[0]['Id']})")
        return found[0]
    made = qbo.create(entity, body)
    print(f"Created: {entity} {label} (id {made['Id']})")
    return made


def ref(obj):
    return {"value": obj["Id"]}


def main():
    load_dotenv(ENV)
    client_id, secret, realm, refresh_token = require("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID",
                                                      "QBO_REFRESH_TOKEN")
    qbo = QBO(realm, refresh_tokens(client_id, secret, realm, refresh_token))

    customer = ensure(qbo, "Customer", f"DisplayName = '{CUSTOMER}'",
                      {"DisplayName": CUSTOMER, "CompanyName": "Northmart (fictional)"}, CUSTOMER)

    income = qbo.query("Account", "AccountType = 'Income'")
    if not income:
        sys.exit("No Income account in the sandbox company to attach product items to.")
    sales = next((a for a in income if a["Name"] == "Sales of Product Income"), income[0])
    items = {}
    for name, _, _ in LINES:
        items[name] = ensure(qbo, "Item", f"Name = '{name}'",
                             {"Name": name, "Type": "NonInventory", "IncomeAccountRef": ref(sales)}, name)

    allowance_acct = ensure(qbo, "Account", f"Name = '{ALLOWANCE_ACCOUNT}'",
                            {"Name": ALLOWANCE_ACCOUNT, "AccountType": "Income",
                             "AccountSubType": "DiscountsRefundsGiven"}, ALLOWANCE_ACCOUNT)
    ensure(qbo, "Item", f"Name = '{ALLOWANCE_ITEM}'",
           {"Name": ALLOWANCE_ITEM, "Type": "Service", "IncomeAccountRef": ref(allowance_acct)}, ALLOWANCE_ITEM)

    invoice_lines = [{"Amount": round(qty * price, 2), "DetailType": "SalesItemLineDetail",
                      "SalesItemLineDetail": {"ItemRef": ref(items[name]), "Qty": qty, "UnitPrice": price}}
                     for name, qty, price in LINES]
    invoice = ensure(qbo, "Invoice", f"DocNumber = '{INVOICE_NO}'",
                     {"DocNumber": INVOICE_NO, "TxnDate": INVOICE_DATE, "CustomerRef": ref(customer),
                      "Line": invoice_lines}, INVOICE_NO)
    if float(invoice["TotalAmt"]) != INVOICED:
        sys.exit(f"{INVOICE_NO} total is {invoice['TotalAmt']}, expected {INVOICED:,.2f}. Fix it in the sandbox.")

    payments = qbo.query("Payment", f"CustomerRef = '{customer['Id']}'")
    applied = [p for p in payments if float(p["TotalAmt"]) == PAID and any(
        lt.get("TxnId") == invoice["Id"] and lt.get("TxnType") == "Invoice"
        for line in p.get("Line", []) for lt in line.get("LinkedTxn", []))]
    if applied:
        print(f"Exists:  Payment ${PAID:,.2f} on {INVOICE_NO} (id {applied[0]['Id']})")
    else:
        pay = qbo.create("Payment", {"CustomerRef": ref(customer), "TotalAmt": PAID, "TxnDate": PAYMENT_DATE,
                                     "Line": [{"Amount": PAID,
                                               "LinkedTxn": [{"TxnId": invoice["Id"], "TxnType": "Invoice"}]}]})
        print(f"Created: Payment ${PAID:,.2f} on {INVOICE_NO} (id {pay['Id']})")

    balance = float(qbo.get("Invoice", invoice["Id"])["Balance"])
    print(f"{INVOICE_NO}: invoiced ${INVOICED:,.2f}, paid ${PAID:,.2f}, open balance ${balance:,.2f}")
    if balance != INVOICED - PAID:
        sys.exit(f"Open balance should be ${INVOICED - PAID:,.2f}. Check the sandbox for other payments.")


if __name__ == "__main__":
    main()
