"""C1 (judge-risk map): on the deployed site only the admin (the owner) answers the questions and approves the memos,
and nobody can burn AI credits by hammering the public routes."""

import pytest
from fastapi.testclient import TestClient

from api import auth, pipeline
from api.agents import claude as claude_mod
from api.tests.test_pipeline import ScenarioClaude


@pytest.fixture
def api(monkeypatch):
    from api.main import app

    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    pipeline.reset(), auth.reset()
    yield TestClient(app), fake
    pipeline.reset(), auth.reset()


def roles(monkeypatch):
    monkeypatch.setenv("OWNER_TOKEN", "owner-test-token")


def as_(role):
    return {"X-Clawback-Role-Token": f"{role}-test-token"}


def test_only_the_owner_answers_the_owners_question(api, monkeypatch):
    client, fake = api
    roles(monkeypatch)
    run = pipeline.start("march", fake, background=False)
    (qid,) = run.questions
    body = {"text": "accept if notice is at least 14 days"}
    assert client.post(f"/questions/{qid}/answer", json=body).status_code == 401
    assert client.post(f"/questions/{qid}/answer", json=body, headers=as_("visitor")).status_code == 401
    assert run.questions[qid].answer is None  # nothing happened
    r = client.post(f"/questions/{qid}/answer", json=body, headers=as_("owner"))
    assert r.status_code == 200 and r.json()["rule"]["label"] == "Rule #1"


def test_only_the_admin_approves_the_memo(api, monkeypatch):
    client, fake = api
    roles(monkeypatch)
    run = pipeline.start("march", fake, background=False)
    client.post(f"/questions/{next(iter(run.questions))}/answer", json={"text": "accept if notice is at least 14 days"},
                headers=as_("owner"))
    (ap,) = [e.data.id for e in run.events if e.type == "approval" and e.data.status == "pending"]
    assert client.post(f"/approvals/{ap}", json={"approve": True}).status_code == 401
    assert client.post(f"/approvals/{ap}", json={"approve": True}, headers=as_("visitor")).status_code == 401
    assert not [e for e in run.events if e.type == "ledger_post"]  # a visitor can't move money
    r = client.post(f"/approvals/{ap}", json={"approve": True}, headers=as_("owner"))
    assert r.status_code == 200 and r.json()["approval"]["status"] == "approved"


def test_without_role_tokens_the_routes_stay_open(api):
    client, fake = api
    run = pipeline.start("march", fake, background=False)
    r = client.post(f"/questions/{next(iter(run.questions))}/answer", json={"text": "accept if notice is at least 14 days"})
    assert r.status_code == 200  # laptops and tests: no tokens set, nothing changes


def test_live_runs_are_limited_per_visitor_and_the_admin_skips_it(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("CLAWBACK_ADMIN_TOKEN", "admin-test-token")
    monkeypatch.setenv("RUNS_PER_IP", "2")
    start = {"kind": "march", "fixture": True}  # the recorded run: the limit is what's tested, not the run
    assert [client.post("/runs", json=start).status_code for _ in range(3)] == [200, 200, 429]
    assert client.post("/runs", json=start, headers={"Authorization": "Bearer admin-test-token"}).status_code == 200
    assert client.post("/demo/reset", headers={"Authorization": "Bearer admin-test-token"}).status_code == 200
    assert client.post("/runs", json=start).status_code == 200  # a reset between judge tables clears the limits


def test_without_the_admin_token_nothing_is_limited(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("RUNS_PER_IP", "1")
    assert {client.post("/runs", json={"kind": "march", "fixture": True}).status_code for _ in range(3)} == {200}


def test_the_assistant_answers_with_the_owners_token():
    import httpx

    from fetch_agent.client import ClawbackClient

    seen = []

    def handler(request):
        seen.append(request.headers.get("X-Clawback-Role-Token"))
        return httpx.Response(200, json={"answer": {"question_id": "Q-1", "from_role": "owner", "text": "UNDO",
                                                    "answered_at": "2026-10-24T10:00:00-07:00"}, "rule": None})

    http = httpx.Client(base_url="https://clawback.test/api", transport=httpx.MockTransport(handler))
    try:
        ClawbackClient("https://clawback.test/api", "ro", http=http, owner_token="owner-test-token").answer("Q-1", "UNDO")
    except Exception:  # noqa: BLE001 - the response shape is the agent's business; the header is what's tested
        pass
    assert seen == ["owner-test-token"]


# ---- the admin's sign-in (POST /auth/login): an ID and password in, the access code out

def _no_login_env(monkeypatch):
    for k in ("OWNER_TOKEN", "ADMIN_USERNAME", "ADMIN_PASSWORD", "CLAWBACK_ADMIN_TOKEN"):
        monkeypatch.delenv(k, raising=False)


def test_a_laptop_with_no_password_signs_anyone_in(api, monkeypatch):
    client, _ = api
    _no_login_env(monkeypatch)
    r = client.post("/auth/login", json={"username": "anyone", "password": "anything"})
    assert r.status_code == 200 and r.json() == {"role": "owner", "code": None}


def test_the_right_id_and_password_get_the_access_code(api, monkeypatch):
    client, _ = api
    _no_login_env(monkeypatch)
    roles(monkeypatch)
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse")
    assert client.post("/auth/login", json={"username": "Admin ", "password": "correct horse"}).json()["code"] == "owner-test-token"
    assert client.post("/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"username": "dana", "password": "correct horse"}).status_code == 401
    monkeypatch.setenv("ADMIN_USERNAME", "dana")
    assert client.post("/auth/login", json={"username": "dana", "password": "correct horse"}).status_code == 200


def test_a_guarded_site_without_a_password_says_sign_in_isnt_set_up(api, monkeypatch):
    client, _ = api
    _no_login_env(monkeypatch)
    roles(monkeypatch)
    r = client.post("/auth/login", json={"username": "admin", "password": "x"})
    assert r.status_code == 503 and "ADMIN_PASSWORD" in r.json()["detail"]


def test_sign_in_attempts_are_limited_per_visitor(api, monkeypatch):
    client, _ = api
    _no_login_env(monkeypatch)
    monkeypatch.setenv("CLAWBACK_ADMIN_TOKEN", "presenter")
    monkeypatch.setenv("ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("LOGIN_PER_IP", "3")
    codes = [client.post("/auth/login", json={"username": "admin", "password": "no"}).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
