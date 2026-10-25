"""Phase B: real sign-in and tenant isolation. Signed in as another supplier (Lantern Hill's Teresa), every Peak Bar
route and id is a 404; signed out where sign-in is on, a 401; the token paths for scripts keep working."""

import pytest
from fastapi.testclient import TestClient

from api import accounts, auth, pipeline, users
from api.agents import claude as claude_mod
from api.tests.test_pipeline import ScenarioClaude

DANA, TERESA = "dana@peakbar.example", "teresa@lanternhillsoda.example"


@pytest.fixture
def site(monkeypatch):
    """Sign-in on (both demo passwords set), Peak Bar and Lantern Hill loaded, and one finished Peak Bar March run
    with its question answered, so a run, charge, evidence, question, approval and dispute id all exist."""
    from api.main import app

    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", "lantern-hill"})
    accounts.clear()
    monkeypatch.setenv("DEMO_USER_PASSWORD", "peak-pass")
    monkeypatch.setenv("DEMO_USER2_PASSWORD", "lantern-pass")
    users.reset(), pipeline.reset(), auth.reset()
    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    run = pipeline.start("march", fake, background=False)
    (qid,) = run.questions
    pipeline.answer(qid, "accept if notice is at least 14 days", "owner", client=fake)
    yield app, run, qid
    users.reset(), pipeline.reset(), auth.reset()
    accounts.clear()


def signed_in(app, email, password):
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return client


def peak_bar_routes(run, qid):
    ap = next(e.data.id for e in run.events if e.type == "approval")
    dispute = next(e.data.id for e in run.events if e.type == "dispute")
    ev = next(iter(run.evidence))
    rid = run.id
    return [
        ("GET", "/accounts/peak-bar/overview", None),
        ("GET", "/accounts/peak-bar/lookback", None),
        ("GET", "/accounts/peak-bar/runs", None),
        ("GET", "/accounts/peak-bar/saved", None),
        ("GET", "/accounts/peak-bar/documents/spring-promo", None),
        ("GET", "/accounts/peak-bar/contract", None),
        ("GET", "/connections?account=peak-bar", None),
        ("GET", "/runs/latest?account=peak-bar", None),
        ("POST", "/runs", {"account": "peak-bar", "fixture": True}),
        ("POST", "/replay/april?fixture=true", None),
        ("GET", f"/runs/{rid}/events?keepalive=false", None),
        ("GET", "/runs/run-march-demo/events?keepalive=false", None),
        ("GET", f"/charges/C1?run_id={rid}", None),
        ("GET", "/charges/C1", None),
        ("GET", f"/evidence/{ev}?run_id={rid}", None),
        ("GET", f"/evidence/{ev}", None),
        ("POST", f"/questions/{qid}/answer", {"text": "accept"}),
        ("POST", f"/approvals/{ap}", {"approve": True}),
        ("POST", "/approvals/AP-1", {"approve": True}),
        ("GET", f"/runs/{rid}/trace", None),
        ("GET", f"/runs/{rid}/trace/summary", None),
        ("POST", "/payments/northmart", None),
        ("POST", "/payments/peak-bar", None),
        ("POST", "/accounts/peak-bar/remittance", {"text": "Remittance"}),
        ("POST", "/accounts/peak-bar/remittance/run", {"read_id": "R-1"}),
        ("GET", "/accounts/peak-bar/remittance/samples/northmart", None),
        ("POST", "/coach?account=peak-bar", None),
        ("POST", "/scenario?account=peak-bar", {"clause": "x", "charge": {}}),
        ("GET", "/db/cap?account=peak-bar", None),
        ("POST", "/suppliers/peak-bar/tracking", {"account_id": "peak-bar", "tracked": False}),
        ("GET", f"/portal/disputes/{dispute}", "public"),
    ]


def _call(client, method, path, body):
    return client.request(method, path, json=body if isinstance(body, dict) else None)


def test_another_supplier_gets_404_on_every_peak_bar_route_and_id(site):
    app, run, qid = site
    teresa = signed_in(app, TERESA, "lantern-pass")
    for method, path, body in peak_bar_routes(run, qid):
        r = _call(teresa, method, path, body)
        if body == "public":  # the distributor's portal opens from the email's link, no sign-in
            assert r.status_code == 200, path
            continue
        if path.startswith("/scenario"):  # the body is checked first; a valid one still gets 404
            assert r.status_code in (404, 422), (path, r.status_code)
            continue
        assert r.status_code == 404, (method, path, r.status_code, r.text[:200])
    assert run.questions[qid].answer is not None and not any(
        e.type == "ledger_post" for e in run.events)  # nothing Teresa sent moved Peak Bar's money


@pytest.mark.parametrize("i", range(31))
def test_each_route_is_404_for_another_supplier(site, i):
    app, run, qid = site
    method, path, body = peak_bar_routes(run, qid)[i]
    r = _call(signed_in(app, TERESA, "lantern-pass"), method, path, body)
    if body == "public":
        assert r.status_code == 200
    elif path.startswith("/scenario"):
        assert r.status_code in (404, 422)
    else:
        assert r.status_code == 404, (method, path, r.status_code)


def test_lists_show_only_the_callers_supplier(site):
    app, run, _ = site
    teresa = signed_in(app, TERESA, "lantern-pass")
    assert [a["id"] for a in teresa.get("/accounts").json()] == ["lantern-hill"]
    assert [s["id"] for s in teresa.get("/suppliers").json()] == ["lantern-hill"]
    inbox = teresa.get("/inbox").json()
    assert inbox["questions"] == [] and inbox["approvals"] == [] and inbox["messages"] == []
    assert teresa.get("/audit").json() == []
    assert teresa.get("/accounts/lantern-hill/overview").status_code == 200  # her own works

    dana = signed_in(app, DANA, "peak-pass")
    assert "peak-bar" in [a["id"] for a in dana.get("/accounts").json()]
    assert "lantern-hill" not in [a["id"] for a in dana.get("/accounts").json()]
    assert dana.get("/inbox").json()["approvals"]  # Peak Bar's memo waits on Dana
    assert any(e["evidence"]["run_id"] == run.id for e in dana.get("/audit").json())
    assert dana.get(f"/charges/C1?run_id={run.id}").status_code == 200
    assert dana.get("/accounts/lantern-hill/overview").status_code == 404


def test_the_owner_of_the_data_still_sees_every_route(site):
    app, run, qid = site
    dana = signed_in(app, DANA, "peak-pass")
    for method, path, body in peak_bar_routes(run, qid):
        if method != "GET" or "/db/cap" in path or "samples" in path:
            continue
        assert dana.get(path).status_code == 200, path


def test_signed_out_is_401_where_sign_in_is_on(site):
    app, run, _ = site
    client = TestClient(app)
    for path in ("/accounts", "/inbox", "/audit", f"/runs/{run.id}/events?keepalive=false", "/suppliers",
                 "/accounts/peak-bar/overview", "/eval/latest", "/auth/me"):
        assert client.get(path).status_code == 401, path
    assert client.get("/health").status_code == 200


def test_scripts_and_the_presenter_keep_their_tokens(site, monkeypatch):
    app, run, _ = site
    monkeypatch.setenv("OWNER_TOKEN", "owner-tok")
    monkeypatch.setenv("CLAWBACK_ADMIN_TOKEN", "admin-tok")
    monkeypatch.setenv("CLAWBACK_READONLY_TOKEN", "ro-tok")
    client = TestClient(app)
    assert client.get("/accounts/peak-bar/overview", headers={"X-Clawback-Role-Token": "owner-tok"}).status_code == 200
    assert client.get("/accounts", headers={"Authorization": "Bearer admin-tok"}).status_code == 200
    assert client.get("/summary", headers={"Authorization": "Bearer ro-tok"}).status_code == 200
    assert client.get("/accounts", headers={"X-Clawback-Role-Token": "wrong"}).status_code == 401


def test_login_logout_and_me(site, monkeypatch):
    app, _, _ = site
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clawback.test")
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/auth/login", json={"email": DANA, "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@x.example", "password": "peak-pass"}).status_code == 401
    r = client.post("/auth/login", json={"email": " Dana@PeakBar.example ", "password": "peak-pass"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{users.COOKIE}=") and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Secure" in cookie  # PUBLIC_BASE_URL is https
    body = r.json()
    assert body["user"] == {"id": DANA, "email": DANA, "name": "Dana Okafor", "role": "admin"}
    assert body["supplier"]["id"] == "peak-bar" and body["supplier"]["name"] == "Peak Bar Co."
    me = client.get("/auth/me").json()
    assert me["user"]["email"] == DANA and me["supplier"]["account_ids"] == ["peak-bar"] and me["auth_required"]
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert client.get("/accounts").status_code == 401


def test_sessions_are_stored_hashed_and_expire(site, monkeypatch):
    app, _, _ = site
    user = users.find(DANA)
    token, session = users.start_session(user)
    assert token not in users._sessions and session.token_hash in users._sessions
    assert users.user_for(token) == user
    from datetime import datetime, timedelta, timezone

    users._sessions[session.token_hash] = users.Session(session.token_hash, user.id,
                                                         datetime.now(timezone.utc) - timedelta(seconds=1))
    assert users.user_for(token) is None and session.token_hash not in users._sessions
    assert b"peak-pass" not in user.password_hash and len(user.salt) == 16


def test_a_text_reaches_only_the_senders_supplier(site, monkeypatch):
    app, run, _ = site
    monkeypatch.setenv("DEMO_USER2_PHONE", "+15550002222")
    monkeypatch.setenv("OWNER_PHONE", "+15550001111")
    client = TestClient(app)
    r = client.post("/webhooks/twilio/sms", data={"From": "+15550002222", "Body": "YES"})
    assert "nothing waiting" in r.text  # Teresa's YES doesn't approve Peak Bar's memo
    assert not any(e.type == "ledger_post" for e in run.events)
    r = client.post("/webhooks/twilio/sms", data={"From": "+15550001111", "Body": "YES"})
    assert "Approved" in r.text


def test_an_open_laptop_stays_open(monkeypatch):
    from api.main import app

    users.reset()
    client = TestClient(app)
    assert client.get("/accounts").status_code == 200
    assert client.get("/auth/me").json() == {"user": None, "supplier": None, "auth_required": False}
    r = client.post("/auth/login", json={"email": "anyone", "password": "x"})
    assert r.status_code == 200 and r.json()["supplier"]["id"] == "peak-bar"
