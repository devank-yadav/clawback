"""The operations Investigator with a fake Claude: its prompt, the evidence it sees, the code checks after it, and
SH / PR / SP charges from the engine through the Investigator to the gate."""

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import get_args

import pytest

from api import adapters, documents
from api import evidence as ev
from api.agents import investigator_ops as inv
from api.contracts import Charge, DeliveryRow, Evidence, FindingType, OpsTerm, PriceRow
from api.engine import types as eng
from api.engine.allowed import OPS_CODES, compute_allowed
from api.engine.gate import decide
from api.engine.policy import load_policy
from api.integrations import replay

POLICY = load_policy()
DEAL = """## 7. Deliveries and returns

7.1 Shortages must be noted on the signed proof of delivery at receipt.

7.2 Supplier allows spoils and unsaleables of up to 1.0% of the amount invoiced each month.
"""


class FakeClaude:
    """Gives the queued answers in order and keeps every request."""

    def __init__(self, *answers):
        self.answers, self.requests = list(answers), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, output_format, messages, system, **_):
        self.requests.append({"system": system, "user": messages[0]["content"], "format": output_format})
        return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                               parsed_output=output_format.model_validate(self.answers.pop(0)))


@pytest.fixture(autouse=True)
def _fixtures(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)


@pytest.fixture(scope="module")
def world():
    deal = documents.paste(DEAL).id
    deliveries = [
        DeliveryRow(line_ref="L-1001", product="Peak Bar Original", shipped_units=1200, received_units=1200,
                    unit_price="2.50", received_by="J. Ortiz", received_at="2026-03-04"),
        DeliveryRow(line_ref="L-2002", product="Peak Bar Chocolate", shipped_units=1000, received_units=1000,
                    unit_price="2.60", received_by="M. Chen", received_at="2026-03-12"),
    ]
    prices = [PriceRow(product="Peak Bar Original", agreed_price="2.40", effective_from="2026-01-01"),
              PriceRow(product="Peak Bar Chocolate", agreed_price="2.45", effective_from="2026-03-01")]
    terms = [OpsTerm(key="shortage_notice", value="noted on the signed proof of delivery", source_doc=deal,
                     quote="Shortages must be noted on the signed proof of delivery at receipt."),
             OpsTerm(key="spoils_allowance_pct", value="1.0", source_doc=deal,
                     quote="Supplier allows spoils and unsaleables of up to 1.0% of the amount invoiced each month.")]
    charges = {c.id: c for c in (
        Charge(id="S1", ref="NM-3101", code="SH", description="Shortage, line L-1001", product="Original", units=120,
               rate="2.50", amount="300.00", period_start="2026-03-01", period_end="2026-03-31", line_ref="L-1001"),
        Charge(id="P2", ref="NM-3102", code="PR", description="Price difference, line L-2002", product="Chocolate",
               units=1000, rate="0.25", amount="250.00", period_start="2026-03-01", period_end="2026-03-31",
               line_ref="L-2002"),
        Charge(id="C1", ref="NM-2229", code="PA", description="Spring promo week 1", product="Original+Chocolate",
               units=1200, rate="1.50", amount="1800.00", period_start="2026-03-01", period_end="2026-03-07"),
    )}
    evidence = {**ev.from_charges(charges.values()), **ev.from_ops(deliveries, prices, terms),
                "ev-sales-2026-03-01": Evidence(id="ev-sales-2026-03-01", kind="sales", label="Sales Mar 1–Mar 7",
                                                summary="1,200 promoted bars sold.")}
    return charges, evidence, adapters.to_engine_ops(deliveries, prices, terms)


def allowance(world, cid):
    charges, _, ops = world
    return compute_allowed(adapters.to_engine_charge(charges[cid]), [], ops=ops)


def good(cites, type_="shortage_not_supported", finding="The signed delivery shows all 1,200 units received.",
         confidence=0.95):
    return {"finding": finding, "type": type_, "evidence_ids": cites, "confidence": confidence, "open_questions": []}


SH_CITES = ["ev-pod-L-1001", "ev-term-shortage_notice", "ev-charge-S1"]


def test_prompt_names_the_account():
    p = inv.system_prompt("Sunrise Oat Co.", "FreshWay")
    assert p.startswith("You are the operations Investigator for Clawback. FreshWay, a distributor, took money out of "
                        "a payment to Sunrise Oat Co.")
    assert "{" not in p and "}" not in p and "Northmart" not in p and "Peak Bar" not in p


def test_finding_types_belong_to_the_contract():
    ops_types = set(get_args(inv.OpsFindingType))
    assert ops_types <= set(get_args(FindingType))
    assert set(inv.TYPES_BY_CODE) == OPS_CODES and {t for ts in inv.TYPES_BY_CODE.values() for t in ts} == ops_types


def test_sees_only_the_charge_its_delivery_and_the_ops_terms(world):
    charges, evidence, _ = world
    fake = FakeClaude(good(SH_CITES))
    got = inv.investigate(charges["S1"], allowance(world, "S1"), evidence, fake, brand="Peak Bar Co.",
                          distributor="Northmart")
    assert got.output.type == "shortage_not_supported" and got.output.evidence_ids == SH_CITES and got.source == "live"
    req = fake.requests[0]
    assert req["system"] == inv.system_prompt("Peak Bar Co.", "Northmart") and req["format"] is inv.LLMOpsFinding
    payload = json.loads(req["user"])
    assert [e["id"] for e in payload["evidence"]] == [
        "ev-charge-S1", "ev-pod-L-1001", "ev-term-shortage_notice", "ev-term-spoils_allowance_pct"]
    assert payload["charge"]["line_ref"] == "L-1001" and "remittance_id" not in payload["charge"]
    assert payload["engine"]["allowed"] == "0.00" and payload["engine"]["facts"]["short_units"] == 0


def test_price_charge_also_sees_the_agreed_price(world):
    charges, evidence, _ = world
    fake = FakeClaude(good(["ev-pod-L-2002", "ev-price-chocolate"], "price_mismatch",
                           "Invoiced $2.60 against the agreed $2.45; the deal supports $0.15 a unit, not $0.25."))
    got = inv.investigate(charges["P2"], allowance(world, "P2"), evidence, fake)
    assert got.output.type == "price_mismatch"
    ids = [e["id"] for e in json.loads(fake.requests[0]["user"])["evidence"]]
    assert ids == ["ev-charge-P2", "ev-pod-L-2002", "ev-price-chocolate", "ev-term-shortage_notice",
                   "ev-term-spoils_allowance_pct"]


@pytest.mark.parametrize("bad, problem", [
    (good(SH_CITES, type_="price_matches"), "doesn't fit a SH charge"),
    (good(SH_CITES, finding="Only 1,150 of the units arrived."), "numbers in the finding that aren't in the input"),
    (good(["ev-pod-L-1001", "ev-sales-2026-03-01"]), "evidence IDs not in the input"),  # in the run, not shown
    (good([]), "cite at least one evidence ID"),
])
def test_code_checks_retry_once_with_the_problem(world, bad, problem):
    charges, evidence, _ = world
    fake = FakeClaude(bad, good(SH_CITES))
    got = inv.investigate(charges["S1"], allowance(world, "S1"), evidence, fake)
    assert got.output is not None and len(fake.requests) == 2
    assert problem in got.errors[0] and problem in fake.requests[1]["user"]


def test_failing_twice_sends_the_charge_to_a_person(world):
    charges, evidence, _ = world
    bad = good(SH_CITES, type_="spoilage_within_allowance")
    got = inv.investigate(charges["S1"], allowance(world, "S1"), evidence, FakeClaude(bad, bad))
    assert got.output is None and len(got.errors) == 2
    d = decide(adapters.to_engine_charge(charges["S1"]), allowance(world, "S1"), None, POLICY)
    assert (d.kind, d.gate_row) == (eng.DecisionKind.ASK, 9)


def test_promo_charges_are_not_its_job(world):
    charges, evidence, _ = world
    assert not inv.handles(charges["C1"]) and inv.handles(charges["S1"])
    with pytest.raises(ValueError, match="handles"):
        inv.investigate(charges["C1"], allowance(world, "C1"), evidence, FakeClaude())


def gate_decision(world, cid, answer):
    """What the pipeline does with a finding: independent sources are the kinds of evidence cited, besides the charge."""
    charges, evidence, _ = world
    a = allowance(world, cid)
    out = inv.investigate(charges[cid], a, evidence, FakeClaude(answer)).output
    kinds = {evidence[i].kind for i in out.evidence_ids} - {"charge"}
    finding = eng.Finding(cid, Decimal(str(out.confidence)), tuple(out.evidence_ids), len(kinds), True, out.type,
                          out.finding)
    return decide(adapters.to_engine_charge(charges[cid]), a, finding, POLICY)


def test_shortage_disproved_end_to_end(world):
    d = gate_decision(world, "S1", good(SH_CITES))
    assert (d.kind, d.disputed, d.accepted, d.gate_row) == (eng.DecisionKind.DISPUTE, Decimal("300.00"), Decimal("0.00"), 7)


def test_price_partial_end_to_end(world):
    d = gate_decision(world, "P2", good(["ev-pod-L-2002", "ev-price-chocolate", "ev-charge-P2"], "price_mismatch",
                                        "Invoiced $2.60 against the agreed $2.45: $0.15 a unit, not $0.25."))
    assert (d.kind, d.disputed, d.accepted) == (eng.DecisionKind.SPLIT, Decimal("100.00"), Decimal("150.00"))


def test_one_source_or_low_confidence_asks(world):
    d = gate_decision(world, "S1", good(["ev-pod-L-1001", "ev-charge-S1"]))  # proof of delivery alone
    assert (d.kind, d.gate_row) == (eng.DecisionKind.ASK, 9)
    d = gate_decision(world, "S1", good(SH_CITES, confidence=0.6))
    assert (d.kind, d.gate_row) == (eng.DecisionKind.ASK, 9)
