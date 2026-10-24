"""F3 acceptance: the engine reproduces every number in data/CLAUDE.md."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from api.engine.allowed import compute_allowed, notice_days, product_key, split_products
from api.engine.tests import scenario as s
from api.engine.types import TermStatus, TermType


def allowed_for(cid, terms=None, charges=None):
    charges = charges or s.march_charges()
    return compute_allowed(charges[cid], s.spring_terms() if terms is None else terms, s.store_sales(), s.prior_payments())


@pytest.mark.parametrize(
    "cid, allowed, delta, units",
    [
        ("C1", "1200.00", "600.00", 1200),   # rate: $1.50 taken, deal says $1.00
        ("C2", "0.00", "980.00", 0),         # duplicate of NM-2178
        ("C3", "330.00", "0.00", 330),       # outside dates, covered by the broker email
        ("C4", "0.00", "1540.00", 0),        # cap reached in week 3
        ("C5", "0.00", "1000.00", 0),        # Mint not in the deal
        ("C6", "1200.00", "0.00", 0),        # fee under the $1,500 maximum
    ],
)
def test_march_charges(cid, allowed, delta, units):
    a = allowed_for(cid)
    assert a.allowed == Decimal(allowed)
    assert a.delta == Decimal(delta)
    assert a.covered_units == units
    assert not a.missing


def test_march_taken_totals_6850():
    total = sum(allowed_for(cid).taken for cid in s.march_charges())
    assert total == Decimal("6850.00")


def test_amounts_are_cents():
    for cid in s.march_charges():
        a = allowed_for(cid)
        assert a.allowed.as_tuple().exponent == -2 and a.delta.as_tuple().exponent == -2


def test_amendment_1_covers_1000_of_week_4():
    a = allowed_for("C4", s.spring_terms() + [s.amendment_1()])
    assert a.allowed == Decimal("1000.00")
    assert a.delta == Decimal("540.00")
    assert any(t.id == "T-cap-a1" for t in a.terms)


def test_c4_says_the_extension_does_not_reach_late_march():
    # The Investigator doubted this on its own; the engine states it, so C4's confidence doesn't sit on the floor.
    assert "The approved extension adds units only for Apr 1–Apr 7, not these dates." in allowed_for("C4").steps
    assert not any("extension" in step for cid in ("C1", "C2", "C3") for step in allowed_for(cid).steps)


def test_c3_without_broker_email_is_not_covered():
    terms = [t for t in s.spring_terms() if t.type != TermType.AMENDMENT]
    assert allowed_for("C3", terms).allowed == Decimal("0.00")


def test_broker_extension_stops_at_500_units():
    charges = s.march_charges()
    big = replace(charges["C3"], units=600, amount=Decimal("600.00"))
    sales = [r for r in s.store_sales() if r.week_start != date(2026, 4, 1)]
    sales += [s.SalesWeek(date(2026, 4, 1), date(2026, 4, 7), s.ORIG, 600)]
    a = compute_allowed(big, s.spring_terms(), sales, s.prior_payments())
    assert a.allowed == Decimal("500.00")


def test_northmart_claim_never_changes_the_rate():
    a = allowed_for("C1", s.spring_terms() + [s.northmart_claim()])
    assert a.allowed == Decimal("1200.00")
    assert all(t.id != "T-claim" for t in a.terms)


def test_partial_prior_payment_only_removes_paid_units():
    priors = [replace(s.prior_payments()[0], units=500, amount=Decimal("500.00"))]
    a = compute_allowed(s.march_charges()["C2"], s.spring_terms(), s.store_sales(), priors)
    assert a.allowed == Decimal("480.00")


def test_week_3_alone_fits_under_cap():
    charges = s.march_charges()
    wk3 = replace(charges["C2"], id="W3", units=2820, amount=Decimal("2820.00"),
                  period_start=date(2026, 3, 15), period_end=date(2026, 3, 21))
    a = compute_allowed(wk3, s.spring_terms(), s.store_sales(), [])
    assert a.allowed == Decimal("2820.00")


def test_covered_units_never_exceed_units_sold():
    charges = s.march_charges()
    inflated = replace(charges["C1"], units=1500, rate=Decimal("1.00"), amount=Decimal("1500.00"))
    assert compute_allowed(inflated, s.spring_terms(), s.store_sales(), []).allowed == Decimal("1200.00")


def test_missing_rate_term_is_reported():
    terms = [t for t in s.spring_terms() if t.type != TermType.PROMO_RATE]
    a = allowed_for("C1", terms)
    assert a.missing == ("promo_rate",)


def test_rejected_term_is_used_only_when_nothing_else_exists():
    terms = [replace(t, status=TermStatus.REJECTED) if t.id == "T-rate" else t for t in s.spring_terms()]
    a = allowed_for("C1", terms)
    assert any(t.id == "T-rate" and t.status == TermStatus.REJECTED for t in a.terms)
    fake = replace(s.amendment_1(), status=TermStatus.REJECTED)
    a = allowed_for("C4", s.spring_terms() + [fake])
    assert a.allowed == Decimal("0.00") and all(t.id != fake.id for t in a.terms)


def test_unknown_code_is_missing():
    c = replace(s.march_charges()["C1"], code="ZZ")
    assert allowed_for("C1", charges={"C1": c}).missing == ("code:ZZ",)


def test_fee_over_maximum():
    c = replace(s.march_charges()["C6"], amount=Decimal("2000.00"))
    a = compute_allowed(c, s.spring_terms())
    assert a.allowed == Decimal("1500.00") and a.delta == Decimal("500.00")


@pytest.mark.parametrize("cid, days", [("C6", 20)])
def test_march_notice_days(cid, days):
    assert allowed_for(cid).facts["notice_days"] == days


def test_april_notice_days():
    april = s.april_charges()
    assert compute_allowed(april["A1"], s.spring_terms()).facts["notice_days"] == 18
    assert compute_allowed(april["A2"], s.spring_terms()).facts["notice_days"] == 5


def test_helpers():
    assert product_key("Peak Bar  Original") == product_key("original")
    assert split_products("Original+Chocolate") == ("Original", "Chocolate")
    assert split_products("Peak Bar Original; Peak Bar Chocolate") == ("Peak Bar Original", "Peak Bar Chocolate")
    assert notice_days(None, date(2026, 3, 31)) is None
