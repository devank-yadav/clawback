"""F2: two independent readers; only terms both find, with quotes found word for word, are verified."""

import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from api import pipeline
from api.agents import reader_b, readers
from api.agents.reader import LLMOutput
from api.integrations import replay
from api.tests.test_pipeline import ScenarioClaude, final, last_totals
from api.tests.test_reader import BROKER_TERMS, CLAIM_TERMS, NULLS, S32, SPRING, answer


class TwoReaders(ScenarioClaude):
    """Reader A answers as ScenarioClaude does; Reader B (its own prompt) can be told to read differently."""

    def __init__(self, b_spring=None):
        super().__init__()
        self.b_spring = b_spring

    def _parse(self, output_format, messages, **kw):
        if output_format is LLMOutput and kw.get("system") == reader_b.prompt():
            self.calls.append("ReaderB")
            if self.b_spring is not None and "Document ID: spring-promo" in messages[0]["content"]:
                return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                                       parsed_output=LLMOutput.model_validate(answer(self.b_spring)))
        return super()._parse(output_format=output_format, messages=messages, **kw)


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    yield
    pipeline.reset()


def statuses(m):
    return {t.type: t.status for t in m.terms}


def test_both_readers_agree_so_every_term_is_verified():
    fake = TwoReaders()
    m = readers.read_both("spring-promo", client=fake)
    assert set(statuses(m).values()) == {"verified"} and len(m.terms) == 5 and m.models == ("claude", "claude-b")
    assert all(t.reader == "merged" for t in m.terms) and fake.calls.count("ReaderB") == 1


def test_a_different_cap_is_disputed_and_explained():
    b = [t if t["type"] != "unit_cap" else {**t, "params": {**NULLS, "max_units": 6000}} for t in SPRING]
    m = readers.read_both("spring-promo", client=TwoReaders(b_spring=b))
    assert statuses(m)["unit_cap"] == "rejected"  # 6,000 isn't in the quote, so Reader B's version fails the quote check
    b = [t for t in SPRING if t["type"] != "unit_cap"]  # Reader B didn't find the cap at all
    m = readers.read_both("spring-promo", client=TwoReaders(b_spring=b))
    assert statuses(m)["unit_cap"] == "disputed" and m.disagreements == [
        "unit_cap: Reader A read max_units 5000; Reader B read nothing"]


def test_readers_reading_the_same_sentence_differently_dispute_it():
    b = [t if t["type"] != "product_scope" else {**t, "params": {**NULLS, "products": ["Peak Bar Original"]}}
         for t in SPRING]
    m = readers.read_both("spring-promo", client=TwoReaders(b_spring=b))
    assert statuses(m)["product_scope"] == "disputed" and "products" in m.disagreements[0]


def test_disputed_term_sends_its_charges_to_a_person():
    """Gate row 2: with the cap disputed, every promo charge that the cap check touches asks instead of filing;
    Mint (not a deal product) is still disputed. Dana settles C4 once with DISPUTE."""
    fake = TwoReaders(b_spring=[t for t in SPRING if t["type"] != "unit_cap"])
    run = pipeline.start("march", fake, background=False)
    got = final(run)
    assert {cid: (got[cid][0], run.shown[cid].gate_row) for cid in ("C1", "C2", "C3", "C4")} == {
        cid: ("ask", 2) for cid in ("C1", "C2", "C3", "C4")}
    assert got["C5"] == ("dispute", D(1000), D(0)) and got["C6"][0] == "ask"
    q = next(q for q in run.questions.values() if q.charge_id == "C4")
    assert "two readers disagree on the deal's unit cap" in q.text and "Reply ACCEPT or DISPUTE" in q.text
    assert any("The readers disagree on unit_cap" in e.data.text for e in run.events if e.type == "log")
    assert next(e.data for e in run.events if e.type == "dispute").total == D(1000)  # only Mint is filed
    pipeline.answer(q.id, "DISPUTE", client=fake)
    assert final(run)["C4"] == ("dispute", D(1540), D(0))


# ---------------------------------------------------------------- Gemini as Reader B

class FakeGemini:
    """Stands in for google.genai.Client: models.generate_content returns queued answers (or raises them)."""

    def __init__(self, outputs):
        self.outputs, self.requests = list(outputs), []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kw):
        self.requests.append(kw)
        out = self.outputs.pop(0) if self.outputs else ConnectionError("no more answers")
        if isinstance(out, BaseException):
            raise out
        return SimpleNamespace(text=out if isinstance(out, str) else json.dumps(out))


def test_gemini_reads_when_configured():
    gemini = FakeGemini([answer(SPRING)])
    m = readers.read_both("spring-promo", client=TwoReaders(), gemini=gemini)
    assert m.models == ("claude", "gemini") and set(statuses(m).values()) == {"verified"}
    req = gemini.requests[0]
    assert (req["model"], req["config"].system_instruction) == (reader_b.DEFAULT_GEMINI_MODEL, reader_b.prompt())
    assert req["config"].response_mime_type == "application/json" and "properties" in req["config"].response_json_schema
    assert "Document ID: spring-promo" in req["contents"] and m.model_ids[1] == reader_b.DEFAULT_GEMINI_MODEL


def test_busy_gemini_model_hands_over_to_the_second_one(monkeypatch):
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)
    gemini = FakeGemini([ConnectionError("503"), ConnectionError("503"), answer(SPRING)])
    m = readers.read_both("spring-promo", client=TwoReaders(), gemini=gemini)
    assert m.models == ("claude", "gemini") and m.model_ids[1] == reader_b.DEFAULT_GEMINI_FALLBACK
    assert [r["model"] for r in gemini.requests] == [reader_b.DEFAULT_GEMINI_MODEL] * 2 + [reader_b.DEFAULT_GEMINI_FALLBACK]


def test_gemini_failing_falls_back_to_a_second_claude_read(monkeypatch):
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)
    gemini = FakeGemini([ConnectionError("down")] * 4)  # both models, both tries
    m = readers.read_both("spring-promo", client=TwoReaders(), gemini=gemini)
    assert m.models == ("claude", "claude-b") and set(statuses(m).values()) == {"verified"} and len(gemini.requests) == 4


def test_gemini_invalid_answer_twice_falls_back():
    bad = [{"terms": [{"type": "promo_rate"}], "unclear": []}, {"terms": "nope", "unclear": []}]
    gemini = FakeGemini(bad + bad)  # each model gets one retry with the error; then Claude
    m = readers.read_both("spring-promo", client=TwoReaders(), gemini=gemini)
    assert m.models == ("claude", "claude-b") and len(gemini.requests) == 4


def test_gemini_model_settings(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    assert reader_b.gemini_models() == ["gemini-3.8-flash", reader_b.DEFAULT_GEMINI_FALLBACK]
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    assert reader_b.gemini_models() == ["gemini-3.8-flash"]


def test_broker_and_claim_documents_merge_too():
    fake = TwoReaders()
    deal = readers.read_both("spring-promo", client=fake)
    broker = readers.read_both("broker-2026-03-28", base_terms=deal.terms, client=fake)
    claim = readers.read_both("northmart-2026-03-30", client=fake)
    assert (broker.terms[0].status, str(broker.terms[0].effective_from)) == ("verified", "2026-04-01")
    assert (claim.terms[0].status, claim.terms[0].source_approved) == ("verified", False)
