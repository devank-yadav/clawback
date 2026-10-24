"""The fixture run must validate against the contracts and reproduce the scenario in data/CLAUDE.md."""

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from api.engine import audit_chain
from api.contracts import RunFixture
from api.stubs import fixtures

DATA = fixtures.REPO / "data"

# data/CLAUDE.md: final decision, disputed, accepted per charge
EXPECTED = {
    "C1": ("split", 600, 1200), "C2": ("dispute", 980, 0), "C3": ("accept", 0, 330),
    "C4": ("dispute", 1540, 0), "C5": ("dispute", 1000, 0), "C6": ("accept", 0, 1200),
}
EXPECTED_APRIL = {"A1": ("accept", 0, 1200), "A2": ("dispute", 800, 0)}


def _load(name: str) -> RunFixture:
    return RunFixture.model_validate_json((fixtures.WEB_FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def march() -> RunFixture:
    return _load("run-events.json")


@pytest.fixture(scope="module")
def april() -> RunFixture:
    return _load("april-events.json")


def test_web_fixtures_are_up_to_date():
    for name, text in fixtures.fixture_files().items():
        assert (fixtures.WEB_FIXTURES / name).read_text() == text, f"{name} is stale: run python -m api.stubs.fixtures"


@pytest.mark.parametrize("name", ["run-events.json", "refusal-events.json", "april-events.json"])
def test_events_are_ordered(name):
    run = _load(name)
    assert [e.id for e in run.events] == list(range(1, len(run.events) + 1))
    ats = [e.at for e in run.events]
    assert ats == sorted(ats)
    assert {e.run_id for e in run.events} == {run.run_id}
    assert run.events[0].type == "run" and run.events[0].data.status == "started"
    assert run.events[-1].type == "run" and run.events[-1].data.status == "finished"


def _final_decisions(run: RunFixture) -> dict:
    return {e.data.charge_id: e.data for e in run.events if e.type == "decision"}


def test_march_decisions_match_scenario(march):
    final = _final_decisions(march)
    assert {k: (d.decision, d.disputed, d.accepted) for k, d in final.items()} == {
        k: (kind, Decimal(dis), Decimal(acc)) for k, (kind, dis, acc) in EXPECTED.items()}
    assert final["C6"].rule_id == "rule-1"
    first_c6 = next(e.data for e in march.events if e.type == "decision" and e.data.charge_id == "C6")
    assert first_c6.decision == "ask" and first_c6.waiting == Decimal(1200)


def test_march_totals(march):
    totals = [e.data for e in march.events if e.type == "totals"]
    for t in totals:
        assert t.taken == t.disputed + t.accepted + t.waiting + t.undecided
    last = totals[-1]
    assert (last.taken, last.disputed, last.accepted, last.waiting, last.undecided, last.questions) == (
        Decimal(6850), Decimal(4120), Decimal(2730), 0, 0, 1)
    rem = march.events[0].data.remittance
    assert (rem.expected, rem.received, rem.taken) == (Decimal(48200), Decimal(41350), Decimal(6850))


def test_one_question_to_owner(march):
    qs = [e.data for e in march.events if e.type == "question"]
    assert len(qs) == 1 and qs[0].to_role == "owner" and qs[0].charge_id == "C6"


def test_dispute_and_books(march):
    dispute = next(e.data for e in march.events if e.type == "dispute")
    assert dispute.id == "D-0417" and dispute.total == Decimal(4120)
    assert sum(ln.amount for ln in dispute.lines) == dispute.total
    approvals = [e.data for e in march.events if e.type == "approval"]
    assert [a.status for a in approvals] == ["pending", "approved"]
    assert approvals[-1].approver_role == "controller" and approvals[-1].amount == Decimal(2730)
    memo = next(e.data for e in march.events if e.type == "ledger_post" and e.data.qbo_entity == "credit_memo")
    assert memo.amount == Decimal(2730) and len(memo.lines) == 3 and memo.approval_id == approvals[-1].id
    # the memo posts only after the controller says yes
    ids = {e.data.id if e.type == "ledger_post" else e.data.status: e.id
           for e in march.events if e.type in ("approval", "ledger_post")}
    assert ids["approved"] < ids[memo.id]


@pytest.mark.parametrize("name", ["run-events.json", "refusal-events.json", "amendment-events.json", "april-events.json"])
def test_every_evidence_id_resolves(name):
    run = _load(name)
    refs = set()
    for d in run.charges.values():
        if d.finding:
            refs |= set(d.finding.evidence_ids) | {p.evidence_id for p in d.finding.math if p.evidence_id}
        if d.rehearsal:
            refs |= set(d.rehearsal.answer_evidence_ids)
        assert {e.id for e in d.evidence} >= set(d.finding.evidence_ids if d.finding else [])
    for e in run.events:
        if e.type == "dispute":
            refs |= {i for ln in e.data.lines for i in ln.evidence_ids}
        if e.type == "portal_message":
            refs |= set(e.data.evidence_ids)
    assert refs <= set(run.evidence), refs - set(run.evidence)


def test_april_uses_rule_and_asks_nothing(april):
    final = _final_decisions(april)
    assert {k: (d.decision, d.disputed, d.accepted) for k, d in final.items()} == {
        k: (kind, Decimal(dis), Decimal(acc)) for k, (kind, dis, acc) in EXPECTED_APRIL.items()}
    assert all(d.rule_id == "rule-1" and d.gate_row == 3 for d in final.values())
    assert not [e for e in april.events if e.type == "question"]


def _norm(s: str) -> str:
    return re.sub(r"[\s ]+", " ", s.replace("‑", "-")).strip()


def _quotes():
    for ev in fixtures.EVIDENCE.values():
        if ev.quote:
            yield ev.id, ev.quote.doc_id, ev.quote.text, ev.quote.char_start, ev.quote.char_end
    draft = {r.clause_ref: r.original_quote for r in fixtures.coach().redlines}
    for ref, (start, end) in fixtures.COACH_QUOTE_OFFSETS.items():
        yield f"coach {ref}", "summer-draft", draft[ref], start, end


@pytest.mark.parametrize("ev_id,doc_id,text,start,end", list(_quotes()))
def test_quotes_match_data_files(ev_id, doc_id, text, start, end):
    path = DATA / fixtures.QUOTE_SOURCES[doc_id]
    if not path.exists():
        pytest.skip(f"{path.relative_to(fixtures.REPO)} not on this branch yet")
    assert _norm(path.read_text()[start:end]) == _norm(text), ev_id


def test_audit_chain():
    rows = [e.as_row() for e in fixtures.audit_chain_rows()]
    assert audit_chain.verify(rows).ok
    rows[3] = {**rows[3], "action": "decision edited"}
    check = audit_chain.verify(rows)
    assert not check.ok and check.broken_at == rows[3]["id"]


def test_schema_file_is_json():
    schema = json.loads((fixtures.WEB_FIXTURES / "schema.json").read_text())
    assert "RunFixture" in schema


@pytest.mark.parametrize("name,cid", [("run-events.json", c) for c in EXPECTED] + [("april-events.json", c) for c in EXPECTED_APRIL])
def test_fixture_amounts_match_engine(name, cid):
    """The fake run's expected/taken/delta are what api/engine/allowed.py computes for the same scenario."""
    from api.engine.allowed import compute_allowed
    from api.engine.tests import scenario as s

    charges = {**s.march_charges(), **s.april_charges()}
    a = compute_allowed(charges[cid], s.spring_terms(), s.store_sales(), s.prior_payments())
    f = _load(name).charges[cid].finding
    assert (f.expected, f.taken, f.delta) == (a.allowed, a.taken, a.delta)


def test_rule_card_data_on_charges(march, april):
    """The RuleCard ("Applied Rule #1, learned Oct 24, approved by Dana") reads the rule from the charge detail;
    the April run never emits a rule event, so this is its only source there."""
    rule = next(e.data for e in march.events if e.type == "rule")
    for run, cid in [(march, "C6"), (april, "A1"), (april, "A2")]:
        assert run.charges[cid].rule == rule
    assert all(d.rule is None for cid, d in march.charges.items() if cid != "C6")


def test_remittance_has_received_at(march):
    rem = march.events[0].data.remittance
    assert rem.received_at is not None and rem.received_at <= march.events[0].at


def test_refusal_posts_nothing_and_keeps_totals(march):
    refused = _load("refusal-events.json")
    approvals = [e.data for e in refused.events if e.type == "approval"]
    assert [a.status for a in approvals] == ["pending", "refused"]
    assert approvals[-1].note and approvals[-1].approver_role == "controller" and approvals[-1].decided_at
    assert not [e for e in refused.events if e.type == "ledger_post"]
    totals = [e.data for e in refused.events if e.type == "totals"]
    assert totals[-1] == [e.data for e in march.events if e.type == "totals"][-1]
    assert _final_decisions(refused) == _final_decisions(march)


def test_amendment_continues_the_march_run(march):
    amended = _load("amendment-events.json")
    assert amended.run_id == march.run_id and {e.run_id for e in amended.events} == {march.run_id}
    assert [e.id for e in amended.events] == list(range(march.events[-1].id + 1, march.events[-1].id + 1 + len(amended.events)))
    ats = [e.at for e in amended.events]
    assert ats == sorted(ats) and ats[0] > march.events[-1].at
    assert amended.events[-1].type == "run" and amended.events[-1].data.status == "finished"


def test_amendment_concession_numbers(march):
    amended = _load("amendment-events.json")
    attach = next(e.data for e in amended.events if e.type == "portal_message")
    assert attach.from_party == "northmart" and attach.attachment_doc_id == "amendment-1"
    assert attach.classification == "new_document"
    c4 = _final_decisions(amended)["C4"]
    assert (c4.decision, c4.disputed, c4.accepted) == ("split", Decimal(540), Decimal(1000))
    t = [e.data for e in amended.events if e.type == "totals"][-1]
    assert (t.disputed, t.accepted, t.waiting, t.undecided, t.questions) == (Decimal(3120), Decimal(3730), 0, 0, 1)
    assert t.taken == t.disputed + t.accepted == Decimal(6850)
    dispute = next(e.data for e in amended.events if e.type == "dispute")
    assert dispute.total == Decimal(3120) == sum(ln.amount for ln in dispute.lines)
    assert {ln.charge_id: ln.amount for ln in dispute.lines}["C4"] == Decimal(540)
    reply = [e.data for e in amended.events if e.type == "portal_message"][-1]
    assert reply.from_party == "clawback" and "$1,000" in reply.text and "$540" in reply.text
    # the other five decisions are untouched
    assert set(_final_decisions(amended)) == {"C4"}


def test_amendment_amounts_match_engine():
    from api.engine.allowed import compute_allowed
    from api.engine.tests import scenario as s

    a = compute_allowed(s.march_charges()["C4"], s.spring_terms() + [s.amendment_1()], s.store_sales(), s.prior_payments())
    f = _load("amendment-events.json").charges["C4"].finding
    assert (f.expected, f.taken, f.delta) == (a.allowed, a.taken, a.delta) == (Decimal(1000), Decimal(1540), Decimal(540))


@pytest.mark.parametrize("ev_id", [e.id for e in fixtures.EVIDENCE.values() if e.quote])
def test_quote_context_is_its_paragraph(ev_id):
    q = fixtures.EVIDENCE[ev_id].quote
    text = (DATA / fixtures.QUOTE_SOURCES[q.doc_id]).read_text()
    assert text[q.char_start - len(q.context_before):q.char_start] == q.context_before
    assert text[q.char_end:q.char_end + len(q.context_after)] == q.context_after
    assert "\n\n" not in q.context_before + q.context_after
    para = q.context_before + text[q.char_start:q.char_end] + q.context_after
    start = q.char_start - len(q.context_before)
    assert start == 0 or text[start - 2:start] == "\n\n"  # starts at the paragraph's start
    end = start + len(para)
    assert end == len(text.rstrip("\n")) or text[end:end + 2] == "\n\n"  # ends at the paragraph's end
