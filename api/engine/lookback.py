"""The six-month lookback: every past deduction run through the same math as today's charges (allowed.py), and how
much of what was wrongly taken can still be claimed before the distributor's dispute window closes.

Plain code, no AI, and no deal read: the terms come from the brand's own promo plan, built here in code.
- PA: the plan promo whose dates overlap the deduction's period (one that also lists its product first) gives the
  rate, the products, the dates and the cap; compute_allowed walks the store sales across that promo's weeks for the
  cap. An earlier past PA deduction for the same period and products counts as already paid (the duplicate check).
- SH, PR, SP: the delivery records, price list and ops terms, exactly as a live charge (allowed.py).
- DF and any other code: not_checked. A fee's discretion clause needs the deal read and a person.
A row missing what its check needs (units, period, products or delivery line), or one the math can't check (no plan
promo for those dates, no proof of delivery, no verified spoils allowance), is not_checked too.

Per row: wrongly_taken = taken - allowed when that's over the match tolerance, else 0; still owed = wrongly_taken -
recovered. Status, first that fits:
- not_checked  as above;
- fair         nothing wrongly taken;
- settled      recovered already covers it;
- claimable    still owed and either already in dispute (outcome open: no file-by date) or inside the window;
- past_window  still owed and the window closed (days_left below zero).
The window runs from deducted_on (else the last day of the row's month) for window_days; days_left counts from
as_of, the account's payment date, so the same files always give the same answer.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from api.engine.allowed import FEE_CODES, OPS_CODES, PROMO_CODES, compute_allowed, product_key
from api.engine.totals import total_of
from api.engine.types import Charge, OpsData, PriorPayment, SalesWeek, Term, TermType, money

ZERO = Decimal("0.00")
OPEN_OUTCOMES = frozenset({"open", "disputed", "pending", "in dispute", "in_dispute"})
STATUSES = ("claimable", "past_window", "settled", "fair", "not_checked")


@dataclass(frozen=True)
class PastDeduction:
    """One row of history/deductions.csv. Blank cells are None (the check then can't run)."""

    ref: str
    month: str  # "2026-02"
    code: str
    amount: Decimal
    description: str = ""
    outcome: str = ""
    recovered: Decimal = ZERO
    deducted_on: date | None = None
    products: tuple[str, ...] = ()
    units: int | None = None
    rate: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    line_ref: str | None = None


@dataclass(frozen=True)
class PlanPromo:
    """One row of a promo plan (plan/promo-plan.csv, history/promo-plan.csv). cap None: no cap."""

    promo_id: str
    products: tuple[str, ...]
    rate: Decimal
    starts: date
    ends: date
    cap: int | None = None


@dataclass(frozen=True)
class LookbackLine:
    ref: str
    month: str
    code: str
    description: str
    taken: Decimal
    allowed: Decimal | None  # None: not checked
    wrongly_taken: Decimal
    outcome: str
    recovered: Decimal
    deducted_on: date | None
    file_by: date | None
    days_left: int | None
    status: str  # one of STATUSES
    note: str = ""  # the math, or why the row wasn't checked


@dataclass(frozen=True)
class LookbackResult:
    as_of: date
    window_days: int
    lines: tuple[LookbackLine, ...] = ()
    totals: dict[str, Decimal | int] = field(default_factory=dict)


def month_end(month: str) -> date:
    """"2026-02" -> 2026-02-28."""
    year, mon = int(month[:4]), int(month[5:7])
    return date(year, mon, calendar.monthrange(year, mon)[1])


def deadline(deducted_on: date, as_of: date, window_days: int) -> tuple[date, int]:
    """The last day to dispute a deduction taken on deducted_on, and the days left from as_of (below zero: closed)."""
    file_by = deducted_on + timedelta(days=window_days)
    return file_by, (file_by - as_of).days


def promo_terms(promo: PlanPromo) -> list[Term]:
    """A plan promo as the verified terms compute_allowed reads (rate, products, dates, and the cap if it has one)."""
    base = f"plan-{promo.promo_id}"
    out = [
        Term(id=f"{base}-rate", type=TermType.PROMO_RATE, params={"rate": str(promo.rate)}, source_doc_id=base),
        Term(id=f"{base}-scope", type=TermType.PRODUCT_SCOPE, params={"products": list(promo.products)},
             source_doc_id=base),
        Term(id=f"{base}-dates", type=TermType.DATE_RANGE,
             params={"start": promo.starts.isoformat(), "end": promo.ends.isoformat()}, source_doc_id=base),
    ]
    if promo.cap is not None:
        out.append(Term(id=f"{base}-cap", type=TermType.UNIT_CAP, params={"max_units": promo.cap}, source_doc_id=base))
    return out


def _plan_promo(row: PastDeduction, plan: Sequence[PlanPromo]) -> PlanPromo | None:
    """The promo whose dates overlap the row's period; one that lists the row's product wins."""
    overlap = [p for p in plan if p.starts <= row.period_end and row.period_start <= p.ends]
    keys = {product_key(x) for x in row.products}
    covering = [p for p in overlap if keys & {product_key(x) for x in p.products}]
    return (covering or overlap or [None])[0]


def _charge(row: PastDeduction, counterparty: str) -> Charge:
    units = row.units or 0
    rate = row.rate if row.rate is not None else (money(row.amount / units) if units else ZERO)
    start = row.period_start or row.deducted_on or month_end(row.month)
    return Charge(id=row.ref, ref=row.ref, code=row.code, description=row.description, products=row.products,
                  units=units, rate=rate, amount=row.amount, period_start=start, period_end=row.period_end or start,
                  counterparty=counterparty, line_ref=row.line_ref)


def _needs(row: PastDeduction) -> str | None:
    """What the row lacks for its check, or None."""
    if row.code in PROMO_CODES:
        lacking = [n for n, v in (("product", row.products), ("units", row.units), ("period_start", row.period_start),
                                  ("period_end", row.period_end)) if not v]
    elif row.code in ("SH", "PR"):
        lacking = [n for n, v in (("line_ref", row.line_ref), ("units", row.units)) if not v]
    elif row.code == "SP":
        lacking = [n for n, v in (("period_start", row.period_start), ("period_end", row.period_end)) if not v]
    else:
        return None
    return f"The history row has no {', '.join(lacking)}." if lacking else None


def _priors(row: PastDeduction, earlier: Iterable[PastDeduction]) -> list[PriorPayment]:
    """Earlier PA deductions for the same period and products: those units were already taken once."""
    keys = {product_key(x) for x in row.products}
    return [PriorPayment(ref=p.ref, paid_on=p.deducted_on or month_end(p.month), promo_id="", products=p.products,
                         period_start=p.period_start, period_end=p.period_end, units=p.units, amount=p.amount)
            for p in earlier
            if p.code in PROMO_CODES and p.ref != row.ref and p.units and p.period_start == row.period_start
            and p.period_end == row.period_end and keys & {product_key(x) for x in p.products}]


def check_row(row: PastDeduction, earlier: Sequence[PastDeduction], plan: Sequence[PlanPromo],
              sales: Sequence[SalesWeek], ops: OpsData, counterparty: str = "") -> tuple[Decimal | None, str]:
    """(allowed, note) for one past deduction; allowed None means not checked, and the note says why."""
    if row.code in FEE_CODES:
        return None, "A display fee turns on the deal's discretion clause: it needs the deal read and a person."
    if row.code not in PROMO_CODES | OPS_CODES:
        return None, f"No check for deduction code {row.code} yet."
    if why := _needs(row):
        return None, why
    charge = _charge(row, counterparty)
    if row.code in PROMO_CODES:
        promo = _plan_promo(row, plan)
        if promo is None:
            return None, "No promo in the plan runs on these dates."
        a = compute_allowed(charge, promo_terms(promo), sales, _priors(row, earlier))
    else:
        a = compute_allowed(charge, [], ops=ops)
    if a.missing:
        return None, a.steps[0] if a.steps else f"Missing {', '.join(a.missing)}."
    return a.allowed, " ".join(a.steps)


def lookback(rows: Sequence[PastDeduction], plan: Sequence[PlanPromo], sales: Sequence[SalesWeek], ops: OpsData, *,
             as_of: date, window_days: int, tolerance: Decimal, counterparty: str = "") -> LookbackResult:
    """Every row checked, in deduction order (deducted_on, else its month's end; ties keep the file's order)."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i].deducted_on or month_end(rows[i].month), i))
    lines: list[LookbackLine] = []
    for n, i in enumerate(order):
        row = rows[i]
        allowed, note = check_row(row, [rows[j] for j in order[:n]], plan, sales, ops, counterparty)
        taken, recovered = money(row.amount), money(row.recovered)
        wrongly = ZERO if allowed is None or taken - allowed <= tolerance else money(taken - allowed)
        owed = max(ZERO, wrongly - recovered)
        file_by = days_left = None
        if allowed is None:
            status = "not_checked"
        elif wrongly == ZERO:
            status = "fair"
        elif owed == ZERO:
            status = "settled"
        elif row.outcome.strip().lower() in OPEN_OUTCOMES:
            status = "claimable"  # already in dispute: no deadline left to meet
        else:
            file_by, days_left = deadline(row.deducted_on or month_end(row.month), as_of, window_days)
            status = "claimable" if days_left >= 0 else "past_window"
        lines.append(LookbackLine(ref=row.ref, month=row.month, code=row.code, description=row.description,
                                  taken=taken, allowed=allowed, wrongly_taken=wrongly, outcome=row.outcome,
                                  recovered=recovered, deducted_on=row.deducted_on, file_by=file_by,
                                  days_left=days_left, status=status, note=note))

    def owed(ln: LookbackLine) -> Decimal:
        return max(ZERO, ln.wrongly_taken - ln.recovered)

    totals: dict[str, Decimal | int] = {
        "wrongly_taken": total_of([ZERO, *(ln.wrongly_taken for ln in lines)]),
        "lost_past_window": total_of([ZERO, *(owed(ln) for ln in lines if ln.status == "past_window")]),
        "claimable_now": total_of([ZERO, *(owed(ln) for ln in lines if ln.status == "claimable")]),
        "checked": sum(ln.status != "not_checked" for ln in lines),
        "not_checked": sum(ln.status == "not_checked" for ln in lines),
    }
    return LookbackResult(as_of=as_of, window_days=window_days, lines=tuple(lines), totals=totals)
