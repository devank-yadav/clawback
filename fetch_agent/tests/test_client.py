"""The client: the two calls, the bearer token, 10 s timeout, one retry, and no retry that could repeat an answer."""

import json

import httpx
import pytest

from fetch_agent.client import ClawbackClient, ClawbackError
from fetch_agent.tests.conftest import load

BASE = "https://clawback.example/api"


def client_with(*replies):
    """Each reply is an httpx.Response or an exception to raise; calls is every request made."""
    calls, queue = [], list(replies)

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        nxt = queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    http = httpx.Client(base_url=BASE, transport=httpx.MockTransport(handle), timeout=10.0)
    return ClawbackClient(BASE, "ro-token", http=http), calls


def ok(body: dict) -> httpx.Response:
    return httpx.Response(200, json=body)


def test_summary_sends_the_read_only_token_under_the_api_prefix():
    c, calls = client_with(ok(load("summary-question.json")))
    s = c.summary()
    assert (calls[0].method, str(calls[0].url)) == ("GET", f"{BASE}/summary")
    assert calls[0].headers["Authorization"] == "Bearer ro-token"
    assert s.pending_question.id == "Q-1" and str(s.totals.taken) == "6850.0"


def test_answer_posts_the_text_as_the_owner_without_the_token():
    c, calls = client_with(ok(load("answer-rule.json")))
    resp = c.answer("Q-1", "accept if notice is at least 14 days")
    assert (calls[0].method, str(calls[0].url)) == ("POST", f"{BASE}/questions/Q-1/answer")
    assert json.loads(calls[0].content) == {"text": "accept if notice is at least 14 days", "from_role": "owner"}
    assert "Authorization" not in calls[0].headers
    assert (resp.rule.label, resp.rule.status) == ("Rule #1", "active")


def test_default_client_uses_a_10_second_timeout_and_the_base_path():
    c = ClawbackClient(BASE + "/", "t")
    assert c.http.timeout == httpx.Timeout(10.0) and str(c.http.base_url) == BASE + "/"


def test_summary_retries_once_on_a_network_error_or_5xx():
    c, calls = client_with(httpx.ReadTimeout("slow"), ok(load("summary-question.json")))
    assert c.summary().run_id and len(calls) == 2
    c, calls = client_with(httpx.Response(502), ok(load("summary-question.json")))
    assert c.summary().run_id and len(calls) == 2


def test_summary_gives_up_after_the_retry():
    c, calls = client_with(httpx.ConnectError("down"), httpx.ConnectError("down"))
    with pytest.raises(ClawbackError) as e:
        c.summary()
    assert e.value.status is None and len(calls) == 2
    c, calls = client_with(httpx.Response(500), httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(ClawbackError) as e:
        c.summary()
    assert (e.value.status, e.value.detail, len(calls)) == (500, "boom", 2)


def test_answer_retries_only_when_the_request_never_left():
    c, calls = client_with(httpx.ConnectError("refused"), ok(load("answer-once.json")))
    assert c.answer("Q-2", "ACCEPT").answer.question_id == "Q-2" and len(calls) == 2
    # It may have gone through: sending it again could undo a second rule.
    for lost in (httpx.ReadTimeout("no reply"), httpx.Response(500)):
        c, calls = client_with(lost, ok(load("answer-undo.json")))
        with pytest.raises(ClawbackError):
            c.answer("Q-1", "UNDO")
        assert len(calls) == 1


def test_errors_carry_the_status_and_the_apis_detail():
    detail = "Q-3 closed: run run-march-8abbaa92 replaced run-march-6a62636f; answer the newer run's question"
    c, _ = client_with(httpx.Response(409, json={"detail": detail}))
    with pytest.raises(ClawbackError) as e:
        c.answer("Q-3", "ACCEPT")
    assert (e.value.status, e.value.detail) == (409, detail)
    c, _ = client_with(httpx.Response(401, json={"detail": "bad token"}))
    with pytest.raises(ClawbackError) as e:
        c.summary()
    assert (e.value.status, e.value.detail) == (401, "bad token")
    c, _ = client_with(httpx.Response(502, text="Bad Gateway"), httpx.Response(502, text="Bad Gateway"))
    with pytest.raises(ClawbackError) as e:
        c.summary()
    assert (e.value.status, e.value.detail) == (502, "Bad Gateway")


def test_question_ids_are_escaped_in_the_path():
    c, calls = client_with(ok(load("answer-once.json")))
    c.answer("Q/../1", "ACCEPT")
    assert calls[0].url.raw_path == b"/api/questions/Q%2F..%2F1/answer"
