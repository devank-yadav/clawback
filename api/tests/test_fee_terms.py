"""The fee-term contracts (fee_schedule, dispute_window, notice_period): what the readers may return, the quote check
on them, and that Peak Bar's requests are unchanged by them."""

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.agents import rule_writer
from api.agents.reader import LLMFeeOutput, LLMFeeParams, LLMOutput
from api.contracts import (
    Charge, DisputeWindowParams, FeeScheduleParams, NoticePeriodParams, ReaderTerm, TERM_PARAMS,
)
from api.engine import quote_check
from api.tests.lantern_hill_answers import NULLS

Q = "A late fee of 5% applies if 0 to 7 days late, and 10% if 8 to 14 days late, with a minimum of $65."


def test_fee_schedule_params():
    p = FeeScheduleParams.model_validate({"fee_code": "MCB", "basis": "percent", "rate": "5", "min": "65"})
    assert (p.rate, p.min, p.max, p.per, p.requires_proof) == (Decimal("5"), Decimal("65.00"), None, "incident", False)
    tiered = FeeScheduleParams.model_validate({"fee_code": "Late", "basis": "percent", "tiers": [
        {"from_days": 0, "to_days": 7, "rate": "5"}, {"from_days": 8, "to_days": None, "rate": "10"}]})
    assert tiered.rate is None and tiered.tiers[1].to_days is None
    with pytest.raises(ValidationError):  # neither a rate nor tiers
        FeeScheduleParams.model_validate({"fee_code": "X", "basis": "flat"})
    with pytest.raises(ValidationError):
        FeeScheduleParams.model_validate({"fee_code": "X", "basis": "per_pallet", "rate": "1"})


def test_dispute_window_and_notice_period_params():
    assert DisputeWindowParams.model_validate({"days": 180, "from": "deduction"}).from_ == "deduction"
    assert DisputeWindowParams.model_validate({"days": 30}).from_ == "deduction"
    with pytest.raises(ValidationError):
        DisputeWindowParams.model_validate({"days": 30, "from": "shipment"})
    assert NoticePeriodParams.model_validate({"days": 30}).days == 30
    assert set(TERM_PARAMS) >= {"fee_schedule", "dispute_window", "notice_period"}


def test_reader_term_keeps_from_as_written():
    t = ReaderTerm(type="dispute_window", params={"days": 180, "from": "deduction"}, exact_quote="within 180 days",
                   char_start=0, char_end=15, source_doc_id="x")
    assert t.params == {"days": 180, "from": "deduction"} and t.typed_params().from_ == "deduction"


def test_the_fee_schema_says_from_everywhere():
    assert "from" in LLMFeeParams.model_json_schema()["properties"]
    p = LLMFeeParams.model_validate({**NULLS, "days": 180, "from": "invoice"})
    assert p.model_dump()["from"] == "invoice"  # claude._parse dumps the parsed answer; it must validate again
    LLMFeeOutput.model_validate({"terms": [], "unclear": []})
    assert "fee_code" not in json.dumps(LLMOutput.model_json_schema())  # Peak Bar's schema is as it was


def test_quote_check_counts_tier_numbers():
    term = {"type": "fee_schedule", "exact_quote": Q, "params": {
        "fee_code": "Late", "basis": "percent", "min": "65",
        "tiers": [{"from_days": 0, "to_days": 7, "rate": "5"}, {"from_days": 8, "to_days": 14, "rate": "10"}]}}
    assert quote_check.check_quote(Q, term).ok
    term["params"]["tiers"][1]["rate"] = "12"  # not in the sentence
    assert quote_check.check_quote(Q, term).reasons == ("params numbers not in quote: 12",)
    words = "with at least thirty (30) days prior notice"
    assert quote_check.check_quote(words, {"exact_quote": words, "params": {"days": 30}}).ok


def test_charge_without_deducted_on_serializes_as_before():
    row = dict(id="C1", ref="NM-2229", code="PA", description="x", product="Original", units=1, rate=1, amount=1,
               period_start=date(2026, 3, 1), period_end=date(2026, 3, 7))
    assert "deducted_on" not in Charge(**row).model_dump(mode="json")
    assert Charge(**row, deducted_on="2026-04-10").model_dump(mode="json")["deducted_on"] == "2026-04-10"
    assert Charge(**row, deducted_on="").deducted_on is None


def test_rule_writer_sends_fee_amount_only_when_there_is_one(monkeypatch):
    sent = []

    def ask(service, system, user, *a, **kw):
        sent.append(json.loads(user)["facts"])
        return type("A", (), {"value": None})()

    monkeypatch.setattr(rule_writer.claude, "ask", ask)
    from datetime import datetime, timezone

    from api.contracts import Question, Term
    q = Question(id="Q-1", to_role="owner", charge_id="C6", text="?", sent_at=datetime(2026, 3, 31, tzinfo=timezone.utc))
    t = Term(id="t", reader="merged", type="fee_discretion", params={"max_fee": 1500}, exact_quote="q", char_start=0,
             char_end=1, source_doc_id="spring-promo")
    rule_writer.write_rule(q, "accept", t, "Northmart", {"notice_days": 20}, 1, "Dana", q.sent_at)
    rule_writer.write_rule(q, "accept", t, "KeHE", {"fee_amount": Decimal("185.76")}, 2, "Teresa", q.sent_at)
    assert sent == [{"notice_days": 20, "amount": None},
                    {"notice_days": None, "amount": None, "fee_amount": "185.76"}]


# --- One canonical form for fee terms (api/agents/fee_terms.py) ---------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from api.agents import fee_terms, readers  # noqa: E402
from api.engine.quote_check import readers_agree  # noqa: E402

VOCAB = ["MCB", "Extra Performance", "Free Placements", "Spoils"]
Q_MCB = ("KeHE will charge a bi weekly processing fee of 5% of the MCB amount (with a minimum of $65 per purchasing "
         "Vendor/facility).")


@pytest.mark.parametrize("name, want", [
    ("MCB", "MCB"), ("mcb", "MCB"), ("MCB processing fee", "MCB"), ("Manufacturer Charge Backs (MCB)", "MCB"),
    ("Extra Performance administrative charge", "Extra Performance"), ("FREE PLACEMENTS", "Free Placements"),
    ("Spoils processing fee", "Spoils"), ("Lumping fee", "Lumping fee"),
])
def test_fee_code_takes_the_accounts_name(name, want):
    assert fee_terms.fee_code(name, VOCAB) == want


def test_rate_and_limits_in_one_form():
    assert fee_terms.rate("5%", "percent", Q_MCB) == "5"
    assert fee_terms.rate("0.05", "percent", Q_MCB) == "5"  # a fraction for the 5% the sentence writes
    assert fee_terms.rate("0.29", "per_unit", "a $0.29 per unit fee") == "0.29"  # dollars stay dollars
    assert fee_terms.rate("0.5", "percent", "a 0.5% fee") == "0.5"  # the sentence writes 0.5%: kept
    assert fee_terms.rate("$1,500.00", "flat", "") == "1500"
    p = fee_terms.canonical({"fee_code": "MCB processing fee", "basis": "percent", "rate": "5%", "min": "$65.00",
                             "max": "0", "tiers": []}, Q_MCB, VOCAB)
    assert p == {"fee_code": "MCB", "basis": "percent", "rate": "5", "min": "65", "per": "incident",
                 "requires_proof": False}


def test_priced_alike_ignores_requires_proof_and_per():
    a = fee_terms.canonical({"fee_code": "MCB", "basis": "percent", "rate": "5", "min": "65", "requires_proof": True},
                            Q_MCB, VOCAB)
    b = fee_terms.canonical({"fee_code": "MCB fee", "basis": "percent", "rate": "0.05", "min": "65.00"}, Q_MCB, VOCAB)
    assert fee_terms.priced_alike(a, b)
    assert fee_terms.priced_alike(a, {**b, "per": "invoice"})  # names the same single charge
    assert not fee_terms.priced_alike(a, {**b, "min": "75"})
    tiered = {"fee_code": "Late", "basis": "percent", "tiers": [{"from_days": 0, "to_days": 7, "rate": "5%"}]}
    assert fee_terms.canonical(tiered, "5% if 0 to 7 days late", [])["tiers"] == [
        {"from_days": 0, "to_days": 7, "rate": "5"}]


@pytest.mark.parametrize("written", ["new store", "each new store P.O.", "New Store PO", "every new store purchase order"])
def test_applies_to_in_one_form(written):
    # Walmart's schedule: "% Applied to each line item for each new store P.O."; live, Gemini wrote the whole phrase
    p = fee_terms.canonical({"fee_code": "New Store/Club Discount", "basis": "percent", "rate": "10",
                             "applies_to": written}, "", ["New Store/Club Discount"])
    assert p["applies_to"].lower() == "new store"


# Five Below's Violation Summary, as the two readers wrote it live
ADMIN = {"fee_code": "administrative fee", "basis": "per_po", "rate": "100", "per": "incident", "add_on": True}
LATE = {"fee_code": "Late Shipment", "basis": "percent", "rate": "5", "per": "incident", "requires_fault": True}
MISSED = {"fee_code": "Missed", "basis": "percent", "rate": "3", "max": "750", "per": "incident"}


def test_per_po_and_flat_are_one_price_and_agree():
    flat = {**ADMIN, "basis": "flat"}
    assert fee_terms.priced_alike(ADMIN, flat)
    a, b = fee_terms.agreed(ADMIN, flat)
    assert readers_agree({"type": "fee_schedule", "params": a}, {"type": "fee_schedule", "params": b})
    assert not fee_terms.priced_alike(ADMIN, {**ADMIN, "basis": "per_unit"})


def test_per_agrees_only_where_no_minimum_or_maximum_groups_it():
    a, b = fee_terms.agreed(LATE, {**LATE, "per": "po"})
    assert readers_agree({"type": "fee_schedule", "params": a}, {"type": "fee_schedule", "params": b})
    a, b = fee_terms.agreed(MISSED, {**MISSED, "per": "po"})  # up to $750 per PO or per incident: a different price
    assert not readers_agree({"type": "fee_schedule", "params": a}, {"type": "fee_schedule", "params": b})


def test_alike_schedules_pair_first_under_one_fee_name():
    # Reader A also named the 50% short-shipment chargeback "Receipt of backorder (shortship)"; Reader B didn't
    t = lambda at, **p: SimpleNamespace(char_start=at, params={"fee_code": "Receipt of backorder (shortship)",  # noqa: E731
                                                                "basis": "percent", "per": "incident", **p})
    a = [t(100, rate="50"), t(900, rate="5")]
    b = [t(905, rate="5")]
    pairs = readers._pairs("fee_schedule", a, b)
    assert [(x.params["rate"] if x else None, y.params["rate"] if y else None) for x, y in pairs] == [
        ("50", None), ("5", "5")]
