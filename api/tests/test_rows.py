"""api/rows.py: the data/ rows load into contracts, run through the engine to the demo numbers, and display
fees get their notice date by strict matching (a wrong match would flip Rule #1)."""

import shutil
from datetime import date
from decimal import Decimal

import pytest

from api import adapters, rows
from api.engine.allowed import compute_allowed, notice_days
from api.engine.gate import concession, decide, summarize
from api.engine.policy import load_policy
from api.engine.quote_check import find_quote
from api.engine.tests import scenario as s
from api.engine.types import DecisionKind

POLICY = load_policy()
K = DecisionKind


def run(month, terms=None, rules=()):
    terms = s.spring_terms() if terms is None else terms
    sales = [adapters.to_engine_sales(r) for r in rows.sales()]
    priors = [adapters.to_engine_prior(p) for p in rows.prior_payments()]
    out = {}
    for c in rows.charges(month):
        e = adapters.to_engine_charge(c)
        out[c.id] = decide(e, compute_allowed(e, terms, sales, priors), s.strong_finding(c.id), POLICY, rules)
    return out


# --- The files say what scenario.py says -------------------------------------------------------------------

@pytest.mark.parametrize("rel,quote", [
    ("deals/spring-promo.md", s.Q_RATE),
    ("deals/spring-promo.md", s.Q_CAP),
    ("deals/spring-promo.md", s.Q_FEE),
    ("emails/broker-2026-03-28.eml", s.Q_BROKER),
    ("emails/northmart-2026-03-30.eml", s.Q_CLAIM),
    ("deals/amendment-1.md", "applies to a maximum of 6,000 units in total."),
])
def test_quotes_found_word_for_word(rel, quote):
    assert find_quote((rows.DATA / rel).read_text(), quote) is not None


def test_charges_match_scenario():
    for c in rows.charges("march"):
        ref = s.march_charges()[c.id]
        assert (c.ref, c.code, c.units, c.amount, c.period_start, c.period_end) == \
               (ref.ref, ref.code, ref.units, ref.amount, ref.period_start, ref.period_end)
    assert sum(c.amount for c in rows.charges("march")) == Decimal("6850.00")


def test_sales_totals_per_week():
    weekly = {}
    for w in rows.sales():
        if "Mint" not in w.product:
            weekly[w.week_start] = weekly.get(w.week_start, 0) + w.promo_units
    assert list(weekly.values()) == [1200, 980, 2820, 1540, 330]
    assert sum(w.promo_units for w in rows.sales() if "Mint" in w.product) == 1000


def test_prior_payments_and_plan():
    assert [(p.ref, p.amount) for p in rows.prior_payments()] == [("NM-2178", Decimal("980.00")), ("NM-2201", Decimal("2820.00"))]
    (plan,) = rows.promo_plan()
    assert (plan.products, plan.rate, plan.cap) == (["Peak Bar Original", "Peak Bar Chocolate"], Decimal("1.00"), 5000)


def test_notice_days_from_the_notice_files():
    days = {c.id: notice_days(c.notice_date, c.period_end)
            for m in ("march", "april") for c in rows.charges(m) if c.code == "DF"}
    assert days == {"C6": 20, "A1": 18, "A2": 5}


# --- The demo numbers from the files ------------------------------------------------------------------------

def test_march_from_files_hits_demo_numbers():
    first = run("march")
    assert {cid: d.kind for cid, d in first.items()} == {
        "C1": K.SPLIT, "C2": K.DISPUTE, "C3": K.ACCEPT, "C4": K.DISPUTE, "C5": K.DISPUTE, "C6": K.ASK}
    assert summarize(first.values()).questions == 1
    t = summarize(run("march", rules=[s.rule_1()]).values())
    assert (t.disputed, t.accepted, t.questions) == (Decimal("4120.00"), Decimal("2730.00"), 0)


def test_april_from_files_uses_rule_1():
    d = run("april", rules=[s.rule_1()])
    assert (d["A1"].kind, d["A1"].accepted) == (K.ACCEPT, Decimal("1200.00"))
    assert (d["A2"].kind, d["A2"].disputed) == (K.DISPUTE, Decimal("800.00"))


def test_amendment_1_from_files_concedes_1000():
    before = run("march")["C4"]
    after = run("march", s.spring_terms() + [s.amendment_1()])["C4"]
    assert (concession(before, after), after.disputed) == (Decimal("1000.00"), Decimal("540.00"))


# --- Strict notice matching ---------------------------------------------------------------------------------

@pytest.fixture
def data(tmp_path):
    """A copy of data/ to break on purpose."""
    for sub in ("charges", "notices"):
        shutil.copytree(rows.DATA / sub, tmp_path / sub)
    return tmp_path


def _notice(path, *, ref=None, amount="1,200.00", when="March 11, 2026", month_end="March 31, 2026"):
    ref_line = f"**Charge ref:** {ref}\n" if ref else ""
    path.write_text(f"# Northmart notice\n\n**Notice date:** {when}\n{ref_line}\n"
                    f"Northmart will charge a display fee of ${amount} for the month ending {month_end}.\n")


def test_ref_wins_over_amount(data):
    # A1 is $1,200 like C6; it must take its own notice (by ref), never the March one.
    a1 = next(c for c in rows.charges("april", data) if c.id == "A1")
    assert a1.notice_date == date(2026, 4, 12)


def test_no_notice_is_an_error_not_a_silent_none(data):
    (data / "notices" / "display-fee-2026-03-11.md").unlink()
    with pytest.raises(rows.DataError, match="C6 .*no notice"):
        rows.charges("march", data)


def test_two_loose_notices_that_fit_are_an_error(data):
    _notice(data / "notices" / "display-fee-2026-03-12.md", when="March 12, 2026")
    with pytest.raises(rows.DataError, match="2 notices without a ref"):
        rows.charges("march", data)


def test_ref_with_the_wrong_amount_is_an_error(data):
    _notice(data / "notices" / "display-fee-2026-04-12.md", ref="NM-2301", amount="1,500.00", when="April 12, 2026",
            month_end="April 30, 2026")
    with pytest.raises(rows.DataError, match="says \\$1500.00"):
        rows.charges("april", data)


def test_loose_notice_for_another_month_does_not_match(data):
    _notice(data / "notices" / "display-fee-2026-03-11.md", month_end="February 28, 2026")
    with pytest.raises(rows.DataError, match="no notice"):
        rows.charges("march", data)
