"""F5 acceptance: C1 to C6 land in the right piles with the demo totals, April uses Rule #1, and one test per gate row."""

from dataclasses import replace
from decimal import Decimal

import pytest

from api.engine.allowed import compute_allowed
from api.engine.gate import concession, decide, needs_controller, summarize, uses_discretion
from api.engine.policy import load_policy
from api.engine.tests import scenario as s
from api.engine.types import Allowance, DecisionKind, Finding, TermStatus

POLICY = load_policy()
K = DecisionKind


def run(charges, terms=None, rules=()):
    terms = s.spring_terms() if terms is None else terms
    out = {}
    for cid, c in charges.items():
        a = compute_allowed(c, terms, s.store_sales(), s.prior_payments())
        out[cid] = decide(c, a, s.strong_finding(cid), POLICY, rules)
    return out


# --- The demo scenario ---------------------------------------------------------------------------------------

EXPECTED_FIRST_PASS = {
    "C1": (K.SPLIT, "600.00", "1200.00", 7),
    "C2": (K.DISPUTE, "980.00", "0.00", 7),
    "C3": (K.ACCEPT, "0.00", "330.00", 5),
    "C4": (K.DISPUTE, "1540.00", "0.00", 7),
    "C5": (K.DISPUTE, "1000.00", "0.00", 7),
    "C6": (K.ASK, "0.00", "0.00", 4),
}


@pytest.mark.parametrize("cid", sorted(EXPECTED_FIRST_PASS))
def test_march_first_pass(cid):
    d = run(s.march_charges())[cid]
    kind, disputed, accepted, row = EXPECTED_FIRST_PASS[cid]
    assert (d.kind, d.disputed, d.accepted, d.gate_row) == (kind, Decimal(disputed), Decimal(accepted), row)


def test_first_pass_asks_exactly_one_question():
    t = summarize(run(s.march_charges()).values())
    assert t.questions == 1
    assert t.disputed == Decimal("4120.00")
    assert t.accepted == Decimal("1530.00")  # everything but C6, which waits on the owner


def test_owner_answer_turns_c6_into_accept_and_hits_demo_totals():
    decisions = run(s.march_charges(), rules=[s.rule_1()])
    c6 = decisions["C6"]
    assert (c6.kind, c6.accepted, c6.gate_row, c6.rule_id) == (K.ACCEPT, Decimal("1200.00"), 3, "rule-1")
    t = summarize(decisions.values())
    assert (t.disputed, t.accepted, t.questions, t.skipped) == (Decimal("4120.00"), Decimal("2730.00"), 0, 0)
    assert t.disputed + t.accepted == Decimal("6850.00")


def test_credit_memo_needs_controller():
    assert needs_controller(Decimal("2730.00"), POLICY)
    assert not needs_controller(Decimal("1000.00"), POLICY)


def test_april_decided_by_rule_1_with_no_questions():
    decisions = run(s.april_charges(), rules=[s.rule_1()])
    a1, a2 = decisions["A1"], decisions["A2"]
    assert (a1.kind, a1.accepted, a1.disputed, a1.rule_id) == (K.ACCEPT, Decimal("1200.00"), Decimal("0.00"), "rule-1")
    assert (a2.kind, a2.disputed, a2.accepted, a2.rule_id) == (K.DISPUTE, Decimal("800.00"), Decimal("0.00"), "rule-1")
    assert summarize(decisions.values()).questions == 0


def test_april_without_rule_asks_twice():
    assert summarize(run(s.april_charges()).values()).questions == 2


def test_amendment_1_concedes_1000_and_keeps_540():
    before = run(s.march_charges())["C4"]
    after = run(s.march_charges(), s.spring_terms() + [s.amendment_1()])["C4"]
    assert (after.kind, after.disputed, after.accepted) == (K.SPLIT, Decimal("540.00"), Decimal("1000.00"))
    assert concession(before, after) == Decimal("1000.00")


def test_northmart_claim_changes_nothing():
    decisions = run(s.march_charges(), s.spring_terms() + [s.northmart_claim()], [s.rule_1()])
    t = summarize(decisions.values())
    assert (t.disputed, t.accepted) == (Decimal("4120.00"), Decimal("2730.00"))


# --- One minimal case per gate row ---------------------------------------------------------------------------

C1 = s.march_charges()["C1"]
C6 = s.march_charges()["C6"]
T = {t.id: t for t in s.spring_terms()}


def allowance(taken, allowed, terms=(T["T-rate"],), facts=None, missing=()):
    taken, allowed = Decimal(taken), Decimal(allowed)
    return Allowance("X", taken, allowed, taken - allowed, terms=terms, facts=facts or {}, missing=missing)


def finding(conf="0.95", sources=2, comeback=True):
    return Finding("X", Decimal(conf), ("e1", "e2"), sources, comeback)


def test_row_1_rejected_quote_skips():
    d = decide(C1, allowance("1800", "1200", (replace(T["T-rate"], status=TermStatus.REJECTED),)), finding(), POLICY)
    assert (d.kind, d.gate_row, d.disputed, d.accepted) == (K.SKIP, 1, 0, 0)


def test_row_2_readers_disagree_asks():
    d = decide(C1, allowance("1800", "1200", (replace(T["T-rate"], status=TermStatus.DISPUTED),)), finding(), POLICY)
    assert (d.kind, d.gate_row) == (K.ASK, 2)


def test_row_3_rule_applies():
    a = allowance("1200", "1200", (T["T-fee"],), {"notice_days": 20})
    d = decide(C6, a, None, POLICY, [s.rule_1()])
    assert (d.kind, d.gate_row, d.rule_id, d.accepted) == (K.ACCEPT, 3, "rule-1", Decimal("1200.00"))


def test_row_3_rule_accepts_fee_only_up_to_the_deal_maximum():
    a = allowance("2000", "1500", (T["T-fee"],), {"notice_days": 20})
    d = decide(C6, a, None, POLICY, [s.rule_1()])
    assert (d.kind, d.accepted, d.disputed) == (K.SPLIT, Decimal("1500.00"), Decimal("500.00"))


def test_row_3_unknown_notice_takes_else_branch():
    d = decide(C6, allowance("1200", "1200", (T["T-fee"],), {"notice_days": None}), None, POLICY, [s.rule_1()])
    assert (d.kind, d.disputed) == (K.DISPUTE, Decimal("1200.00"))


def test_row_4_discretion_without_rule_asks():
    d = decide(C6, allowance("1200", "1200", (T["T-fee"],)), finding(), POLICY, [s.rule_1(status="pending")])
    assert (d.kind, d.gate_row) == (K.ASK, 4)


def test_row_4_discretion_word_in_quote_counts_even_without_flag():
    unflagged = replace(T["T-fee"], discretion=False)
    assert uses_discretion(unflagged, POLICY)
    assert not uses_discretion(T["T-cap"], POLICY)
    assert decide(C6, allowance("1200", "1200", (unflagged,)), None, POLICY).gate_row == 4


@pytest.mark.parametrize("taken, allowed", [("1200.00", "1200.00"), ("1200.99", "1200.00"), ("1199.00", "1200.00")])
def test_row_5_within_one_dollar_accepts(taken, allowed):
    d = decide(C1, allowance(taken, allowed), None, POLICY)
    assert (d.kind, d.gate_row, d.accepted) == (K.ACCEPT, 5, Decimal(taken))


def test_row_6_undercharge_accepts_and_never_asks_for_more():
    d = decide(C1, allowance("900", "1200"), None, POLICY)
    assert (d.kind, d.gate_row, d.accepted, d.disputed) == (K.ACCEPT, 6, Decimal("900.00"), Decimal("0.00"))


def test_row_7_dispute_and_split():
    d = decide(C1, allowance("1800", "1200"), finding(), POLICY)
    assert (d.kind, d.gate_row, d.disputed, d.accepted) == (K.SPLIT, 7, Decimal("600.00"), Decimal("1200.00"))
    d = decide(C1, allowance("980", "0"), finding(), POLICY)
    assert (d.kind, d.gate_row, d.disputed, d.accepted) == (K.DISPUTE, 7, Decimal("980.00"), Decimal("0.00"))


def test_row_7_exactly_at_the_limit_still_files():
    d = decide(C1, allowance("5000", "0"), finding(), POLICY)
    assert (d.kind, d.gate_row) == (K.DISPUTE, 7)


def test_row_8_over_auto_dispute_limit_asks():
    d = decide(C1, allowance("5000.01", "0"), finding(), POLICY)
    assert (d.kind, d.gate_row, d.disputed) == (K.ASK, 8, Decimal("0.00"))


@pytest.mark.parametrize(
    "f",
    [None, finding(conf="0.89"), finding(sources=1), finding(comeback=False)],
    ids=["no finding", "low confidence", "one source", "no comeback"],
)
def test_row_9_unsupported_overcharge_asks(f):
    d = decide(C1, allowance("1800", "1200"), f, POLICY)
    assert (d.kind, d.gate_row) == (K.ASK, 9)


def test_row_9_missing_term_never_disputes():
    d = decide(C1, allowance("1800", "0", terms=(), missing=("promo_rate",)), finding(), POLICY)
    assert (d.kind, d.gate_row) == (K.ASK, 9)


def test_ties_go_to_the_earlier_row():
    # Rejected beats disputed beats discretion.
    rejected = replace(T["T-fee"], status=TermStatus.REJECTED)
    disputed = replace(T["T-rate"], status=TermStatus.DISPUTED)
    assert decide(C6, allowance("1200", "1200", (disputed, rejected)), finding(), POLICY, [s.rule_1()]).gate_row == 1
    assert decide(C6, allowance("1200", "1200", (disputed, T["T-fee"])), finding(), POLICY, [s.rule_1()]).gate_row == 2
