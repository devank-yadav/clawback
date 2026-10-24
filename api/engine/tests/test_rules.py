from dataclasses import replace
from decimal import Decimal

import pytest

from api.engine.policy import load_policy
from api.engine.rules import evaluate, find_rule, match_rule, parse_condition
from api.engine.tests import scenario as s
from api.engine.types import DecisionKind, RuleMatch, TermType

FEE, FLOOR = TermType.FEE_DISCRETION, Decimal("0.85")


def test_exact_match_on_term_type_and_counterparty():
    r = s.rule_1()
    assert find_rule([r], TermType.FEE_DISCRETION, "northmart ") is r
    assert find_rule([r], TermType.FEE_DISCRETION, "Southmart") is None
    assert find_rule([r], TermType.PROMO_RATE, "Northmart") is None


@pytest.mark.parametrize("status", ["pending", "undone"])
def test_only_active_rules_match(status):
    assert find_rule([s.rule_1(status)], TermType.FEE_DISCRETION, "Northmart") is None


def test_first_active_rule_wins():
    older, newer = replace(s.rule_1(), id="rule-0", status="undone"), s.rule_1()
    assert find_rule([older, newer], TermType.FEE_DISCRETION, "Northmart") is newer


def match(rule_id, similarity):
    return RuleMatch(rule_id, Decimal(similarity))


@pytest.mark.parametrize("similarity, matched", [("0.91", True), ("0.85", True), ("0.84", False), ("0.70", False)])
def test_moss_match_needs_the_similarity_floor(similarity, matched):
    r = s.rule_1()
    expected = (r, Decimal(similarity)) if matched else None
    assert match_rule([r], [match("rule-1", similarity)], FEE, "Northmart", FLOOR) == expected


def test_moss_match_needs_the_same_term_type_and_counterparty():
    r = s.rule_1()
    assert match_rule([r], [match("rule-1", "0.99")], FEE, "Southmart", FLOOR) is None
    assert match_rule([r], [match("rule-1", "0.99")], TermType.PROMO_RATE, "Northmart", FLOOR) is None
    assert match_rule([r], [match("rule-1", "0.99")], FEE, " northmart", FLOOR) == (r, Decimal("0.99"))


def test_moss_match_ignores_unknown_and_inactive_rules():
    assert match_rule([s.rule_1()], [match("rule-9", "0.99")], FEE, "Northmart", FLOOR) is None
    assert match_rule([s.rule_1("undone")], [match("rule-1", "0.99")], FEE, "Northmart", FLOOR) is None
    assert match_rule([s.rule_1()], [], FEE, "Northmart", FLOOR) is None


def test_moss_picks_the_closer_wording_where_the_exact_match_takes_the_first():
    display = s.rule_1()
    slotting = replace(display, id="rule-2", label="Rule #2", pattern_text="Slotting fee charged at Northmart's discretion")
    matches = [match("rule-1", "0.86"), match("rule-2", "0.93")]
    assert match_rule([display, slotting], matches, FEE, "Northmart", FLOOR) == (slotting, Decimal("0.93"))
    assert find_rule([display, slotting], FEE, "Northmart") is display


@pytest.mark.parametrize("days, expected", [(20, "accept"), (18, "accept"), (14, "accept"), (13, "dispute"), (5, "dispute")])
def test_rule_1_notice_days(days, expected):
    assert evaluate(s.rule_1(), {"notice_days": days}) == DecisionKind(expected)


def test_unknown_fact_takes_else_decision():
    assert evaluate(s.rule_1(), {}) == DecisionKind.DISPUTE


@pytest.mark.parametrize("bad", ["notice_days >= fourteen", "__import__('os')", "notice_days => 14", ""])
def test_bad_conditions_raise(bad):
    with pytest.raises(ValueError):
        parse_condition(bad)


def test_policy_loads_as_decimals():
    p = load_policy()
    assert p.auto_dispute_limit == Decimal("5000")
    assert p.approval_over == Decimal("1000")
    assert p.auto_post_limit is None
    assert p.confidence_floor == Decimal("0.90")
    assert p.match_tolerance == Decimal("1.00")
    assert p.rule_match_similarity == Decimal("0.85")
    assert "at its discretion" in p.discretion_words
    assert "jordan@peakbar-broker.example" in p.approved_amendment_senders
