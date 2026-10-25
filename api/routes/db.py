"""GET /db/cap?promo_id=&account=: one account's cap query (Peak Bar's SPRING-26 by default), answered by the
database. The Tiger Data proof (store_sales is a hypertable and promo_units_weekly its continuous aggregate), and the
running total the evidence drawer can show next to §3.2.

Read-only. Without a database (no DATABASE_URL, or DEMO_MODE) or when it doesn't answer, it says so with a 503.
"""

from datetime import date
from typing import Literal

from fastapi import Depends, APIRouter, HTTPException, Query

from api import accounts, tenancy
from api.contracts import Contract
from api.db import conn, reads
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["db"])


class CapWeek(Contract):
    week_start: date
    week_end: date
    promo_units: int  # the deal's products, promoted units sold that week
    running_units: int  # the promo's total so far
    cap: int


class CapReport(Contract):
    account: str
    promo_id: str
    source: Literal["promo_units_weekly", "store_sales"]  # the continuous aggregate on TimescaleDB, else the table
    cap: int
    weeks: list[CapWeek]


@router.get("/db/cap", response_model=CapReport)
def cap(promo_id: str = Query(default="SPRING-26"), account: str = Query(default=accounts.DEFAULT), who: Caller = Depends(current_supplier)) -> CapReport:
    if not tenancy.can_see(who, account):
        raise HTTPException(404, f"unknown account {account}")
    if not conn.enabled():
        raise HTTPException(503, "no database: DATABASE_URL isn't set, or DEMO_MODE is on")

    def query(db):
        source = reads.weekly(db)
        return source, reads.cap_query(db, account, promo_id, source)

    try:
        source, rows = conn.shared.run(query)
    except Exception as e:  # noqa: BLE001 - unreachable, not seeded, or the query failed
        raise HTTPException(503, f"the database didn't answer the cap query ({conn.scrub(e)})") from None
    if not rows:
        raise HTTPException(404, f"no sales for {account}'s promo {promo_id} in the database (make seed loads them)")
    weeks = [CapWeek(week_start=s, week_end=e, promo_units=u, running_units=r, cap=c) for s, e, u, r, c in rows]
    return CapReport(account=account, promo_id=promo_id, source=source, cap=weeks[0].cap, weeks=weeks)
