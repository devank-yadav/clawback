"""One admin decides everything: "Save as a rule for next time" (save_rule) on an answer, and "Post fair charges like
these automatically from now on" (auto_post) on an approval."""

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from api import pipeline
from api.agents import claude as claude_mod
from api.integrations import qbo, replay
from api.tests.test_pipeline import ScenarioClaude, final, last_totals

ANSWER = "accept if notice is at least 14 days"


@pytest.fixture
def api(monkeypatch, tmp_path):
    from api.main import app

    for k in qbo.KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    pipeline.reset()
    yield TestClient(app), fake
    pipeline.reset()


def approvals(run):
    return [e.data for e in run.events if e.type == "approval"]


def pending(run):
    latest = {a.id: a for a in approvals(run)}
    (a,) = [a for a in latest.values() if a.status == "pending"]
    return a


def march(client, fake, save_rule=True):
    run = pipeline.start("march", fake, background=False)
    r = client.post(f"/questions/{next(iter(run.questions))}/answer", json={"text": ANSWER, "save_rule": save_rule})
    assert r.status_code == 200, r.text
    return run, r.json()


# ---------------------------------------------------------------- save_rule

def test_save_rule_false_settles_this_charge_only_and_april_asks_again(api):
    client, fake = api
    run, body = march(client, fake, save_rule=False)
    assert body["rule"] is None and not pipeline.rules_of()
    assert not any(e.type == "rule" for e in run.events)
    assert final(run)["C6"] == ("accept", D(0), D(1200))  # notice came 20 days ahead: accepted, as the rule would
    t = last_totals(run)
    assert (t.disputed, t.accepted, t.waiting, t.questions) == (D(4120), D(2730), D(0), 1)
    assert run.questions["Q-1"].answer == ANSWER and run.questions["Q-1"].rule_id is None
    assert any("I didn't save a rule" in text for _, text in run.texts)

    april = pipeline.start("april", fake, background=False)
    assert [q.charge_id for q in april.questions.values()] == ["A1", "A2"]  # nothing saved, so both fees ask


def test_save_rule_defaults_to_true(api):
    client, fake = api
    run, body = march(client, fake)
    assert body["rule"]["label"] == "Rule #1"
    april = pipeline.start("april", fake, background=False)
    assert not april.questions and {d.rule_id for d in april.shown.values()} == {"rule-1"}


def test_save_rule_false_with_a_rule_the_charge_fails_disputes_it(api):
    client, fake = api
    run = pipeline.start("march", fake, background=False)
    client.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 30 days", "save_rule": False})
    assert final(run)["C6"] == ("dispute", D(1200), D(0))  # 20 days < 30: disputed, and still no rule
    assert not pipeline.rules_of()


# ---------------------------------------------------------------- auto_post

def test_auto_post_lets_the_next_memo_under_the_limit_post_without_asking(api):
    client, fake = api
    run, _ = march(client, fake)
    ap = pending(run)
    r = client.post(f"/approvals/{ap.id}", json={"approve": True, "auto_post": True}).json()
    assert r["approval"]["status"] == "approved" and r["approval"]["sets_auto_post"]["limit"] == 2730.0
    assert pipeline.AUTO_POST["peak-bar"].limit == D(2730)

    april = pipeline.start("april", fake, background=False)
    assert not april.questions  # 0 questions, and no approval either: $1,200 is under the $2,730 limit
    (a,) = approvals(april)
    assert (a.status, a.amount, a.posted_by_auto_post.approval_id) == ("approved", D(1200), ap.id)
    assert "auto-post rule" in a.note
    assert [p.status for p in (e.data for e in april.events if e.type == "ledger_post")] == ["posted"]
    assert client.get("/inbox").json()["approvals"] == []
    from api import audit
    assert ("auto_post:Dana", "credit_memo_auto_posted", f"approval:{a.id}") in {
        (r.actor, r.action, r.object_ref) for r in audit.entries()}


def test_a_memo_above_the_limit_still_asks(api):
    client, fake = api
    # Rule #1 first, from March; then April's $1,200 memo, approved with auto_post, sets a $1,200 limit
    march_run, _ = march(client, fake)
    client.post(f"/approvals/{pending(march_run).id}", json={"approve": True})  # no auto_post: nothing saved
    assert "peak-bar" not in pipeline.AUTO_POST
    april = pipeline.start("april", fake, background=False)
    client.post(f"/approvals/{pending(april).id}", json={"approve": True, "auto_post": True})
    assert pipeline.AUTO_POST["peak-bar"].limit == D(1200)

    again = pipeline.start("march", fake, background=False)  # Rule #1 decides C6: no question, a $2,730 memo
    a = pending(again)
    assert (a.amount, a.approver_role, a.posted_by_auto_post) == (D(2730), "owner", None)
    assert any("above the $1,200 auto-post limit" in e.data.text for e in again.events if e.type == "log")


def test_auto_post_with_a_no_saves_nothing(api):
    client, fake = api
    run, _ = march(client, fake)
    client.post(f"/approvals/{pending(run).id}", json={"approve": False, "note": "not yet", "auto_post": True})
    assert "peak-bar" not in pipeline.AUTO_POST


def test_policy_auto_post_limit_is_used_when_the_admin_set_none(api, monkeypatch):
    client, fake = api
    policy = pipeline.load_policy()
    monkeypatch.setattr(pipeline, "load_policy", lambda: type(policy)(**{**policy.__dict__, "auto_post_limit": D(5000)}))
    run = pipeline.start("march", fake, background=False)
    client.post(f"/questions/{next(iter(run.questions))}/answer", json={"text": ANSWER})
    (a,) = approvals(run)
    assert a.status == "approved" and a.posted_by_auto_post.set_by == "policy.yaml"


def test_auto_post_survives_a_restart_through_the_saved_state(api):
    client, fake = api
    run, _ = march(client, fake)
    client.post(f"/approvals/{pending(run).id}", json={"approve": True, "auto_post": True})
    saved = dict(pipeline.AUTO_POST)
    pipeline.reset()
    pipeline.restore_auto_post(saved)
    assert pipeline.auto_post_of("peak-bar", pipeline.load_policy()).limit == D(2730)
