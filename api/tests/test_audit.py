"""F18: every action of a live run lands in the hash-chained audit log; editing a past row breaks the check."""

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from api import audit, disputes, pipeline
from api.integrations import replay
from api.tests.test_disputes import PortalClaude, finished_march


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    for k in ("DEMO_MODE", "RECORD_FIXTURES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset(), disputes.reset()
    yield
    pipeline.reset(), disputes.reset()


def full_story():
    """March, Dana's answer, Sam's yes, then Northmart's signed amendment on the portal."""
    fake = PortalClaude()
    run = finished_march(fake)
    approval = next(e.data for e in run.events if e.type == "approval" and e.data.status == "pending")
    pipeline.decide_approval(approval.id, True)
    disputes.post("D-0417", "Signed amendment attached.", attachment_doc_id="amendment-1", client=fake)
    return run


def test_every_action_is_written_in_order():
    run = full_story()
    rows = audit.entries()
    audited = [e for e in run.events if e.type in audit.AUDITED]
    assert [r.evidence["event_id"] for r in rows] == [e.id for e in audited]  # nothing missing, nothing extra
    assert [r.id for r in rows] == list(range(1, len(rows) + 1))
    by_action = {(r.actor, r.action, r.object_ref) for r in rows}
    assert ("gate", "decision_split", "charge:C1") in by_action
    assert ("gate", "question_asked", "question:Q-1") in by_action
    assert ("owner:Dana", "answer_received", "question:Q-1") in by_action
    assert ("owner:Dana", "rule_saved", "rule:rule-1") in by_action
    assert ("controller:Sam", "credit_memo_approved", f"approval:AP-{run.id}") in by_action
    assert ("policy", "credit_memo_approved", f"approval:AP-{run.id}-2") in by_action  # the $1,000 concession
    assert ("bookkeeper", "qbo_credit_memo_posted", f"ledger:LP-AP-{run.id}") in by_action
    assert ("negotiator", "dispute_answered", "dispute:D-0417") in by_action
    assert ("northmart", "portal_message", "portal:PM-D-0417-1") in by_action
    c4 = [r for r in rows if r.object_ref == "charge:C4"]
    assert [r.evidence["data"]["disputed"] for r in c4] == ["1540.00", "540.00"]  # money kept as strings
    assert audit.verify().ok


def test_editing_a_past_row_breaks_the_chain():
    full_story()
    rows = [e.as_row() for e in audit.entries()]
    i = next(n for n, r in enumerate(rows) if r["object_ref"] == "charge:C4")
    rows[i] = {**rows[i], "evidence": {**rows[i]["evidence"], "data": {**rows[i]["evidence"]["data"], "disputed": "0.00"}}}
    check = audit.verify(rows)
    assert (check.ok, check.broken_at) == (False, i + 1) and "edited" in check.reason


def test_removing_rows_breaks_the_chain():
    full_story()
    rows = [e.as_row() for e in audit.entries()]
    assert not audit.verify(rows[:-1]).ok  # newest row cut off: the saved head no longer matches
    gap = rows[:4] + rows[5:]
    check = audit.verify(gap)
    assert (check.ok, check.broken_at) == (False, 5)  # a row missing in the middle


def test_audit_routes_show_the_live_chain_and_catch_tampering():
    from api.main import app

    client = TestClient(app)
    run = full_story()
    log = client.get("/audit").json()
    assert len(log) == len(audit.entries()) and log[0]["prev_hash"] == "0" * 64
    assert any(r["evidence"]["run_id"] == run.id for r in log)
    assert client.get("/audit/verify").json() == {"ok": True, "checked": len(log), "broken_at": None, "reason": ""}
    # Someone edits a stored row behind the app's back (in the database, once there is one):
    stored = audit._chain._entries
    assert stored[2].action == "decision_accept"  # C3
    stored[2] = stored[2].__class__(**{**stored[2].as_row(), "action": "decision_dispute"})
    bad = client.get("/audit/verify").json()
    assert bad["ok"] is False and bad["broken_at"] == 3


def test_reset_starts_a_new_chain_and_the_fixture_log_shows_before_any_run():
    from api.main import app

    full_story()
    pipeline.reset()
    assert audit.entries() == ()
    client = TestClient(app)
    assert client.get("/audit/verify").json()["ok"] is True and client.get("/audit").json()[0]["id"] == 1
