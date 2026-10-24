"""Post the $41,350 Northmart remittance as a Nessie deposit (the run's trigger).

Run: python scripts/nessie_deposit.py
Keys (.env): NESSIE_API_KEY; NESSIE_ACCOUNT_ID once you have it (printed on the first run).
Optional: NESSIE_BASE_URL (default http://api.nessieisreal.com).

Creates customer "Peak Bar Co." and a checking account only if they don't exist yet, then posts one deposit.
Endpoints and fields follow Nessie's official SDK (github.com/nessieisreal/nessie-android-sdk):
GET/POST /customers, GET/POST /customers/{id}/accounts, POST /accounts/{id}/deposits, all with ?key=.
"""

import os
import sys
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 30
AMOUNT = 41350.00
DESCRIPTION = "Northmart remittance INV-3102"
FIRST, LAST = "Peak Bar", "Co."
NICKNAME = "Peak Bar Co. operating"
ADDRESS = {"street_number": "100", "street_name": "Market St", "city": "Oakland", "state": "CA", "zip": "94607"}


def require(*names):
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")
    return [os.environ[n] for n in names]


def call(client, method, path, **kw):
    """One request with a timeout and one retry on network errors or 5xx."""
    for attempt in (1, 2):
        try:
            r = client.request(method, path, **kw)
        except httpx.HTTPError as e:
            if attempt == 2:
                sys.exit(f"Nessie {method} {path} failed: {e}")
            continue
        if r.status_code >= 500 and attempt == 1:
            continue
        if r.status_code >= 400:
            sys.exit(f"Nessie {method} {path} returned {r.status_code}: {r.text[:300]}")
        return r.json()


def created_id(resp):
    obj = resp.get("objectCreated") or {}
    if "_id" not in obj:
        sys.exit(f"Unexpected Nessie response: {resp}")
    return obj["_id"]


def find_or_create_account(client):
    customers = call(client, "GET", "/customers")
    cust = next((c for c in customers if c.get("first_name") == FIRST and c.get("last_name") == LAST), None)
    if cust:
        cust_id = cust["_id"]
        print(f"Customer exists: {cust_id}")
    else:
        cust_id = created_id(call(client, "POST", "/customers",
                                  json={"first_name": FIRST, "last_name": LAST, "address": ADDRESS}))
        print(f"Created customer Peak Bar Co.: {cust_id}")

    accounts = call(client, "GET", f"/customers/{cust_id}/accounts")
    acct = next((a for a in accounts if a.get("type") == "Checking" and a.get("nickname") == NICKNAME), None)
    if acct:
        print(f"Checking account exists: {acct['_id']}")
        return acct["_id"]
    acct_id = created_id(call(client, "POST", f"/customers/{cust_id}/accounts",
                              json={"type": "Checking", "nickname": NICKNAME, "rewards": 0, "balance": 0}))
    print(f"Created checking account: {acct_id}")
    return acct_id


def main():
    load_dotenv(ROOT / ".env")
    (key,) = require("NESSIE_API_KEY")
    base = os.getenv("NESSIE_BASE_URL") or "http://api.nessieisreal.com"

    with httpx.Client(base_url=base, params={"key": key}, timeout=TIMEOUT) as client:
        acct_id = os.getenv("NESSIE_ACCOUNT_ID") or find_or_create_account(client)
        deposit = {"medium": "balance", "transaction_date": date.today().isoformat(),
                   "amount": AMOUNT, "description": DESCRIPTION}
        dep_id = created_id(call(client, "POST", f"/accounts/{acct_id}/deposits", json=deposit))

    print(f"NESSIE_ACCOUNT_ID={acct_id}")
    print(f"Deposit posted: id={dep_id} amount=${AMOUNT:,.2f} description=\"{DESCRIPTION}\"")
    if not os.getenv("NESSIE_ACCOUNT_ID"):
        print("Add the NESSIE_ACCOUNT_ID line above to .env so later runs reuse this account.")


if __name__ == "__main__":
    main()
