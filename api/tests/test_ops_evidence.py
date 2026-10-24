"""Operations evidence: proof of delivery, agreed prices and ops terms as evidence items, ops terms checked word for
word against their deal, the math line's links for SH / PR / SP, and the adapter into the engine's OpsData."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from api import adapters, documents
from api import evidence as ev
from api.contracts import Charge, DeliveryRow, OpsTerm, PriceRow
from api.engine.allowed import compute_allowed
from api.engine.types import TermStatus

# A deal with an operations section, as an account's deal document would have.
OPS_DEAL = """# Supply Agreement

## 7. Deliveries and returns

7.1 Shortages must be noted on the signed proof of delivery at receipt.

7.2 Supplier allows spoils and unsaleables of up to 1.0% of the amount invoiced each month.
"""
SPOILS = "Supplier allows spoils and unsaleables of up to 1.0% of the amount invoiced each month."


@pytest.fixture(scope="module")
def deal_id() -> str:
    return documents.paste(OPS_DEAL).id


def deliveries() -> list[DeliveryRow]:
    return [
        DeliveryRow(line_ref="L-1001", product="Peak Bar Original", shipped_units=1200, received_units=1200,
                    unit_price="2.50", received_by="J. Ortiz", received_at="2026-03-04"),
        DeliveryRow(line_ref="L-1002", product="Peak Bar Chocolate", shipped_units=600, received_units=552,
                    unit_price="3.00", received_by="J. Ortiz", received_at="2026-03-06T09:30:00-08:00"),
        DeliveryRow(line_ref="L-2002", product="Peak Bar Chocolate", shipped_units=1000, received_units=1000,
                    unit_price="2.60", received_by="", received_at="2026-03-12"),
    ]


def prices() -> list[PriceRow]:
    return [
        PriceRow(product="Peak Bar Chocolate", agreed_price="2.55", effective_from="2026-01-01",
                 effective_to="2026-02-28", source_doc="spring-promo"),
        PriceRow(product="Peak Bar Chocolate", agreed_price="2.45", effective_from="2026-03-01", effective_to="",
                 source_doc="spring-promo"),
        PriceRow(product="Oat Milk Barista", agreed_price="4.10", effective_from="2026-03-01"),
    ]


def spoils(deal_id: str, **kw) -> OpsTerm:
    return OpsTerm(**{"key": "spoils_allowance_pct", "value": "1.0", "source_doc": deal_id, "quote": SPOILS, **kw})


def charge(cid, code, units, rate, amount, line_ref=None, start="2026-03-01", end="2026-03-31") -> Charge:
    return Charge(id=cid, ref=f"NM-{cid}", code=code, description=f"{code} charge", product=None, units=units, rate=rate,
                  amount=amount, period_start=start, period_end=end, line_ref=line_ref)


# --- Evidence builders ----------------------------------------------------------------------------------------

def test_from_deliveries_one_item_per_line():
    items = ev.from_deliveries(deliveries())
    assert list(items) == ["ev-pod-L-1001", "ev-pod-L-1002", "ev-pod-L-2002"]
    pod = items["ev-pod-L-1002"]
    assert (pod.kind, pod.label) == ("delivery", "Delivery L-1002")
    assert pod.summary == ("600 units of Peak Bar Chocolate shipped and 552 received, signed for by J. Ortiz on "
                           "Mar 6, 2026, invoiced at $3.00 a unit.")
    assert pod.rows == [{"line_ref": "L-1002", "product": "Peak Bar Chocolate", "shipped_units": 600,
                         "received_units": 552, "unit_price": 3.0, "received_by": "J. Ortiz",
                         "received_at": "2026-03-06T09:30:00-08:00"}]
    assert items["ev-pod-L-2002"].summary.startswith("1,000 units of Peak Bar Chocolate shipped and 1,000 received on")


def test_from_prices_one_item_per_product():
    items = ev.from_prices(prices())
    assert list(items) == ["ev-price-chocolate", "ev-price-oat-milk-barista"]
    choc = items["ev-price-chocolate"]
    assert (choc.kind, choc.label, len(choc.rows)) == ("price", "Price list: Peak Bar Chocolate", 2)
    assert choc.summary == ("Agreed price for Peak Bar Chocolate: $2.55 a unit from Jan 1, 2026 to Feb 28, 2026; "
                            "$2.45 a unit from Mar 1, 2026, per spring-promo.")
    assert items["ev-price-oat-milk-barista"].summary == "Agreed price for Oat Milk Barista: $4.10 a unit from Mar 1, 2026."


def test_from_ops_terms_quotes_the_deal(deal_id):
    item = ev.from_ops_terms([spoils(deal_id)])["ev-term-spoils_allowance_pct"]
    assert (item.kind, item.label) == ("policy", "§7.2 spoils allowance")
    assert item.summary == "The deal sets the spoils allowance at 1.0%."
    q = item.quote
    assert (q.doc_id, q.text) == (deal_id, SPOILS) and OPS_DEAL[q.char_start:q.char_end] == SPOILS
    assert q.context_before == "7.2 " and q.context_after == ""
    assert item.rows == [{"key": "spoils_allowance_pct", "value": "1.0", "source_doc": deal_id, "quote": SPOILS}]


def test_ops_term_quote_found_across_a_line_break_in_a_real_deal():
    window = OpsTerm(key="dispute_window_days", value="60", source_doc="spring-promo",
                     quote="Supplier may dispute any deduction within 60 days of the remittance date")
    item = ev.from_ops_terms([window])["ev-term-dispute_window_days"]
    assert item.label == "§4.3 dispute window days" and item.summary == "The deal sets the dispute window days at 60."


@pytest.mark.parametrize("change", [
    {"quote": "Supplier allows spoils and unsaleables of up to 2.0% of the amount invoiced each month."},  # not in it
    {"value": "2.0"},  # the quote doesn't state the value
    {"source_doc": "no-such-doc"},
    {"quote": ""},
])
def test_ops_term_not_found_word_for_word_is_rejected(deal_id, change):
    t = spoils(deal_id, **change)
    assert ev.ops_quote(t) is None and ev.from_ops_terms([t]) == {}
    assert adapters.to_engine_ops([], [], [t]).terms[0].status == TermStatus.REJECTED


def test_ops_term_quote_tolerates_spacing_and_dashes(deal_id):
    t = spoils(deal_id, quote="Supplier allows spoils and  unsaleables of up to 1.0%\nof the amount invoiced each month.")
    assert ev.ops_quote(t) is not None


def test_from_ops_merges_all_three(deal_id):
    items = ev.from_ops(deliveries(), prices(), [spoils(deal_id)])
    assert {i.kind for i in items.values()} == {"delivery", "price", "policy"} and len(items) == 6


# --- The math line links each step to its evidence (F7) ------------------------------------------------------

@pytest.fixture
def run_evidence(deal_id):
    charges = [charge("S2", "SH", 48, "3.00", "144.00", "L-1002"), charge("P2", "PR", 1000, "0.25", "250.00", "L-2002"),
               charge("Z1", "SP", 1, "1296.00", "1296.00")]
    items = {**ev.from_charges(charges), **ev.from_ops(deliveries(), prices(), [spoils(deal_id)])}
    return {c.id: c for c in charges}, items, adapters.to_engine_ops(deliveries(), prices(), [spoils(deal_id)])


def links(c, items, ops):
    a = compute_allowed(adapters.to_engine_charge(c), [], ops=ops)
    assert not a.missing
    return [(p.text, p.evidence_id) for p in ev.math_parts(a.steps, a.terms, c, [], items)]


def test_shortage_math_links(run_evidence):
    charges, items, ops = run_evidence
    assert links(charges["S2"], items, ops) == [
        ("Delivery L-1002: 600 units shipped, 552 received, signed by J. Ortiz on Mar 6.", "ev-pod-L-1002"),
        ("Claimed 48 units short; the delivery shows 48 short.", "ev-charge-S2"),
        ("48 units x $3.00 = $144.00.", "ev-pod-L-1002"),
    ]


def test_price_math_links(run_evidence):
    charges, items, ops = run_evidence
    assert [i for _, i in links(charges["P2"], items, ops)] == [
        "ev-pod-L-2002", "ev-price-chocolate", "ev-charge-P2", "ev-charge-P2"]


def test_spoilage_math_links(run_evidence):
    charges, items, ops = run_evidence
    got = links(charges["Z1"], items, ops)
    assert got == [
        ("Delivery L-1001: 1,200 units shipped x $2.50 = $3,000.00, received Mar 4.", "ev-pod-L-1001"),
        ("Delivery L-1002: 600 units shipped x $3.00 = $1,800.00, received Mar 6.", "ev-pod-L-1002"),
        ("Delivery L-2002: 1,000 units shipped x $2.60 = $2,600.00, received Mar 12.", "ev-pod-L-2002"),
        ("Invoiced Mar 1 to Mar 31: $7,400.00.", None),  # a sum of the lines above: nothing more to open
        ("Spoils allowance 1.0% of $7,400.00 = $74.00.", "ev-term-spoils_allowance_pct"),
        ("Claimed $1,296.00; allowed is the smaller: $74.00.", "ev-charge-Z1"),
    ]


def test_missing_steps_and_unknown_evidence_stay_plain(run_evidence):
    charges, items, ops = run_evidence
    lost = charges["S2"].model_copy(update={"line_ref": "L-9999"})
    a = compute_allowed(adapters.to_engine_charge(lost), [], ops=ops)
    assert [p.evidence_id for p in ev.math_parts(a.steps, a.terms, lost, [], items)] == [None]
    # The links only point at evidence that exists in the run.
    a = compute_allowed(adapters.to_engine_charge(charges["S2"]), [], ops=ops)
    assert [p.evidence_id for p in ev.math_parts(a.steps, a.terms, charges["S2"], [], {})] == [None, None, None]


# --- The adapter and the Charge contract ---------------------------------------------------------------------

def test_to_engine_ops(deal_id):
    ops = adapters.to_engine_ops(deliveries(), prices(), [spoils(deal_id)])
    assert ops.deliveries[1].received_at == date(2026, 3, 6)  # a datetime becomes its date
    assert ops.deliveries[1].unit_price == Decimal("3.00") and ops.deliveries[2].received_by == ""
    assert ops.prices[1].effective_to is None and ops.prices[2].source_doc == ""
    assert ops.terms[0].status == TermStatus.VERIFIED and ops.terms[0].value == "1.0"


def test_charge_line_ref_reaches_the_engine():
    c = charge("S2", "SH", 48, "3.00", "144.00", "L-1002")
    assert adapters.to_engine_charge(c).line_ref == "L-1002"
    assert adapters.to_engine_charge(c.model_copy(update={"line_ref": None})).line_ref is None


def test_charge_without_line_ref_serializes_as_before():
    """Charge rows reach the agents' requests, and so the DEMO_MODE fixture keys: no line_ref key unless it's set."""
    c = charge("C1", "PA", 1200, "1.50", "1800.00")
    assert "line_ref" not in c.model_dump(mode="json") and "line_ref" not in c.model_dump_json()
    assert Charge.model_validate({**c.model_dump(), "line_ref": " "}).line_ref is None
    shortage = charge("S2", "SH", 48, "3.00", "144.00", "L-1002")
    assert shortage.model_dump(mode="json", exclude={"remittance_id"})["line_ref"] == "L-1002"
    assert Charge.model_validate_json(shortage.model_dump_json()) == shortage


def test_delivery_row_parses_csv_strings():
    r = DeliveryRow.model_validate({"line_ref": "L-1", "product": "P", "shipped_units": "10", "received_units": "9",
                                    "unit_price": "2.455", "received_by": " ", "received_at": "2026-03-04T10:15:00+00:00"})
    assert (r.received_by, r.received_at, r.unit_price) == (None, datetime.fromisoformat("2026-03-04T10:15:00+00:00"),
                                                            Decimal("2.455"))
    assert OpsTerm.model_validate({"key": "k", "value": 1.5, "source_doc": "d", "quote": "q"}).value == "1.5"
