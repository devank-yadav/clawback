from dataclasses import replace
from decimal import Decimal

import pytest

from api.engine.policy import load_policy
from api.engine.rules import evaluate, find_rule, parse_condition
from api.engine.tests import scenario as s
from api.engine.types import DecisionKind, TermType


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
    assert p.controller_approval_over == Decimal("1000")
    assert p.confidence_floor == Decimal("0.90")
    assert p.match_tolerance == Decimal("1.00")
    assert "at its discretion" in p.discretion_words
    assert "jordan@peakbar-broker.example" in p.approved_amendment_senders
