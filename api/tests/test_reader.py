"""Deal Reader A with a fake Claude client: validation, retry, quote check, claims, DEMO_MODE fixtures."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from api import adapters
from api.agents import reader
from api.agents.reader import LLMOutput
from api.engine import quote_check
from api.engine.allowed import compute_allowed
from api.engine.tests import scenario as s
from api.integrations import replay

RECORDED = replay.FIXTURES  # data/fixtures, before the autouse fixture points replay at a temp dir

S31 = ("Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and Peak Bar Chocolate "
       "sold between March 1 and March 31, 2026.")
S32 = "The promotional allowance applies to a maximum of 5,000 units in total."
S54 = "Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice to Supplier."
BROKER = "Northmart asked to extend Spring Promo through April 7, same terms, up to 500 additional units. Approved."
CLAIM = "Per our call, the Spring Promo rate is $1.50 per unit."
FAKE = "Supplier will fund a promotional allowance of $2.00 per unit on every Peak Bar product."

NULLS = dict(rate=None, products=None, start=None, end=None, max_units=None, max_fee=None, extra_units=None)


def term(type_, quote, discretion=False, effective_from=None, effective_to=None, **params):
    return {"type": type_, "params": {**NULLS, **params}, "effective_from": effective_from,
            "effective_to": effective_to, "exact_quote": quote, "discretion": discretion}


SPRING = [
    term("promo_rate", S31, effective_from="2026-03-01", effective_to="2026-03-31", rate="1.00"),
    term("product_scope", S31, products=["Peak Bar Original", "Peak Bar Chocolate"]),
    term("date_range", S31, start="2026-03-01", end="2026-03-31"),
    term("unit_cap", S32, max_units=5000),
    term("fee_discretion", S54, discretion=True, max_fee="1500"),
]
BROKER_TERMS = [term("amendment", BROKER, effective_to="2026-04-07", extra_units=500)]
CLAIM_TERMS = [term("promo_rate", CLAIM, effective_from="2026-03-30", rate="1.50")]


class FakeClaude:
    """Stands in for anthropic.Anthropic: returns queued answers (dicts, or exceptions to raise)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.users: list[str] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, **kw):
        self.users.append(kw["messages"][0]["content"])
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        if a == "refusal":
            return SimpleNamespace(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"), parsed_output=None)
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=LLMOutput.model_validate(a))


def answer(terms, unclear=()):
    return {"terms": terms, "unclear": list(unclear)}


@pytest.fixture(autouse=True)
def _isolated_fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)


def read_spring_and_broker():
    deal = reader.read_document("spring-promo", client=FakeClaude(answer(SPRING)))
    broker = reader.read_document("broker-2026-03-28", base_terms=deal.terms, client=FakeClaude(answer(BROKER_TERMS)))
    return deal, broker


def test_six_spring_terms_verified_with_real_offsets():
    deal, broker = read_spring_and_broker()
    terms = deal.terms + broker.terms
    assert [t.type for t in terms] == ["promo_rate", "product_scope", "date_range", "unit_cap", "fee_discretion", "amendment"]
    assert all(t.status == "verified" and t.source_approved for t in terms), [t.reasons for t in terms]
    _, text = reader.documents.load("spring-promo")
    for t in deal.terms:
        assert quote_check.normalize(text[t.char_start:t.char_end]) == quote_check.normalize(t.exact_quote)
    assert deal.terms[4].discretion is True


def test_extension_starts_the_day_after_the_deal_ends():
    _, broker = read_spring_and_broker()
    ext = broker.terms[0]
    assert (str(ext.effective_from), str(ext.effective_to), ext.params) == ("2026-04-01", "2026-04-07", {"extra_units": 500})


def test_planted_fake_quote_is_rejected():
    r = reader.read_document("spring-promo", client=FakeClaude(answer(SPRING + [term("promo_rate", FAKE, rate="2.00")])))
    fake = r.terms[-1]
    assert fake.status == "rejected" and "quote not found in source" in fake.reasons


def test_number_not_in_quote_is_rejected():
    r = reader.read_document("spring-promo", client=FakeClaude(answer([term("promo_rate", S31, rate="1.50")])))
    assert r.terms[0].status == "rejected" and r.terms[0].reasons[0].startswith("params numbers not in quote")


def test_northmart_email_is_a_claim():
    r = reader.read_document("northmart-2026-03-30", client=FakeClaude(answer(CLAIM_TERMS)))
    t = r.terms[0]
    assert t.status == "verified" and t.source_approved is False  # quote is real; sender can't change the deal


def test_reader_terms_drive_the_engine_to_the_scenario_numbers():
    deal, broker = read_spring_and_broker()
    claim = reader.read_document("northmart-2026-03-30", client=FakeClaude(answer(CLAIM_TERMS)))
    terms = [adapters.to_engine_term(t) for t in deal.terms + broker.terms + claim.terms]
    expected = {"C1": "1200.00", "C2": "0.00", "C3": "330.00", "C4": "0.00", "C5": "0.00", "C6": "1200.00"}
    got = {cid: str(compute_allowed(c, terms, s.store_sales(), s.prior_payments()).allowed)
           for cid, c in s.march_charges().items()}
    assert got == expected


def test_validation_error_is_retried_once_with_the_error():
    bad = answer([term("promo_rate", S31)])  # rate missing: the contract rejects it
    fake = FakeClaude(bad, answer(SPRING))
    r = reader.read_document("spring-promo", client=fake)
    assert r.attempts == 2 and len(r.terms) == 5 and r.errors
    assert "failed validation" in fake.users[1] and "rate" in fake.users[1]


def test_two_failures_go_to_unclear():
    bad = answer([term("promo_rate", S31)])
    r = reader.read_document("spring-promo", client=FakeClaude(bad, bad))
    assert r.terms == [] and "needs a person" in r.unclear[0]


def test_refusal_goes_to_unclear():
    r = reader.read_document("spring-promo", client=FakeClaude("refusal", "refusal"))
    assert r.terms == [] and "needs a person" in r.unclear[0] and "declined" in r.errors[0]


def test_demo_mode_replays_recorded_answer(monkeypatch):
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    live = reader.read_document("spring-promo", client=FakeClaude(answer(SPRING)))
    assert live.source == "live" and list((replay.FIXTURES / reader.SERVICE).glob("*.json"))
    monkeypatch.setenv("DEMO_MODE", "true")
    again = reader.read_document("spring-promo", client=FakeClaude())  # would fail if it called out
    assert again.source == "fixture" and [t.params for t in again.terms] == [t.params for t in live.terms]


def test_demo_mode_without_fixture_goes_to_unclear(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    r = reader.read_document("spring-promo", client=FakeClaude())
    assert r.terms == [] and "DEMO_MODE is on" in r.errors[0]


def test_network_failure_falls_back_to_saved_answer(monkeypatch):
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    reader.read_document("spring-promo", client=FakeClaude(answer(SPRING)))
    monkeypatch.delenv("RECORD_FIXTURES")
    down = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    r = reader.read_document("spring-promo", client=FakeClaude(down, down))
    assert r.source == "fixture" and len(r.terms) == 5


def test_recorded_fixtures_replay_to_the_six_spring_terms(monkeypatch):
    """The committed recordings in data/fixtures/claude-reader still match the prompt. If this fails after a prompt
    change, re-record: RECORD_FIXTURES=1 python -m api.agents.reader"""
    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    monkeypatch.setenv("DEMO_MODE", "true")
    deal = reader.read_document("spring-promo", client=FakeClaude())
    broker = reader.read_document("broker-2026-03-28", base_terms=deal.terms, client=FakeClaude())
    claim = reader.read_document("northmart-2026-03-30", client=FakeClaude())
    terms = deal.terms + broker.terms
    assert sorted(t.type for t in terms) == sorted(
        ["promo_rate", "product_scope", "date_range", "unit_cap", "fee_discretion", "amendment"])
    assert all(t.status == "verified" and t.source_approved for t in terms)
    assert [(t.type, t.source_approved) for t in claim.terms] == [("promo_rate", False)]
