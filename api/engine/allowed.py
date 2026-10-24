"""The math engine (F3): what the deal allows for one charge. docs/design.md, "Math engine", steps 1 to 7, plus the
operations charges (shortage, price mismatch, spoilage), checked against delivery records instead of store sales, and
fee-schedule charges (a % with a minimum and a cap, per unit, per PO, per carton or flat, maybe tiered by days),
checked against the other side's fee backup. Any charge also gets the deal's dispute window, when it states one.

Plain code, no AI. Every amount the product shows comes from here or from gate.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

from api.engine.types import (
    AgreedPrice,
    Allowance,
    Charge,
    Delivery,
    FeeData,
    FeeLine,
    OpsData,
    PriorPayment,
    SalesWeek,
    Term,
    TermStatus,
    TermType,
    money,
)

PROMO_CODES = frozenset({"PA", "OI"})  # OI: an off-invoice allowance the distributor recovers by deduction
FEE_CODES = frozenset({"DF"})
OPS_CODES = frozenset({"SH", "PR", "SP"})  # shortage, price mismatch, spoilage: checked against OpsData
SPOILS_ALLOWANCE = "spoils_allowance_pct"  # the ops term an SP charge is capped by


def product_key(name: str) -> str:
    """'Peak Bar Original', 'original' and ' Original ' are the same product."""
    key = " ".join(name.lower().split())
    return key.removeprefix("peak bar ").strip()


def split_products(text: str) -> tuple[str, ...]:
    """'Original+Chocolate' or 'Peak Bar Original; Peak Bar Chocolate' -> a tuple of product names."""
    parts = text.replace(";", "+").split("+")
    return tuple(p.strip() for p in parts if p.strip())


def usd(value) -> str:
    """$2.50, or $2.455 for a unit price finer than a cent."""
    d = Decimal(str(value))
    return f"${money(d):,}" if d == money(d) else f"${d.normalize():,}"


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"  # Mar 4, built by hand as evidence.day() is


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
    ops: OpsData | None = None,
    fees: FeeData | None = None,
) -> Allowance:
    """Step 1: the code says which promo the charge claims (PA promo allowance, DF display fee). SH, PR and SP
    (shortage, price mismatch, spoilage) are checked against the account's delivery records, price list and ops terms.
    A code the deal names in a fee_schedule term (directly, or through fees.codes) is priced by that schedule.
    Then the deal's dispute window, if it states one, is checked for every charge."""
    fees = fees or FeeData()
    return _dispute_window(_allowed(charge, terms, list(sales), list(prior_payments), ops, fees), charge, terms, fees)


def _allowed(charge: Charge, terms: Sequence[Term], sales: list[SalesWeek], priors: list[PriorPayment],
             ops: OpsData | None, fees: FeeData) -> Allowance:
    if charge.code in PROMO_CODES:
        return _promo(charge, terms, sales, priors)
    schedules = fee_terms(charge, terms, fees)
    if schedules or charge.code in fees.codes:
        return _fee_schedule(charge, schedules, terms, fees)
    if charge.code in FEE_CODES:
        return _fee(charge, terms)
    if charge.code in OPS_CODES:
        if ops is None:
            return _missing(charge, "delivery records, price list and ops terms",
                            "No delivery records, price list or ops terms to check this charge against.")
        return {"SH": _shortage, "PR": _price_mismatch, "SP": _spoilage}[charge.code](charge, ops)
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


# --- Operations charges ------------------------------------------------------------------------------------------
# Steps keep fixed forms that api/evidence.py math_parts links to their evidence: "Delivery <line_ref>: ..." opens
# that line's proof of delivery, "Price list: ..." the agreed price, "Spoils allowance ..." the ops term, and
# "Claimed ..." the charge row.

def _missing(charge: Charge, what: str, step: str, **kw) -> Allowance:
    """Nothing to check the charge against: allowed $0 with `what` missing, so the gate asks a person."""
    return _result(charge, Decimal(0), missing=(what,), steps=(step,), **kw)


def _delivery(charge: Charge, ops: OpsData) -> Delivery | Allowance:
    """The delivery line an SH or PR charge points to, or the Allowance saying it's missing."""
    if not charge.line_ref:
        return _missing(charge, "the delivery line this charge points to", f"Charge {charge.ref} names no delivery line.")
    row = next((d for d in ops.deliveries if d.line_ref.strip() == charge.line_ref.strip()), None)
    if row is None:
        return _missing(charge, f"proof of delivery for {charge.line_ref}", f"No proof of delivery for line {charge.line_ref}.")
    return row


def _shortage(charge: Charge, ops: OpsData) -> Allowance:
    """SH: short = shipped - received on the signed delivery; allowed = min(units claimed, short) x the unit price."""
    row = _delivery(charge, ops)
    if isinstance(row, Allowance):
        return row
    short = max(0, row.shipped_units - row.received_units)
    covered = min(charge.units, short)
    price = Decimal(str(row.unit_price))
    signed = (f", signed by {row.received_by}" if row.received_by else "") + (
        f" on {_day(row.received_at)}" if row.received_at else "")
    steps = (
        f"Delivery {row.line_ref}: {row.shipped_units:,} units shipped, {row.received_units:,} received{signed}.",
        f"Claimed {charge.units:,} units short; the delivery shows {short:,} short.",
        f"{covered:,} units x {usd(price)} = ${money(covered * price):,}.",
    )
    facts = {"line_refs": (row.line_ref,), "shipped_units": row.shipped_units, "received_units": row.received_units,
             "short_units": short}
    return _result(charge, covered * price, covered_units=covered, facts=facts, steps=steps)


def _agreed_price(prices: Iterable[AgreedPrice], product: str, on: date) -> AgreedPrice | None:
    """The price-list row for the product in effect on that date; the latest effective_from wins."""
    rows = [p for p in prices if product_key(p.product) == product_key(product)
            and p.effective_from <= on and (p.effective_to is None or on <= p.effective_to)]
    return max(rows, key=lambda p: p.effective_from, default=None)


def _price_mismatch(charge: Charge, ops: OpsData) -> Allowance:
    """PR: the delivery's invoiced unit price against the agreed price on the day it was received;
    allowed = units claimed x the amount invoiced above the agreed price (never below zero)."""
    row = _delivery(charge, ops)
    if isinstance(row, Allowance):
        return row
    facts = {"line_refs": (row.line_ref,), "product": row.product}
    if row.received_at is None:
        return _missing(charge, f"the received date on {row.line_ref}",
                        f"Delivery {row.line_ref}: no received date, so the agreed price can't be dated.", facts=facts)
    agreed_row = _agreed_price(ops.prices, row.product, row.received_at)
    if agreed_row is None:
        return _missing(charge, f"an agreed price for {row.product} on {_day(row.received_at)}",
                        f"The price list has no agreed price for {row.product} on {_day(row.received_at)}.", facts=facts)
    invoiced, agreed = Decimal(str(row.unit_price)), Decimal(str(agreed_row.agreed_price))
    gap = max(Decimal(0), invoiced - agreed)
    until = f" to {_day(agreed_row.effective_to)}" if agreed_row.effective_to else ""
    steps = (
        f"Delivery {row.line_ref}: invoiced at {usd(invoiced)} a unit, received {_day(row.received_at)}.",
        f"Price list: {usd(agreed)} a unit for {row.product} from {_day(agreed_row.effective_from)}{until}.",
        f"Invoiced {usd(gap)} a unit above the agreed price; the charge claims {usd(charge.rate)}." if gap else
        f"Invoiced at or below the agreed price; the charge claims {usd(charge.rate)} a unit.",
        f"{charge.units:,} units x {usd(gap)} = ${money(charge.units * gap):,}.",
    )
    facts |= {"invoiced_price": invoiced, "agreed_price": agreed, "price_gap": gap}
    return _result(charge, charge.units * gap, covered_units=charge.units if gap else 0, facts=facts, steps=steps)


def _percent(value: str) -> Decimal | None:
    """1.0, "1.0" or "1.0%" -> Decimal("1.0"); anything else, or below zero, is not a percentage."""
    try:
        pct = Decimal(value.strip().removesuffix("%").strip())
    except InvalidOperation:
        return None
    return pct if pct.is_finite() and pct >= 0 else None


def _spoilage(charge: Charge, ops: OpsData) -> Allowance:
    """SP: allowed = min(amount taken, the spoils allowance % of what was invoiced on deliveries received in the
    charge's period, shipped units x unit price)."""
    named = [t for t in ops.terms if t.key == SPOILS_ALLOWANCE]
    live = [t for t in named if t.status != TermStatus.REJECTED]
    pct = _percent(live[-1].value) if live else None
    if pct is None:
        why = ("its quote isn't found word for word in the deal" if named and not live else
               f"its value {live[-1].value!r} isn't a percentage" if live else "the deal states none")
        return _missing(charge, f"a verified {SPOILS_ALLOWANCE} term", f"No spoils allowance to check against: {why}.")
    start, end = charge.period_start, charge.period_end
    lines = sorted((d for d in ops.deliveries if d.received_at and start <= d.received_at <= end),
                   key=lambda d: (d.received_at, d.line_ref))
    if not lines:
        return _missing(charge, f"deliveries received {_day(start)} to {_day(end)}",
                        f"No deliveries received {_day(start)} to {_day(end)} to take a spoils allowance on.")
    amounts = [money(d.shipped_units * Decimal(str(d.unit_price))) for d in lines]
    invoiced = sum(amounts, Decimal(0))
    cap = money(pct / 100 * invoiced)
    taken = money(charge.amount)
    allowed = min(taken, cap)
    steps = [f"Delivery {d.line_ref}: {d.shipped_units:,} units shipped x {usd(d.unit_price)} = ${a:,}, received "
             f"{_day(d.received_at)}." for d, a in zip(lines, amounts)]
    steps += [
        f"Invoiced {_day(start)} to {_day(end)}: ${invoiced:,}.",
        f"Spoils allowance {pct}% of ${invoiced:,} = ${cap:,}.",
        f"Claimed ${taken:,}; allowed is the smaller: ${allowed:,}.",
    ]
    facts = {"line_refs": tuple(d.line_ref for d in lines), "allowance_pct": pct, "period_invoiced": invoiced,
             "spoils_allowance": cap}
    return _result(charge, allowed, facts=facts, steps=tuple(steps))


# --- Fee schedules -----------------------------------------------------------------------------------------------
# A fee_schedule term prices one kind of fee (params, as in api/contracts.py FeeScheduleParams):
#   fee_code        the fee's name as the deal writes it ("MCB", "Extra Performance"); FeeData.codes maps charge codes
#   basis           percent (rate% of each backup line's base_amount) · per_unit (rate x units) · per_carton
#                   (rate x cartons) · per_po and flat (rate once per group, whatever its lines)
#   rate            the rate; with tiers, each line's rate is the tier its days fall in (no tier: no fee)
#   min, max        clamp each group's fee; the minimum applies only to a group that owes some fee
#   per             what a group is: invoice / po / incident (FeeLine.group, else each line alone) or month
#   requires_proof  every backup line must name a proof_doc that exists, else the gate asks a person
# allowed = sum of the groups' clamped fees + every line's pass_through (cost charged on at cost, e.g. landed cost).
# A schedule from a later document (a policy change) applies to a line only from its effective_from, and never
# sooner than its noticed_on + the deal's notice_period days.


def fee_key(name: str) -> str:
    return " ".join(str(name).lower().split())


def fee_terms(charge: Charge, terms: Sequence[Term], fees: FeeData) -> list[Term]:
    """The fee_schedule terms for this charge's fee, from approved sources: the verified ones, or (only if none is)
    the rejected or disputed ones, so the gate can Skip or Ask."""
    want = fee_key(fees.codes.get(charge.code, charge.code))
    pool = [t for t in terms if t.type == TermType.FEE_SCHEDULE and t.source_approved
            and fee_key(t.params.get("fee_code", "")) == want]
    live = [t for t in pool if t.status != TermStatus.REJECTED]
    return live or pool


def notice_days_required(terms: Sequence[Term]) -> tuple[int | None, Term | None]:
    t = _pick(terms, TermType.NOTICE_PERIOD)
    if t is None or t.status != TermStatus.VERIFIED:
        return None, None
    return int(t.params["days"]), t


def applies_from(term: Term, notice: int | None) -> date:
    """The first purchase date a schedule can price: its effective_from, pushed to noticed_on + notice days when the
    notice was short. A term with neither date applies from the start."""
    start = term.effective_from or date.min
    if term.noticed_on is not None and notice is not None:
        start = max(start, term.noticed_on + timedelta(days=notice))
    return start


def _dec(value) -> Decimal | None:
    return None if value is None or value == "" else Decimal(str(value))


def _line_rate(term: Term, line: FeeLine) -> Decimal | None:
    tiers = term.params.get("tiers") or []
    if not tiers:
        return _dec(term.params.get("rate"))
    if line.days is None:
        return None
    for tier in tiers:
        lo, hi = int(tier["from_days"]), tier.get("to_days")
        if lo <= line.days and (hi is None or line.days <= int(hi)):
            return Decimal(str(tier["rate"]))
    return Decimal(0)  # outside every tier: no fee


def _fee_label(term: Term) -> str:
    return str(term.params.get("fee_code") or "fee")


def _pct(rate: Decimal) -> str:
    return f"{rate.normalize():f}%"


def _fee_schedule(charge: Charge, schedules: list[Term], terms: Sequence[Term], fees: FeeData) -> Allowance:
    code = fees.codes.get(charge.code, charge.code)
    if not schedules:
        return _missing(charge, f"a fee_schedule term for {code}", f"The deal states no fee schedule for {code}.")
    lines = sorted((ln for ln in fees.lines if ln.deduction_ref.strip() == charge.ref.strip()),
                   key=lambda ln: (ln.on, ln.group, ln.description))
    if not lines:
        return _missing(charge, f"the backup for {charge.ref}", f"No backup lines for {charge.ref}.")
    notice, notice_t = notice_days_required(terms)
    used: list[Term] = []
    held: list[Term] = []
    steps: list[str] = []
    groups: dict[tuple, list[tuple[FeeLine, Term]]] = {}
    unproven: list[str] = []
    no_days: list[str] = []
    for i, ln in enumerate(lines):
        in_force = [(applies_from(t, notice), n, t) for n, t in enumerate(schedules) if applies_from(t, notice) <= ln.on]
        if not in_force:
            return _missing(charge, f"a {code} fee schedule in effect on {_day(ln.on)}",
                            f"No {code} fee schedule was in effect on {_day(ln.on)}.", terms=tuple(schedules))
        term = max(in_force, key=lambda x: (x[0], x[1]))[2]
        for t in schedules:  # its stated date has passed but its notice hasn't run: it can't price this line yet
            if t is not term and t not in held and (t.effective_from or date.min) <= ln.on < applies_from(t, notice):
                held.append(t)
        if term not in used:
            used.append(term)
        if term.params.get("requires_proof") and ln.proof_doc not in fees.proof_docs:
            unproven.append(ln.group or ln.description or ln.deduction_ref)
        if term.params.get("tiers") and ln.days is None:
            no_days.append(ln.group or ln.description or ln.deduction_ref)
        per = term.params.get("per") or "incident"
        key = (f"{ln.on:%Y-%m}",) if per == "month" else (ln.group or f"line {i + 1}",)
        groups.setdefault((id(term),) + key, []).append((ln, term))
    if no_days:
        return _missing(charge, f"the days for {', '.join(no_days)}",
                        f"The {code} fee is tiered by days and the backup doesn't give them.", terms=tuple(used))

    for t in held:
        steps.append(f"A {_fee_label(t)} change set to start {_day(t.effective_from or date.min)} was noticed "
                     f"{_day(t.noticed_on)}; with {notice} days' notice it applies only from "
                     f"{_day(applies_from(t, notice))}, so earlier purchases keep the earlier schedule.")
    fee_total = Decimal(0)
    for (_, *key), members in groups.items():
        term = members[0][1]
        basis = term.params.get("basis")
        lo, hi = _dec(term.params.get("min")), _dec(term.params.get("max"))
        label = key[0]
        if basis in ("per_po", "flat"):
            rate = _dec(term.params.get("rate")) or Decimal(0)
            raw = rate
            how = f"{usd(rate)} {'per PO' if basis == 'per_po' else 'flat'}"
        else:
            raw, parts = Decimal(0), []
            for ln, _t in members:
                rate = _line_rate(term, ln)
                if basis == "percent":
                    raw += rate * Decimal(str(ln.base_amount)) / 100
                    parts.append(f"{_pct(rate)} of ${money(ln.base_amount):,}")
                elif basis == "per_unit":
                    raw += rate * ln.units
                    parts.append(f"{ln.units:,} units x {usd(rate)}")
                elif basis == "per_carton":
                    raw += rate * ln.cartons
                    parts.append(f"{ln.cartons:,} cartons x {usd(rate)}")
                else:
                    return _missing(charge, f"a known basis for the {code} fee",
                                    f"The {code} fee schedule has basis {basis!r}, which the engine doesn't price.",
                                    terms=tuple(used))
                if ln.days is not None and term.params.get("tiers"):
                    parts[-1] += f" ({ln.days} days)"
            how = " + ".join(parts)
        raw = money(raw)
        fee = raw
        clamp = ""
        if lo is not None and Decimal(0) < fee < lo:
            fee, clamp = money(lo), f"; minimum ${money(lo):,}"
        if hi is not None and fee > hi:
            fee, clamp = money(hi), f"; maximum ${money(hi):,}"
        fee_total += fee
        steps.append(f"Fee {label}: {how} = ${raw:,}{clamp} -> ${fee:,}.")
    pass_through = money(sum((Decimal(str(ln.pass_through)) for ln in lines), Decimal(0)))
    if pass_through:
        steps.append(f"Cost passed through at cost: ${pass_through:,}.")
    allowed = fee_total + pass_through
    steps.append(f"Allowed: ${allowed:,}; taken ${money(charge.amount):,}.")
    facts = {"fee_code": code, "fee_amount": money(fee_total), "pass_through": pass_through,
             "line_refs": tuple(ln.group or ln.description for ln in lines)}
    missing: tuple[str, ...] = ()
    if unproven:
        facts["missing_proof"] = tuple(unproven)
        missing = (f"the backup document for {', '.join(unproven)}",)
        steps.append(f"The deal requires backup for this fee; none came for {', '.join(unproven)}.")
    if held:
        facts["change_before_notice"] = tuple(t.id for t in held)
    used_terms = tuple(used) + tuple(held) + ((notice_t,) if held and notice_t else ())
    return _result(charge, allowed, terms=used_terms, facts=facts, steps=tuple(steps), missing=missing,
                   firm=pass_through)


# --- Dispute window ----------------------------------------------------------------------------------------------
# A dispute_window term {days, from: deduction|invoice}: the dispute is due within `days` of the deduction (the
# charge's deducted_on) or of the invoice (FeeData.invoice_date), counted to FeeData.as_of, the day it would be filed.
# The engine only records the facts; the gate decides (gate.py rows 10 and 7).

def _dispute_window(a: Allowance, charge: Charge, terms: Sequence[Term], fees: FeeData) -> Allowance:
    t = _pick(terms, TermType.DISPUTE_WINDOW)
    if t is None or t.status != TermStatus.VERIFIED or fees.as_of is None:
        return a
    start = fees.invoice_date if t.params.get("from") == "invoice" else charge.deducted_on
    if start is None:
        return a
    days = int(t.params["days"])
    closes = start + timedelta(days=days)
    left = (closes - fees.as_of).days
    what = "invoice" if t.params.get("from") == "invoice" else "deduction"
    step = (f"Disputes are due within {days} days of the {what} ({_day(start)}, {start.year}): the window "
            + (f"closed {_day(closes)}, {closes.year}, {-left} days ago." if left < 0 else
               f"closes {_day(closes)}, {closes.year}, in {left} days."))
    facts = {**a.facts, "dispute_window_closes": closes, "dispute_days_left": left, "past_dispute_window": left < 0}
    return Allowance(a.charge_id, a.taken, a.allowed, a.delta, a.covered_units, a.terms + (t,), a.missing, facts,
                     a.steps + (step,), a.firm)
