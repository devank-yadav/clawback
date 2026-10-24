"""Stub routes serve the fixture run in the contract shapes."""

import json

import pytest
from fastapi.testclient import TestClient

from api.contracts import EventAdapter
from api.main import app
from api.stubs import fixtures

client = TestClient(app)


def _sse(text: str) -> list:
    return [EventAdapter.validate_json(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_start_run_and_stream_all_events():
    run = client.post("/runs", json={"kind": "march"}).json()
    assert run["run_id"] == fixtures.MARCH_RUN
    r = client.get(run["events_url"], params={"delay_ms": 0, "keepalive": False})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r.text)
    assert [e.id for e in events] == [e.id for e in fixtures.march_run().events]


def test_stream_resumes_after_last_event_id():
    r = client.get(f"/runs/{fixtures.MARCH_RUN}/events", params={"delay_ms": 0, "keepalive": False},
                   headers={"Last-Event-ID": "60"})
    assert [e.id for e in _sse(r.text)][0] == 61


def test_april_replay():
    run = client.post("/replay/april").json()
    events = _sse(client.get(run["events_url"], params={"delay_ms": 0, "keepalive": False}).text)
    assert events[-1].type == "run" and events[-1].data.status == "finished"


def test_unknown_run_404():
    assert client.get("/runs/nope/events").status_code == 404


def test_charge_and_evidence():
    c4 = client.get("/charges/C4").json()
    assert c4["decision"]["disputed"] == 1540.0 and c4["rehearsal"]["predicted_rebuttal"]
    assert client.get("/evidence/ev-deal-3.2").json()["quote"]["doc_id"] == "spring-promo"
    assert client.get("/charges/C9").status_code == 404
    assert client.get("/evidence/ev-nope").status_code == 404


def test_answer_question():
    r = client.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 14 days"}).json()
    assert r["rule"]["id"] == "rule-1" and r["answer"]["question_id"] == "Q-1"
    assert client.post("/questions/Q-9/answer", json={"text": "x"}).status_code == 404


def test_portal_thread_and_amendment():
    client.post("/demo/reset")
    thread = client.get("/portal/disputes/D-0417/messages").json()
    assert [m["from_party"] for m in thread] == ["northmart", "clawback"]
    theirs, ours = client.post("/portal/disputes/D-0417/messages",
                               json={"text": "Signed amendment attached.", "attachment_doc_id": "amendment-1"}).json()
    assert theirs["classification"] == "new_document" and "$540" in ours["text"]
    assert len(client.get("/portal/disputes/D-0417/messages").json()) == 4
    client.post("/demo/reset")
    assert len(client.get("/portal/disputes/D-0417/messages").json()) == 2


def test_summary_needs_token(monkeypatch):
    monkeypatch.delenv("CLAWBACK_READONLY_TOKEN", raising=False)
    assert client.get("/summary").status_code == 503
    monkeypatch.setenv("CLAWBACK_READONLY_TOKEN", "test-token")
    assert client.get("/summary").status_code == 401
    s = client.get("/summary", headers={"Authorization": "Bearer test-token"}).json()
    assert s["totals"]["disputed"] == 4120.0 and s["open_disputes"][0]["id"] == "D-0417"


def test_twilio_webhook_returns_twiml():
    r = client.post("/webhooks/twilio/sms", content="Body=yes&From=%2B15550000000",
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and "<Response>" in r.text


@pytest.mark.parametrize("method,path,check", [
    ("post", "/coach", lambda j: len(j["redlines"]) == 3),
    ("post", "/eval/run", lambda j: j["status"] == "not_run" and j["correct"] is None),
    ("get", "/eval/latest", lambda j: j["cases"] == 30),
    ("get", "/audit", lambda j: len(j) > 0 and j[0]["prev_hash"] == "0" * 64),
    ("get", "/audit/verify", lambda j: j["ok"] is True),
])
def test_simple_stubs(method, path, check):
    r = getattr(client, method)(path)
    assert r.status_code == 200 and check(r.json())


def test_scenario_stub():
    r = client.post("/scenario", json={"clause": "x", "charge": {"description": "y", "amount": 10}}).json()
    assert r["stub"] is True


def test_portal_dispute_and_amendment_flow():
    client.post("/demo/reset")
    d = client.get("/portal/disputes/D-0417").json()
    assert d["total"] == 4120.0 and len(d["lines"]) == 4 and d["status"] == "filed"
    assert client.get("/portal/disputes/D-9999").status_code == 404
    march_ids = [e.id for e in fixtures.march_run().events]
    stream = {"delay_ms": 0, "keepalive": False}
    assert [e.id for e in _sse(client.get(f"/runs/{fixtures.MARCH_RUN}/events", params=stream).text)] == march_ids

    client.post("/portal/disputes/D-0417/messages", json={"text": "Amendment attached.", "attachment_doc_id": "amendment-1"})
    d = client.get("/portal/disputes/D-0417").json()
    assert d["total"] == 3120.0 and {ln["charge_id"]: ln["amount"] for ln in d["lines"]}["C4"] == 540.0
    events = _sse(client.get(f"/runs/{fixtures.MARCH_RUN}/events", params=stream,
                             headers={"Last-Event-ID": str(march_ids[-1])}).text)
    assert [e.id for e in events] == [e.id for e in fixtures.amendment_run().events]
    c4 = client.get("/charges/C4").json()
    assert (c4["decision"]["disputed"], c4["decision"]["accepted"]) == (540.0, 1000.0)

    client.post("/demo/reset")
    assert client.get("/portal/disputes/D-0417").json()["total"] == 4120.0
    assert client.get("/charges/C4").json()["decision"]["disputed"] == 1540.0


def test_refusal_run_streams():
    events = _sse(client.get(f"/runs/{fixtures.REFUSED_RUN}/events", params={"delay_ms": 0, "keepalive": False}).text)
    assert [e.data.status for e in events if e.type == "approval"] == ["pending", "refused"]


def test_controller_approves_in_app():
    client.post("/demo/reset")
    r = client.post("/approvals/AP-1", json={"approve": True}).json()
    assert r["approval"]["status"] == "approved" and r["ledger_post"]["amount"] == 2730.0
    assert r["ledger_post"]["approval_id"] == "AP-1"
    assert client.post("/approvals/AP-1", json={"approve": False}).status_code == 409
    client.post("/demo/reset")


def test_controller_refuses_in_app():
    client.post("/demo/reset")
    r = client.post("/approvals/AP-1", json={"approve": False, "note": "Not yet."}).json()
    assert r["approval"]["status"] == "refused" and r["approval"]["note"] == "Not yet."
    assert r["ledger_post"] is None
    assert client.post("/approvals/AP-9", json={"approve": True}).status_code == 404
    client.post("/demo/reset")
