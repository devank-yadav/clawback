"""Is the app on Postgres? `make db-check` or `python -m api.db.check`, with DATABASE_URL from .env.

Shows each data loader (api/rows.py) reading the database and getting back exactly what data/ holds, the newest runs
saved in the events table, and the cap query. Read-only; the URL is never printed. Exits 1 if a loader falls back
to the files or the database disagrees with them.
"""

from __future__ import annotations

import sys
from datetime import timezone
from pathlib import Path

from dotenv import load_dotenv

from api import accounts, rows
from api.db import conn, reads

ROOT = Path(__file__).resolve().parents[2]


def _loaders(a: accounts.Account) -> list[tuple[str, str, tuple, str, list]]:
    """(label, table, args, data file, rows from the file) for every loader the pipeline calls, for one account."""
    return [
        *((f"charges {m}", "charges", (rows.charge_file(m),), rows.charge_file(m),
           rows.charges_from_files(m, account=a)) for m in a.months),
        ("store sales", "store_sales", (), rows.SALES_FILE, rows.sales_from_files(account=a)),
        ("prior payments", "prior_payments", (), rows.PRIOR_FILE, rows.prior_payments_from_files(account=a)),
        ("promo plan", "promo_plan", (), rows.PLAN_FILE, rows.promo_plan_from_files(account=a)),
    ]


def main() -> None:
    load_dotenv(ROOT / ".env")
    if not conn.enabled():
        sys.exit("No database: DATABASE_URL isn't set in .env, or DEMO_MODE is on (the app then reads data/).")
    good = True
    for a in accounts.every():
        print(f"{a.id}: rows the app reads (api/rows.py):")
        for label, table, args, path, files in _loaders(a):
            where = f"data/accounts/{a.id}/{path}"
            got = reads.load(table, a.id, *args)
            if got is None and not files:
                print(f"  {label:<16} none in {where} or the database")
                continue
            if got is None:
                print(f"  {label:<16} from {where}: the database didn't give them (warning above)")
            elif repr(got) != repr(files):
                print(f"  {label:<16} {len(got):>3} rows from Postgres, NOT the same as {where} (run make seed)")
            else:
                print(f"  {label:<16} {len(got):>3} row{'s' * (len(got) != 1)} from Postgres, exactly as in {where}")
            good = good and repr(got) == repr(files)
    try:
        saved = conn.shared.run(lambda db: db.execute(
            "SELECT run_id, count(*), min(at), max(at) FROM events GROUP BY run_id ORDER BY min(at) DESC LIMIT 5"
        ).fetchall())
        source = conn.shared.run(reads.weekly)
        weeks = conn.shared.run(lambda db: reads.cap_query(db, accounts.DEFAULT, "SPRING-26", source))
    except Exception as e:  # noqa: BLE001 - say what failed, without the URL
        sys.exit(f"The database didn't answer: {conn.scrub(e)}")
    print("\nNewest runs in the events table (GET /runs/latest falls back to the first):")
    for run_id, n, first, last in saved:
        first, last = first.astimezone(timezone.utc), last.astimezone(timezone.utc)
        print(f"  {run_id:<22}{n:>5} events  {first:%Y-%m-%d %H:%M:%S} to {last:%H:%M:%S} UTC")
    if not saved:
        print("  none yet: start a run (POST /payments/northmart) with the API on this database")
    print(f"\nPeak Bar's cap query over {source} (GET /db/cap):")
    for start, end, units, running, cap in weeks:
        print(f"  {f'{start} to {end}':<26}{units:>7,} promoted{running:>8,} of {cap:,}")
    sys.exit(0 if good else 1)


if __name__ == "__main__":
    main()
