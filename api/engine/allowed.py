"""The math engine (F3): what the deal allows for one charge. docs/design.md, "Math engine", steps 1 to 7.

Plain code, no AI. Every amount the product shows comes from here or from gate.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

from api.engine.types import (
    Allowance,
    Charge,
    PriorPayment,
    SalesWeek,
    Term,
    TermStatus,
    TermType,
    money,
)

PROMO_CODES = frozenset({"PA"})
FEE_CODES = frozenset({"DF"})


def product_key(name: str) -> str:
    """'Peak Bar Original', 'original' and ' Original ' are the same product."""
    key = " ".join(name.lower().split())
    return key.removeprefix("peak bar ").strip()


def split_products(text: str) -> tuple[str, ...]:
    """'Original+Chocolate' or 'Peak Bar Original; Peak Bar Chocolate' -> a tuple of product names."""
    parts = text.replace(";", "+").split("+")
    return tuple(p.strip() for p in parts if p.strip())


def notice_days(notice_date: date | None, due: date) -> int | None:
    """Days of written notice before a fee's period ends (Mar 11 -> Mar 31 is 20)."""
    return None if notice_date is None else (due - notice_date).days


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _pick(terms: Sequence[Term], ttype: TermType) -> Term | None:
    """The term of this type that governs: approved sources only; a rejected term only if nothing else
    exists (so the gate can Skip); the latest effective_from wins, then the later one in the list."""
    pool = [(i, t) for i, t in enumerate(terms) if t.type == ttype and t.source_approved]
    live = [(i, t) for i, t in pool if t.status != TermStatus.REJECTED]
    pool = live or pool
    if not pool:
        return None
    return max(pool, key=lambda it: (it[1].effective_from or date.min, it[0]))[1]


def compute_allowed(
    charge: Charge,
    terms: Sequence[Term],
    sales: Iterable[SalesWeek] = (),
    prior_payments: Iterable[PriorPayment] = (),
) -> Allowance:
    """Step 1: the code says which promo the charge claims (PA promo allowance, DF display fee)."""
    if charge.code in PROMO_CODES:
        return _promo(charge, terms, list(sales), list(prior_payments))
    if charge.code in FEE_CODES:
        return _fee(charge, terms)
    return _result(charge, Decimal(0), missing=(f"code:{charge.code}",), steps=(f"Unknown deduction code {charge.code}.",))


def _result(charge: Charge, allowed: Decimal, **kw) -> Allowance:
    taken = money(charge.amount)
    allowed = money(allowed)
    return Allowance(charge_id=charge.id, taken=taken, allowed=allowed, delta=taken - allowed, **kw)


def _promo(charge: Charge, terms: Sequence[Term], sales: list[SalesWeek], priors: list[PriorPayment]) -> Allowance:
    rate_t = _pick(terms, TermType.PROMO_RATE)
    scope_t = _pick(terms, TermType.PRODUCT_SCOPE)
    range_t = _pick(terms, TermType.DATE_RANGE)
    cap_t = _pick(terms, TermType.UNIT_CAP)  # optional: no cap term means no cap
    missing = tuple(n for n, t in (("promo_rate", rate_t), ("product_scope", scope_t), ("date_range", range_t)) if t is None)
    if missing:
        return _result(charge, Decimal(0), missing=missing, steps=(f"Deal has no verified {', '.join(missing)}.",))

    # Step 2: product check.
    deal_keys = {product_key(p) for p in scope_t.params["products"]}
    charge_keys = {product_key(p) for p in charge.products} & deal_keys
    if not charge_keys:
        return _result(
            charge, Decimal(0), terms=(scope_t,),
            steps=(f"{' + '.join(charge.products)} is not a product the deal covers.",),
        )

    # Steps 3 and 4: walk the deal's promoted sales in date order. Units inside the deal dates count against
    # the cap; units outside count only if an approved amendment covers those dates, up to its extra units.
    start, end = _as_date(range_t.params["start"]), _as_date(range_t.params["end"])
    cap = int(cap_t.params["max_units"]) if cap_t else None
    amendments = [
        t for t in terms
        if t.type == TermType.AMENDMENT and t.source_approved and t.status != TermStatus.REJECTED
        and t.effective_from and t.effective_to
    ]
    ext_used = {a.id: 0 for a in amendments}
    used_amendments: list[Term] = []
    running = sold = in_dates = by_amendment = 0
    rows = sorted((s for s in sales if product_key(s.product) in deal_keys), key=lambda s: (s.week_start, product_key(s.product)))
    for row in rows:
        in_charge = (
            charge.period_start <= row.week_start and row.week_end <= charge.period_end
            and product_key(row.product) in charge_keys
        )
        if in_charge:
            sold += row.promo_units
        if start <= row.week_start and row.week_end <= end:
            room = row.promo_units if cap is None else max(0, min(row.promo_units, cap - running))
            running += row.promo_units
            if in_charge:
                in_dates += room
            continue
        for a in amendments:
            if a.effective_from <= row.week_start and row.week_end <= a.effective_to:
                covered = max(0, min(row.promo_units, int(a.params["extra_units"]) - ext_used[a.id]))
                ext_used[a.id] += covered
                if in_charge:
                    by_amendment += covered
                    if covered and a not in used_amendments:
                        used_amendments.append(a)
                break

    steps = [f"Store sales show {sold:,} promoted units for this period."]
    if cap is not None:
        steps.append(f"Cap {cap:,} units: {in_dates:,} of the in-date units are still under it.")
    if by_amendment:
        steps.append(f"{by_amendment:,} units outside the deal dates are covered by an approved amendment.")
    elif amendments and in_dates < sold:  # the cap left units out and no extension reaches this period
        spans = " and ".join(f"{_as_date(a.effective_from):%b} {_as_date(a.effective_from).day}–"
                             f"{_as_date(a.effective_to):%b} {_as_date(a.effective_to).day}" for a in amendments)
        steps.append(f"The approved extension adds units only for {spans}, not these dates.")
    covered = min(charge.units, in_dates + by_amendment)

    # Step 5: duplicate check. Units a prior payment already paid for the same products and period are not owed again.
    paid = sum(
        p.units for p in priors
        if p.period_start == charge.period_start and p.period_end == charge.period_end
        and {product_key(x) for x in p.products} & charge_keys
    )
    if paid:
        steps.append(f"A prior payment already covered {paid:,} units for this period.")
        covered = max(0, covered - paid)

    # Step 6: allowed = covered units x the deal's rate.
    rate = Decimal(str(rate_t.params["rate"]))
    steps.append(f"{covered:,} units x ${rate} = ${money(covered * rate):,}.")
    used = [rate_t, scope_t, range_t] + ([cap_t] if cap_t else []) + used_amendments
    return _result(charge, covered * rate, covered_units=covered, terms=tuple(used), steps=tuple(steps))


def _fee(charge: Charge, terms: Sequence[Term]) -> Allowance:
    """Step 7: a fee is allowed up to the stated maximum; whether to accept it is the gate's call."""
    fee_t = _pick(terms, TermType.FEE_DISCRETION)
    days = notice_days(charge.notice_date, charge.period_end)
    facts = {"notice_days": days}
    if fee_t is None:
        return _result(charge, Decimal(0), missing=("fee_discretion",), facts=facts, steps=("Deal has no verified fee clause.",))
    max_fee = money(fee_t.params["max_fee"])
    allowed = min(money(charge.amount), max_fee)
    steps = [f"Deal allows a fee of up to ${max_fee:,}."]
    if days is not None:
        steps.append(f"Written notice came {days} days ahead.")
    return _result(charge, allowed, terms=(fee_t,), facts=facts, steps=tuple(steps))
