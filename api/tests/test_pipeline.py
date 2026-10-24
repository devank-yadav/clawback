"""The whole March loop and the April replay with a fake Claude: the demo numbers, one question, Rule #1."""

import json
import re
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
    assert any(e.type == "log" and e.data.text.startswith("0 questions asked") for e in april.events)


def test_every_cited_evidence_id_resolves():
    run = pipeline.start("march", ScenarioClaude(), background=False)
    for cid in run.charges:
        d = run.detail(cid)
        assert {e.id for e in d.evidence} >= set(d.finding.evidence_ids)
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
