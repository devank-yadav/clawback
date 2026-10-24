"""Seed the QuickBooks Online sandbox for the demo, every account in the one sandbox company. Idempotent: a second run
creates nothing new.

Run: python scripts/seed_quickbooks.py [account id ...]   (no ids: every account in data/accounts/)
Keys (.env): QBO_CLIENT_ID, QBO_CLIENT_SECRET, QBO_REALM_ID, QBO_REFRESH_TOKEN.

Creates (only if missing), from each data/accounts/<id>/account.yaml: its customer (qbo.customer); an item per invoice
line (qbo.lines; without them one line for the whole invoice); its invoice (qbo.invoice_no, dated invoice.period_end,
for invoice.expected); a payment of invoice.received applied to it (dated qbo.payment_date, else 20 days after the
period). Once for all accounts: account "Promotional Allowances" and service item "Promotional Allowance". Peak Bar's:
customer Northmart, items Peak Bar Original / Chocolate / Mint, INV-3102 for $48,200 and a $41,350 payment. Refresh
tokens rotate, so the newest one is written back to .env after every refresh.
API: https://sandbox-quickbooks.api.intuit.com/v3/company/{realm}/..., minorversion 75.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv, set_key
from intuitlib.client import AuthClient
from intuitlib.exceptions import AuthClientError

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
ACCOUNTS = ROOT / "data" / "accounts"
DEFAULT = "peak-bar"
TIMEOUT = 30
BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"
MINOR = "75"
# Only used by the authorization-code flow; a refresh doesn't redirect anywhere.
REDIRECT_URI = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"

PAYMENT_AFTER = timedelta(days=20)  # when qbo.payment_date isn't given: Peak Bar's is Apr 20 for a Mar 31 invoice
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


def quoted(name):
    """A name inside a QuickBooks query string: a single quote is escaped with a backslash."""
    return str(name).replace("'", "\\'")


def _day(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def load_accounts(ids=()):
    """Each account.yaml as the seed needs it, Peak Bar first. Exits naming an id that isn't there."""
    found = {p.parent.name: yaml.safe_load(p.read_text()) for p in sorted(ACCOUNTS.glob("*/account.yaml"))}
    if missing := [i for i in ids if i not in found]:
        sys.exit(f"No account {', '.join(missing)} in {ACCOUNTS}")
    chosen = [found[i] for i in ids] if ids else [found[k] for k in sorted(found, key=lambda k: (k != DEFAULT, k))]
    out = []
    for a in chosen:
        inv, qbo = a["invoice"], a["qbo"]
        lines = [(ln["item"], ln["qty"], float(ln["unit_price"])) for ln in qbo.get("lines") or []] or [
            (f"{a['brand']['name']} products", 1, float(inv["expected"]))]
        out.append({"id": a["id"], "customer": qbo["customer"], "invoice_no": qbo["invoice_no"],
                    "invoice_date": _day(inv["period_end"]).isoformat(),
                    "payment_date": _day(qbo.get("payment_date") or _day(inv["period_end"]) + PAYMENT_AFTER)
                    .isoformat(),
                    "invoiced": float(inv["expected"]), "paid": float(inv["received"]), "lines": lines})
    return out


def seed_account(qbo, a, sales):
    """One account's customer, items, invoice and payment."""
    print(f"{a['id']}:")
    name, invoice_no, invoiced, paid = a["customer"], a["invoice_no"], a["invoiced"], a["paid"]
    customer = ensure(qbo, "Customer", f"DisplayName = '{quoted(name)}'",
                      {"DisplayName": name, "CompanyName": f"{name} (fictional)"}, name)
    items = {}
    for item, _, _ in a["lines"]:
        items[item] = ensure(qbo, "Item", f"Name = '{quoted(item)}'",
                             {"Name": item, "Type": "NonInventory", "IncomeAccountRef": ref(sales)}, item)

    invoice_lines = [{"Amount": round(qty * price, 2), "DetailType": "SalesItemLineDetail",
                      "SalesItemLineDetail": {"ItemRef": ref(items[item]), "Qty": qty, "UnitPrice": price}}
                     for item, qty, price in a["lines"]]
    invoice = ensure(qbo, "Invoice", f"DocNumber = '{quoted(invoice_no)}'",
                     {"DocNumber": invoice_no, "TxnDate": a["invoice_date"], "CustomerRef": ref(customer),
                      "Line": invoice_lines}, invoice_no)
    if float(invoice["TotalAmt"]) != invoiced:
        sys.exit(f"{invoice_no} total is {invoice['TotalAmt']}, expected {invoiced:,.2f}. Fix it in the sandbox.")

    payments = qbo.query("Payment", f"CustomerRef = '{customer['Id']}'")
    applied = [p for p in payments if float(p["TotalAmt"]) == paid and any(
        lt.get("TxnId") == invoice["Id"] and lt.get("TxnType") == "Invoice"
        for line in p.get("Line", []) for lt in line.get("LinkedTxn", []))]
    if applied:
        print(f"Exists:  Payment ${paid:,.2f} on {invoice_no} (id {applied[0]['Id']})")
    else:
        pay = qbo.create("Payment", {"CustomerRef": ref(customer), "TotalAmt": paid, "TxnDate": a["payment_date"],
                                     "Line": [{"Amount": paid,
                                               "LinkedTxn": [{"TxnId": invoice["Id"], "TxnType": "Invoice"}]}]})
        print(f"Created: Payment ${paid:,.2f} on {invoice_no} (id {pay['Id']})")

    balance = float(qbo.get("Invoice", invoice["Id"])["Balance"])
    print(f"{invoice_no}: invoiced ${invoiced:,.2f}, paid ${paid:,.2f}, open balance ${balance:,.2f}")
    if round(balance, 2) != round(invoiced - paid, 2):
        sys.exit(f"Open balance should be ${invoiced - paid:,.2f}. Check the sandbox for other payments.")


def main(ids=None):
    load_dotenv(ENV)
    chosen = load_accounts(sys.argv[1:] if ids is None and __name__ == "__main__" else ids or ())
    client_id, secret, realm, refresh_token = require("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID",
                                                      "QBO_REFRESH_TOKEN")
    qbo = QBO(realm, refresh_tokens(client_id, secret, realm, refresh_token))

    income = qbo.query("Account", "AccountType = 'Income'")
    if not income:
        sys.exit("No Income account in the sandbox company to attach product items to.")
    sales = next((a for a in income if a["Name"] == "Sales of Product Income"), income[0])
    allowance_acct = ensure(qbo, "Account", f"Name = '{ALLOWANCE_ACCOUNT}'",
                            {"Name": ALLOWANCE_ACCOUNT, "AccountType": "Income",
                             "AccountSubType": "DiscountsRefundsGiven"}, ALLOWANCE_ACCOUNT)
    ensure(qbo, "Item", f"Name = '{ALLOWANCE_ITEM}'",
           {"Name": ALLOWANCE_ITEM, "Type": "Service", "IncomeAccountRef": ref(allowance_acct)}, ALLOWANCE_ITEM)
    for a in chosen:
        seed_account(qbo, a, sales)


if __name__ == "__main__":
    main()
