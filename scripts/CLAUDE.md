# scripts/ (owner: Manasv, written by AI)

Small standalone scripts. Each one does ONE thing, reads keys from `.env` (python-dotenv), prints the result,
and exits with a clear message naming any missing key. Devank wires them into the app later.

- check_data.py: asserts every number in data/CLAUDE.md (sums, per-charge decisions, totals 4,120 / 2,730 / 6,850).
- check_eval.py: asserts data/eval/ has 30 cases with the 12 / 12 / 6 mix and expected amounts on every row.
- send_sms.py: sends one SMS through Twilio to OWNER_PHONE, the admin (arg: owner, text).
- nessie_deposit.py: creates (once) customer "Peak Bar Co." + a checking account, posts a $41,350 deposit
  described "Northmart remittance INV-3102", prints the account ID (goes in `NESSIE_ACCOUNT_ID`) and the deposit ID. Endpoints per Nessie's docs (verify).
- seed_quickbooks.py: in the QBO sandbox, creates customer Northmart, items Peak Bar Original / Chocolate / Mint,
  service item "Promotional Allowance", invoice INV-3102 for $48,200 and a $41,350 payment applied to it.
  Saves the newest refresh token after every refresh (tokens rotate). Idempotent: running twice creates nothing new.
- fetch_agent.py (stretch, only when Devank says go): Agentverse agent with the Agent Chat Protocol that calls
  only GET /summary (with CLAWBACK_READONLY_TOKEN). Follow Fetch.ai's hackpack exactly.

Rules: timeouts on every call; never print full keys; never commit .env; no money logic here.
