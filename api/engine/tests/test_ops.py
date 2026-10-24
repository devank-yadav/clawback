"""Operations charges: shortage (SH), price mismatch (PR) and spoilage (SP), checked against delivery records, the
agreed price list and ops terms, then decided by the gate's existing rows. Numbers are worked by hand."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from api.engine.allowed import compute_allowed, usd
from api.engine.gate import decide
from api.engine.policy import load_policy
from api.engine.tests import scenario as s
from api.engine.types import (
    AgreedPrice, Charge, DecisionKind, Delivery, Finding, OpsData, OpsTerm, TermStatus,
)

POLICY = load_policy()
K = DecisionKind
D = date
ORIG, CHOC = s.ORIG, s.CHOC
SPOILS_QUOTE = "Supplier allows spoils and unsaleables of up to 1.0% of the amount invoiced each month."


def deliveries() -> tuple[Delivery, ...]:
    return (
        Delivery("L-1001", ORIG, 1200, 1200, Decimal("2.50"), "J. Ortiz", D(2026, 3, 4)),     # nothing short
        Delivery("L-1002", CHOC, 600, 552, Decimal("3.00"), "J. Ortiz", D(2026, 3, 6)),       # 48 short
        Delivery("L-2001", ORIG, 2000, 2000, Decimal("2.40"), "M. Chen", D(2026, 3, 9)),      # invoiced at the price
        Delivery("L-2002", CHOC, 1000, 1000, Decimal("2.60"), "M. Chen", D(2026, 3, 12)),     # invoiced $0.15 over
        # Spoilage month: April, $86,400 invoiced over three lines.
        Delivery("L-3001", ORIG, 12000, 11990, Decimal("2.40"), "J. Ortiz", D(2026, 4, 6)),   # $28,800
        Delivery("L-3002", CHOC, 10000, 10000, Decimal("3.00"), "J. Ortiz", D(2026, 4, 14)),  # $30,000
        Delivery("L-3003", ORIG, 11500, 11500, Decimal("2.40"), "M. Chen", D(2026, 4, 27)),   # $27,600
        Delivery("L-3004", ORIG, 9000, 9000, Decimal("2.40"), "M. Chen", D(2026, 5, 2)),      # May: not counted
    )


def prices() -> tuple[AgreedPrice, ...]:
    return (
        AgreedPrice(ORIG, Decimal("2.40"), D(2026, 1, 1), D(2026, 12, 31), "spring-promo"),
        AgreedPrice(CHOC, Decimal("2.55"), D(2026, 1, 1), D(2026, 2, 28), "spring-promo"),
        AgreedPrice(CHOC, Decimal("2.45"), D(2026, 3, 1), None, "spring-promo"),  # lowered Mar 1, still in effect
    )


def ops(**changes) -> OpsData:
    base = OpsData(deliveries(), prices(), (OpsTerm("spoils_allowance_pct", "1.0", "spring-promo", SPOILS_QUOTE),))
    return replace(base, **changes)


def charge(cid, code, units, rate, amount, line_ref=None, start=D(2026, 3, 1), end=D(2026, 3, 31), products=()):
    return Charge(cid, f"NM-{cid}", code, f"{code} charge", products, units, Decimal(rate), Decimal(amount), start, end,
                  line_ref=line_ref)


SH_DISPROVED = charge("S1", "SH", 120, "2.50", "300.00", "L-1001")
SH_CONFIRMED = charge("S2", "SH", 48, "3.00", "144.00", "L-1002")
PR_NO_BASIS = charge("P1", "PR", 2000, "0.20", "400.00", "L-2001")
PR_PARTIAL = charge("P2", "PR", 1000, "0.25", "250.00", "L-2002")
SP_OVER = charge("Z1", "SP", 1, "1296.00", "1296.00", start=D(2026, 4, 1), end=D(2026, 4, 30))
SP_WITHIN = charge("Z2", "SP", 1, "600.00", "600.00", start=D(2026, 4, 1), end=D(2026, 4, 30))


def decided(c: Charge, data: OpsData | None = None, finding: Finding | None = None):
    a = compute_allowed(c, [], ops=ops() if data is None else data)
    return a, decide(c, a, s.strong_finding(c.id) if finding is None else finding, POLICY)


# --- The hand-worked cases ------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "c, allowed, delta, kind, disputed, accepted, row",
    [
        (SH_DISPROVED, "0.00", "300.00", K.DISPUTE, "300.00", "0.00", 7),   # 1,200 shipped, 1,200 received
        (SH_CONFIRMED, "144.00", "0.00", K.ACCEPT, "0.00", "144.00", 5),    # 600 shipped, 552 received: 48 x $3.00
        (PR_NO_BASIS, "0.00", "400.00", K.DISPUTE, "400.00", "0.00", 7),    # invoiced $2.40, agreed $2.40
        (PR_PARTIAL, "150.00", "100.00", K.SPLIT, "100.00", "150.00", 7),   # $2.60 - $2.45 = $0.15 x 1,000
        (SP_OVER, "864.00", "432.00", K.SPLIT, "432.00", "864.00", 7),      # 1.0% of $86,400
        (SP_WITHIN, "600.00", "0.00", K.ACCEPT, "0.00", "600.00", 5),       # $600 is under $864
    ],
    ids=["SH-disproved", "SH-confirmed", "PR-no-basis", "PR-partial", "SP-over", "SP-within"],
)
def test_hand_worked_cases(c, allowed, delta, kind, disputed, accepted, row):
    a, d = decided(c)
    assert (a.allowed, a.delta, a.taken) == (Decimal(allowed), Decimal(delta), c.amount)
    assert not a.missing
    assert (d.kind, d.disputed, d.accepted, d.gate_row) == (kind, Decimal(disputed), Decimal(accepted), row)


def test_shortage_steps_and_facts():
    a = compute_allowed(SH_CONFIRMED, [], ops=ops())
    assert a.steps == (
        "Delivery L-1002: 600 units shipped, 552 received, signed by J. Ortiz on Mar 6.",
        "Claimed 48 units short; the delivery shows 48 short.",
        "48 units x $3.00 = $144.00.",
    )
    assert a.covered_units == 48 and a.facts["short_units"] == 48 and a.facts["line_refs"] == ("L-1002",)


def test_shortage_claims_more_than_the_delivery_shows():
    """120 claimed on a line 48 short: only the 48 are owed."""
    a = compute_allowed(replace(SH_CONFIRMED, units=120, amount=Decimal("360.00")), [], ops=ops())
    assert (a.allowed, a.delta, a.covered_units) == (Decimal("144.00"), Decimal("216.00"), 48)


def test_shortage_received_more_than_shipped_is_not_short():
    over = ops(deliveries=(Delivery("L-1001", ORIG, 1200, 1210, Decimal("2.50"), "J. Ortiz", D(2026, 3, 4)),))
    assert compute_allowed(SH_DISPROVED, [], ops=over).allowed == Decimal("0.00")


def test_price_steps_use_the_price_in_effect_when_received():
    a = compute_allowed(PR_PARTIAL, [], ops=ops())
    assert a.steps == (
        "Delivery L-2002: invoiced at $2.60 a unit, received Mar 12.",
        "Price list: $2.45 a unit for Peak Bar Chocolate from Mar 1.",
        "Invoiced $0.15 a unit above the agreed price; the charge claims $0.25.",
        "1,000 units x $0.15 = $150.00.",
    )
    assert (a.facts["invoiced_price"], a.facts["agreed_price"], a.facts["price_gap"]) == (
        Decimal("2.60"), Decimal("2.45"), Decimal("0.15"))
    # Received in February, the old $2.55 applies: $0.05 over.
    feb = ops(deliveries=(replace(deliveries()[3], received_at=D(2026, 2, 20)),))
    assert compute_allowed(PR_PARTIAL, [], ops=feb).allowed == Decimal("50.00")


def test_price_at_or_below_agreed_allows_nothing():
    a = compute_allowed(PR_NO_BASIS, [], ops=ops())
    assert a.steps[2] == "Invoiced at or below the agreed price; the charge claims $0.20 a unit."
    assert a.steps[3] == "2,000 units x $0.00 = $0.00." and a.covered_units == 0
    under = ops(deliveries=(replace(deliveries()[2], unit_price=Decimal("2.30")),))
    assert compute_allowed(PR_NO_BASIS, [], ops=under).allowed == Decimal("0.00")


def test_price_product_names_match_loosely():
    loose = ops(prices=(AgreedPrice("original", Decimal("2.40"), D(2026, 1, 1)),))
    assert not compute_allowed(PR_NO_BASIS, [], ops=loose).missing


def test_spoilage_steps_count_only_deliveries_in_the_period():
    a = compute_allowed(SP_OVER, [], ops=ops())
    assert a.steps == (
        "Delivery L-3001: 12,000 units shipped x $2.40 = $28,800.00, received Apr 6.",
        "Delivery L-3002: 10,000 units shipped x $3.00 = $30,000.00, received Apr 14.",
        "Delivery L-3003: 11,500 units shipped x $2.40 = $27,600.00, received Apr 27.",
        "Invoiced Apr 1 to Apr 30: $86,400.00.",
        "Spoils allowance 1.0% of $86,400.00 = $864.00.",
        "Claimed $1,296.00; allowed is the smaller: $864.00.",
    )
    assert a.facts["line_refs"] == ("L-3001", "L-3002", "L-3003")
    assert (a.facts["period_invoiced"], a.facts["spoils_allowance"]) == (Decimal("86400.00"), Decimal("864.00"))


def test_spoilage_percent_written_with_a_sign():
    pct = ops(terms=(OpsTerm("spoils_allowance_pct", "1.0%", "spring-promo", SPOILS_QUOTE),))
    assert compute_allowed(SP_OVER, [], ops=pct).allowed == Decimal("864.00")


def test_unit_prices_finer_than_a_cent():
    assert (usd(Decimal("2.5")), usd(Decimal("2.455")), usd(Decimal("1500"))) == ("$2.50", "$2.455", "$1,500.00")
    fine = ops(deliveries=(Delivery("L-1002", CHOC, 600, 552, Decimal("3.125"), "J. Ortiz", D(2026, 3, 6)),))
    a = compute_allowed(SH_CONFIRMED, [], ops=fine)
    assert a.allowed == Decimal("150.00") and a.steps[2] == "48 units x $3.125 = $150.00."


def test_amounts_are_cents():
    for c in (SH_DISPROVED, SH_CONFIRMED, PR_NO_BASIS, PR_PARTIAL, SP_OVER, SP_WITHIN):
        a = compute_allowed(c, [], ops=ops())
        assert a.allowed.as_tuple().exponent == -2 and a.delta.as_tuple().exponent == -2


# --- Missing data goes to a person ----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "c, data, missing",
    [
        (SH_DISPROVED, None, "delivery records, price list and ops terms"),
        (replace(SH_DISPROVED, line_ref=None), ops(), "the delivery line this charge points to"),
        (replace(SH_DISPROVED, line_ref="L-9999"), ops(), "proof of delivery for L-9999"),
        (replace(PR_PARTIAL, line_ref="L-9999"), ops(), "proof of delivery for L-9999"),
        (PR_PARTIAL, ops(prices=()), "an agreed price for Peak Bar Chocolate on Mar 12"),
        (PR_PARTIAL, ops(deliveries=(replace(deliveries()[3], received_at=None),)), "the received date on L-2002"),
        (SP_OVER, ops(terms=()), "a verified spoils_allowance_pct term"),
        (SP_OVER, ops(terms=(OpsTerm("spoils_allowance_pct", "1.0", "spring-promo", SPOILS_QUOTE,
                                     TermStatus.REJECTED),)), "a verified spoils_allowance_pct term"),
        (SP_OVER, ops(terms=(OpsTerm("spoils_allowance_pct", "one percent", "spring-promo", SPOILS_QUOTE),)),
         "a verified spoils_allowance_pct term"),
        (SP_OVER, ops(terms=(OpsTerm("spoils_allowance_pct", "-1.0", "spring-promo", SPOILS_QUOTE),)),
         "a verified spoils_allowance_pct term"),
        (SP_OVER, ops(deliveries=deliveries()[:4]), "deliveries received Apr 1 to Apr 30"),
    ],
    ids=["no-ops-data", "no-line-ref", "no-pod-row-SH", "no-pod-row-PR", "no-price", "no-received-date", "no-term",
         "term-quote-rejected", "term-not-a-number", "term-negative", "no-deliveries-in-period"],
)
def test_missing_data_asks(c, data, missing):
    a = compute_allowed(c, [], ops=data)
    assert a.missing == (missing,) and a.allowed == Decimal("0.00") and len(a.steps) == 1
    d = decide(c, a, s.strong_finding(c.id), POLICY)
    assert (d.kind, d.gate_row, d.disputed, d.accepted) == (K.ASK, 9, Decimal("0.00"), Decimal("0.00"))


def test_rejected_term_steps_say_why():
    rejected = ops(terms=(OpsTerm("spoils_allowance_pct", "1.0", "spring-promo", SPOILS_QUOTE, TermStatus.REJECTED),))
    assert "isn't found word for word" in compute_allowed(SP_OVER, [], ops=rejected).steps[0]
    # A verified term beside a rejected one is used.
    both = ops(terms=(OpsTerm("spoils_allowance_pct", "2.0", "x", "x", TermStatus.REJECTED), *ops().terms))
    assert compute_allowed(SP_OVER, [], ops=both).allowed == Decimal("864.00")


# --- The gate's other rows still apply ------------------------------------------------------------------------

def test_weak_finding_asks_instead_of_disputing():
    for weak in (replace(s.strong_finding("S1"), confidence=Decimal("0.80")),
                 replace(s.strong_finding("S1"), independent_sources=1),
                 replace(s.strong_finding("S1"), comeback_answered=False)):
        _, d = decided(SH_DISPROVED, finding=weak)
        assert (d.kind, d.gate_row) == (K.ASK, 9)
    d = decide(SH_DISPROVED, compute_allowed(SH_DISPROVED, [], ops=ops()), None, POLICY)  # no finding at all
    assert (d.kind, d.gate_row) == (K.ASK, 9)


def test_overcharge_above_the_auto_dispute_limit_asks():
    big = replace(SH_DISPROVED, units=2400, amount=Decimal("6000.00"))
    _, d = decided(big)
    assert (d.kind, d.gate_row) == (K.ASK, 8)


def test_charged_less_than_allowed_is_accepted_and_never_claimed():
    small = replace(PR_PARTIAL, rate=Decimal("0.10"), amount=Decimal("100.00"))  # $150 allowed
    _, d = decided(small)
    assert (d.kind, d.gate_row, d.accepted) == (K.ACCEPT, 6, Decimal("100.00"))


def test_promo_and_fee_charges_ignore_ops_data():
    """PA and DF behave exactly as without ops data."""
    for c in s.march_charges().values():
        before = compute_allowed(c, s.spring_terms(), s.store_sales(), s.prior_payments())
        assert compute_allowed(c, s.spring_terms(), s.store_sales(), s.prior_payments(), ops=ops()) == before
