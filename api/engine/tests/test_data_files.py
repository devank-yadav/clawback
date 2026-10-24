"""Cross-check: the real files in data/ (Manasv's) run through the engine and give the demo numbers.

scenario.py builds the same story in code, so engine tests don't depend on data/. This file closes the gap: it
loads data/charges, sales, payments and notices, finds every quote scenario.py uses word for word in the deal
and email files, and checks the totals. It skips while data/ isn't on this branch; set CLAWBACK_DATA_DIR to
point it at another checkout (e.g. the story branch).
"""

import csv
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from api.engine.allowed import compute_allowed, split_products
from api.engine.gate import concession, decide, summarize
from api.engine.policy import load_policy
from api.engine.quote_check import find_quote
from api.engine.tests import scenario as s
from api.engine.types import Charge, DecisionKind, PriorPayment, SalesWeek, money

DATA = Path(os.environ.get("CLAWBACK_DATA_DIR", Path(__file__).resolve().parents[3] / "data"))
pytestmark = pytest.mark.skipif(not (DATA / "charges" / "northmart-march.csv").exists(),
                                reason=f"no scenario data at {DATA}")
POLICY = load_policy()
K = DecisionKind


def _rows(rel):
    with open(DATA / rel, newline="") as f:
        return list(csv.DictReader(f))


def _notices():
    """notices/*.md -> {(ref or None, amount): notice date}. A notice names its charge ref when it has one."""
    out = {}
    for p in sorted((DATA / "notices").glob("*.md")):
        text = p.read_text()
        when = datetime.strptime(re.search(r"\*\*Notice date:\*\*\s*(.+)", text).group(1).strip(), "%B %d, %Y").date()
        ref = re.search(r"\*\*Charge ref:\*\*\s*(\S+)", text)
        amount = money(re.search(r"\$([\d,]+\.\d\d)", text).group(1).replace(",", ""))
        out[(ref.group(1) if ref else None, amount)] = when
    return out


def charges(rel):
    notices = _notices()
    out = {}
    for r in _rows(rel):
        amount = money(r["amount"])
        notice = None
        if r["code"] == "DF":
            notice = notices.get((r["ref"], amount)) or notices.get((None, amount))
        products = () if r["product"] == "none" else split_products(r["product"])
        out[r["charge_id"]] = Charge(r["charge_id"], r["ref"], r["code"], r["description"], products, int(r["units"]),
                                     money(r["rate"]), amount, date.fromisoformat(r["period_start"]),
                                     date.fromisoformat(r["period_end"]), notice_date=notice)
    return out


def sales():
    return [SalesWeek(date.fromisoformat(r["week_start"]), date.fromisoformat(r["week_end"]), r["product"],
                      int(r["promo_units"]), int(r["total_units"])) for r in _rows("sales/store-sales.csv")]


def priors():
    return [PriorPayment(r["ref"], date.fromisoformat(r["paid_on"]), r["promo_id"], split_products(r["product"]),
                         date.fromisoformat(r["period_start"]), date.fromisoformat(r["period_end"]), int(r["units"]),
                         money(r["amount"])) for r in _rows("payments/prior.csv")]


def run(cs, terms=None, rules=()):
    terms = s.spring_terms() if terms is None else terms
    return {cid: decide(c, compute_allowed(c, terms, sales(), priors()), s.strong_finding(cid), POLICY, rules)
            for cid, c in cs.items()}


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
    assert find_quote((DATA / rel).read_text(), quote) is not None


def test_charges_match_scenario():
    for cid, c in charges("charges/northmart-march.csv").items():
        ref = s.march_charges()[cid]
        assert (c.ref, c.code, c.units, c.amount, c.period_start, c.period_end) == \
               (ref.ref, ref.code, ref.units, ref.amount, ref.period_start, ref.period_end)


def test_sales_totals_per_week():
    weekly = {}
    for w in sales():
        if "Mint" not in w.product:
            weekly[w.week_start] = weekly.get(w.week_start, 0) + w.promo_units
    assert list(weekly.values()) == [1200, 980, 2820, 1540, 330]
    assert sum(w.promo_units for w in sales() if "Mint" in w.product) == 1000


def test_notice_days_from_the_notice_files():
    from api.engine.allowed import notice_days
    days = {cid: notice_days(c.notice_date, c.period_end)
            for f in ("charges/northmart-march.csv", "charges/northmart-april.csv")
            for cid, c in charges(f).items() if c.code == "DF"}
    assert days == {"C6": 20, "A1": 18, "A2": 5}


# --- The demo numbers from the files ------------------------------------------------------------------------

def test_march_from_files_hits_demo_numbers():
    cs = charges("charges/northmart-march.csv")
    first = run(cs)
    assert {cid: d.kind for cid, d in first.items()} == {
        "C1": K.SPLIT, "C2": K.DISPUTE, "C3": K.ACCEPT, "C4": K.DISPUTE, "C5": K.DISPUTE, "C6": K.ASK}
    assert summarize(first.values()).questions == 1

    final = run(cs, rules=[s.rule_1()])
    t = summarize(final.values())
    assert (t.disputed, t.accepted, t.questions) == (Decimal("4120.00"), Decimal("2730.00"), 0)
    assert sum((c.amount for c in cs.values()), Decimal(0)) == Decimal("6850.00")


def test_april_from_files_uses_rule_1():
    d = run(charges("charges/northmart-april.csv"), rules=[s.rule_1()])
    assert (d["A1"].kind, d["A1"].accepted) == (K.ACCEPT, Decimal("1200.00"))
    assert (d["A2"].kind, d["A2"].disputed) == (K.DISPUTE, Decimal("800.00"))


def test_amendment_1_from_files_concedes_1000():
    cs = charges("charges/northmart-march.csv")
    before = run(cs)["C4"]
    after = run(cs, s.spring_terms() + [s.amendment_1()])["C4"]
    assert concession(before, after) == Decimal("1000.00")
    assert after.disputed == Decimal("540.00")
