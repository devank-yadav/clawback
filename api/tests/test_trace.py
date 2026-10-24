"""GET /runs/{id}/trace: every AI and outside call a run makes, recorded by replay.call_outside (api/trace.py).

The pipeline doesn't enter the trace contexts yet (Devank wires them after merging), so the `wired` fixture enters
them where api/trace.py's docstring says the pipeline will: the run's thread (_guarded), the owner's answer, the
gate's per-charge decision, and a ContextPool for the two readers.
"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import pipeline, trace
from api.agents import claude, investigator, reader_b, readers
from api.agents.investigator import LLMFinding
from api.integrations import moss, replay
from api.main import app
from api.tests.test_moss import FakeMoss
from api.tests.test_pipeline import MARCH_FIRST, ScenarioClaude, final
from api.tests.test_reader import SPRING, answer

http = TestClient(app)
READERS = {"Deal reader (Claude)", "Deal reader (second Claude read)"}


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset(), trace.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)  # DEMO_MODE's pacing delay
    monkeypatch.setattr(moss, "_built", {})
    yield
    pipeline.reset(), trace.reset()


@pytest.fixture
def wired(monkeypatch):
    """The contexts, entered where the pipeline will enter them."""
    guarded, answer, decide = pipeline._guarded, pipeline.answer, pipeline._decide

    def run_thread(run, client):
        with trace.run_context(run.id):
            guarded(run, client)

    def owner_answer(question_id, *args, **kwargs):
        with trace.run_context(pipeline.QUESTIONS[question_id][0]):
            return answer(question_id, *args, **kwargs)

    def per_charge(run, charge_id, policy):
        with trace.charge_context(charge_id):
            return decide(run, charge_id, policy)

    monkeypatch.setattr(pipeline, "_guarded", run_thread)
    monkeypatch.setattr(pipeline, "answer", owner_answer)
    monkeypatch.setattr(pipeline, "_decide", per_charge)
    monkeypatch.setattr(readers, "ThreadPoolExecutor", trace.ContextPool)


def flow(entries):
    return [(e.agent, e.charge_id) for e in entries]


# ---------------------------------------------------------------- a whole run


def test_march_trace_lists_every_ai_call_in_order(wired):
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    t = trace.trace_for(run.id)
    assert len(t) == len(fake.calls) == 16 and [e.seq for e in t] == list(range(1, 17))
    assert all(e.run_id == run.id and e.status == "live" and e.attempts == 1 and e.error is None for e in t)
    assert all(e.model == claude.MODEL and isinstance(e.at, datetime) and e.latency_ms >= 0 for e in t)

    # Both readers on each deal document, one document after the other (the two of a pair run side by side).
    reads, rest = t[:6], t[6:]
    for n, doc in enumerate(pipeline.DEAL_DOCS):
        pair = reads[2 * n:2 * n + 2]
        assert {e.agent for e in pair} == READERS and {e.input["doc_id"] for e in pair} == {doc}
        assert all(e.charge_id is None and e.output["terms"] for e in pair)
    # Then each charge in turn: the Investigator, and the comeback for every charge it would dispute.
    expected = []
    for cid in run.charges:
        expected += [("Investigator", cid)] + ([("Negotiator: comeback", cid)] if cid in run.rehearsals else [])
    assert flow(rest) == expected
    assert sorted(run.rehearsals) == ["C1", "C2", "C4", "C5"]

    # What the trace shows is what the Investigator was sent (the engine's numbers) and what it answered.
    for e in (e for e in rest if e.agent == "Investigator"):
        sent, f, a = json.loads(e.input["user"]), run.findings[e.charge_id], run.allowances[e.charge_id]
        assert sent["charge"]["id"] == e.charge_id == e.input["charge_id"]
        assert (sent["engine"]["allowed"], sent["engine"]["taken"]) == (str(a.allowed), str(a.taken))
        assert e.output["finding"] == f.finding and e.output["evidence_ids"] == f.evidence_ids
        assert e.input["system"] == investigator.PROMPT
        assert e.prompt.startswith("api/agents/prompts/investigator.md: You are the Investigator for Clawback.")


def test_route_serves_the_trace_and_filters_by_charge(wired):
    run = pipeline.start("march", ScenarioClaude(), background=False)
    r = http.get(f"/runs/{run.id}/trace")
    assert r.status_code == 200
    body = r.json()
    assert [e["seq"] for e in body] == list(range(1, 17))
    assert set(body[0]) == {"seq", "at", "agent", "service", "run_id", "charge_id", "model", "prompt", "input",
                            "output", "latency_ms", "status", "attempts", "error", "usage"}
    c1 = http.get(f"/runs/{run.id}/trace", params={"charge_id": "C1"}).json()
    assert [(e["agent"], e["charge_id"]) for e in c1] == [("Investigator", "C1"), ("Negotiator: comeback", "C1")]
    c3 = http.get(f"/runs/{run.id}/trace", params={"charge_id": "C3"}).json()
    assert [e["agent"] for e in c3] == ["Investigator"]  # C3 is fair: nothing to rehearse
    assert http.get(f"/runs/{run.id}/trace", params={"charge_id": "C9"}).json() == []
    assert http.get("/runs/run-march-nope/trace").status_code == 404


def test_charge_context_names_the_charge_of_calls_that_dont_carry_one(wired, monkeypatch):
    """Moss's requests name no charge: the per-charge context does. April: one Investigator and one Moss search each."""
    monkeypatch.setattr(moss, "MEMORY", moss.RuleMemory(lambda: FakeMoss()))
    fake = ScenarioClaude()
    march = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(march.questions)), "accept if notice is at least 14 days", client=fake)
    after_answer = [e for e in trace.trace_for(march.id) if e.seq > 16]
    assert flow(after_answer) == [("Rule memory (Moss)", None), ("Rule memory (Moss)", "C6")]
    assert [e.prompt for e in after_answer] == ["Moss upsert", "Moss query"] and after_answer[0].model is None

    april = pipeline.start("april", fake, background=False)
    assert flow(trace.trace_for(april.id)[6:]) == [("Investigator", "A1"), ("Rule memory (Moss)", "A1"),
                                                   ("Investigator", "A2"), ("Rule memory (Moss)", "A2")]
    query = trace.trace_for(april.id, "A1")[1]
    assert query.input["op"] == "query" and query.output[0]["id"] == "rule-1"
    assert all(d.rule_id == "rule-1" for d in april.shown.values())


def test_an_answer_code_cant_read_goes_to_the_rule_writer_and_shows(wired):
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    _, rule = pipeline.answer(next(iter(run.questions)), "ok when the heads-up is a fortnight or more", client=fake)
    (e,) = trace.trace_for(run.id, "C6")[1:]  # after C6's Investigator
    assert (e.agent, e.service, e.status) == ("Rule writer", "claude-rule-writer", "live")
    assert "ok when the heads-up is a fortnight or more" in e.input["user"]
    assert (e.output["fact"], e.output["op"], e.output["value"]) == ("notice_days", ">=", 14)
    assert rule.condition == "notice_days >= 14"  # the rule saved is the one the trace shows, checked by code


# ---------------------------------------------------------------- failed, retried, live, recorded


class FailingClaude(ScenarioClaude):
    """The Investigator call for C2 never answers; one other answer cites a number nobody gave it, once."""

    def __init__(self):
        super().__init__()
        self.invented = False

    def _finding(self, user):
        sent = user.split("\n\nYour previous answer")[0]  # a retry repeats the request, then the error
        payload = json.loads(sent)
        if payload["charge"]["id"] == "C2":
            raise ConnectionError("Claude is unreachable")
        out = super()._finding(sent)
        if payload["charge"]["id"] == "C4" and not self.invented:
            self.invented = True
            out["finding"] = "Northmart took 9,999 bars more than the cap."
        return out


def test_a_failed_call_is_recorded_with_its_error(wired):
    run = pipeline.start("march", FailingClaude(), background=False)
    (failed,) = trace.trace_for(run.id, "C2")
    assert (failed.agent, failed.status, failed.attempts, failed.output) == ("Investigator", "failed", 2, None)
    assert failed.error == ("ConnectionError: Claude is unreachable; ConnectionError: Claude is unreachable; "
                            "no recorded answer to fall back on")
    assert run.shown["C2"].decision == "ask"  # no explanation, so a person decides


def test_a_validation_retry_is_its_own_entry(wired):
    run = pipeline.start("march", FailingClaude(), background=False)
    first, second = [e for e in trace.trace_for(run.id, "C4") if e.agent == "Investigator"]
    assert "9,999" in first.output["finding"] and first.status == "live"
    assert "Your previous answer failed validation" in second.input["user"] and "9999" in second.input["user"]
    assert second.output["finding"] == run.findings["C4"].finding


def test_recorded_answers_are_marked_recorded(wired, monkeypatch):
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    live = pipeline.start("march", ScenarioClaude(), background=False)
    monkeypatch.delenv("RECORD_FIXTURES")
    monkeypatch.setenv("DEMO_MODE", "true")

    class NoCalls:
        def with_options(self, **_):
            raise AssertionError("DEMO_MODE must not call Claude")

    replayed = pipeline.start("march", NoCalls(), background=False)
    a, b = trace.trace_for(live.id), trace.trace_for(replayed.id)
    assert {e.status for e in a} == {"live"} and {e.status for e in b} == {"recorded"}
    assert all(e.attempts == 0 for e in b)
    key = lambda e: (e.agent, e.charge_id, e.input.get("doc_id"))  # noqa: E731 - the readers finish in either order
    assert sorted((key(e), json.dumps(e.output, sort_keys=True)) for e in a) == \
           sorted((key(e), json.dumps(e.output, sort_keys=True)) for e in b)


def test_live_first_falls_back_to_the_recording_and_says_why(tmp_path):
    req = {"model": "m", "system": "s", "user": "u"}
    replay.save_fixture("claude-portal-reply", replay.request_key("claude-portal-reply", req), req, {"ok": 1}, tmp_path)

    def down(_req, _timeout):
        raise TimeoutError("no answer in 20s")

    with trace.run_context("run-x"):
        res = replay.call_outside("claude-portal-reply", req, down, live_first=True, demo=True, fixtures_dir=tmp_path)
    (e,) = trace.trace_for("run-x")
    assert (res.source, e.status, e.attempts, e.output) == ("fixture", "recorded", 2, {"ok": 1})
    assert e.error == "TimeoutError: no answer in 20s; TimeoutError: no answer in 20s"
    assert e.agent == "Negotiator: portal reply"


# ---------------------------------------------------------------- outside a run, and call_outside unchanged


def test_nothing_outside_a_run_context_is_recorded(tmp_path):
    run = pipeline.start("march", ScenarioClaude(), background=False)  # no contexts entered
    assert trace.trace_for(run.id) == [] and not trace.known(run.id) and not trace._store
    assert http.get(f"/runs/{run.id}/trace").json() == []  # a known run that recorded nothing
    with trace.charge_context("C1"):  # a charge with no run isn't enough
        replay.call_outside("claude-investigator", {"x": 1}, lambda r, t: {"ok": True}, fixtures_dir=tmp_path)
    assert not trace._store


def _ok(req, _timeout):
    return {"terms": [], "echo": req}


def _flaky():
    calls = {"n": 0}

    def fn(req, _timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("blip")
        return {"n": calls["n"]}
    return fn


def _down(_req, _timeout):
    raise ConnectionError("down")


CASES = {
    "answered": dict(fn=lambda: _ok),
    "retried": dict(fn=_flaky),
    "live failed, recording": dict(fn=lambda: _down, saved=True),
    "live failed, nothing saved": dict(fn=lambda: _down),
    "demo, recording": dict(fn=lambda: _down, demo=True, saved=True),
    "demo, nothing saved": dict(fn=lambda: _down, demo=True),
}


def _outcome(case, tmp_path, ctx):
    req = {"model": "m", "system": "System line\nmore", "user": "hello", "charge_id": "C1"}
    if case.get("saved"):
        replay.save_fixture("claude-investigator", replay.request_key("claude-investigator", req), req, {"saved": 1},
                            tmp_path)
    try:
        with ctx:
            r = replay.call_outside("claude-investigator", req, case["fn"](), demo=case.get("demo", False),
                                    record=False, fixtures_dir=tmp_path)
        r.latency_ms = 0
        return ("ok", r)
    except Exception as e:  # noqa: BLE001
        return ("raised", type(e), str(e))


@pytest.mark.parametrize("name", CASES)
def test_call_outside_behaves_exactly_as_before(name, tmp_path, monkeypatch):
    case = CASES[name]
    without = _outcome(case, tmp_path, trace.charge_context("C1"))
    with_trace = _outcome(case, tmp_path, trace.run_context("run-x"))
    assert with_trace == without
    (e,) = trace.trace_for("run-x")
    assert e.status == ("failed" if without[0] == "raised" else "live" if without[1].source == "live" else "recorded")
    assert (e.agent, e.charge_id, e.prompt) == ("Investigator", "C1", "claude-investigator: System line")

    def broken(*_a, **_k):
        raise RuntimeError("trace store broken")

    monkeypatch.setattr(trace, "record", broken)  # a broken trace changes nothing either
    assert _outcome(case, tmp_path, trace.run_context("run-y")) == without


def test_the_response_is_the_callers_own_object(tmp_path, monkeypatch):
    answer = {"terms": [{"type": "unit_cap"}]}
    with trace.run_context("run-x"):
        r = replay.call_outside("claude-reader", {"user": "u"}, lambda req, t: answer, fixtures_dir=tmp_path)
    assert r.response is answer
    trace.trace_for("run-x")[0].output["terms"].append("changed in the trace")
    assert answer == {"terms": [{"type": "unit_cap"}]}

    monkeypatch.setattr(trace, "_clean", lambda *a: 1 / 0)  # recording fails inside: no entry, same answer
    with trace.run_context("run-y"):
        r = replay.call_outside("claude-reader", {"user": "u"}, lambda req, t: answer, fixtures_dir=tmp_path)
    assert r.response is answer and trace.trace_for("run-y") == []


def test_async_calls_are_recorded_too(tmp_path):
    async def fn(req, timeout):
        return {"ok": True}

    async def go():
        with trace.run_context("run-x"):
            return await replay.acall_outside("moss", {"op": "query", "text": "t"}, fn, fixtures_dir=tmp_path)

    assert asyncio.run(go()).response == {"ok": True}
    (e,) = trace.trace_for("run-x")
    assert (e.agent, e.prompt, e.status, e.output) == ("Rule memory (Moss)", "Moss query", "live", {"ok": True})


# ---------------------------------------------------------------- secrets, size, threads


def _rejected(_req, _timeout):
    raise ValueError("token nessie-secret-123456 rejected")


def test_secrets_never_reach_the_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("NESSIE_API_KEY", "nessie-secret-123456")
    req = {"model": "m", "system": "s", "api_key": "abc12345678", "user": "key nessie-secret-123456, "
           "sk-ant-api03-abcdefghijkl, AIzaSyA1234567890abcdefghijklmn, Authorization: Bearer eyJhbGciOi.abc.def"}
    answer = {"echo": "nessie-secret-123456"}
    with trace.run_context("run-x"):
        r = replay.call_outside("claude-reader", req, lambda q, t: answer, fixtures_dir=tmp_path)
        with pytest.raises(replay.OutsideCallFailed):
            replay.call_outside("qbo", {"method": "GET", "path": "/query"}, _rejected, fixtures_dir=tmp_path)
    stored = json.dumps([e.model_dump(mode="json") for e in trace.trace_for("run-x")])
    for secret in ("nessie-secret-123456", "abc12345678", "sk-ant-api03", "AIzaSyA", "eyJhbGciOi"):
        assert secret not in stored
    assert stored.count("[redacted]") >= 7
    assert r.response is answer and answer["echo"] == "nessie-secret-123456"  # the call itself is untouched
    assert trace.trace_for("run-x")[1].prompt == "QuickBooks GET /query"


def test_the_trace_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(trace, "MAX_PER_RUN", 3)
    monkeypatch.setattr(trace, "MAX_RUNS", 2)
    with trace.run_context("run-a"):
        for n in range(5):
            assert replay.call_outside("moss", {"op": "query", "n": n}, _ok, fixtures_dir=tmp_path).source == "live"
    assert [e.input["n"] for e in trace.trace_for("run-a")] == [0, 1, 2]
    for run_id in ("run-b", "run-c"):
        with trace.run_context(run_id):
            replay.call_outside("moss", {"op": "query"}, _ok, fixtures_dir=tmp_path)
    assert not trace.known("run-a") and trace.known("run-b") and trace.known("run-c")
    big = "x" * (trace.MAX_TEXT + 10)
    with trace.run_context("run-c"):
        replay.call_outside("claude-coach", {"user": big}, _ok, fixtures_dir=tmp_path)
    assert trace.trace_for("run-c")[-1].input["user"].endswith("... [cut 10 characters]")


def test_context_pool_carries_the_run_into_its_threads(tmp_path):
    def call(n):
        return replay.call_outside("claude-reader", {"n": n}, _ok, fixtures_dir=tmp_path)

    with trace.run_context("run-x"):
        with ThreadPoolExecutor(max_workers=2) as pool:  # a new thread starts with no context
            [f.result() for f in [pool.submit(call, 1), pool.submit(call, 2)]]
        assert trace.trace_for("run-x") == []
        with trace.ContextPool(max_workers=2) as pool:
            [f.result() for f in [pool.submit(call, 3), pool.submit(call, 4)]]
    assert sorted(e.input["n"] for e in trace.trace_for("run-x")) == [3, 4]
    assert trace.current_run() is None


def test_every_service_has_a_plain_name():
    services = {"claude-reader", "gemini-reader", "claude-reader-b", "claude-investigator", "claude-rehearsal",
                "claude-portal-reply", "claude-coach", "claude-rule-writer", "moss", "qbo"}
    assert set(trace.AGENTS) == services
    assert {d.name for d in (replay.ROOT / "data" / "fixtures").iterdir() if d.is_dir()} <= services


# ---------------------------------------------------------------- tokens, the summary, and a model per agent


class MeteredClaude(ScenarioClaude):
    """ScenarioClaude whose answers report their tokens and model, as the API's do: 1,000 in and 200 out each."""

    def _parse(self, output_format, messages, **kw):
        resp = super()._parse(output_format=output_format, messages=messages, **kw)
        resp.model = kw["model"]
        resp.usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=None,
                                     cache_read_input_tokens=None, cache_creation=None, speed=None,
                                     inference_geo="global")
        return resp


class MeteredGemini:
    """Stands in for google.genai.Client: reads the Spring deal and reports 900 prompt, 150 answer, 50 thinking."""

    def __init__(self):
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, **_):
        usage = SimpleNamespace(prompt_token_count=900, candidates_token_count=150, thoughts_token_count=50)
        return SimpleNamespace(text=json.dumps(answer(SPRING)), usage_metadata=usage, model_version=model)


def test_live_calls_carry_their_tokens_and_recordings_dont(wired, monkeypatch):
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    live = pipeline.start("march", MeteredClaude(), background=False)
    assert final(live) == MARCH_FIRST  # the answers the agents got are the same
    t = trace.trace_for(live.id)
    assert all(e.usage == {"input_tokens": 1000, "output_tokens": 200} and e.model == claude.MODEL for e in t)
    for f in replay.FIXTURES.glob("*/*.json"):  # what's recorded is the answer alone
        assert "usage" not in json.loads(f.read_text())["response"]
    monkeypatch.delenv("RECORD_FIXTURES")
    monkeypatch.setenv("DEMO_MODE", "true")
    replayed = pipeline.start("march", MeteredClaude(), background=False)
    assert final(replayed) == MARCH_FIRST and all(e.usage is None for e in trace.trace_for(replayed.id))


def test_summary_adds_up_calls_tokens_time_and_cost(wired):
    run = pipeline.start("march", MeteredClaude(), background=False)
    s = http.get(f"/runs/{run.id}/trace/summary").json()
    assert (s["calls"], s["live"], s["recorded"], s["failed"], s["metered_calls"]) == (16, 16, 0, 0, 16)
    assert (s["input_tokens"], s["output_tokens"], s["cache_write_tokens"], s["cache_read_tokens"]) == (16000, 3200, 0, 0)
    # Opus 5.5 at $4 in and $20 out per million tokens: each call 1,000 x $4 + 200 x $20 = $0.008
    assert s["cost_usd"] == 0.128 and s["unpriced_models"] == []
    assert "https://platform.claude.com/docs/en/about-claude/pricing" in s["pricing_sources"]
    rows = {(r["agent"], r["model"]): (r["calls"], r["input_tokens"], r["cost_usd"]) for r in s["by_agent"]}
    assert rows == {("Deal reader (Claude)", "claude-opus-5-5"): (3, 3000, 0.024),
                    ("Deal reader (second Claude read)", "claude-opus-5-5"): (3, 3000, 0.024),
                    ("Investigator", "claude-opus-5-5"): (6, 6000, 0.048),
                    ("Negotiator: comeback", "claude-opus-5-5"): (4, 4000, 0.032)}
    events = run.events_after(0)
    decided = next(e.at for e in events if e.type == "run" and e.data.status == "waiting")
    assert s["wall_ms"] == int((decided - events[0].at).total_seconds() * 1000)
    assert s["ai_ms"] == sum(e.latency_ms for e in trace.trace_for(run.id))
    assert http.get("/runs/run-march-nope/trace/summary").status_code == 404


def test_a_model_without_a_price_shows_tokens_and_no_cost(monkeypatch):
    monkeypatch.setattr(readers, "ThreadPoolExecutor", trace.ContextPool)
    with trace.run_context("run-x"):
        readers.read_both("spring-promo", client=MeteredClaude(), gemini=MeteredGemini())
    gemini = next(e for e in trace.trace_for("run-x") if e.agent == "Deal reader (Gemini)")
    assert gemini.model == "gemini-3.6-flash" and gemini.usage == {"input_tokens": 900, "output_tokens": 200,
                                                                   "thinking_tokens": 50}
    s = trace.summarize("run-x")
    assert (s.input_tokens, s.output_tokens, s.cost_usd, s.unpriced_models) == (1900, 400, None, ["gemini-3.6-flash"])
    claude_row = next(r for r in s.by_agent if r.agent == "Deal reader (Claude)")
    assert claude_row.cost_usd == 0.008 and s.wall_ms is None  # priced where it can be; no run events here


def test_call_cost_follows_the_price_table():
    models, _ = trace.load_pricing()
    opus = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_write_tokens": 10_000,
            "cache_write_1h_tokens": 10_000, "cache_read_tokens": 100_000}
    # $4 + $2 output + $0.05 5-minute writes + $0.08 1-hour writes + $0.02 cache reads
    assert trace.call_cost("claude-opus-5-5", opus, models) == Decimal("6.15")
    short = {"input_tokens": 90_000, "output_tokens": 1_000, "cache_read_tokens": 10_000}
    long = {"input_tokens": 90_000, "output_tokens": 1_000, "cache_read_tokens": 10_001}  # the prompt passes 100,000
    # up to 100,000: $0.009 in + $0.0005 out + $0.0001 cache reads; over it every token pays the higher price
    assert trace.call_cost("claude-haiku-5-5", short, models) == Decimal("0.0096")
    assert trace.call_cost("claude-haiku-5-5", long, models) == Decimal("0.04800005")
    assert trace.call_cost("claude-opus-5-5", {**short, "speed": "fast"}, models) is None
    assert trace.call_cost("claude-opus-5-5", {**short, "inference_geo": "us"}, models) is None
    assert trace.call_cost("gemini-3.6-flash", short, models) is None  # no price copied yet
    assert trace.call_cost("claude-opus-5-5", None, models) is None
    priced = {"gemini-3.6-flash": {"input": "1", "output": "2"}}
    assert trace.call_cost("gemini-3.6-flash-001", {"input_tokens": 1_000_000}, priced) == Decimal(1)
    assert trace.call_cost("gemini-3.6-flash", {"cache_read_tokens": 5}, priced) is None  # no cache_read price


def test_each_price_names_its_source():
    models, sources = trace.load_pricing()
    assert sources and all(s.startswith("https://") for s in sources)
    assert models["claude-opus-5-5"] == {"input": 4, "output": 20, "cache_write_5m": 5, "cache_write_1h": 8,
                                         "cache_read": 0.20}
    assert claude.MODEL in models and reader_b.DEFAULT_GEMINI_MODEL in models


def test_a_model_per_agent_and_the_default_unchanged(wired, monkeypatch):
    for service in claude.MODEL_ENV:
        assert claude.model_for(service) == claude.MODEL  # unset: every request, so every recording's key, as before
    monkeypatch.setenv("CLAWBACK_MODEL_INVESTIGATOR", " claude-sonnet-5-5 ")
    monkeypatch.setenv("CLAWBACK_MODEL_READER", "")
    fake = MeteredClaude()
    run = pipeline.start("march", fake, background=False)
    assert final(run) == MARCH_FIRST
    models = {(e.agent, e.input["model"]) for e in trace.trace_for(run.id)}
    assert models == {("Deal reader (Claude)", "claude-opus-5-5"), ("Deal reader (second Claude read)", "claude-opus-5-5"),
                      ("Investigator", "claude-sonnet-5-5"), ("Negotiator: comeback", "claude-opus-5-5")}
    s = trace.summarize(run.id)  # Sonnet 5.5 at $2 / $10: 6 x $0.004, plus 10 Opus calls x $0.008
    assert s.cost_usd == 0.104 and s.unpriced_models == []
    monkeypatch.setenv("CLAWBACK_MODEL_READER", "claude-haiku-5-5")
    assert claude.model_for("claude-reader") == claude.model_for("claude-reader-b") == "claude-haiku-5-5"
