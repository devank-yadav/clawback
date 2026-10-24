from decimal import Decimal

from api.engine.gate import decide
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy
from api.engine.tests import scenario as s
from api.engine.totals import meters, remittance_short, taken, total_of


def test_march_meters_before_and_after_the_owner_answers():
    charges = s.march_charges()
    policy = load_policy()
    first = {cid: decide(c, compute_allowed(c, s.spring_terms(), s.store_sales(), s.prior_payments()),
                         s.strong_finding(cid), policy) for cid, c in charges.items()}
    m = meters(charges, first)
    assert (m["taken"], m["disputed"], m["accepted"], m["waiting"], m["undecided"]) == (
        Decimal("6850.00"), Decimal("4120.00"), Decimal("1530.00"), Decimal("1200.00"), Decimal("0.00"))
    after = {cid: decide(c, compute_allowed(c, s.spring_terms(), s.store_sales(), s.prior_payments()),
                         s.strong_finding(cid), policy, [s.rule_1()]) for cid, c in charges.items()}
    m = meters(charges, after)
    assert (m["disputed"], m["accepted"], m["waiting"]) == (Decimal("4120.00"), Decimal("2730.00"), Decimal("0.00"))


def test_partial_meters_count_the_rest_as_undecided():
    charges = s.march_charges()
    assert meters(charges, {})["undecided"] == taken(charges.values()) == Decimal("6850.00")


def test_remittance_and_totals():
    assert remittance_short(Decimal("48200"), Decimal("41350")) == Decimal("6850.00")
    assert total_of([Decimal("600"), Decimal("980"), Decimal("1540"), Decimal("1000")]) == Decimal("4120.00")
