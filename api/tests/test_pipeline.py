"""The whole March loop and the April replay with a fake Claude: the demo numbers, one question, Rule #1."""

import json
import re
import threading
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import pipeline
from api.agents import claude as claude_mod
from api.agents.investigator import LLMFinding
from api.agents.negotiator import LLMRehearsal
from api.agents.reader import LLMOutput
from api.agents.rule_writer import LLMRule
from api.integrations import replay
from api.tests.test_reader import BROKER_TERMS, CLAIM_TERMS, SPRING, answer


class ScenarioClaude:
    """Answers each agent the way a careful model would, citing only IDs from the request."""

    def __init__(self, owner_understood=True):
        self.calls: list[str] = []
        self.owner_understood = owner_understood
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, output_format, messages, **_):
        user = messages[0]["content"]
        self.calls.append(output_format.__name__)
        out = {LLMOutput: self._reader, LLMFinding: self._finding, LLMRehearsal: self._rehearsal,
               LLMRule: self._rule}[output_format](user)
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=output_format.model_validate(out))

    def _reader(self, user):
        doc = re.search(r"Document ID: (\S+)", user).group(1)
        return answer({"spring-promo": SPRING, "broker-2026-03-28": BROKER_TERMS, "northmart-2026-03-30": CLAIM_TERMS}[doc])

    def _finding(self, user):
        payload = json.loads(user)
        ids = [e["id"] for e in payload["evidence"]]
        cites = [i for i in ids if i.startswith("ev-spring-promo")][:1] + [i for i in ids if i.startswith("ev-sales")][:1]
        cites.append(f"ev-charge-{payload['charge']['id']}")
        return {"finding": "The deal and the store sales explain this charge.", "type": "matches_deal",
                "evidence_ids": cites, "confidence": 0.95, "open_questions": []}

    def _rehearsal(self, user):
        ids = [e["id"] for e in json.loads(user)["evidence"]]
        return {"predicted_rebuttal": "The deduction stands.",
                "answer": "The signed deal and the store sales show the charge is too high.",
                "answer_evidence_ids": [next(i for i in ids if i.startswith("ev-spring-promo"))]}

    def _rule(self, user):
        return {"understood": self.owner_understood, "fact": "notice_days", "op": ">=", "value": 14,
                "decision": "accept", "else_decision": "dispute",
                "summary": "Accept display fees with at least 14 days' notice; otherwise dispute."}


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)
    yield
    pipeline.reset()


def final(run):
    return {cid: (d.decision, d.disputed, d.accepted) for cid, d in run.shown.items()}


def last_totals(run):
    return [e.data for e in run.events if e.type == "totals"][-1]


D = Decimal
MARCH_FIRST = {"C1": ("split", D(600), D(1200)), "C2": ("dispute", D(980), D(0)), "C3": ("accept", D(0), D(330)),
               "C4": ("dispute", D(1540), D(0)), "C5": ("dispute", D(1000), D(0)), "C6": ("ask", D(0), D(0))}


def test_march_first_pass_asks_one_question_and_files_d0417():
    run = pipeline.start("march", ScenarioClaude(), background=False)
    assert final(run) == MARCH_FIRST
    t = last_totals(run)
    assert (t.taken, t.disputed, t.accepted, t.waiting, t.undecided, t.questions) == (D(6850), D(4120), D(1530), D(1200), D(0), 1)
    dispute = next(e.data for e in run.events if e.type == "dispute")
    assert (dispute.id, dispute.total, dispute.status, dispute.approved_by) == ("D-0417", D(4120), "filed", "policy")
    assert [ln.charge_id for ln in dispute.lines] == ["C1", "C2", "C4", "C5"]
    assert [q.charge_id for q in run.questions.values()] == ["C6"]
    assert run.events[-1].type == "run" and run.events[-1].data.status == "waiting" and not run.done


def test_march_streams_its_stages_for_the_board():
    """The board's progress bars: a tick per document read (with the agreed quotes), a tick per charge checked."""
    run = pipeline.start("march", ScenarioClaude(), background=False)
    stages = [e.data for e in run.events if e.type == "stage"]
    read = [s for s in stages if s.stage == "read"]
    assert [(s.status, s.done, s.total) for s in read] == [
        ("started", 0, 3), ("progress", 0, 3), ("progress", 1, 3), ("progress", 1, 3), ("progress", 2, 3),
        ("progress", 2, 3), ("progress", 3, 3), ("done", 3, 3)]
    assert read[1].label == "Reading the signed deal" and read[3].label.startswith("Reading the email from ")
    spring = [t for t in run.terms if t.source_doc_id == "spring-promo" and t.status == "verified"]
    assert spring and read[2].items == [pipeline._short(t.exact_quote) for t in spring]
    check = [s for s in stages if s.stage == "check"]
    assert [(s.status, s.done, s.charge_id) for s in check] == [("started", 0, None)] + [
        ("progress", i, f"C{i + 1}") for i in range(6)] + [("done", 6, None)]
    # each charge's tick comes right before its charge event, and reading ends before the first one
    types = [e.type for e in run.events]
    assert types.index("charge") > max(i for i, e in enumerate(run.events) if e.type == "stage" and e.data.stage == "read")
    assert run.events[0].type == "run" and run.events[-1].type == "run"


def test_the_board_names_each_document_of_a_real_contract_account(monkeypatch):
    """Several deals or notices go by their own titles (dated when the id is), and a long read says it's long."""
    from api import accounts
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", "copperline"})
    accounts.clear()
    try:
        names = pipeline._doc_names(["walmart-supplier-agreement-2013", "copperline-item-setup-2026",
                                     "copperline-walmart-fine-2026-03-26", "copperline-walmart-fine-2026-03-27"])
        assert len(set(names.values())) == 4
        assert names["walmart-supplier-agreement-2013"].startswith("Walmart Supplier Agreement 2013 · a long document")
        assert names["copperline-walmart-fine-2026-03-27"] == "Walmart compliance assessment (Mar 27)"
        assert pipeline._doc_names(["spring-promo"]) == {"spring-promo": "the signed deal"}
    finally:
        accounts.clear()


def test_owner_answer_becomes_rule_1_and_finishes_march():
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    (qid,) = run.questions
    ans, rule = pipeline.answer(qid, "accept if notice is at least 14 days", client=fake)
    assert (rule.id, rule.condition, rule.decision, rule.else_decision) == ("rule-1", "notice_days >= 14", "accept", "dispute")
    assert final(run)["C6"] == ("accept", D(0), D(1200)) and run.shown["C6"].rule_id == "rule-1"
    t = last_totals(run)
    assert (t.disputed, t.accepted, t.waiting, t.questions) == (D(4120), D(2730), D(0), 1)
    approval = next(e.data for e in run.events if e.type == "approval")
    assert (approval.amount, approval.status, approval.approver_role, len(approval.lines)) == (D(2730), "pending", "controller", 3)
    assert run.done and run.events[-1].data.status == "finished"
    assert sum(1 for e in run.events if e.type == "dispute") == 1  # not refiled after the answer


def test_unclear_answer_keeps_the_question_open():
    fake = ScenarioClaude(owner_understood=False)
    run = pipeline.start("march", fake, background=False)
    (qid,) = run.questions
    _, rule = pipeline.answer(qid, "hmm not sure", client=fake)
    assert rule is None and final(run)["C6"][0] == "ask" and not run.done


def test_april_is_decided_by_rule_1_with_no_questions():
    fake = ScenarioClaude()
    march = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(march.questions)), "accept if notice is at least 14 days", client=fake)
    april = pipeline.start("april", fake, background=False)
    assert final(april) == {"A1": ("accept", D(0), D(1200)), "A2": ("dispute", D(800), D(0))}
    assert not april.questions and all(d.rule_id == "rule-1" for d in april.shown.values())
    assert all(d.reason == "Applied Rule #1." for d in april.shown.values())
    assert any(e.type == "log" and e.data.text.startswith("0 questions asked") for e in april.events)


def test_every_cited_evidence_id_resolves():
    run = pipeline.start("march", ScenarioClaude(), background=False)
    for cid in run.charges:
        d = run.detail(cid)
        assert {e.id for e in d.evidence} >= set(d.finding.evidence_ids)
        kinds = [e.kind for e in d.evidence]  # the deal's sentence leads the drawer, the charge row comes last
        assert kinds[-1] == "charge" and kinds == sorted(kinds, key=lambda k: 0 if k == "clause" else 2 if k == "charge" else 1)
        assert cid == "C2" or kinds[0] == "clause"  # C2 is a repeat payment: its proof is NM-2178 and week 2 sales
    for e in run.events:
        if e.type == "dispute":
            assert all(i in run.evidence for ln in e.data.lines for i in ln.evidence_ids)


def test_routes_run_the_live_pipeline(monkeypatch):
    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    from api.main import app
    client = TestClient(app)
    run_id = client.post("/runs", json={"kind": "march"}).json()["run_id"]
    assert run_id.startswith("run-march-")
    run = pipeline.RUNS[run_id]
    for _ in range(200):
        if any(e.type == "run" and e.data.status == "waiting" for e in run.events):
            break
        import time; time.sleep(0.05)
    body = client.get(f"/runs/{run_id}/events", params={"keepalive": False}).text
    assert body.count("data: ") == len(run.events)
    assert client.get("/charges/C4", params={"run_id": run_id}).json()["decision"]["disputed"] == 1540.0
    r = client.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 14 days"}).json()
    assert r["rule"]["label"] == "Rule #1"
    assert client.get(f"/evidence/ev-rule-1", params={"run_id": run_id}).json()["kind"] == "rule"
    assert client.post("/runs", json={"kind": "march", "fixture": True}).json()["run_id"] == "run-march-demo"


def test_committed_recordings_replay_the_whole_demo_offline(monkeypatch):
    """F11: the full demo runs with Wi-Fi off from data/fixtures. If this fails after a prompt or payload
    change, re-record with `make record`."""
    from api.tests.test_reader import RECORDED

    class Offline:
        def with_options(self, **_):
            raise AssertionError("DEMO_MODE must not call out")

    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)  # skip the demo pacing delay
    monkeypatch.setenv("DEMO_MODE", "true")
    march = pipeline.start("march", Offline(), background=False)
    assert final(march) == MARCH_FIRST
    pipeline.answer("Q-1", "accept if notice is at least 14 days", client=Offline())
    t = last_totals(march)
    assert (t.disputed, t.accepted, t.questions, march.done) == (D(4120), D(2730), 1, True)
    april = pipeline.start("april", Offline(), background=False)
    assert final(april) == {"A1": ("accept", D(0), D(1200)), "A2": ("dispute", D(800), D(0))} and not april.questions


def _march_waiting():
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    (qid,) = run.questions
    return fake, run, qid


def logs(run):
    return [e.data.text for e in run.events if e.type == "log"]


def test_parser_saves_rule_1_without_claude():
    fake, run, qid = _march_waiting()
    _, rule = pipeline.answer(qid, "accept if notice is at least 14 days", client=fake)
    assert "LLMRule" not in fake.calls
    assert rule.summary == "Accept Northmart display fees with at least 14 days' notice; otherwise dispute."
    assert any("Saved: accept display fees with 14+ days' notice. Reply UNDO to cancel." in t for t in logs(run))


def test_two_weeks_means_14_days():
    fake, run, qid = _march_waiting()
    _, rule = pipeline.answer(qid, "two weeks", client=fake)
    assert rule.condition == "notice_days >= 14" and final(run)["C6"] == ("accept", D(0), D(1200))


def test_one_off_accept_settles_c6_without_a_rule():
    fake, run, qid = _march_waiting()
    _, rule = pipeline.answer(qid, "ACCEPT", client=fake)
    assert rule is None and not pipeline.RULES
    assert final(run)["C6"] == ("accept", D(0), D(1200)) and run.shown["C6"].decided_by == "owner"
    assert run.done and last_totals(run).accepted == D(2730)
    april = pipeline.start("april", fake, background=False)
    assert len(april.questions) == 2  # nothing was learned, so April asks


def test_one_off_dispute_files_its_own_line():
    fake, run, qid = _march_waiting()
    pipeline.answer(qid, "dispute", client=fake)
    disputes = [e.data for e in run.events if e.type == "dispute"]
    assert [(x.id, x.total, [ln.charge_id for ln in x.lines]) for x in disputes] == [
        ("D-0417", D(4120), ["C1", "C2", "C4", "C5"]), ("D-0418", D(1200), ["C6"])]
    t = last_totals(run)
    assert (t.disputed, t.accepted) == (D(5320), D(1530))
    assert next(e.data for e in run.events if e.type == "approval").amount == D(1530)


def test_undo_cancels_rule_1_for_next_time():
    fake, run, qid = _march_waiting()
    pipeline.answer(qid, "accept if notice is at least 14 days", client=fake)
    _, undone = pipeline.answer(qid, "UNDO", client=fake)
    assert undone.id == "rule-1" and undone.status == "undone" and pipeline.RULES[0].status == "undone"
    assert final(run)["C6"] == ("accept", D(0), D(1200))  # this charge keeps its decision
    assert any("Undone: Rule #1 is cancelled" in t for t in logs(run))
    april = pipeline.start("april", fake, background=False)
    assert len(april.questions) == 2


def test_reply_after_settled_changes_nothing():
    fake, run, qid = _march_waiting()
    pipeline.answer(qid, "accept if notice is at least 14 days", client=fake)
    _, rule = pipeline.answer(qid, "dispute", client=fake)
    assert rule is None and final(run)["C6"] == ("accept", D(0), D(1200)) and len(pipeline.RULES) == 1


def test_reply_the_parser_cant_read_goes_to_claude():
    fake, run, qid = _march_waiting()
    _, rule = pipeline.answer(qid, "fine as long as they warn us early enough", client=fake)
    assert "LLMRule" in fake.calls and rule.condition == "notice_days >= 14"
    assert final(run)["C6"] == ("accept", D(0), D(1200))


def test_nobody_can_read_it_so_dana_is_asked_again():
    fake = ScenarioClaude(owner_understood=False)
    run = pipeline.start("march", fake, background=False)
    (qid,) = run.questions
    _, rule = pipeline.answer(qid, "hmm not sure", client=fake)
    assert rule is None and final(run)["C6"][0] == "ask"
    from api import replies
    assert any(replies.REASK_TEXT in t for t in logs(run)) and len(run.questions) == 1


# ---------------------------------------------------------------- a newer run replaces an older one

def test_a_new_run_closes_the_old_runs_question():
    """A reload (or a second tab) starts another March run: the old question closes, so Dana's answer, the inbox and
    her texts all land on the run she's looking at."""
    fake = ScenarioClaude()
    old = pipeline.start("march", fake, background=False)
    (q1,) = old.questions
    new = pipeline.start("march", fake, background=False)
    (q2,) = new.questions
    assert old.replaced_by == new.id and old.questions[q1].closed_at and pipeline.is_open(new.questions[q2])
    assert [e.data.closed_at is not None for e in old.events if e.type == "question"] == [False, True]
    assert [q.id for q in pipeline.inbox()[0]] == [q2]
    with pytest.raises(pipeline.QuestionClosed):
        pipeline.answer(q1, "accept if notice is at least 14 days", client=fake)
    _, rule = pipeline.answer(q2, "accept if notice is at least 14 days", client=fake)
    assert rule.label == "Rule #1" and final(new)["C6"] == ("accept", D(0), D(1200))
    assert final(old)["C6"] == ("ask", D(0), D(0))  # the replaced run stays as it was
    april = pipeline.start("april", fake, background=False)
    assert april.replaced_by is None and new.replaced_by is None  # another payment replaces nothing


def test_a_replaced_runs_approval_waits_on_nobody():
    """Sam's YES and the inbox only see the newest run, even while it's still deciding."""
    fake = ScenarioClaude()
    old = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(old.questions)), "accept if notice is at least 14 days", client=fake)
    (stale,) = pipeline.inbox()[1]
    assert pipeline.pending_approval() == stale.id
    old.replaced_by = "run-march-still-deciding"  # a newer run has started and hasn't asked Sam yet
    assert pipeline.pending_approval() is None and pipeline.inbox()[1] == []
    new = pipeline.start("march", fake, background=False)  # Rule #1 is saved: it goes straight to Sam
    (fresh,) = pipeline.inbox()[1]
    assert fresh.id == f"AP-{new.id}" and pipeline.pending_approval() == fresh.id


class ReloadMidRun(ScenarioClaude):
    """The page reloads while the first run's agents are still working: a second run starts and finishes first."""

    def __init__(self):
        super().__init__()
        self.newer, self.lock = None, threading.Lock()

    def _parse(self, output_format, messages, **kw):
        with self.lock:  # the two readers call at once
            if self.newer is None:
                self.newer = pipeline.start("march", ScenarioClaude(), background=False)
        return super()._parse(output_format=output_format, messages=messages, **kw)


def test_a_run_replaced_mid_decision_asks_nobody():
    from api.integrations import sms
    fake = ReloadMidRun()
    old = pipeline.start("march", fake, background=False)
    (q_new,), (q_old,) = fake.newer.questions, old.questions
    assert old.replaced_by == fake.newer.id and old.questions[q_old].closed_at  # born closed
    assert pipeline.is_open(fake.newer.questions[q_new]) and [q.id for q in pipeline.inbox()[0]] == [q_new]
    owner = [text for role, text in sms.outbox if role == "owner"]
    summaries = [t for t in owner if t.startswith("Clawback checked")]
    assert len(owner) - len(summaries) == 1  # only the newer run asked Dana
    assert len(summaries) == 1 and [m.run_id for m in pipeline.owner_messages()] == [fake.newer.id]
    assert any("Didn't ask Dana about C6" in e.data.text for e in old.events if e.type == "log")


def test_answering_a_closed_question_is_refused_but_undo_still_works(monkeypatch):
    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    from api.main import app
    client = TestClient(app)
    first = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(first.questions)), "accept if notice is at least 14 days", client=fake)
    old = pipeline.start("march", ScenarioClaude(), background=False)  # Rule #1 decides C6: no question
    assert not old.questions
    pipeline.RULES.clear()  # pretend Dana's rule never existed, so the next run asks again
    asking = pipeline.start("march", fake, background=False)
    (q,) = asking.questions
    pipeline.start("march", fake, background=False)
    r = client.post(f"/questions/{q}/answer", json={"text": "accept if notice is at least 14 days"})
    assert r.status_code == 409 and "newer run" in r.json()["detail"]
    assert client.post(f"/questions/{q}/answer", json={"text": "UNDO"}).status_code == 200


def test_each_dispute_line_quotes_the_clause_its_charge_turns_on():
    """D-0417's C4 line quotes the §3.2 cap (the portal's opening moment), not the §3.1 rate."""
    run = pipeline.start("march", ScenarioClaude(), background=False)
    for cid in run.findings:  # ScenarioClaude labels every finding matches_deal; give each its real type
        run.findings[cid] = run.findings[cid].model_copy(update={"type": {
            "C1": "rate_over", "C2": "duplicate", "C4": "over_cap", "C5": "product_not_covered"}.get(cid, "matches_deal")})
    clauses = {cid: pipeline._line_clause(run, cid, run.findings[cid]) for cid in ("C1", "C2", "C4", "C5")}
    assert {cid: c.label for cid, c in clauses.items()} == {"C1": "§3.1", "C2": "§3.1", "C4": "§3.2", "C5": "§3.1"}
    assert "maximum of 5,000 units" in clauses["C4"].quote.text


def test_every_number_on_a_live_card_opens_its_source():
    """F7 on live runs: each math step links to the evidence it rests on (the board makes it clickable)."""
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days", client=fake)
    links = {cid: [m.evidence_id for m in f.math] for cid, f in run.findings.items()}
    assert all(i in run.evidence for ids in links.values() for i in ids)  # every step links, and every link opens
    assert links["C1"] == ["ev-sales-2026-03-01", "ev-spring-promo-3.2", "ev-spring-promo-3.1"]
    assert links["C2"][2] == "ev-payment-NM-2178" and links["C3"][2] == "ev-broker-2026-03-28"
    assert links["C5"] == ["ev-spring-promo-3.1"] and links["C6"] == ["ev-spring-promo-5.4", "ev-display-fee-2026-03-11"]
