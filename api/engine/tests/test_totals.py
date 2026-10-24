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


def test_owner_one_off_decisions():
    from api.engine.gate import decide_by_owner
    from api.engine.types import DecisionKind as K

    policy = load_policy()
    charges = s.march_charges()
    allow = lambda cid: compute_allowed(charges[cid], s.spring_terms(), s.store_sales(), s.prior_payments())  # noqa: E731
    d = decide_by_owner(charges["C6"], allow("C6"), K.ACCEPT, policy, 4, cap_at_deal=True)
    assert (d.kind, d.disputed, d.accepted, d.rule_id) == (K.ACCEPT, Decimal("0.00"), Decimal("1200.00"), None)
    d = decide_by_owner(charges["C6"], allow("C6"), K.DISPUTE, policy, 4, cap_at_deal=True)
    assert (d.kind, d.disputed, d.accepted) == (K.DISPUTE, Decimal("1200.00"), Decimal("0.00"))
    # A discretion fee above the deal's maximum: accepting keeps the excess disputed.
    over = s._charge("C9", "NM-9", "DF", "Display fee", (), 1, Decimal("1800"), Decimal("1800"),
                     s.D(2026, 3, 1), s.D(2026, 3, 31), notice=s.D(2026, 3, 1))
    d = decide_by_owner(over, compute_allowed(over, s.spring_terms()), K.ACCEPT, policy, 4, cap_at_deal=True)
    assert (d.kind, d.disputed, d.accepted) == (K.SPLIT, Decimal("300.00"), Decimal("1500.00"))
    # Not a discretion clause: the owner's ACCEPT accepts the whole charge.
    d = decide_by_owner(charges["C4"], allow("C4"), K.ACCEPT, policy, 9, cap_at_deal=False)
    assert (d.kind, d.disputed, d.accepted) == (K.ACCEPT, Decimal("0.00"), Decimal("1540.00"))
