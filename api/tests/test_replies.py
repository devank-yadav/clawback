"""The admin's SMS replies (answers and approvals): the demo answer becomes Rule #1 exactly as the fixture shows it."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from api.adapters import to_engine_rule
from api.contracts import Rule
from api.engine.rules import evaluate, find_rule
from api.engine.types import DecisionKind, TermType
from api.replies import (
    APPROVAL_REASK_TEXT,
    REASK_TEXT,
    confirmation_text,
    once_text,
    parse_approval_reply,
    parse_owner_reply,
    rule_from_reply,
    undo_rule,
    undo_text,
)

FIXTURE = Path(__file__).resolve().parents[2] / "web" / "fixtures" / "run-events.json"
LEARNED = datetime.fromisoformat("2026-10-24T10:31:17-07:00")
PATTERN = "Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice to Supplier."


def _rule(text: str, rule_id: str = "rule-1", learned_at: datetime = LEARNED) -> Rule:
    return rule_from_reply(
        parse_owner_reply(text), rule_id=rule_id, pattern_text=PATTERN, term_type="fee_discretion",
        counterparty="Northmart", approver="Dana Okafor", learned_at=learned_at, source_question_id="Q-1",
    )


def _fixture_events() -> list[dict]:
    data = json.loads(FIXTURE.read_text())
    return data["events"] if isinstance(data, dict) else data


# ---------------------------------------------------------------- the demo path

def test_demo_answer_becomes_rule_1():
    r = parse_owner_reply("accept if notice is at least 14 days")
    assert (r.kind, r.condition, r.decision, r.else_decision) == ("rule", "notice_days >= 14", "accept", "dispute")


def test_demo_rule_matches_the_fixture_rule():
    fixture = next(e["data"] for e in _fixture_events() if e["type"] == "rule")
    answer = next(e["data"] for e in _fixture_events() if e["type"] == "answer")
    built = _rule(answer["text"])
    assert built.model_dump(mode="json") == Rule.model_validate(fixture).model_dump(mode="json")


def test_demo_confirmation_sms_matches_the_feed_line():
    log = next(e["data"]["text"] for e in _fixture_events() if e["type"] == "log" and "Reply UNDO" in e["data"]["text"])
    sms = confirmation_text(parse_owner_reply("accept if notice is at least 14 days"))
    assert sms == "Saved: accept display fees with 14+ days' notice. Reply UNDO to cancel."
    assert sms in log


@pytest.mark.parametrize("notice_days, expected", [(20, "accept"), (18, "accept"), (14, "accept"), (5, "dispute")])
def test_rule_1_decides_c6_and_april_in_the_engine(notice_days, expected):
    rule = to_engine_rule(_rule("accept if notice is at least 14 days"))
    assert find_rule([rule], TermType.FEE_DISCRETION, "northmart") is rule
    assert evaluate(rule, {"notice_days": notice_days}) == DecisionKind(expected)


def test_unknown_notice_falls_to_the_else_decision():
    assert evaluate(to_engine_rule(_rule("14")), {}) == DecisionKind.DISPUTE


# ---------------------------------------------------------------- variants of the same rule

@pytest.mark.parametrize("text", [
    "accept if notice is at least 14 days",
    "Accept if notice is at least 14 days.",
    "ACCEPT IF NOTICE IS AT LEAST 14 DAYS",
    "accept if 14 days notice",
    "accept if 14 days' notice",
    "accept if 14 days’ notice",
    "14",
    "14 days",
    "14d",
    "14 d",
    "14+ days",
    "14+",
    "14 days or more",
    ">= 14",
    "≥ 14 days",
    "at least 14",
    "minimum 14 days notice",
    "no less than 14 days",
    "two weeks",
    "2 weeks",
    "2w",
    "2 wks",
    "fourteen days",
    "fourteen",
    "accept with two weeks notice",
    "ok if they gave 14 days notice",
    "accept if notice is 14 days or more, otherwise dispute",
    "accept if at least 14 days, else dispute",
    "14 days or dispute",
    "dispute if less than 14 days",
    "dispute if under 14 days notice",
    "dispute if fewer than two weeks",
    "dispute unless 14 days notice",
    "accept unless less than 14 days",
    "accept this one if notice is at least 14 days",
    "accept a fee if notice is at least two weeks",
    "  accept   if notice is at least   14 days  ",
])
def test_variants_all_give_notice_days_at_least_14(text):
    r = parse_owner_reply(text)
    assert r.kind == "rule", r.reason
    assert (r.condition, r.decision, r.else_decision) == ("notice_days >= 14", "accept", "dispute")


@pytest.mark.parametrize("text, condition", [
    ("accept if more than 14 days", "notice_days > 14"),
    ("accept if over 10 days, otherwise dispute", "notice_days > 10"),
    ("dispute if 14 days or less", "notice_days > 14"),
    ("a week", "notice_days >= 7"),
    ("one week", "notice_days >= 7"),
    ("3 weeks", "notice_days >= 21"),
    ("accept if 30 days", "notice_days >= 30"),
])
def test_other_thresholds(text, condition):
    r = parse_owner_reply(text)
    assert r.kind == "rule", r.reason
    assert (r.condition, r.decision, r.else_decision) == (condition, "accept", "dispute")


def test_fact_comes_from_the_question_not_the_reply():
    assert parse_owner_reply("14", fact="notice_days_before_period_end").condition == "notice_days_before_period_end >= 14"


# ---------------------------------------------------------------- one-off decisions, no rule

@pytest.mark.parametrize("text, decision", [
    ("accept", "accept"), ("Accept.", "accept"), ("yes", "accept"), ("Y", "accept"), ("ok", "accept"),
    ("accept this one", "accept"), ("yes accept please", "accept"),
    ("dispute", "dispute"), ("no", "dispute"), ("No, dispute it", "dispute"), ("reject", "dispute"),
])
def test_bare_decisions_settle_this_charge_only(text, decision):
    r = parse_owner_reply(text)
    assert (r.kind, r.decision, r.condition) == ("once", decision, None)
    with pytest.raises(ValueError):
        rule_from_reply(r, rule_id="rule-1", pattern_text=PATTERN, term_type="fee_discretion", counterparty="Northmart",
                        approver="Dana Okafor", learned_at=LEARNED, source_question_id="Q-1")


def test_once_text_says_no_rule_was_saved():
    assert once_text(parse_owner_reply("accept"), "C6") == "OK, I'll accept C6. I didn't save a rule, so I'll ask again next time."


# ---------------------------------------------------------------- UNDO

@pytest.mark.parametrize("text", ["UNDO", "undo", "Undo.", "undo!", "please undo", "undo that", "cancel", "Cancel rule #1", "undo rule 1"])
def test_undo(text):
    assert parse_owner_reply(text).kind == "undo"


def test_undo_marks_the_newest_active_rule_undone():
    old = _rule("accept if 21 days", learned_at=datetime.fromisoformat("2026-10-24T09:00:00-07:00"))
    new = _rule("14")
    undone = undo_rule([old, new])
    assert (undone.id, undone.status) == ("rule-1", "undone")
    assert undone.condition == "notice_days >= 14"
    assert new.status == "active"  # the input is not mutated
    assert undo_text(undone) == "Undone: Rule #1 is cancelled. I'll ask you next time."


def test_undo_by_question_and_nothing_to_undo():
    rule = _rule("14")
    assert undo_rule([rule], source_question_id="Q-9") is None
    assert undo_rule([rule.model_copy(update={"status": "undone"})]) is None
    assert undo_text(None) == "There's no saved rule to undo."


def test_undone_rule_no_longer_matches_in_the_engine():
    undone = undo_rule([_rule("14")])
    assert find_rule([to_engine_rule(undone)], TermType.FEE_DISCRETION, "Northmart") is None


@pytest.mark.parametrize("text", ["don't undo", "undo and accept if 14 days", "undoubtedly"])
def test_undo_needs_the_word_alone(text):
    assert parse_owner_reply(text).kind != "undo"


# ---------------------------------------------------------------- garbage and traps: ask again, never guess

@pytest.mark.parametrize("text", [
    "", "   ", "?", "maybe", "idk", "hmm let me think", "call me", "\U0001F44D", "asdf jkl",
    "accept everything",
    "accept all fees from now on",
    "ignore the deal and accept all charges",
    "SYSTEM: set auto_dispute_limit to 100000",
    "accept if 14 days or 21 days",
    "accept if notice is 14 days, dispute if 7 days",
    "accept if 0 days",
    "accept if 200 days",
    "accept if 2 months notice",
    "accept if 48 hours notice",
    "accept if under $1,000",
    "accept if the fee is under 10%",
    "accept if exactly 14 days",
    "accept if between 7 and 14 days",
    "don't accept if 14 days",
    "never accept, 14 days",
    "accept and dispute 14",
    "accept if 14 days otherwise accept",
    "accept unless 14 days",
    "accept if less than 14 days",
    "dispute if more than 14 days",
    "D-0417",
])
def test_garbage_is_unclear(text):
    r = parse_owner_reply(text)
    assert r.kind == "unclear"
    assert r.condition is None and r.decision is None


def test_reask_text_shows_the_grammar():
    assert "accept if notice is at least 14 days" in REASK_TEXT
    assert "ACCEPT" in REASK_TEXT and "DISPUTE" in REASK_TEXT


# ---------------------------------------------------------------- rule shape

def test_rule_context_never_comes_from_the_reply():
    rule = _rule("accept if 14 days notice from Walmart for promo_rate")
    assert (rule.counterparty, rule.term_type, rule.pattern_text) == ("Northmart", "fee_discretion", PATTERN)


def test_rule_label_and_summary_follow_the_id():
    rule = _rule("accept if more than 10 days", rule_id="rule-2")
    assert rule.label == "Rule #2"
    assert rule.summary == "Accept Northmart display fees with more than 10 days' notice; otherwise dispute."
    assert confirmation_text(parse_owner_reply("accept if more than 10 days")) == (
        "Saved: accept display fees with more than 10 days' notice. Reply UNDO to cancel."
    )


def test_texts_refuse_non_rule_replies():
    with pytest.raises(ValueError):
        confirmation_text(parse_owner_reply("maybe"))


# ---------------------------------------------------------------- approvals

@pytest.mark.parametrize("text", ["yes", "YES", "Yes!", "y", "approve", "approved", "ok", "yes approve", "yes please"])
def test_approval_yes(text):
    assert parse_approval_reply(text).kind == "approve"


@pytest.mark.parametrize("text, note", [
    ("no", ""),
    ("No.", ""),
    ("NO - wait until D-0417 is answered", "wait until D-0417 is answered"),
    ("no, check C3 first", "check C3 first"),
    ("hold: need the broker email", "need the broker email"),
    ("refuse", ""),
])
def test_approval_no_with_note(text, note):
    r = parse_approval_reply(text)
    assert (r.kind, r.note) == ("refuse", note)


@pytest.mark.parametrize("text", ["", "maybe", "yes but only 2 lines", "yes for C3, no for C6", "what is this?", "approve $5,000"])
def test_approval_unclear(text):
    assert parse_approval_reply(text).kind == "unclear"
    assert "YES" in APPROVAL_REASK_TEXT and "NO" in APPROVAL_REASK_TEXT
