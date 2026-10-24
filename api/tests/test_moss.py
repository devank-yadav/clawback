"""F16: saved rules matched with Moss semantic search, so a differently worded discretion clause still finds Rule #1.
The exact match on clause type + counterparty stays the fallback. A fake Moss here, never the network."""

import asyncio
import inspect
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from api import pipeline
from api.engine import types as eng
from api.integrations import moss, replay
from api.tests.test_coach_scenario import CoachClaude, example
from api.tests.test_pipeline import ScenarioClaude, final, logs
from api.tests.test_reader import S54

REWORDED = ("Northmart may, in its sole judgment, charge a display fee of up to $1,500 a month once it has told "
            "Supplier in writing.")
ANSWER = "accept if notice is at least 14 days"
APRIL = {"A1": ("accept", D(0), D(1200)), "A2": ("dispute", D(800), D(0))}


class FakeMoss:
    """Moss in memory: the same wording scores 1.0, any other wording `score`. fail=True: every call raises."""

    def __init__(self, score=0.9, fail=False):
        self.docs: dict[str, tuple[str, dict]] = {}
        self.calls: list[tuple[str, str]] = []
        self.score, self.fail = score, fail

    def _call(self, op, arg):
        self.calls.append((op, arg))
        if self.fail:
            raise ConnectionError("Moss is down")

    def upsert(self, doc_id, text, metadata):
        self._call("upsert", doc_id)
        self.docs[doc_id] = (text, metadata)

    def delete(self, doc_ids):
        self._call("delete", ",".join(doc_ids))
        for i in doc_ids:
            self.docs.pop(i, None)

    def query(self, text, top_k):
        self._call("query", text)
        return [{"id": i, "score": 1.0 if t == text else self.score} for i, (t, _) in list(self.docs.items())[:top_k]]


class NoCalls:
    def __getattr__(self, name):
        raise AssertionError("DEMO_MODE must not call Moss")


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)
    monkeypatch.setattr(moss, "_built", {})
    yield
    pipeline.reset()


def use(monkeypatch, backend):
    monkeypatch.setattr(moss, "MEMORY", moss.RuleMemory(lambda: backend))
    return backend


def reword_april(monkeypatch):
    """April's deal states the display-fee clause in other words; the charges, notices and math are unchanged."""
    real = pipeline.compute_allowed

    def allowed(charge, terms, sales, payments, ops=None, fees=None):
        a = real(charge, terms, sales, payments, ops=ops, fees=fees)
        if not charge.id.startswith("A"):
            return a
        return replace(a, terms=tuple(replace(t, exact_quote=REWORDED) if t.type == eng.TermType.FEE_DISCRETION else t
                                      for t in a.terms))

    monkeypatch.setattr(pipeline, "compute_allowed", allowed)


def march_with_rule_1(client):
    march = pipeline.start("march", client, background=False)
    pipeline.answer(next(iter(march.questions)), ANSWER, client=client)
    return march


def applied(run, charge_id, how):
    rule = pipeline.RULES[0]
    return (f"Applied Rule #1 (learned {pipeline.evidence_mod.day(rule.learned_at)}, approved by Dana; {how}) to "
            f"{charge_id}.") in logs(run)


# ---------------------------------------------------------------- the run

def test_reworded_april_clause_matches_rule_1_with_zero_questions(monkeypatch):
    backend = use(monkeypatch, FakeMoss(score=0.9))
    fake = ScenarioClaude()
    march = pipeline.start("march", fake, background=False)
    assert backend.calls == []  # no saved rule yet, so Moss isn't asked and C6 goes to Dana
    pipeline.answer(next(iter(march.questions)), ANSWER, client=fake)
    assert backend.docs == {"rule-1": (S54, {"term_type": "fee_discretion", "counterparty": "Northmart", "label": "Rule #1"})}
    assert "Indexed Rule #1 in Moss, so a differently worded clause still finds it." in logs(march)
    assert march.decisions["C6"].rule_similarity == D("1.0") and applied(march, "C6", "matched by Moss, similarity 1.00")

    reword_april(monkeypatch)
    april = pipeline.start("april", fake, background=False)
    assert final(april) == APRIL and not april.questions
    assert ("query", REWORDED) in backend.calls
    assert all(d.rule_id == "rule-1" and d.rule_similarity == D("0.9") for d in april.decisions.values())
    assert applied(april, "A1", "matched by Moss, similarity 0.90") and applied(april, "A2", "matched by Moss, similarity 0.90")
    assert any(t.startswith("0 questions asked") for t in logs(april))


def test_a_weak_match_does_not_apply_so_the_exact_match_decides(monkeypatch):
    use(monkeypatch, FakeMoss(score=0.7))
    fake = ScenarioClaude()
    march_with_rule_1(fake)
    reword_april(monkeypatch)
    april = pipeline.start("april", fake, background=False)
    assert final(april) == APRIL and not april.questions
    assert all(d.rule_id == "rule-1" and d.rule_similarity is None for d in april.decisions.values())
    assert applied(april, "A1", "same clause type and counterparty")


def test_another_counterpartys_rule_never_matches(monkeypatch):
    use(monkeypatch, FakeMoss(score=0.99))
    fake = ScenarioClaude()
    march_with_rule_1(fake)
    pipeline.RULES[0] = pipeline.RULES[0].model_copy(update={"counterparty": "Southmart"})
    april = pipeline.start("april", fake, background=False)
    assert {d.decision for d in april.shown.values()} == {"ask"} and len(april.questions) == 2


def test_moss_failing_falls_back_to_the_exact_match(monkeypatch):
    backend = use(monkeypatch, FakeMoss(fail=True))
    fake = ScenarioClaude()
    march = march_with_rule_1(fake)
    assert any(t.startswith("Moss couldn't index Rule #1 (live failed 2x (ConnectionError: Moss is down))") for t in logs(march))
    assert final(march)["C6"] == ("accept", D(0), D(1200))
    reword_april(monkeypatch)
    april = pipeline.start("april", fake, background=False)
    assert final(april) == APRIL and not april.questions
    assert applied(april, "A1", "same clause type and counterparty")
    assert any(t.startswith("Moss didn't answer (live failed 2x") for t in logs(april))
    assert backend.calls.count(("query", REWORDED)) == 4  # A1 and A2: one call and one retry each


def test_undo_drops_rule_1_from_moss(monkeypatch):
    backend = use(monkeypatch, FakeMoss())
    fake = ScenarioClaude()
    march = march_with_rule_1(fake)
    pipeline.answer(next(iter(march.questions)), "UNDO", client=fake)
    assert backend.docs == {} and "Dropped Rule #1 from Moss." in logs(march)
    april = pipeline.start("april", fake, background=False)
    assert len(april.questions) == 2


def test_demo_mode_replays_recorded_moss_answers(monkeypatch):
    use(monkeypatch, FakeMoss(score=0.9))
    reword_april(monkeypatch)
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    march_with_rule_1(ScenarioClaude())
    pipeline.start("april", ScenarioClaude(), background=False)
    assert moss.recorded()

    pipeline.reset()
    monkeypatch.setattr(moss, "MEMORY", None)  # no keys: DEMO_MODE turns Moss on because a run was recorded
    monkeypatch.delenv("RECORD_FIXTURES")
    monkeypatch.setenv("DEMO_MODE", "true")
    march_with_rule_1(NoCalls())
    april = pipeline.start("april", NoCalls(), background=False)
    assert final(april) == APRIL and not april.questions
    assert applied(april, "A1", "matched by Moss, similarity 0.90")


# ---------------------------------------------------------------- the scenario box

def test_scenario_box_finds_rule_1_for_a_reworded_clause(monkeypatch):
    fake = CoachClaude()
    backend = use(monkeypatch, FakeMoss(score=0.92))
    march_with_rule_1(fake)
    clause = "Northmart may, in its sole judgment, charge a display fee of up to $900 a month after telling Supplier in writing."
    from api import scenario
    from api.contracts import ScenarioRequest

    r = scenario.run(ScenarioRequest.model_validate(example("slotting-fee") | {"clause": clause}), fake)
    assert (r.decision.decision, r.decision.disputed, r.rule.label) == ("dispute", D(900), "Rule #1")  # 6 days' notice
    assert r.message.endswith("(Rule #1, learned from Dana; matched by Moss, similarity 0.92.)")
    assert ("query", clause) in backend.calls


# ---------------------------------------------------------------- the module

def test_off_without_keys_and_nothing_is_asked():
    assert moss.memory() is None and not moss.configured()
    assert moss.search(S54) == moss.Outcome() and moss.index_rule("rule-1", S54, "fee_discretion", "Northmart") == moss.Outcome()


def test_on_with_both_keys(monkeypatch):
    monkeypatch.setenv("MOSS_API_KEY", "test-key")
    assert moss.memory() is None  # the project id is needed too
    monkeypatch.setenv("MOSS_PROJECT_ID", "test-project")
    assert moss.configured() and moss.memory() is moss.memory()


def test_demo_mode_without_a_recording_leaves_moss_off(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert not moss.recorded() and moss.memory() is None


def test_a_missing_sdk_is_a_failed_call_not_a_crash():
    def no_sdk():
        raise ModuleNotFoundError("No module named 'moss'")

    out = moss.RuleMemory(no_sdk).search(S54)
    assert out.used and out.matches == () and "ModuleNotFoundError" in out.error


class FakeClient:
    """The SDK client's async methods, recording each call."""

    def __init__(self, indexes=(), job_error=None):
        self.calls, self.indexes, self.job_error = [], list(indexes), job_error

    async def list_indexes(self):
        self.calls.append(("list_indexes",))
        return [SimpleNamespace(name=n) for n in self.indexes]

    async def create_index(self, name, docs, model_id=None):
        self.calls.append(("create_index", name, [d.id for d in docs], model_id))
        self.indexes.append(name)

    async def add_docs(self, name, docs, options):
        self.calls.append(("add_docs", name, [d.id for d in docs], options.upsert))
        return SimpleNamespace(job_id="job-1", index_name=name, doc_count=1)

    async def wait_for_job(self, job_id, poll_interval_seconds, timeout_seconds):
        self.calls.append(("wait_for_job", job_id))
        if self.job_error:
            raise self.job_error

    async def delete_docs(self, name, doc_ids):
        self.calls.append(("delete_docs", name, doc_ids))

    async def load_index(self, name):
        self.calls.append(("load_index", name))

    async def query(self, name, text, options):
        self.calls.append(("query", name, text, options.top_k, options.alpha))
        return SimpleNamespace(docs=[SimpleNamespace(id="rule-1", text=S54, score=0.912345, metadata={})])


def fake_sdk(client):
    return SimpleNamespace(MossClient=lambda project_id, project_key: client, DocumentInfo=SimpleNamespace,
                           QueryOptions=SimpleNamespace, MutationOptions=SimpleNamespace)


def test_sdk_backend_creates_the_index_for_the_first_rule():
    client = FakeClient()
    moss.SdkBackend("p", "k", sdk=fake_sdk(client)).upsert("rule-1", S54, {"term_type": "fee_discretion"})
    assert client.calls == [("list_indexes",), ("create_index", moss.INDEX, ["rule-1"], "moss-mediumlm"),
                            ("load_index", moss.INDEX)]


@pytest.mark.parametrize("job_error", [None, TimeoutError("still building")])
def test_sdk_backend_upserts_into_an_existing_index(job_error):
    client = FakeClient(indexes=[moss.INDEX], job_error=job_error)
    moss.SdkBackend("p", "k", sdk=fake_sdk(client)).upsert("rule-2", "Slotting fee at Northmart's discretion", {})
    assert client.calls == [("list_indexes",), ("add_docs", moss.INDEX, ["rule-2"], True), ("wait_for_job", "job-1"),
                            ("load_index", moss.INDEX)]


def test_sdk_backend_queries_a_fresh_copy_by_meaning_and_deletes():
    client = FakeClient(indexes=[moss.INDEX])
    backend = moss.SdkBackend("p", "k", sdk=fake_sdk(client))
    assert backend.query(REWORDED, 5) == [{"id": "rule-1", "score": 0.9123}]
    backend.delete(["rule-1"])
    assert client.calls == [("load_index", moss.INDEX), ("query", moss.INDEX, REWORDED, 5, 1.0),
                            ("delete_docs", moss.INDEX, ["rule-1"])]


def test_the_installed_sdk_has_the_calls_we_make():
    """Only when `moss` is installed (api/requirements.txt): its names and parameters match SdkBackend's calls.
    Builds option objects only; no client, so nothing reaches Moss."""
    sdk = pytest.importorskip("moss")
    for name, params in {"create_index": ["name", "docs", "model_id"], "add_docs": ["name", "docs", "options"],
                         "delete_docs": ["name", "doc_ids"], "list_indexes": [], "load_index": ["name"],
                         "query": ["name", "query", "options"],
                         "wait_for_job": ["job_id", "poll_interval_seconds", "timeout_seconds"]}.items():
        method = getattr(sdk.MossClient, name)
        assert asyncio.iscoroutinefunction(method) and set(params) <= set(inspect.signature(method).parameters), name
    doc = sdk.DocumentInfo(id="rule-1", text=S54, metadata={"term_type": "fee_discretion"})
    assert (doc.id, doc.metadata) == ("rule-1", {"term_type": "fee_discretion"})
    assert sdk.QueryOptions(top_k=5, alpha=1.0).top_k == 5 and sdk.MutationOptions(upsert=True).upsert is True


def test_the_project_key_works_under_mosss_own_name(monkeypatch):
    monkeypatch.setenv("MOSS_PROJECT_ID", "test-project")
    monkeypatch.setenv("MOSS_PROJECT_KEY", "test-key")  # docs.moss.dev quickstart's name
    assert moss.credentials() == ("test-project", "test-key") and moss.configured()
    monkeypatch.delenv("MOSS_PROJECT_KEY")
    monkeypatch.setenv("MOSS_API_KEY", "older-name")
    assert moss.credentials() == ("test-project", "older-name")
