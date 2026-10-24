"""Seed Postgres (Tiger Data) from data/: `make seed` or `python -m api.db.seed`. Safe to run again.

1. Applies every file in migrations/ in order. 001_init.sql's TimescaleDB part (store_sales as a hypertable on
   week_start, and the promo_units_weekly continuous aggregate) runs only where CREATE EXTENSION timescaledb works;
   on plain Postgres (a local Docker one) the seed warns and skips it.
2. Upserts, for every account (api/accounts.py), the rows api/documents.py and api/rows.py load from its files, so
   nothing here parses a data file: documents, the invoice month's remittance, each month's charges, prior
   payments, store sales and the promo plan, each row with its account and each data row with its file and row
   number (002_source_rows.sql, 003_accounts.sql). A row that is already there and equal is left alone, so a second
   run inserts and updates nothing.
3. Seeds the QuickBooks sandbox with scripts/seed_quickbooks.py when the four QBO_* keys are set (not in DEMO_MODE):
   every account's customer, items, invoice and payment.
4. Prints row counts and the cap query per account: the running total of promoted units against each promo's cap.

DATABASE_URL comes from .env and is never printed. Once seeded, the app reads these rows back from here
(api/rows.py through api/db/reads.py) and saves every run's events.
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

from api import accounts, documents, rows
from api.db import migration, migrations
from api.db.reads import cap_query
from api.integrations import replay

try:
    import psycopg
    from psycopg import sql
except ImportError:  # the row mapping below works without it; main() says what to install
    psycopg = None

ROOT = Path(__file__).resolve().parents[2]
QBO_KEYS = ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN")
CONNECT_TIMEOUT = 30

# Seeded tables in foreign-key order, with their primary keys. Columns are the keys of each row dict.
KEYS = {
    "documents": ("id",),
    "remittances": ("id",),
    "charges": ("account_id", "id"),
    "prior_payments": ("account_id", "ref"),
    "store_sales": ("account_id", "week_start", "product"),
    "promo_plan": ("account_id", "promo_id"),
}

# ---------------------------------------------------------------- rows (no database needed)

def _utc(value: datetime | None) -> datetime | None:
    """Markdown documents give a bare date; store it as midnight UTC so every session reads the same instant."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def remittance_id(account: accounts.Account) -> str:
    """The id api/pipeline.py gives the invoice month's remittance: REM-INV-3102."""
    return f"REM-{account.invoice.id}"


def document_rows(account: accounts.Account) -> list[dict[str, Any]]:
    out = []
    for doc_id in account.docs:
        doc, text = documents.load(doc_id)
        out.append({"id": doc.id, "kind": doc.kind, "path": doc.path, "sender": doc.sender,
                    "approved_sender": doc.approved_sender, "signed_by_both": doc.signed_by_both,
                    "received_at": _utc(doc.received_at), "text": text, "sha256": doc.sha256, "account_id": account.id})
    return out


def remittance_rows(account: accounts.Account) -> list[dict[str, Any]]:
    # received_at and nessie_tx_id aren't seeded: the run sets them when the Nessie deposit arrives.
    inv = account.invoice
    return [{"id": remittance_id(account), "counterparty": account.distributor.name, "invoice_id": inv.id,
             "expected": inv.expected, "received": inv.received, "account_id": account.id}]


def _with_source(items: list[Any], source_file: str, account: accounts.Account) -> list[dict[str, Any]]:
    """Each row with its account and where it came from in the account's folder: its file and its row number there
    (1 is the row after the header), so the app reads the tables back in the files' order (api/db/reads.py)."""
    return [{**item.model_dump(), "account_id": account.id, "source_file": source_file, "source_row": n}
            for n, item in enumerate(items, 1)]


def charge_rows(account: accounts.Account) -> list[dict[str, Any]]:
    # Only the invoice month has a remittance on file; a later month's charges (Peak Bar's April) have NULL.
    out = []
    for month in account.months:
        got = rows.charges_from_files(month, account=account)
        if month == account.invoice.month:
            got = [c.model_copy(update={"remittance_id": remittance_id(account)}) for c in got]
        # line_ref is left out of a dump when unset; every row needs the same columns
        seeded = _with_source(got, rows.charge_file(month), account)
        out += [{**row, "line_ref": c.line_ref} for row, c in zip(seeded, got)]
    return out


def seed_rows() -> dict[str, list[dict[str, Any]]]:
    """Every seeded table's rows for every account, keyed like KEYS and in its order."""
    out: dict[str, list[dict[str, Any]]] = {t: [] for t in KEYS}
    for a in accounts.every():
        out["documents"] += document_rows(a)
        out["remittances"] += remittance_rows(a)
        out["charges"] += charge_rows(a)
        out["prior_payments"] += _with_source(rows.prior_payments_from_files(account=a), rows.PRIOR_FILE, a)
        out["store_sales"] += _with_source(rows.sales_from_files(account=a), rows.SALES_FILE, a)
        out["promo_plan"] += _with_source(rows.promo_plan_from_files(account=a), rows.PLAN_FILE, a)
    return out


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
    """Runs every migration in order; their TimescaleDB parts only when the extension is there (result.timescale)."""
    parts = [migration(name) for name in migrations()]
    with conn.transaction():
        for plain, _ in parts:
            conn.execute(plain)
    result.timescale, result.timescale_skipped = _timescale(conn)
    if result.timescale:
        with conn.transaction():
            for _, timescale in parts:
                if timescale.strip():
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


def _print_cap(account: accounts.Account, promo, weeks: list[tuple], weekly: str) -> None:
    print(f"\nThe cap query ({account.id}, {promo.promo_id}: {' + '.join(promo.products)}, {promo.starts} to "
          f"{promo.ends}, cap {promo.cap:,} units), over {weekly}:")
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
        print(f"Schema: api/db/migrations/ applied ({', '.join(migrations())}).")
        if seeded.timescale:
            print("TimescaleDB: store_sales is a hypertable on week_start; promo_units_weekly is its continuous "
                  "aggregate.")
        else:
            print(f"Warning: TimescaleDB isn't available here ({seeded.timescale_skipped}). store_sales stays a plain "
                  "table and the promo_units_weekly continuous aggregate is skipped; the cap query reads store_sales.")
        qbo_error = seed_quickbooks()
        _report(seeded, counts(conn))
        for problem in accounts.problems():
            print(f"Warning: account left out: {problem}")
        for a in accounts.every():
            for promo in rows.promo_plan_from_files(account=a):
                _print_cap(a, promo, cap_query(conn, a.id, promo.promo_id, seeded.weekly), seeded.weekly)
    if qbo_error:
        sys.exit(f"QuickBooks seed failed: {qbo_error}")


if __name__ == "__main__":
    main()
