"""Seeded rows read back from Postgres as api/contracts.py models, for api/rows.py when the database is on; and the
cap query (GET /db/cap, make seed). Every read is one account's rows (account_id, 003_accounts.sql).

The rows come back as the files give them: the same rows, in each file's order (source_row, which the seed writes),
with the same values. Postgres returns numeric(12,4) as 1.5000 where the file says 1.50, so a rate that fits in
cents comes back in cents. Any difference would change what the agents are sent, and with it the DEMO_MODE fixture
keys of a run recorded on the database; api/tests/test_db_runtime.py compares the two on the seeded data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from api.contracts import Charge, PriorPayment, PromoPlan, SalesRow
from api.db import conn

try:
    from psycopg import sql
    from psycopg.rows import dict_row
except ImportError:  # conn.enabled() is False without psycopg, so nothing here runs
    sql = dict_row = None

CENT = Decimal("0.01")

# One account's running total of promoted units per reporting week inside the promo's dates, next to its cap.
# {weekly} is the continuous aggregate on TimescaleDB, store_sales on plain Postgres; both have these columns. The
# engine's cap check (api/engine/allowed.py) is what decides charges; this is the same count, seen from the database.
CAP_QUERY = """
SELECT w.week_start, w.week_end, sum(w.promo_units)::int AS promo_units,
       (sum(sum(w.promo_units)) OVER (ORDER BY w.week_start))::int AS running_units, p.cap
FROM {weekly} AS w
JOIN promo_plan AS p ON w.account_id = p.account_id AND w.product = ANY (p.products)
WHERE p.account_id = %s AND p.promo_id = %s AND w.week_start >= p.starts AND w.week_end <= p.ends
GROUP BY w.week_start, w.week_end, p.cap
ORDER BY w.week_start
"""


def _as_written(rate: Decimal) -> Decimal:
    cents = rate.quantize(CENT)
    return cents if cents == rate else rate.normalize()


def _select(db, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchall()


def charges(db, account_id: str, source_file: str) -> list[Charge]:
    """One month's charges: the rows the seed copied from that month's file (api/rows.py charge_file)."""
    return [Charge(**{**r, "rate": _as_written(r["rate"])}) for r in _select(
        db, "SELECT id, ref, code, description, product, units, rate, amount, period_start, period_end, notice_date, "
            "line_ref FROM charges WHERE account_id = %s AND source_file = %s ORDER BY source_row, id",
        (account_id, source_file))]


def sales(db, account_id: str) -> list[SalesRow]:
    return [SalesRow(**r) for r in _select(
        db, "SELECT week_start, week_end, product, promo_units, total_units FROM store_sales WHERE account_id = %s "
            "ORDER BY source_row NULLS LAST, week_start, product", (account_id,))]


def prior_payments(db, account_id: str) -> list[PriorPayment]:
    return [PriorPayment(**r) for r in _select(
        db, "SELECT ref, paid_on, promo_id, product, period_start, period_end, units, amount FROM prior_payments "
            "WHERE account_id = %s ORDER BY source_row NULLS LAST, paid_on, ref", (account_id,))]


def promo_plan(db, account_id: str) -> list[PromoPlan]:
    return [PromoPlan(**{**r, "rate": _as_written(r["rate"])}) for r in _select(
        db, "SELECT promo_id, products, rate, starts, ends, cap FROM promo_plan WHERE account_id = %s "
            "ORDER BY source_row NULLS LAST, promo_id", (account_id,))]


TABLES = {"charges": charges, "store_sales": sales, "prior_payments": prior_payments, "promo_plan": promo_plan}
_trouble = {t: conn.LogOnce(f"Postgres {t}") for t in TABLES}


def load(table: str, account_id: str, *args: Any) -> list | None:
    """An account's rows of a seeded table from Postgres, or None, meaning read the files: the database is off or
    unreachable (api/db/conn.py logs that), a query failed or the account has no rows there (each logged once until it
    works)."""
    if not conn.enabled():
        return None
    try:
        got = conn.shared.run(lambda db: TABLES[table](db, account_id, *args))
    except conn.Unavailable:
        return None
    except Exception as e:  # noqa: BLE001 - any database problem means the files, never a failed run
        _trouble[table].failed(f"{conn.scrub(e)}; reading data/ instead (make seed sets the tables up)")
        return None
    if not got:
        _trouble[table].failed("no rows; reading data/ instead (make seed fills them)")
        return None
    _trouble[table].ok()
    return got


def weekly(db) -> str:
    """Where the cap query reads weekly promoted units: the continuous aggregate on TimescaleDB, else store_sales."""
    found = db.execute("SELECT to_regclass('promo_units_weekly') IS NOT NULL").fetchone()[0]
    return "promo_units_weekly" if found else "store_sales"


def cap_query(db, account_id: str, promo_id: str, weekly: str) -> list[tuple]:
    """(week_start, week_end, promo_units, running_units, cap) per week of one account's promo, in date order."""
    query = sql.SQL(CAP_QUERY).format(weekly=sql.Identifier(weekly))
    return db.execute(query, (account_id, promo_id)).fetchall()
