"""Agent-mode eval wiring: with readers that read each generated document correctly (and disagree on the vague
"core bars" clause), agent mode must reproduce the answer key. The live score then measures only the models."""

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.agents import reader_b
from api.agents.investigator import LLMFinding
from api.agents.negotiator import LLMRehearsal
from api.agents.reader import LLMOutput
from api.integrations import replay
from api.tests.test_reader import NULLS, answer

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "eval" / "charges-30.csv").exists(), reason="no eval set")


def harness():
    sys.path.insert(0, str(ROOT / "eval"))
    spec = importlib.util.spec_from_file_location("eval_run_agent", ROOT / "eval" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}


def _iso(month: str, day: str, year: str) -> str:
    return f"{year}-{MONTHS[month]:02d}-{int(day):02d}"


def term(type_, quote, discretion=False, effective_from=None, effective_to=None, **params):
    return {"type": type_, "params": {**NULLS, **params}, "effective_from": effective_from,
            "effective_to": effective_to, "exact_quote": quote, "discretion": discretion}


class EvalClaude:
    """A careful reader and investigator for the eval's generated documents."""

    def __init__(self):
        self.calls: list[str] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, output_format, messages, system, **_):
        user = messages[0]["content"]
        b = system == reader_b.prompt()
        self.calls.append(output_format.__name__ + ("-B" if b else ""))
        out = {LLMOutput: lambda: self._read(user, b), LLMFinding: lambda: self._find(user),
               LLMRehearsal: lambda: self._rehearse(user)}[output_format]()
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=output_format.model_validate(out))

    def _read(self, user, b):
        doc = re.search(r"<document>\n(.*)\n</document>", user, re.S).group(1)
        terms, unclear = [], []
        if m := re.search(r"(Supplier will fund a promotional allowance of \$([\d.]+) per unit on (.+?) sold "
                          r"between (\w+) (\d+) and (\w+) (\d+), (\d{4})\.)", doc):
            quote, rate, products, m1, d1, m2, d2, y = m.groups()
            start, end = _iso(m1, d1, y), _iso(m2, d2, y)
            terms += [term("promo_rate", quote, effective_from=start, effective_to=end, rate=rate),
                      term("product_scope", quote, products=[p.strip() for p in products.split(" and ")]),
                      term("date_range", quote, start=start, end=end)]
        elif m := re.search(r"(Supplier will fund a promotional allowance of \$([\d.]+) per unit on its core bars "
                            r"sold in March 2026\.)", doc):
            quote = m.group(1)  # vague products: Reader A guesses, Reader B leaves it out
            terms += [term("promo_rate", quote, rate=m.group(2)), term("date_range", quote, start="2026-03-01", end="2026-03-31")]
            terms += [] if b else [term("product_scope", quote, products=["core bars"])]
        elif "reasonable per-unit rate" in doc:
            unclear.append("The rate is 'reasonable', not a number.")
        if m := re.search(r"(The promotional allowance applies to a maximum of ([\d,]+) units in total\.)", doc):
            terms.append(term("unit_cap", m.group(1), max_units=int(m.group(2).replace(",", ""))))
        if m := re.search(r"(Northmart may charge a display fee of up to \$([\d,]+) per month at its discretion, "
                          r"with written notice to Supplier\.)", doc):
            terms.append(term("fee_discretion", m.group(1), discretion=True, max_fee=m.group(2).replace(",", "")))
        if m := re.search(r"((?:[^\n]*?)through April (\d+)(?:[^\n]*?)(?:up to|capped at) ([\d,]+) (?:additional|more) "
                          r"units\.(?: Approved\.)?)", doc):
            terms.append(term("amendment", m.group(1).strip(), effective_to=f"2026-04-{int(m.group(2)):02d}",
                              extra_units=int(m.group(3).replace(",", ""))))
        elif m := re.search(r"(Per our call, the Spring Promo now runs through April (\d+)\.)", doc):
            terms.append(term("date_range", m.group(1), start="2026-03-01", end=f"2026-04-{int(m.group(2)):02d}"))
        return answer(terms, unclear)

    def _find(self, user):
        p = json.loads(user)
        ids = [e["id"] for e in p["evidence"]]
        cites = [i for i in ids if i.startswith("ev-pasted")][:1]
        cites += [i for i in ids if i.startswith(("ev-sales", "ev-payment", "ev-notice"))][:1]
        cites.append(f"ev-charge-{p['charge']['id']}")
        return {"finding": "The deal and the data explain this charge.", "type": "matches_deal", "evidence_ids": cites,
                "confidence": 0.95, "open_questions": []}

    def _rehearse(self, user):
        ids = [e["id"] for e in json.loads(user)["evidence"]]
        return {"predicted_rebuttal": "The deduction stands.", "answer": "The signed deal and the data show otherwise.",
                "answer_evidence_ids": [next(i for i in ids if i.startswith("ev-pasted"))]}


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)


def test_agent_mode_with_careful_readers_reproduces_the_key():
    ev = harness()
    import agent

    fake = EvalClaude()
    results, models = agent.run(ev.DEFAULT_DATA, client=fake, ev=ev)
    s = ev.summary(results, mode="agent")
    misses = [(r.case_id, r.verdict, r.decision.value, r.gate_row, r.notes) for r in results if r.verdict != "correct"]
    assert (s["correct"], s["wrong_actions"], s["cases"]) == (30, 0, 30), misses
    assert models == [("claude", "claude-b")] and s["mode"] == "agent"
    by_id = {r.case_id: r for r in results}
    assert (by_id["E29"].decision.value, by_id["E29"].gate_row) == ("ask", 2)  # readers disagreed on "core bars"
    assert any("product_scope" in n for n in by_id["E29"].notes)
    assert by_id["E12"].decision.value == "dispute"  # Northmart's own email can't extend the deal
    assert fake.calls.count("LLMOutput") == fake.calls.count("LLMOutput-B") == 34  # both readers on every document


def test_estimate_counts_calls_without_calling(capsys):
    ev = harness()
    assert ev.main(["--mode", "agent", "--estimate", "--json"]) == 0
    e = json.loads(capsys.readouterr().out)
    assert (e["cases"], e["reader_calls"], e["investigator_calls"]) == (30, 68, 30) and e["calls"] == 111


def test_eval_latest_prefers_the_agent_score(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routes import eval as eval_route

    h = eval_route._harness()
    monkeypatch.setattr(h, "LATEST", tmp_path / "latest.json")
    monkeypatch.setattr(h, "LATEST_AGENT", tmp_path / "latest-agent.json")
    monkeypatch.setattr(eval_route, "PUBLISHED", tmp_path / "published")  # none published in this test
    h.save(h.summary(h.run(h.DEFAULT_DATA)), h.LATEST)
    client = TestClient(app)
    assert client.get("/eval/latest").json()["mode"] == "engine"
    h.save({**h.summary(h.run(h.DEFAULT_DATA), mode="agent"), "correct": 27}, h.LATEST_AGENT)
    r = client.get("/eval/latest").json()
    assert (r["mode"], r["correct"]) == ("agent", 27)


def test_the_deployed_scoreboard_shows_the_published_score(tmp_path, monkeypatch):
    """The API image has no eval/latest*.json (gitignored), only eval/published/: that's what /eval/latest serves."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routes import eval as eval_route

    h = eval_route._harness()
    monkeypatch.setattr(h, "LATEST", tmp_path / "latest.json")
    monkeypatch.setattr(h, "LATEST_AGENT", tmp_path / "latest-agent.json")
    r = TestClient(app).get("/eval/latest").json()
    published = json.loads((eval_route.PUBLISHED / "agent.json").read_text())
    assert (r["status"], r["mode"], r["cases"], r["correct"], r["wrong_automatic"]) == (
        "done", "agent", 30, published["correct"], published["wrong_actions"])
    assert published["partial"] is False  # a full 30-case run, not a smoke test
