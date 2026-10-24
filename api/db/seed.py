"""Seed Postgres (Tiger Data) from data/: `make seed` or `python -m api.db.seed`. Safe to run again.

1. Applies migrations/001_init.sql. Its TimescaleDB part (store_sales as a hypertable on week_start, and the
   promo_units_weekly continuous aggregate) runs only where CREATE EXTENSION timescaledb works; on plain Postgres
   (a local Docker one) the seed warns and skips it.
2. Upserts the rows api/documents.py and api/rows.py load, so nothing here parses a data file: documents, the
   March remittance, the March and April charges, prior payments, store sales and the promo plan. A row that is
   already there and equal is left alone, so a second run inserts and updates nothing.
3. Seeds the QuickBooks sandbox with scripts/seed_quickbooks.py when the four QBO_* keys are set (not in DEMO_MODE).
4. Prints row counts and the cap query: the running total of promoted units against the promo's cap.

DATABASE_URL comes from .env and is never printed. The pipeline still reads data/ directly; reading from the
database is later work.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from api import documents, rows
from api.db import migration
from api.integrations import replay
from api.pipeline import COUNTERPARTY, EXPECTED, INVOICE_ID, RECEIVED

try:
    import psycopg
    from psycopg import sql
except ImportError:  # the row mapping below works without it; main() says what to install
    psycopg = None

ROOT = Path(__file__).resolve().parents[2]
REMITTANCE_ID = f"REM-{INVOICE_ID}"  # the id api/pipeline.py gives the March run's remittance
QBO_KEYS = ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN")
CONNECT_TIMEOUT = 30

# Seeded tables in foreign-key order, with their primary keys. Columns are the keys of each row dict.
KEYS = {
    "documents": ("id",),
    "remittances": ("id",),
    "charges": ("id",),
    "prior_payments": ("ref",),
    "store_sales": ("week_start", "product"),
    "promo_plan": ("promo_id",),
}

# Running total of promoted units per reporting week inside the promo's dates, next to its cap. {weekly} is the
# continuous aggregate on TimescaleDB, store_sales on plain Postgres; both have these columns. The engine's cap
# check (api/engine/allowed.py) is what decides charges; this is the same count, seen from the database.
CAP_QUERY = """
SELECT w.week_start, w.week_end, sum(w.promo_units)::int AS promo_units,
       (sum(sum(w.promo_units)) OVER (ORDER BY w.week_start))::int AS running_units, p.cap
FROM {weekly} AS w
JOIN promo_plan AS p ON w.product = ANY (p.products)
WHERE p.promo_id = %s AND w.week_start >= p.starts AND w.week_end <= p.ends
GROUP BY w.week_start, w.week_end, p.cap
ORDER BY w.week_start
"""


# ---------------------------------------------------------------- rows (no database needed)

def _utc(value: datetime | None) -> datetime | None:
    """Markdown documents give a bare date; store it as midnight UTC so every session reads the same instant."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def document_rows() -> list[dict[str, Any]]:
    out = []
    for doc_id in documents.PATHS:
        doc, text = documents.load(doc_id)
        out.append({"id": doc.id, "kind": doc.kind, "path": doc.path, "sender": doc.sender,
                    "approved_sender": doc.approved_sender, "signed_by_both": doc.signed_by_both,
                    "received_at": _utc(doc.received_at), "text": text, "sha256": doc.sha256})
    return out


def remittance_rows() -> list[dict[str, Any]]:
    # received_at and nessie_tx_id aren't seeded: the run sets them when the Nessie deposit arrives.
    return [{"id": REMITTANCE_ID, "counterparty": COUNTERPARTY, "invoice_id": INVOICE_ID,
             "expected": EXPECTED, "received": RECEIVED}]


def charge_rows() -> list[dict[str, Any]]:
    # April's charges have no remittance on file yet (no April invoice or payment in the data), so theirs is NULL.
    march = [c.model_copy(update={"remittance_id": REMITTANCE_ID}) for c in rows.charges("march")]
    return [c.model_dump() for c in march + rows.charges("april")]


def seed_rows() -> dict[str, list[dict[str, Any]]]:
    """Every seeded table's rows, keyed like KEYS and in its order."""
    return {
        "documents": document_rows(),
        "remittances": remittance_rows(),
        "charges": charge_rows(),
        "prior_payments": [p.model_dump() for p in rows.prior_payments()],
        "store_sales": [s.model_dump() for s in rows.sales()],
        "promo_plan": [p.model_dump() for p in rows.promo_plan()],
    }


def schema_tables() -> list[str]:
    plain, _ = migration()
    return re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", plain)


# ---------------------------------------------------------------- database

@dataclass
class Seeded:
    timescale: str | None = None  # the extension's version; None on plain Postgres
    timescale_skipped: str | None = None  # why CREATE EXTENSION timescaledb failed
    inserted: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)

    @property
    def weekly(self) -> str:
        """Where the cap query reads weekly promoted units."""
        return "promo_units_weekly" if self.timescale else "store_sales"


def _timescale(conn) -> tuple[str | None, str | None]:
    """Creates the extension if it can: (its version, None). A plain Postgres can't: (None, why)."""
    try:
        with conn.transaction():
            conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    except psycopg.Error as e:
        return None, (str(e).strip().splitlines() or [type(e).__name__])[0]
    return conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'").fetchone()[0], None


def apply_schema(conn, result: Seeded) -> None:
    """Runs 001_init.sql; its TimescaleDB part only when the extension is there (result.timescale)."""
    plain, timescale = migration()
    with conn.transaction():
        conn.execute(plain)
    result.timescale, result.timescale_skipped = _timescale(conn)
    if result.timescale:
        with conn.transaction():
            conn.execute(timescale)


def _upsert(conn, table: str, key: tuple[str, ...], items: list[dict[str, Any]]) -> tuple[int, int]:
    """Inserts new rows and updates changed ones; equal rows aren't touched. Returns (inserted, updated)."""
    if not items:
        return 0, 0
    cols = list(items[0])
    rest = [c for c in cols if c not in key]
    t, ident = sql.Identifier(table), sql.Identifier
    query = sql.SQL(
        "INSERT INTO {t} ({cols}) VALUES ({vals}) ON CONFLICT ({key}) DO UPDATE SET {sets} "
        "WHERE ROW({current}) IS DISTINCT FROM ROW({new}) RETURNING {key}"
    ).format(
        t=t,
        cols=sql.SQL(", ").join(map(ident, cols)),
        vals=sql.SQL(", ").join(map(sql.Placeholder, cols)),
        key=sql.SQL(", ").join(map(ident, key)),
        sets=sql.SQL(", ").join(sql.SQL("{c} = EXCLUDED.{c}").format(c=ident(c)) for c in rest),
        current=sql.SQL(", ").join(sql.SQL("{t}.{c}").format(t=t, c=ident(c)) for c in rest),
        new=sql.SQL(", ").join(sql.SQL("EXCLUDED.{c}").format(c=ident(c)) for c in rest),
    )
    with conn.cursor() as cur:
        before = set(cur.execute(sql.SQL("SELECT {key} FROM {t}").format(
            key=sql.SQL(", ").join(map(ident, key)), t=t)).fetchall())
        cur.executemany(query, items, returning=True)
        changed = []
        while True:
            changed += cur.fetchall()  # nothing for a row that was already equal
            if not cur.nextset():
                break
    inserted = sum(1 for k in changed if k not in before)
    return inserted, len(changed) - inserted


def seed(conn) -> Seeded:
    """Schema, then every seeded table in one transaction. `conn` must be in autocommit mode: refreshing the
    continuous aggregate can't run inside a transaction block."""
    result = Seeded()
    apply_schema(conn, result)
    with conn.transaction():
        for table, items in seed_rows().items():
            result.inserted[table], result.updated[table] = _upsert(conn, table, KEYS[table], items)
    if result.timescale:
        conn.execute("CALL refresh_continuous_aggregate('promo_units_weekly', NULL, NULL)")
    return result


def counts(conn) -> dict[str, int]:
    return {t: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone()[0]
            for t in schema_tables()}


def cap_query(conn, promo_id: str, weekly: str) -> list[tuple]:
    """(week_start, week_end, promo_units, running_units, cap) per week, in date order."""
    query = sql.SQL(CAP_QUERY).format(weekly=sql.Identifier(weekly))
    return conn.execute(query, (promo_id,)).fetchall()


# ---------------------------------------------------------------- QuickBooks and the command

def seed_quickbooks() -> str | None:
    """scripts/seed_quickbooks.py's main(), when the keys are set and DEMO_MODE is off. Returns why it failed."""
    missing = [k for k in QBO_KEYS if not os.getenv(k)]
    if missing:
        print(f"QuickBooks: skipped ({', '.join(missing)} not set in .env).")
        return None
    if replay.demo_mode():
        print("QuickBooks: skipped (DEMO_MODE is on; run with DEMO_MODE=false to seed the sandbox).")
        return None
    print("QuickBooks sandbox (scripts/seed_quickbooks.py):")
    try:
        _quickbooks_script().main()
    except SystemExit as e:  # the script exits with its message on any failure
        if e.code not in (None, 0):
            return str(e.code)
    return None


def _quickbooks_script():
    """scripts/ isn't a package, so load the file itself."""
    spec = importlib.util.spec_from_file_location("seed_quickbooks", ROOT / "scripts" / "seed_quickbooks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _connect(url: str):
    for attempt in (1, 2):
        try:
            return psycopg.connect(url, autocommit=True, connect_timeout=CONNECT_TIMEOUT)
        except psycopg.OperationalError as e:
            if attempt == 2:
                reason = str(e).replace(url, "DATABASE_URL").strip()
                sys.exit(f"Could not connect to the database in DATABASE_URL: {reason}")
            time.sleep(2)


def _report(seeded: Seeded, table_counts: dict[str, int]) -> None:
    where = f"TimescaleDB {seeded.timescale}" if seeded.timescale else "plain Postgres, no TimescaleDB"
    print(f"\nRows ({where}):")
    print(f"  {'table':<16}{'rows':>6}{'inserted':>10}{'updated':>9}")
    for table, n in table_counts.items():
        if table in KEYS:
            print(f"  {table:<16}{n:>6}{seeded.inserted[table]:>10}{seeded.updated[table]:>9}")
        else:
            print(f"  {table:<16}{n:>6}   (written by runs)")


def _print_cap(promo, weeks: list[tuple], weekly: str) -> None:
    print(f"\nThe cap query ({promo.promo_id}: {' + '.join(promo.products)}, {promo.starts} to {promo.ends}, "
          f"cap {promo.cap:,} units), over {weekly}:")
    print(f"  {'week':<26}{'promoted':>9}{'running total':>15}")
    for start, end, units, running, _cap in weeks:
        print(f"  {f'{start} to {end}':<26}{units:>9,}{running:>15,}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    if psycopg is None:
        sys.exit("psycopg isn't installed: pip install -r api/requirements.txt")
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set in .env (Tiger Data's service URL, docs/design.md Setup runbook row 4).")
    with _connect(url) as conn:
        seeded = seed(conn)
        print("Schema: api/db/migrations/001_init.sql applied.")
        if seeded.timescale:
            print("TimescaleDB: store_sales is a hypertable on week_start; promo_units_weekly is its continuous "
                  "aggregate.")
        else:
            print(f"Warning: TimescaleDB isn't available here ({seeded.timescale_skipped}). store_sales stays a plain "
                  "table and the promo_units_weekly continuous aggregate is skipped; the cap query reads store_sales.")
        qbo_error = seed_quickbooks()
        _report(seeded, counts(conn))
        for promo in rows.promo_plan():
            _print_cap(promo, cap_query(conn, promo.promo_id, seeded.weekly), seeded.weekly)
    if qbo_error:
        sys.exit(f"QuickBooks seed failed: {qbo_error}")


if __name__ == "__main__":
    main()
