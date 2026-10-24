"""The words: money is formatted, never computed; approvals are described, never offered."""

from decimal import Decimal

from fetch_agent import text as say
from fetch_agent.client import ClawbackError
from fetch_agent.models import Approval, AnswerResponse, Summary
from fetch_agent.tests.conftest import load


def test_money_formats_the_apis_number_as_is():
    assert say.money(Decimal("4120.0")) == "$4,120"
    assert say.money(Decimal("0")) == "$0"
    assert say.money(Decimal("12.5")) == "$12.50"
    assert say.money(Decimal("41350.25")) == "$41,350.25"


def test_owner_approvals_point_to_the_inbox():
    a = Approval(id="AP-9", kind="dispute_over_limit", amount=Decimal("6200"), approver_role="owner",
                 status="pending", text="Approve filing D-0418 for $6,200?")
    assert say._approval(a) == ("**Waiting on you:** a $6,200 dispute needs your OK before Clawback files it. "
                                "Approve it in the Clawback inbox; this chat can't approve money.")
    other = a.model_copy(update={"kind": "closed_period", "approver_role": "controller", "text": "Post to March?"})
    assert say._approval(other) == "**Waiting on Sam, your bookkeeper:** Post to March? This chat can't approve money."


def test_one_charge_is_singular():
    s = Summary.model_validate(load("summary-question.json"))
    s.open_disputes[0].lines = s.open_disputes[0].lines[:1]
    assert "over 1 charge (filed" in say.summary_text(s)


def test_undo_text_needs_an_undone_rule():
    assert say.undo_text(AnswerResponse.model_validate(load("answer-rule.json"))) == "There's no saved rule to undo."


def test_error_text_for_other_statuses():
    assert say.error_text(ClawbackError("x", 500)) == "Clawback answered with an error (500). Try again in a minute."
