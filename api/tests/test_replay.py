"""F11: outside calls get a timeout, one retry, record mode and the DEMO_MODE fixture fallback."""

import asyncio
import json
import time
from decimal import Decimal

import pytest

from api.integrations import replay as r

REQ = {"model": "m", "messages": [{"role": "user", "content": "read §3.1"}], "max_tokens": 100}
RESP = {"terms": [{"type": "promo_rate", "params": {"rate": "1.00"}}]}


class Fake:
    """A service that fails the first `fails` calls, or sleeps past the timeout."""

    def __init__(self, fails=0, sleep=0.0, response=RESP):
        self.calls, self.fails, self.sleep, self.response = 0, fails, sleep, response

    def __call__(self, request, timeout):
        self.calls += 1
        if self.sleep:
            time.sleep(self.sleep)
        if self.calls <= self.fails:
            raise ConnectionError("network down")
        return self.response


def call(fn, tmp_path, **kw):
    kw.setdefault("demo", False)
    kw.setdefault("record", False)
    kw.setdefault("delay", 0)
    return r.call_outside("claude", REQ, fn, fixtures_dir=tmp_path, **kw)


def test_key_ignores_dict_order_and_separates_services():
    shuffled = {"max_tokens": 100, "messages": REQ["messages"], "model": "m"}
    assert r.request_key("claude", REQ) == r.request_key("claude", shuffled)
    assert r.request_key("claude", REQ) != r.request_key("gemini", REQ)
    assert r.request_key("qbo", {"amount": Decimal("2730.00")}) == r.request_key("qbo", {"amount": Decimal("2730.00")})


def test_live_success_is_one_call(tmp_path):
    fn = Fake()
    res = call(fn, tmp_path)
    assert (res.response, res.source, res.attempts, fn.calls) == (RESP, "live", 1, 1)
    assert not any(tmp_path.iterdir())  # nothing recorded unless asked


def test_one_retry_then_success(tmp_path):
    fn = Fake(fails=1)
    res = call(fn, tmp_path)
    assert (res.source, res.attempts, fn.calls) == ("live", 2, 2)
    assert "ConnectionError" in res.errors[0]


def test_two_failures_fall_back_to_the_fixture(tmp_path):
    key = r.request_key("claude", REQ)
    r.save_fixture("claude", key, REQ, {"saved": True}, tmp_path, env={})
    fn = Fake(fails=5)
    res = call(fn, tmp_path)
    assert (res.response, res.source, fn.calls) == ({"saved": True}, "fixture", 2)


def test_two_failures_and_no_fixture_raise(tmp_path):
    with pytest.raises(r.OutsideCallFailed, match="live failed 2x"):
        call(Fake(fails=5), tmp_path)


def test_timeout_counts_as_a_failure(tmp_path):
    fn = Fake(sleep=0.3)
    with pytest.raises(r.OutsideCallFailed, match="TimeoutError"):
        call(fn, tmp_path, timeout=0.05)
    assert fn.calls == 2


def test_record_then_demo_mode_replays_without_calling(tmp_path):
    call(Fake(), tmp_path, record=True)
    saved = json.loads(r.fixture_path("claude", r.request_key("claude", REQ), tmp_path).read_text())
    assert saved["request"] == REQ and saved["response"] == RESP

    fn = Fake()
    res = call(fn, tmp_path, demo=True)
    assert (res.response, res.source, fn.calls) == (RESP, "fixture", 0)


def test_demo_mode_with_no_fixture_raises_instead_of_calling(tmp_path):
    fn = Fake()
    with pytest.raises(r.OutsideCallFailed, match="DEMO_MODE"):
        call(fn, tmp_path, demo=True)
    assert fn.calls == 0


def test_demo_mode_waits_so_cards_still_stream(tmp_path):
    call(Fake(), tmp_path, record=True)
    t = time.monotonic()
    call(Fake(), tmp_path, demo=True, delay=0.05)
    assert time.monotonic() - t >= 0.05


def test_live_first_tries_live_even_in_demo_mode(tmp_path):
    call(Fake(response={"old": 1}), tmp_path, record=True)
    fn = Fake(response={"new": 1})
    res = call(fn, tmp_path, demo=True, live_first=True)
    assert (res.response, res.source, fn.calls) == ({"new": 1}, "live", 1)
    res = call(Fake(fails=5), tmp_path, demo=True, live_first=True)
    assert (res.response, res.source) == ({"old": 1}, "fixture")


def test_live_first_uses_the_20_second_timeout(tmp_path, monkeypatch):
    seen = []
    call(lambda req, timeout: seen.append(timeout) or RESP, tmp_path, live_first=True)
    call(lambda req, timeout: seen.append(timeout) or RESP, tmp_path)
    assert seen == [20.0, 30.0]


def test_recording_refuses_a_secret_from_the_environment(tmp_path):
    env = {"ANTHROPIC_API_KEY": "sk-ant-not-a-real-key-123", "DEMO_MODE": "true"}
    with pytest.raises(r.SecretInFixture):
        r.save_fixture("claude", "k", {"auth": "sk-ant-not-a-real-key-123"}, RESP, tmp_path, env=env)
    assert not r.fixture_path("claude", "k", tmp_path).exists()
    r.save_fixture("claude", "k", REQ, RESP, tmp_path, env=env)  # flags like DEMO_MODE aren't secrets


def test_env_flags(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("RECORD_FIXTURES", "0")
    assert r.demo_mode() and not r.recording()
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    assert not r.demo_mode() and r.recording()


def test_async_version_has_the_same_rules(tmp_path):
    calls = []

    async def flaky(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("down")
        return RESP

    async def slow(request, timeout):
        await asyncio.sleep(1)

    res = asyncio.run(r.acall_outside("claude", REQ, flaky, fixtures_dir=tmp_path, demo=False, record=True, delay=0))
    assert (res.source, res.attempts) == ("live", 2)
    res = asyncio.run(r.acall_outside("claude", REQ, slow, fixtures_dir=tmp_path, demo=False, record=False,
                                      timeout=0.05, delay=0))
    assert (res.response, res.source, res.attempts) == (RESP, "fixture", 2)
