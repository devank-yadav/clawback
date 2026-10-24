"""The Peak Bar Co. / Northmart scenario from data/CLAUDE.md, built in code so engine tests don't depend on data/."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from api.engine.types import (
    Charge,
    DecisionKind,
    Finding,
    PriorPayment,
    Rule,
    SalesWeek,
    Term,
    TermType,
)

D = date
ORIG, CHOC, MINT = "Peak Bar Original", "Peak Bar Chocolate", "Peak Bar Mint"
BOTH = (ORIG, CHOC)

Q_RATE = ("Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and Peak Bar Chocolate "
          "sold between March 1 and March 31, 2026.")
Q_CAP = "The promotional allowance applies to a maximum of 5,000 units in total."
Q_FEE = ("Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice to "
         "Supplier.")
Q_BROKER = ("Northmart asked to extend Spring Promo through April 7, same terms, up to 500 additional units. "
            "Approved.")
Q_CLAIM = "Per our call, the Spring Promo rate is $1.50 per unit."


def spring_terms() -> list[Term]:
    """The deal (§3.1, §3.2, §5.4) plus the approved broker email of Mar 28."""
    return [
        Term("T-rate", TermType.PROMO_RATE, {"rate": "1.00"}, Q_RATE, D(2026, 3, 1), D(2026, 3, 31), source_doc_id="spring-promo"),
        Term("T-scope", TermType.PRODUCT_SCOPE, {"products": [ORIG, CHOC]}, Q_RATE, source_doc_id="spring-promo"),
        Term("T-dates", TermType.DATE_RANGE, {"start": "2026-03-01", "end": "2026-03-31"}, Q_RATE, source_doc_id="spring-promo"),
        Term("T-cap", TermType.UNIT_CAP, {"max_units": 5000}, Q_CAP, source_doc_id="spring-promo"),
        Term("T-fee", TermType.FEE_DISCRETION, {"max_fee": 1500}, Q_FEE, discretion=True, source_doc_id="spring-promo"),
        Term("T-ext", TermType.AMENDMENT, {"extra_units": 500}, Q_BROKER, D(2026, 4, 1), D(2026, 4, 7),
             source_doc_id="broker-2026-03-28"),
    ]


def amendment_1() -> Term:
    """Signed by both parties; raises the cap to 6,000. Only used when the judge attaches it."""
    return Term("T-cap-a1", TermType.UNIT_CAP, {"max_units": 6000}, "The maximum in Section 3.2 is raised to 6,000 units.",
                effective_from=D(2026, 4, 10), source_doc_id="amendment-1")


def northmart_claim() -> Term:
    """Northmart's Mar 30 email. Not an approved sender: a claim, never applied."""
    return Term("T-claim", TermType.PROMO_RATE, {"rate": "1.50"}, Q_CLAIM, D(2026, 3, 30),
                source_doc_id="northmart-2026-03-30", source_approved=False)


def _week(start, end, orig, choc):
    return [SalesWeek(start, end, ORIG, orig), SalesWeek(start, end, CHOC, choc)]


def store_sales() -> list[SalesWeek]:
    rows = (
        _week(D(2026, 3, 1), D(2026, 3, 7), 700, 500)        # week 1: 1,200
        + _week(D(2026, 3, 8), D(2026, 3, 14), 560, 420)     # week 2: 980
        + _week(D(2026, 3, 15), D(2026, 3, 21), 1620, 1200)  # week 3: 2,820 (running 5,000)
        + _week(D(2026, 3, 22), D(2026, 3, 31), 900, 640)    # week 4: 1,540
        + _week(D(2026, 4, 1), D(2026, 4, 7), 200, 130)      # Apr 1-7: 330
    )
    for s, e in ((D(2026, 3, 1), D(2026, 3, 7)), (D(2026, 3, 8), D(2026, 3, 14)),
                 (D(2026, 3, 15), D(2026, 3, 21)), (D(2026, 3, 22), D(2026, 3, 31))):
        rows.append(SalesWeek(s, e, MINT, 250))              # Mint: 1,000 in March
    return rows


def prior_payments() -> list[PriorPayment]:
    return [
        PriorPayment("NM-2178", D(2026, 3, 14), "SPRING-26", BOTH, D(2026, 3, 8), D(2026, 3, 14), 980, Decimal("980.00")),
        PriorPayment("NM-2201", D(2026, 3, 28), "SPRING-26", BOTH, D(2026, 3, 15), D(2026, 3, 21), 2820, Decimal("2820.00")),
    ]


def _charge(cid, ref, code, desc, products, units, rate, amount, start, end, notice=None):
    return Charge(cid, ref, code, desc, products, units, Decimal(rate), Decimal(amount), start, end, notice_date=notice)


def march_charges() -> dict[str, Charge]:
    cs = [
        _charge("C1", "NM-2229", "PA", "Spring promo week 1", BOTH, 1200, "1.50", "1800.00", D(2026, 3, 1), D(2026, 3, 7)),
        _charge("C2", "NM-2231", "PA", "Spring promo week 2", BOTH, 980, "1.00", "980.00", D(2026, 3, 8), D(2026, 3, 14)),
        _charge("C3", "NM-2240", "PA", "Spring promo Apr 1 to 7", BOTH, 330, "1.00", "330.00", D(2026, 4, 1), D(2026, 4, 7)),
        _charge("C4", "NM-2236", "PA", "Spring promo week 4", BOTH, 1540, "1.00", "1540.00", D(2026, 3, 22), D(2026, 3, 31)),
        _charge("C5", "NM-2237", "PA", "Spring promo Mint", (MINT,), 1000, "1.00", "1000.00", D(2026, 3, 1), D(2026, 3, 31)),
        _charge("C6", "NM-2238", "DF", "Display fee (notice Mar 11)", (), 1, "1200.00", "1200.00",
                D(2026, 3, 1), D(2026, 3, 31), notice=D(2026, 3, 11)),
    ]
    return {c.id: c for c in cs}


def april_charges() -> dict[str, Charge]:
    """April dates are ours until data/charges/northmart-april.csv lands; only the 18 and 5 days of notice matter."""
    cs = [
        _charge("A1", "NM-2301", "DF", "Display fee (18 days' notice)", (), 1, "1200.00", "1200.00",
                D(2026, 4, 1), D(2026, 4, 30), notice=D(2026, 4, 12)),
        _charge("A2", "NM-2302", "DF", "Display fee (5 days' notice)", (), 1, "800.00", "800.00",
                D(2026, 4, 1), D(2026, 4, 30), notice=D(2026, 4, 25)),
    ]
    return {c.id: c for c in cs}


def strong_finding(charge_id: str) -> Finding:
    """What the Investigator and the rehearsal return for a well-supported charge."""
    return Finding(charge_id, Decimal("0.95"), ("ev-1", "ev-2"), independent_sources=2, comeback_answered=True)


def rule_1(status: str = "active") -> Rule:
    return Rule(
        id="rule-1",
        pattern_text="Display fee charged at the distributor's discretion with written notice",
        term_type=TermType.FEE_DISCRETION,
        counterparty="Northmart",
        condition="notice_days >= 14",
        decision=DecisionKind.ACCEPT,
        else_decision=DecisionKind.DISPUTE,
        approver="Dana Okafor (owner)",
        learned_at=D(2026, 10, 24),
        source_question_id="Q-1",
        status=status,
        label="Rule #1",
    )
