"""F13 Deal Coach and F14 scenario box on live runs, with a fake Claude."""

import re
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import disputes, pipeline, scenario
from api.agents import claude as claude_mod
from api.agents.coach import LLMCoach
from api.engine import quote_check
from api.integrations import replay
from api.tests.test_disputes import PortalClaude
from api.tests.test_reader import NULLS, answer

DRAFT_54 = "Northmart may charge a display fee of up to $1,500 per month at its discretion."
DRAFT_32 = "The promotional allowance applies to a maximum of 6,000 units in total."
DRAFT_31 = ("Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and Peak Bar Chocolate "
            "sold between May 1 and May 31, 2026.")
GOOD = [
    {"original_quote": DRAFT_54, "finding_ids": ["F-C6"], "reason": "This fee needed a question to the owner.",
     "suggested_text": DRAFT_54[:-1] + ", with written notice at least 14 days before the end of that month."},
    {"original_quote": DRAFT_32, "finding_ids": ["F-C4"], "reason": "Week 4 was taken after the cap.",
     "suggested_text": DRAFT_32[:-1] + ", including units added by any extension."},
    {"original_quote": DRAFT_31, "finding_ids": ["F-C5"], "reason": "Mint was taken though it wasn't covered.",
     "suggested_text": "Supplier will fund $1.00 per unit on the items listed by number in Schedule A only."},
]


def term(type_, quote, discretion=False, **params):
    return {"type": type_, "params": {**NULLS, **params}, "effective_from": None, "effective_to": None,
            "exact_quote": quote, "discretion": discretion}


class CoachClaude(PortalClaude):
    """Adds the Deal Coach and reads clauses pasted into the scenario box."""

    def __init__(self, coach_answers=None):
        super().__init__()
        self.coach_answers = list(coach_answers or [{"redlines": GOOD}])

    def _parse(self, output_format, messages, **kw):
        if output_format is LLMCoach:
            self.calls.append("LLMCoach")
            out = self.coach_answers.pop(0) if len(self.coach_answers) > 1 else self.coach_answers[0]
            return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=LLMCoach.model_validate(out))
        return super()._parse(output_format=output_format, messages=messages, **kw)

    def _reader(self, user):
        if "Document ID: pasted-" not in user:
            return super()._reader(user)
        clause = re.search(r"<document>\n(.*)\n</document>", user, re.S).group(1)
        if "6,500 units" in clause:
            return answer([term("unit_cap", clause, max_units=6500)])
        if "$0.75" in clause:
            return answer([term("promo_rate", clause, rate="0.75"),
                           term("product_scope", clause, products=["Peak Bar Original", "Peak Bar Chocolate"]),
                           term("date_range", clause, start="2026-03-01", end="2026-03-31")])
        if "display fee" in clause:
            return answer([term("fee_discretion", clause, discretion=True, max_fee="900")])
        if "7,000 units" in clause:  # the model "quotes" a number the clause doesn't say
            return answer([term("unit_cap", "The allowance applies to a maximum of 9,000 units.", max_units=9000)])
        return answer([], unclear=["No deal term in this text."])


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    for k in ("DEMO_MODE", "RECORD_FIXTURES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset(), disputes.reset()
    yield
    pipeline.reset(), disputes.reset()


@pytest.fixture
def fake(monkeypatch):
    f = CoachClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: f)
    return f


@pytest.fixture
def api():
    from api.main import app
    return TestClient(app)


def finish_march(fake):
    run = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days", client=fake)
    return run


# ---------------------------------------------------------------- F13 Deal Coach

def test_coach_gives_three_redlines_with_dollars_from_findings(fake, api):
    finish_march(fake)
    out = api.post("/coach").json()
    assert out["draft_doc_id"] == "summer-draft"
    got = {r["clause_ref"]: (r["dollars_at_stake"], r["finding_ids"]) for r in out["redlines"]}
    assert got == {"§5.4": (1200.0, ["F-C6"]), "§3.2": (1540.0, ["F-C4"]), "§3.1": (1000.0, ["F-C5"])}
    _, draft = pipeline.reader.documents.load("summer-draft")
    for r in out["redlines"]:
        q = r["quote"]
        assert quote_check.normalize(draft[q["char_start"]:q["char_end"]]) == quote_check.normalize(r["original_quote"])
    api.post("/coach")
    assert fake.calls.count("LLMCoach") == 1  # cached on the run


def test_coach_retries_a_quote_that_isnt_in_the_draft(fake, api):
    fake.coach_answers = [{"redlines": [{**GOOD[0], "original_quote": "Northmart may charge any fee it likes."}]},
                          {"redlines": GOOD}]
    finish_march(fake)
    assert len(api.post("/coach").json()["redlines"]) == 3 and fake.calls.count("LLMCoach") == 2


def test_coach_adds_dollars_in_code_when_a_redline_cites_two_costs(fake, api):
    fake.coach_answers = [{"redlines": [{**GOOD[1], "finding_ids": ["F-C4", "F-C2"]}]}]
    finish_march(fake)
    assert api.post("/coach").json()["redlines"][0]["dollars_at_stake"] == 2520.0  # 1,540 + 980


def test_coach_without_a_live_run_shows_the_recorded_redlines(api):
    assert len(api.post("/coach").json()["redlines"]) == 3


# ---------------------------------------------------------------- F14 scenario box

def example(id_):
    return next(e.request for e in scenario.EXAMPLES if e.id == id_).model_dump(mode="json")


def test_higher_cap_changes_the_outcome(fake, api):
    r = api.post("/scenario", json=example("higher-cap")).json()
    d = r["decision"]
    assert (d["decision"], d["disputed"], d["accepted"]) == ("split", 40.0, 1500.0)
    assert [t["type"] for t in r["terms"]] == ["unit_cap"] and r["terms"][0]["status"] == "verified"
    assert r["rehearsal"]["answered"] and r["message"].startswith("Split: $1,500.00 is fair, $40.00 is disputed.")
    assert any(e["kind"] == "clause" and e["quote"]["text"].startswith("The promotional allowance") for e in r["evidence"])


def test_lower_rate_splits_week_1(fake, api):
    d = api.post("/scenario", json=example("lower-rate")).json()["decision"]
    assert (d["decision"], d["disputed"], d["accepted"]) == ("split", 300.0, 900.0)


def test_discretion_fee_asks_without_a_rule_and_uses_rule_1_after(fake, api):
    d = api.post("/scenario", json=example("slotting-fee")).json()["decision"]
    assert (d["decision"], d["gate_row"]) == ("ask", 4)
    finish_march(fake)  # Dana's answer saves Rule #1
    r = api.post("/scenario", json=example("slotting-fee")).json()
    assert (r["decision"]["decision"], r["decision"]["disputed"], r["rule"]["label"]) == ("dispute", 900.0, "Rule #1")
    assert "Rule #1" in r["message"] and r["decision"]["rule_id"] == "rule-1"  # 6 days' notice: under 14, dispute


def test_a_clause_quoted_wrong_is_skipped(fake, api):
    req = example("higher-cap") | {"clause": "The promotional allowance applies to a maximum of 7,000 units in total."}
    r = api.post("/scenario", json=req).json()
    assert r["terms"][0]["status"] == "rejected" and r["decision"]["decision"] == "skip"


def test_text_with_no_term_decides_nothing(fake, api):
    r = api.post("/scenario", json=example("higher-cap") | {"clause": "Thanks for a great quarter!"}).json()
    assert r["decision"] is None and r["unclear"] == ["No deal term in this text."]


def test_examples_are_served(api):
    assert [e["id"] for e in api.get("/scenario/examples").json()] == ["higher-cap", "lower-rate", "slotting-fee"]


def test_committed_recordings_replay_coach_and_examples_offline(monkeypatch):
    """F13 + F14 with Wi-Fi off, from data/fixtures. Re-record with `make record` if this breaks."""
    from api.tests.test_reader import RECORDED

    class Offline:
        def with_options(self, **_):
            raise ConnectionError("offline")

    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)
    monkeypatch.setenv("DEMO_MODE", "true")
    run = finish_march(Offline())
    from api.agents import coach
    out = coach.coach(pipeline.coach_costs(run), client=Offline())
    assert sorted((r.clause_ref, r.dollars_at_stake) for r in out.redlines) == [
        ("§3.1", D(1000)), ("§3.2", D(1540)), ("§5.4", D(1200))]
    got = {ex.id: scenario.run(ex.request, client=Offline()).decision for ex in scenario.EXAMPLES}
    assert {k: (d.decision, d.disputed, d.accepted) for k, d in got.items()} == {
        "higher-cap": ("split", D(40), D(1500)), "lower-rate": ("split", D(300), D(900)),
        "slotting-fee": ("dispute", D(900), D(0))}
