"""F1 seed (api/db/seed.py): the rows it writes match the data files, and seeding twice changes nothing.

The row-mapping tests need no database. The seed-twice tests run only when TEST_DATABASE_URL points at a throwaway
Postgres (ideally with TimescaleDB); each makes its own schema and drops it after. .env isn't read in tests, so set
it in the shell:
    TEST_DATABASE_URL=postgresql://postgres:pw@localhost:5432/clawback_test python -m pytest -q api/tests/test_db_seed.py
"""

import csv
import hashlib
import os
import re
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from api import documents, rows
from api.db import migration, seed

DATA = rows.DATA
DESIGN = DATA.parent / "docs" / "design.md"
SEEDED = {"documents": 8, "remittances": 1, "charges": 8, "prior_payments": 2, "store_sales": 14, "promo_plan": 1}
RUNNING = [1200, 2180, 5000, 6540]  # weeks 1 to 4 of March, Original + Chocolate (data/CLAUDE.md)


def _csv_rows(rel):
    with open(DATA / rel, newline="") as f:
        return list(csv.DictReader(f))


def _columns(table):
    plain, _ = migration()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", plain, re.S).group(1)
    names = [line.split()[0] for line in body.splitlines() if line.strip()]
    return {n for n in names if n not in ("PRIMARY", "CHECK", "UNIQUE", "--")}


# --- Rows, no database --------------------------------------------------------------------------------------

def test_row_counts_match_the_data_files():
    got = {t: len(r) for t, r in seed.seed_rows().items()}
    assert got == SEEDED
    files = [p for d in ("deals", "emails", "notices") for p in (DATA / d).iterdir() if p.suffix in (".md", ".eml")]
    assert got["documents"] == len(files)
    assert got["charges"] == len(_csv_rows("charges/northmart-march.csv")) + len(_csv_rows("charges/northmart-april.csv"))
    assert got["prior_payments"] == len(_csv_rows("payments/prior.csv"))
    assert got["store_sales"] == len(_csv_rows("sales/store-sales.csv"))
    assert got["promo_plan"] == len(_csv_rows("plan/promo-plan.csv"))


def test_store_sales_rows_keep_week_end():
    sales = seed.seed_rows()["store_sales"]
    assert all(isinstance(r["week_end"], date) and r["week_end"] >= r["week_start"] for r in sales)
    week4 = {r["product"]: r["week_end"] for r in sales if r["week_start"] == date(2026, 3, 22)}
    assert set(week4.values()) == {date(2026, 3, 31)}  # week 4 runs Mar 22 to 31
    assert len({(r["week_start"], r["product"]) for r in sales}) == len(sales)  # the primary key holds


def test_documents_carry_their_text_and_sha256():
    docs = {d["id"]: d for d in seed.document_rows()}
    assert set(docs) == set(documents.PATHS)
    for doc_id, rel in documents.PATHS.items():
        text = (DATA / rel).read_text()
        assert docs[doc_id]["text"] == text
        assert docs[doc_id]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert docs[doc_id]["received_at"] is None or docs[doc_id]["received_at"].tzinfo is not None
    assert docs["broker-2026-03-28"]["approved_sender"] and not docs["northmart-2026-03-30"]["approved_sender"]
    assert docs["spring-promo"]["signed_by_both"] and docs["amendment-1"]["signed_by_both"]


def test_remittance_and_charges_are_the_scenario():
    (rem,) = seed.remittance_rows()
    assert (rem["id"], rem["invoice_id"], rem["expected"], rem["received"]) == \
           ("REM-INV-3102", "INV-3102", Decimal("48200.00"), Decimal("41350.00"))
    charges = {c["id"]: c for c in seed.charge_rows()}
    march = [c for c in charges.values() if c["id"].startswith("C")]
    assert all(c["remittance_id"] == rem["id"] for c in march)
    assert sum(c["amount"] for c in march) == Decimal("6850.00")
    assert charges["A1"]["remittance_id"] is None and charges["A2"]["remittance_id"] is None
    assert (charges["C6"]["notice_date"], charges["A1"]["notice_date"], charges["A2"]["notice_date"]) == \
           (date(2026, 3, 11), date(2026, 4, 12), date(2026, 4, 25))


def test_rows_fit_the_schema():
    for table, items in seed.seed_rows().items():
        cols = _columns(table)
        assert set(seed.KEYS[table]) <= set(items[0]), table
        for r in items:
            assert set(r) <= cols, f"{table}: {set(r) - cols} not in 001_init.sql"


def test_schema_has_every_table_in_the_design():
    text = DESIGN.read_text()
    section = text[text.index("**Tables:**"):text.index("**Data files")]
    design_tables = re.findall(r"^\| `(\w+)` \|", section, re.M)
    assert len(design_tables) == 16
    assert set(design_tables) <= set(seed.schema_tables())


def test_timescale_part_makes_the_hypertable_and_the_aggregate():
    plain, timescale = migration()
    assert not re.search(r"create_hypertable|CREATE EXTENSION|timescaledb\.|time_bucket", plain)  # plain Postgres runs it
    assert "create_hypertable('store_sales', by_range('week_start')" in timescale
    view = timescale[timescale.index("CREATE MATERIALIZED VIEW"):]
    assert "timescaledb.continuous" in view and "WITH NO DATA" in view
    assert " OVER " not in view.upper()  # continuous aggregates can't hold window functions


def test_main_needs_database_url():
    with pytest.raises(SystemExit, match="DATABASE_URL is not set"):
        seed.main()


def test_quickbooks_runs_only_with_all_four_keys_and_outside_demo_mode(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(seed, "_quickbooks_script", lambda: SimpleNamespace(main=lambda: calls.append(1)))
    for k in seed.QBO_KEYS[:3]:
        monkeypatch.setenv(k, "x")
    assert seed.seed_quickbooks() is None and not calls
    assert "skipped (QBO_REFRESH_TOKEN not set" in capsys.readouterr().out
    monkeypatch.setenv("QBO_REFRESH_TOKEN", "x")
    monkeypatch.setenv("DEMO_MODE", "true")
    assert seed.seed_quickbooks() is None and not calls
    assert "DEMO_MODE is on" in capsys.readouterr().out
    monkeypatch.setenv("DEMO_MODE", "false")
    assert seed.seed_quickbooks() is None and calls == [1]


def test_quickbooks_failure_is_reported(monkeypatch):
    def fail():
        raise SystemExit("QuickBooks token refresh failed: 400")

    monkeypatch.setattr(seed, "_quickbooks_script", lambda: SimpleNamespace(main=fail))
    for k in seed.QBO_KEYS:
        monkeypatch.setenv(k, "x")
    assert seed.seed_quickbooks() == "QuickBooks token refresh failed: 400"


# --- Seeding a real database (TEST_DATABASE_URL) ------------------------------------------------------------

@pytest.fixture
def schema():
    psycopg = pytest.importorskip("psycopg")
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to a throwaway Postgres to run the seed-twice tests")
    name = f"seed_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {name}")
        try:
            yield url, f"-c search_path={name},public", name
        finally:
            admin.execute(f"DROP SCHEMA {name} CASCADE")


@pytest.fixture
def db(schema):
    import psycopg

    url, options, _ = schema
    with psycopg.connect(url, autocommit=True, options=options) as conn:
        yield conn


def test_seed_twice_changes_nothing(db):
    first = seed.seed(db)
    assert first.inserted == SEEDED and set(first.updated.values()) == {0}
    after_first = seed.counts(db)
    second = seed.seed(db)
    assert set(second.inserted.values()) == {0} and set(second.updated.values()) == {0}
    assert seed.counts(db) == after_first
    assert {t: after_first[t] for t in SEEDED} == SEEDED
    assert all(n == 0 for t, n in after_first.items() if t not in SEEDED)  # run tables start empty


def test_cap_query_reads_the_running_total(db):
    seeded = seed.seed(db)
    weeks = seed.cap_query(db, "SPRING-26", seeded.weekly)
    assert [w[3] for w in weeks] == RUNNING
    assert [w[2] for w in weeks] == [1200, 980, 2820, 1540]
    assert [(w[0], w[1]) for w in weeks][-1] == (date(2026, 3, 22), date(2026, 3, 31))
    assert {w[4] for w in weeks} == {5000}
    seed.seed(db)
    assert seed.cap_query(db, "SPRING-26", seeded.weekly) == weeks


def test_a_changed_row_is_put_back(db):
    seed.seed(db)
    db.execute("UPDATE charges SET amount = 1 WHERE id = 'C1'")
    again = seed.seed(db)
    assert again.updated["charges"] == 1 and sum(again.inserted.values()) == 0
    assert db.execute("SELECT amount FROM charges WHERE id = 'C1'").fetchone()[0] == Decimal("1800.00")


def test_hypertable_and_aggregate_where_timescaledb_is_there(db, schema):
    seeded = seed.seed(db)
    if not seeded.timescale:
        assert seeded.timescale_skipped and seeded.weekly == "store_sales"
        pytest.skip(f"plain Postgres ({seeded.timescale_skipped}): the TimescaleDB part was skipped, as intended")
    name = schema[2]
    hyper = db.execute("SELECT 1 FROM timescaledb_information.hypertables "
                       "WHERE hypertable_schema = %s AND hypertable_name = 'store_sales'", (name,)).fetchall()
    cagg = db.execute("SELECT materialized_only FROM timescaledb_information.continuous_aggregates "
                      "WHERE view_schema = %s AND view_name = 'promo_units_weekly'", (name,)).fetchall()
    assert hyper == [(1,)] and cagg == [(False,)]
    assert db.execute("SELECT count(*) FROM promo_units_weekly").fetchone()[0] == SEEDED["store_sales"]


def test_make_seed_twice_prints_counts_and_the_cap_query(schema, monkeypatch, capsys):
    url, options, _ = schema
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("PGOPTIONS", options)  # libpq reads it, so main() lands in this test's schema
    seed.main()
    first = capsys.readouterr().out
    seed.main()
    second = capsys.readouterr().out
    for out in (first, second):
        assert url not in out
        assert "QuickBooks: skipped" in out
        assert re.search(r"2026-03-22 to 2026-03-31\s+1,540\s+6,540", out)
    table_line = r"^  (\w+)\s+(\d+)\s+(\d+)\s+(\d+)$"  # table, rows, inserted, updated
    assert {t: (int(n), int(i), int(u)) for t, n, i, u in re.findall(table_line, first, re.M)} == \
           {t: (n, n, 0) for t, n in SEEDED.items()}
    assert {t: (int(n), int(i), int(u)) for t, n, i, u in re.findall(table_line, second, re.M)} == \
           {t: (n, 0, 0) for t, n in SEEDED.items()}
