"""A faster live run: documents read at once, charges' agents four at a time, and cache-first recordings. None of it
changes a request (recordings are keyed by its hash), a decision, or the order the board sees them in."""

import hashlib
import json
import time

import pytest

from api import pipeline
from api.agents import readers
from api.integrations import replay
from api.tests.test_pipeline import MARCH_FIRST, final
from api.tests.test_reader import RECORDED


class Offline:
    def with_options(self, **_):
        raise AssertionError("DEMO_MODE must not call out")


@pytest.fixture
def recorded(monkeypatch):
    """Peak Bar's committed recordings, replayed, with each answer arriving after its own short delay so the
    concurrent calls finish out of order."""
    load, sleep = replay.load_fixture, time.sleep

    def jittered(service, key, fixtures_dir=None):
        sleep(int(hashlib.sha256(key.encode()).hexdigest()[:2], 16) / 255 * 0.03)
        return load(service, key, fixtures_dir)

    pipeline.reset()
    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    monkeypatch.setattr(replay, "load_fixture", jittered)
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)  # the demo pacing delay; jittered keeps its own
    monkeypatch.setenv("DEMO_MODE", "true")
    yield
    pipeline.reset()


def _shape(run) -> list:
    """Every event the board gets, in order, without its clock times (and how long the run took) or the run's id."""
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if not k.endswith("at") and k != "seconds_to_decided"}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v

    return [(e.type, strip(json.loads(json.dumps(e.data.model_dump(mode="json")).replace(run.id, "RUN"))))
            for e in run.events]


def _march(monkeypatch, workers: int):
    monkeypatch.setattr(pipeline, "READ_WORKERS", workers)
    monkeypatch.setattr(pipeline, "CHECK_WORKERS", workers)
    pipeline.reset()
    return pipeline.start("march", Offline(), background=False)


def test_concurrent_run_streams_the_same_events_as_one_at_a_time(recorded, monkeypatch):
    one = _march(monkeypatch, 1)
    one_shape, one_final = _shape(one), final(one)
    four = _march(monkeypatch, 4)
    assert final(four) == one_final == MARCH_FIRST
    assert [cid for cid in four.shown] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert _shape(four) == one_shape


def test_reads_at_once_then_checked_in_order_match_reading_one_by_one(recorded):
    docs = pipeline.documents_of(pipeline.accounts.resolve(pipeline.accounts.DEFAULT))
    before, deal = [], []
    for doc_id in docs:  # what _read_terms did: each document read with the deal terms read before it
        m = readers.read_both(doc_id, base_terms=deal, client=Offline())
        before.append(m)
        if m.doc.kind == "deal":
            deal += m.terms
    deal = []
    for doc_id, b in zip(docs, before):
        m = readers.recheck(readers.read_both(doc_id, client=Offline()), deal)
        assert (m.terms, m.disagreements, m.unclear, m.models) == (b.terms, b.disagreements, b.unclear, b.models)
        assert (m.a.terms, m.b.terms) == (b.a.terms, b.b.terms)
        if m.doc.kind == "deal":
            deal += m.terms
    extension = next(t for b in before for t in b.terms if t.type == "amendment")
    assert extension.effective_from is not None  # dated from the deal's date_range, as before


# ---------------------------------------------------------------- cache-first

REQ = {"model": "m", "system": "s", "messages": [{"role": "user", "content": "read §3.1"}]}
RESP = {"terms": []}


class Live:
    def __init__(self, response=RESP):
        self.calls, self.response = 0, response

    def __call__(self, request, timeout):
        self.calls += 1
        return self.response


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAWBACK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLAWBACK_CACHE_FIRST", "1")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)
    image = tmp_path / "image"
    image.mkdir()
    return image


def call(fn, image, service="claude-reader"):
    return replay.call_outside(service, REQ, fn, fixtures_dir=image, delay=0)


def test_cache_first_replays_a_recording_without_calling_out(cache):
    key = replay.request_key("claude-reader", REQ)
    replay.save_fixture("claude-reader", key, REQ, {"terms": ["recorded"]}, cache)
    fn = Live()
    res = call(fn, cache)
    assert (res.response, res.source, fn.calls) == ({"terms": ["recorded"]}, "fixture", 0)


def test_cache_first_goes_live_once_and_saves_to_the_state_folder(cache, tmp_path):
    fn = Live()
    first = call(fn, cache)
    key = replay.request_key("claude-reader", REQ)
    saved = tmp_path / "state" / "fixtures" / "claude-reader" / f"{key}.json"
    assert (first.source, fn.calls) == ("live", 1) and saved.exists()
    assert not any(cache.iterdir())  # the image's recordings are never written
    again = call(fn, cache)
    assert (again.response, again.source, fn.calls) == (RESP, "fixture", 1)


def test_cache_first_reads_the_state_folder_before_the_image(cache):
    key = replay.request_key("claude-reader", REQ)
    replay.save_fixture("claude-reader", key, REQ, {"terms": ["image"]}, cache)
    replay.save_fixture("claude-reader", key, REQ, {"terms": ["state"]}, replay.cache_dir())
    assert call(Live(), cache).response == {"terms": ["state"]}


def test_cache_first_leaves_quickbooks_and_moss_live(cache):
    for service in ("qbo", "moss"):
        key = replay.request_key(service, REQ)
        replay.save_fixture(service, key, REQ, {"old": True}, cache)
        fn = Live()
        assert (call(fn, cache, service).source, fn.calls) == ("live", 1)
    assert not replay.cache_dir().exists()


def test_without_cache_first_nothing_changes(cache, monkeypatch):
    monkeypatch.delenv("CLAWBACK_CACHE_FIRST")
    key = replay.request_key("claude-reader", REQ)
    replay.save_fixture("claude-reader", key, REQ, {"terms": ["recorded"]}, cache)
    fn = Live()
    assert (call(fn, cache).source, fn.calls) == ("live", 1)  # live first, as always
    assert not replay.cache_dir().exists()
