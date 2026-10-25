"""Record the AI answers an account's run is missing, live, once, under a hard cost cap. Never overwrites a recording.

    .venv/bin/python scripts/record_missing.py peak-bar-kehe peak-bar-walmart --cap 3.00

Run it from a checkout with .env. It reads .env for ANTHROPIC_API_KEY only, and turns everything else off for the
process, so a recording run can't text a phone, write to QuickBooks, save to the database or call Moss or Gemini.
Reader B is the second Claude read, the same as the startup history replays (api/story.py).
A call that already has a recording replays it (RECORD_MISSING); a missing one goes live and is saved. Every live
call's cost (config/pricing.yaml) is added up, and once the cap is reached no further call goes out: those charges
go to Ask instead, and the script says so. At the end each account's decisions are scored against its expected.csv.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OFF = ("GEMINI_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "OWNER_PHONE", "DEMO_USER2_PHONE",
       "QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN", "DATABASE_URL", "MOSS_API_KEY",
       "MOSS_PROJECT_KEY", "MOSS_PROJECT_ID", "NESSIE_API_KEY", "NESSIE_ACCOUNT_ID", "MAILGUN_API_KEY", "GMAIL_ADDRESS",
       "GMAIL_APP_PASSWORD", "GOOGLE_SERVICE_ACCOUNT_JSON", "DEMO_MODE")


class OverBudget(RuntimeError):
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("accounts", nargs="+")
    ap.add_argument("--cap", type=Decimal, default=Decimal("3.00"), help="USD for every live call together")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    for name in OFF:
        os.environ.pop(name, None)
    os.environ["RECORD_FIXTURES"] = "1"
    os.environ["RECORD_MISSING"] = "1"
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY isn't set in .env", file=sys.stderr)
        return 2

    from api import accounts, pipeline, trace
    from api.agents import claude

    pricing, _ = trace.load_pricing()
    spent = {"usd": Decimal("0"), "calls": 0, "unpriced": 0}
    real_parse = claude._parse

    def capped(client, req, output_format, timeout):
        if spent["usd"] >= args.cap:
            raise OverBudget(f"the ${args.cap} cap is reached")
        out = real_parse(client, req, output_format, timeout)
        cost = trace.call_cost(out.model or req["model"], out.usage, pricing)
        spent["calls"] += 1
        if cost is None:
            spent["unpriced"] += 1
        else:
            spent["usd"] += cost
        return out

    claude._parse = capped
    for aid in args.accounts:
        a = accounts.get(aid)
        before = spent["usd"]
        run = pipeline.start(a.invoice.month, account=a, background=False)
        expected = {r["charge_id"]: r for r in csv.DictReader((a.dir / "expected.csv").open())} \
            if (a.dir / "expected.csv").is_file() else {}
        right = sum(1 for cid, d in run.shown.items() if cid in expected
                    and d.decision == expected[cid]["decision"]
                    and Decimal(expected[cid]["disputed"]) == d.disputed
                    and Decimal(expected[cid]["accepted"]) == d.accepted)
        t = [e.data for e in run.events if e.type == "totals"][-1]
        print(f"{aid}: {right} of {len(expected) or len(run.shown)} decided as expected; disputed ${t.disputed:,.2f}, "
              f"fair ${t.accepted:,.2f}, waiting ${t.waiting:,.2f}, {len(run.questions)} question(s); "
              f"${spent['usd'] - before:.2f} spent")
        for cid, d in run.shown.items():
            want = expected.get(cid)
            mark = "ok" if want and d.decision == want["decision"] and Decimal(want["disputed"]) == d.disputed else "--"
            print(f"   {mark} {cid}: {d.decision} disputed {d.disputed} accepted {d.accepted}"
                  + (f" (expected {want['decision']} {want['disputed']} / {want['accepted']})" if want and mark == "--" else ""))
    print(f"total: ${spent['usd']:.2f} over {spent['calls']} live calls ({spent['unpriced']} unpriced); cap ${args.cap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
