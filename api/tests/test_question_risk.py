"""The admin's question carries a severity (api/engine/question_risk.py): level from the amount, raised a step by a
discretionary clause with no notice period, a closing dispute window or readers who disagree; kind by fixed rules;
a one-sentence reason and the details. Plain code, so the recordings and demo numbers don't change."""

from datetime import date
from decimal import Decimal as D

import pytest

from api import pipeline
from api.engine import question_risk as qr
from api.stubs import fixtures
from api.tests.test_pipeline import ScenarioClaude

T = qr.Thresholds()


def facts(**kw):
    base = dict(amount=D("100"), payment=D("41350"), what="display fee", distributor="Northmart")
    return qr.Facts(**{**base, **kw})


@pytest.mark.parametrize("amount, payment, expected", [
    (D("1000"), D("100000"), "high"),     # at the dollar line
    (D("999"), D("100000"), "medium"),
    (D("300"), D("5000"), "high"),        # 6% of the payment
    (D("250"), D("100000"), "medium"),
    (D("249.99"), D("100000"), "low"),
    (D("249.99"), None, "low"),           # no payment: dollars only
])
def test_level_from_the_amount(amount, payment, expected):
    assert qr.level(facts(amount=amount, payment=payment), T) == (expected, ())


def test_each_raiser_lifts_one_step_and_never_past_high():
    low = dict(amount=D("100"), payment=D("100000"))
    assert qr.level(facts(**low, discretionary=True), T)[0] == "medium"  # no notice period in days
    assert qr.level(facts(**low, discretionary=True, notice_period_days=14), T)[0] == "low"
    assert qr.level(facts(**low, days_left=14), T)[0] == "medium"
    assert qr.level(facts(**low, days_left=15), T)[0] == "low"
    assert qr.level(facts(**low, readers_disagree=True), T)[0] == "medium"
    lv, why = qr.level(facts(**low, discretionary=True, days_left=3, readers_disagree=True), T)
    assert lv == "medium" and len(why) == 3  # one step, however many hold
    assert qr.level(facts(amount=D("5000"), payment=D("100000"), readers_disagree=True), T)[0] == "high"


def test_kind_rules_in_order():
    assert qr.kind(facts(readers_disagree=True, days_left=3, term_type="fee_discretion"), T) == "legal"
    assert qr.kind(facts(days_left=3, term_type="fee_discretion", discretionary=True), T) == "deadline"
    assert qr.kind(facts(term_type="fee_discretion", discretionary=True), T) == "relationship"
    assert qr.kind(facts(term_type="promo_rate", discretionary=True), T) == "legal"
    assert qr.kind(facts(term_type="notice_period"), T) == "legal"
    assert qr.kind(facts(term_type="promo_rate"), T) == "financial"


def test_reasons_are_one_sentence_of_25_words_or_fewer():
    long_quote = "Northmart may at its discretion " + "charge a very long fee description " * 10
    for f in (facts(quote=long_quote, clause_ref="§5.4", term_type="fee_discretion", discretionary=True,
                    rule_label="Rule #1"),
              facts(readers_disagree=True, clause_ref="§3.2", term_type="unit_cap"),
              facts(days_left=4, file_by=date(2026, 5, 1)),
              facts(amount=D("80"), term_type="promo_rate")):
        r = qr.assess(f, T)
        assert len(r.reason.split()) <= 25 and r.reason.endswith(".") and r.reason.count(". ") == 0, r.reason
    assert qr.assess(facts(days_left=4, file_by=date(2026, 5, 1)), T).reason == \
        "$100 display fee: the dispute window closes in 4 days on May 1; decide before then."


def test_the_northmart_c6_question_is_high_relationship_with_its_details():
    pipeline.reset()
    run = pipeline.start("march", ScenarioClaude(), background=False)
    (q,) = run.questions.values()
    assert q.charge_id == "C6"
    assert (q.risk.level, q.risk.kind) == ("high", "relationship")  # $1,200 is over the $1,000 line
    assert q.risk.reason == ("$1,200 display fee rests on §5.4 'at its discretion' with written notice; your answer "
                             "becomes a rule for every future fee.")
    details = {d.label: d.value for d in q.details}
    assert details["Clause"].startswith('§5.4 "Northmart may charge a display fee')
    assert (details["Notice date"], details["Days of notice"]) == ("Mar 11, 2026", "20 days")
    assert details["Amount"] == "$1,200.00 of a $41,350.00 payment"
    assert details["What your answer does"].startswith("Becomes Rule #1")
    event = next(e for e in run.events if e.type == "question")
    assert event.data.risk == q.risk  # the owner question event carries it
    # The recorded fake run the screens use says the same as the live one.
    fixture_q = next(e.data for e in fixtures.march_run().events if e.type == "question")
    assert fixture_q.risk == q.risk and fixture_q.details == q.details
    pipeline.reset()


def test_thresholds_come_from_policy_yaml():
    t = qr.load_thresholds()
    assert (t.high_usd, t.high_pct_of_payment, t.medium_usd, t.deadline_days) == (D("1000"), D("5"), D("250"), 14)
