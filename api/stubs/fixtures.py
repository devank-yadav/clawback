"""The fake demo run the stub routes serve and web/ builds against, written as contract objects.

Every amount here is copied from data/CLAUDE.md (the scenario); nothing is computed. When the real pipeline
lands, a recorded run replaces this file's output.

Regenerate the web fixtures:  python -m api.stubs.fixtures
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from api.engine import audit_chain
from api.contracts import (
    Answer, Approval, ApprovalLine, AuditEntry, Charge, ChargeDetail, CoachResponse, Decision, Dispute,
    DisputeLine, EvalReport, EventAdapter, Evidence, Finding, LedgerLine, LedgerPost, LogLine, MathPart,
    PortalMessage, Question, Quote, Redline, Rehearsal, Remittance, Rule, RunFixture, RunInfo,
    Summary, Totals,
)

PDT = timezone(timedelta(hours=-7))
REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
WEB_FIXTURES = REPO / "web" / "fixtures"

MARCH_RUN = "run-march-demo"
REFUSED_RUN = "run-march-refused"  # same run, but Sam refuses the credit memo
APRIL_RUN = "run-april-demo"
REMITTANCE_ID = "REM-3102"
DISPUTE_ID = "D-0417"


def _m(v: str | int) -> Decimal:
    return Decimal(str(v))


# ---------------------------------------------------------------- evidence
# Quote offsets are into the files under data/ (api/tests check them); the context comes from the same files.

def _paragraph_context(doc_id: str, start: int, end: int) -> tuple[str, str]:
    """The rest of the paragraph (blank-line block) around source[start:end], as written in the file."""
    text = (DATA / QUOTE_SOURCES[doc_id]).read_text()
    para_start = text.rfind("\n\n", 0, start)
    para_start = 0 if para_start == -1 else para_start + 2
    para_end = text.find("\n\n", end)
    para_end = len(text.rstrip("\n")) if para_end == -1 else para_end
    return text[para_start:start], text[end:para_end]


def _q(doc_id: str, text: str, start: int, end: int) -> Quote:
    before, after = _paragraph_context(doc_id, start, end)
    return Quote(doc_id=doc_id, text=text, char_start=start, char_end=end, context_before=before, context_after=after)


S31 = "Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and Peak Bar Chocolate sold between March 1 and March 31, 2026."
S32 = "The promotional allowance applies to a maximum of 5,000 units in total."
S42 = "A unit may be claimed only once."
S54 = "Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice to Supplier."
S61 = "This Agreement may be changed only in writing: by an amendment signed by both parties, or by a written approval sent by one of Supplier's approved representatives named in Section 6.2."
BROKER = "Northmart asked to extend Spring Promo through April 7, same terms, up to 500 additional units. Approved."
CLAIM = "Per our call, the Spring Promo rate is $1.50 per unit."
A32 = "The promotional allowance applies to a maximum of 6,000 units in total."  # amendment-1, replacing §3.2

QUOTE_SOURCES = {  # doc_id -> path under data/ (Peak Bar's account folder)
    "spring-promo": "accounts/peak-bar/deals/spring-promo.md",
    "amendment-1": "accounts/peak-bar/deals/amendment-1.md",
    "summer-draft": "accounts/peak-bar/deals/summer-draft.md",
    "broker-2026-03-28": "accounts/peak-bar/emails/broker-2026-03-28.eml",
    "northmart-2026-03-30": "accounts/peak-bar/emails/northmart-2026-03-30.eml",
    "display-fee-2026-03-11": "accounts/peak-bar/notices/display-fee-2026-03-11.md",
    "display-fee-2026-04-12": "accounts/peak-bar/notices/display-fee-2026-04-12.md",
    "display-fee-2026-04-25": "accounts/peak-bar/notices/display-fee-2026-04-25.md",
}


def _sales(week_start: str, week_end: str, *rows: tuple[str, int, int]) -> list[dict[str, Any]]:
    return [
        {"week_start": week_start, "week_end": week_end, "product": p, "promo_units": u, "total_units": t}
        for p, u, t in rows
    ]


MARCH_CHARGES = [
    Charge(id="C1", remittance_id=REMITTANCE_ID, ref="NM-2229", code="PA", description="Spring promo week 1",
           product="Original+Chocolate", units=1200, rate=_m("1.50"), amount=_m(1800),
           period_start=date(2026, 3, 1), period_end=date(2026, 3, 7)),
    Charge(id="C2", remittance_id=REMITTANCE_ID, ref="NM-2231", code="PA", description="Spring promo week 2",
           product="Original+Chocolate", units=980, rate=_m("1.00"), amount=_m(980),
           period_start=date(2026, 3, 8), period_end=date(2026, 3, 14)),
    Charge(id="C3", remittance_id=REMITTANCE_ID, ref="NM-2240", code="PA", description="Spring promo Apr 1 to 7",
           product="Original+Chocolate", units=330, rate=_m("1.00"), amount=_m(330),
           period_start=date(2026, 4, 1), period_end=date(2026, 4, 7)),
    Charge(id="C4", remittance_id=REMITTANCE_ID, ref="NM-2236", code="PA", description="Spring promo week 4",
           product="Original+Chocolate", units=1540, rate=_m("1.00"), amount=_m(1540),
           period_start=date(2026, 3, 22), period_end=date(2026, 3, 31)),
    Charge(id="C5", remittance_id=REMITTANCE_ID, ref="NM-2237", code="PA", description="Spring promo Mint",
           product="Mint", units=1000, rate=_m("1.00"), amount=_m(1000),
           period_start=date(2026, 3, 1), period_end=date(2026, 3, 31)),
    Charge(id="C6", remittance_id=REMITTANCE_ID, ref="NM-2238", code="DF", description="Display fee (notice Mar 11)",
           product=None, units=1, rate=_m("1200.00"), amount=_m(1200),
           period_start=date(2026, 3, 1), period_end=date(2026, 3, 31), notice_date=date(2026, 3, 11)),
]

APRIL_CHARGES = [
    Charge(id="A1", ref="NM-2301", code="DF", description="Display fee (notice Apr 12)", product=None, units=1,
           rate=_m("1200.00"), amount=_m(1200), period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
           notice_date=date(2026, 4, 12)),
    Charge(id="A2", ref="NM-2302", code="DF", description="End-cap display fee (notice Apr 25)", product=None,
           units=1, rate=_m("800.00"), amount=_m(800), period_start=date(2026, 4, 1), period_end=date(2026, 4, 30),
           notice_date=date(2026, 4, 25)),
]


def _charge_ev(c: Charge) -> Evidence:
    return Evidence(id=f"ev-charge-{c.id}", kind="charge", label=f"Charge {c.id} ({c.ref})",
                    summary=f"Northmart's remittance line {c.ref}: {c.description}.",
                    rows=[c.model_dump(mode="json")])


EVIDENCE: dict[str, Evidence] = {e.id: e for e in [
    Evidence(id="ev-deal-3.1", kind="clause", label="§3.1 rate and products",
             summary="The deal pays $1.00 a bar on Original and Chocolate sold March 1 to 31.",
             quote=_q("spring-promo", S31, 934, 1079)),
    Evidence(id="ev-deal-3.2", kind="clause", label="§3.2 cap",
             summary="The promo covers at most 5,000 bars in total.",
             quote=_q("spring-promo", S32, 1085, 1156)),
    Evidence(id="ev-deal-4.2", kind="clause", label="§4.2 claim once",
             summary="A bar can be claimed only once.",
             quote=_q("spring-promo", S42, 1451, 1483)),
    Evidence(id="ev-deal-5.4", kind="clause", label="§5.4 display fee",
             summary="Northmart may charge up to $1,500 a month for display, at its discretion, with written notice.",
             quote=_q("spring-promo", S54, 1968, 2080)),
    Evidence(id="ev-deal-6.1", kind="clause", label="§6.1 changes in writing",
             summary="The deal changes only by an amendment both sides sign, or written approval from Dana or the broker.",
             quote=_q("spring-promo", S61, 2119, 2303)),
    Evidence(id="ev-amendment-1", kind="clause", label="Amendment No. 1 (signed)",
             summary="Signed by Peak Bar and Northmart on Mar 20: raises the §3.2 cap to 6,000 bars.",
             quote=_q("amendment-1", A32, 544, 615)),
    Evidence(id="ev-email-broker-0328", kind="email", label="Broker email Mar 28",
             summary="Jordan Lee, Peak Bar's approved broker, extended the promo through Apr 7, up to 500 more bars.",
             quote=_q("broker-2026-03-28", BROKER, 417, 522), sender="jordan@peakbar-broker.example",
             approved_sender=True, sent_at=datetime(2026, 3, 28, 10, 14, tzinfo=PDT)),
    Evidence(id="ev-claim-northmart-0330", kind="claim", label="Northmart email Mar 30 (claim)",
             summary="Northmart says the rate is $1.50. Northmart can't change the deal by email, so this is a claim.",
             quote=_q("northmart-2026-03-30", CLAIM, 369, 423), sender="deductions@northmart.example",
             approved_sender=False, sent_at=datetime(2026, 3, 30, 16, 42, tzinfo=PDT)),
    Evidence(id="ev-notice-0311", kind="notice", label="Notice Mar 11",
             summary="Northmart gave written notice of a $1,200 display fee on Mar 11, 20 days before month end.",
             quote=_q("display-fee-2026-03-11", "Northmart will charge a display fee of $1,200.00 for the month ending March 31, 2026, for secondary display placement of Peak Bar products.", 312, 451),
             rows=[{"notice_date": "2026-03-11", "period_end": "2026-03-31", "notice_days": 20}]),
    Evidence(id="ev-notice-0412", kind="notice", label="Notice Apr 12",
             summary="Northmart gave written notice of a $1,200 display fee on Apr 12, 18 days before month end.",
             quote=_q("display-fee-2026-04-12", "Northmart will charge a display fee of $1,200.00 for the month ending April 30, 2026, for secondary display placement of Peak Bar products.", 336, 475),
             rows=[{"notice_date": "2026-04-12", "period_end": "2026-04-30", "notice_days": 18}]),
    Evidence(id="ev-notice-0425", kind="notice", label="Notice Apr 25",
             summary="Northmart gave written notice of an $800 end-cap display fee on Apr 25, 5 days before month end.",
             quote=_q("display-fee-2026-04-25", "Northmart will charge an additional display fee of $800.00 for the month ending April 30, 2026, for end-cap display placement of Peak Bar products.", 336, 483),
             rows=[{"notice_date": "2026-04-25", "period_end": "2026-04-30", "notice_days": 5}]),
    Evidence(id="ev-sales-w1", kind="sales", label="Week 1 sales", summary="1,200 promoted bars sold Mar 1 to 7.",
             rows=_sales("2026-03-01", "2026-03-07", ("Peak Bar Original", 700, 820), ("Peak Bar Chocolate", 500, 590))),
    Evidence(id="ev-sales-w2", kind="sales", label="Week 2 sales", summary="980 promoted bars sold Mar 8 to 14.",
             rows=_sales("2026-03-08", "2026-03-14", ("Peak Bar Original", 540, 650), ("Peak Bar Chocolate", 440, 520))),
    Evidence(id="ev-sales-w3", kind="sales", label="Week 3 sales",
             summary="2,820 promoted bars sold Mar 15 to 21; the running total reaches the 5,000 cap.",
             rows=_sales("2026-03-15", "2026-03-21", ("Peak Bar Original", 1600, 1780), ("Peak Bar Chocolate", 1220, 1370))),
    Evidence(id="ev-sales-w4", kind="sales", label="Week 4 sales", summary="1,540 promoted bars sold Mar 22 to 31, all after the cap.",
             rows=_sales("2026-03-22", "2026-03-31", ("Peak Bar Original", 880, 1010), ("Peak Bar Chocolate", 660, 760))),
    Evidence(id="ev-sales-apr1-7", kind="sales", label="Apr 1 to 7 sales", summary="330 promoted bars sold Apr 1 to 7.",
             rows=_sales("2026-04-01", "2026-04-07", ("Peak Bar Original", 190, 260), ("Peak Bar Chocolate", 140, 200))),
    Evidence(id="ev-sales-mint", kind="sales", label="Mint sales", summary="1,000 Mint bars sold on promo in March.",
             rows=[r for ws, we, total in [("2026-03-01", "2026-03-07", 300), ("2026-03-08", "2026-03-14", 290),
                                           ("2026-03-15", "2026-03-21", 310), ("2026-03-22", "2026-03-31", 320)]
                   for r in _sales(ws, we, ("Peak Bar Mint", 250, total))]),
    Evidence(id="ev-payment-NM-2178", kind="prior_payment", label="Paid Mar 14 (NM-2178)",
             summary="Northmart already took $980 for week 2 on Mar 14.",
             rows=[{"ref": "NM-2178", "paid_on": "2026-03-14", "promo_id": "SPRING-26", "product": "Original+Chocolate",
                    "period_start": "2026-03-08", "period_end": "2026-03-14", "units": 980, "amount": 980.0}]),
    Evidence(id="ev-rule-1", kind="rule", label="Rule #1",
             summary="Accept Northmart display fees with at least 14 days' notice; otherwise dispute. Learned from Dana's answer.",
             rule_id="rule-1", person="Dana Okafor (owner)"),
    Evidence(id="ev-answer-Q-1", kind="person", label="Dana's answer",
             summary="Dana Okafor (owner) answered by text: \"accept if notice is at least 14 days\".",
             person="Dana Okafor (owner)"),
    Evidence(id="ev-approval-AP-1", kind="approval", label="Sam approved",
             summary="Sam Reyes (controller) approved the $2,730 credit memo.",
             approval_id="AP-1", person="Sam Reyes (controller)"),
    *[_charge_ev(c) for c in MARCH_CHARGES + APRIL_CHARGES],
]}


def _p(text: str, ev: str | None = None) -> MathPart:
    return MathPart(text=text, evidence_id=ev)


# ---------------------------------------------------------------- per-charge results (from data/CLAUDE.md)

FINDINGS = {f.charge_id: f for f in [
    Finding(id="F-C1", charge_id="C1", type="rate_over", expected=_m(1200), taken=_m(1800), delta=_m(600),
            finding="Charged $1.50 a bar, but §3.1 sets $1.00. Week 1 sold 1,200 bars, so $1,200 is allowed and $600 is too much.",
            evidence_ids=["ev-deal-3.1", "ev-sales-w1", "ev-charge-C1", "ev-claim-northmart-0330"], confidence=0.97,
            math=[_p("1,200 bars", "ev-sales-w1"), _p(" × "), _p("$1.00", "ev-deal-3.1"), _p(" = $1,200 allowed · took "),
                  _p("$1,800", "ev-charge-C1"), _p(" → $600 too much")]),
    Finding(id="F-C2", charge_id="C2", type="duplicate", expected=_m(0), taken=_m(980), delta=_m(980),
            finding="Week 2 was already paid on Mar 14 under NM-2178 for the same 980 bars. This charge takes it again.",
            evidence_ids=["ev-payment-NM-2178", "ev-sales-w2", "ev-charge-C2"], confidence=0.98,
            math=[_p("Week 2 already paid: "), _p("$980 on Mar 14", "ev-payment-NM-2178"), _p(" · took "),
                  _p("$980 again", "ev-charge-C2"), _p(" → $0 allowed")]),
    Finding(id="F-C3", charge_id="C3", type="amended_by_email", expected=_m(330), taken=_m(330), delta=_m(0),
            finding="Dated after the promo ended, but broker Jordan Lee extended it through Apr 7 by email on Mar 28. The charge matches.",
            evidence_ids=["ev-email-broker-0328", "ev-sales-apr1-7", "ev-deal-3.1", "ev-charge-C3"], confidence=0.96,
            math=[_p("330 bars", "ev-sales-apr1-7"), _p(" × "), _p("$1.00", "ev-deal-3.1"), _p(" = $330, inside the "),
                  _p("Apr 7 extension", "ev-email-broker-0328"), _p(" · took "), _p("$330", "ev-charge-C3"), _p(" → fair")]),
    Finding(id="F-C4", charge_id="C4", type="over_cap", expected=_m(0), taken=_m(1540), delta=_m(1540),
            finding="§3.2 caps the promo at 5,000 bars. Weeks 1 to 3 already sold 5,000, so week 4's 1,540 bars aren't covered.",
            evidence_ids=["ev-deal-3.2", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3", "ev-sales-w4", "ev-charge-C4"],
            confidence=0.95,
            math=[_p("1,200", "ev-sales-w1"), _p(" + "), _p("980", "ev-sales-w2"), _p(" + "), _p("2,820", "ev-sales-w3"),
                  _p(" = 5,000 = the "), _p("cap", "ev-deal-3.2"), _p(" · "), _p("1,540 bars", "ev-sales-w4"),
                  _p(" after it → $0 allowed · took "), _p("$1,540", "ev-charge-C4")]),
    Finding(id="F-C5", charge_id="C5", type="product_not_covered", expected=_m(0), taken=_m(1000), delta=_m(1000),
            finding="§3.1 covers only Peak Bar Original and Chocolate. Mint isn't in the deal, so none of this charge is allowed.",
            evidence_ids=["ev-deal-3.1", "ev-sales-mint", "ev-charge-C5"], confidence=0.99,
            math=[_p("Mint", "ev-sales-mint"), _p(" isn't in "), _p("§3.1", "ev-deal-3.1"), _p(" → $0 allowed · took "),
                  _p("$1,000", "ev-charge-C5")]),
    Finding(id="F-C6", charge_id="C6", type="discretionary_fee", expected=_m(1200), taken=_m(1200), delta=_m(0),
            finding="The $1,200 fee is within §5.4's $1,500 limit, but the clause says 'at its discretion'. Notice came Mar 11, 20 days ahead.",
            evidence_ids=["ev-deal-5.4", "ev-notice-0311", "ev-charge-C6"], confidence=0.93,
            open_questions=["Accept a $1,200 display fee given with 20 days' notice?"],
            math=[_p("$1,200 fee", "ev-charge-C6"), _p(" ≤ "), _p("$1,500 limit", "ev-deal-5.4"), _p(" · "),
                  _p("notice Mar 11", "ev-notice-0311"), _p(" (20 days) · discretion → ask")]),
    Finding(id="F-A1", charge_id="A1", type="discretionary_fee", expected=_m(1200), taken=_m(1200), delta=_m(0),
            finding="Display fee of $1,200 is within §5.4's $1,500 limit. Notice came Apr 12, 18 days ahead.",
            evidence_ids=["ev-deal-5.4", "ev-notice-0412", "ev-charge-A1", "ev-rule-1"], confidence=0.95,
            math=[_p("$1,200 fee", "ev-charge-A1"), _p(" ≤ "), _p("$1,500 limit", "ev-deal-5.4"), _p(" · "),
                  _p("notice Apr 12", "ev-notice-0412"), _p(" (18 days) · "), _p("Rule #1", "ev-rule-1"), _p(": 18 ≥ 14 → accept")]),
    Finding(id="F-A2", charge_id="A2", type="discretionary_fee", expected=_m(800), taken=_m(800), delta=_m(0),
            finding="Display fee of $800 is within §5.4's $1,500 limit. Notice came Apr 25, only 5 days ahead.",
            evidence_ids=["ev-deal-5.4", "ev-notice-0425", "ev-charge-A2", "ev-rule-1"], confidence=0.95,
            math=[_p("$800 fee", "ev-charge-A2"), _p(" · "), _p("notice Apr 25", "ev-notice-0425"), _p(" (5 days) · "),
                  _p("Rule #1", "ev-rule-1"), _p(": 5 < 14 → dispute")]),
]}

REHEARSALS = {r.charge_id: r for r in [
    Rehearsal(charge_id="C1", predicted_rebuttal="Our email of Mar 30 set the rate at $1.50 per unit.",
              answer="That email came from Northmart. Under §6.1 the deal changes only by an amendment both sides sign or written approval from Peak Bar's named representatives. The rate is $1.00 (§3.1).",
              answer_evidence_ids=["ev-claim-northmart-0330", "ev-deal-6.1", "ev-deal-3.1"], answered=True),
    Rehearsal(charge_id="C2", predicted_rebuttal="NM-2231 is a new claim, not a repeat of week 2.",
              answer="NM-2178, paid Mar 14, already covered the same 980 bars for Mar 8 to 14. §4.2: a unit may be claimed only once.",
              answer_evidence_ids=["ev-payment-NM-2178", "ev-sales-w2", "ev-deal-4.2"], answered=True),
    Rehearsal(charge_id="C4", predicted_rebuttal="The promo had no unit cap.",
              answer="§3.2 caps the promo at 5,000 bars in total. Weeks 1 to 3 sold 1,200 + 980 + 2,820 = 5,000, so week 4's 1,540 bars aren't covered.",
              answer_evidence_ids=["ev-deal-3.2", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3"], answered=True),
    Rehearsal(charge_id="C5", predicted_rebuttal="Mint is part of the Peak Bar line, so it's covered.",
              answer="§3.1 names only Peak Bar Original and Peak Bar Chocolate. Mint isn't in the deal.",
              answer_evidence_ids=["ev-deal-3.1", "ev-sales-mint"], answered=True),
]}


def _rule_1(learned_at: datetime) -> Rule:
    return Rule(
        id="rule-1", label="Rule #1", pattern_text=S54, term_type="fee_discretion", counterparty="Northmart",
        condition="notice_days >= 14", decision="accept", else_decision="dispute",
        summary="Accept Northmart display fees with at least 14 days' notice; otherwise dispute.",
        approver="Dana Okafor", approver_role="owner", learned_at=learned_at, source_question_id="Q-1",
        status="active",
    )


DISPUTE_LINES = [
    DisputeLine(charge_id="C1", ref="NM-2229", amount=_m(600), reason="Rate charged $1.50 a bar; the deal says $1.00.",
                clause_ref="§3.1", quote=S31, math="1,200 bars × ($1.50 − $1.00) = $600",
                evidence_ids=["ev-deal-3.1", "ev-sales-w1", "ev-charge-C1"]),
    DisputeLine(charge_id="C2", ref="NM-2231", amount=_m(980), reason="Week 2 was already paid on Mar 14 (NM-2178).",
                clause_ref="§4.2", quote=S42, math="980 bars for Mar 8 to 14 already paid under NM-2178",
                evidence_ids=["ev-payment-NM-2178", "ev-sales-w2", "ev-charge-C2", "ev-deal-4.2"]),
    DisputeLine(charge_id="C4", ref="NM-2236", amount=_m(1540), reason="Over the 5,000-unit cap.",
                clause_ref="§3.2", quote=S32, math="1,200 + 980 + 2,820 = 5,000 by Mar 21; 1,540 bars after the cap",
                evidence_ids=["ev-deal-3.2", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3", "ev-sales-w4", "ev-charge-C4"]),
    DisputeLine(charge_id="C5", ref="NM-2237", amount=_m(1000), reason="Mint is not a promoted product.",
                clause_ref="§3.1", quote=S31, math="1,000 Mint bars; Mint isn't covered, so $0 allowed",
                evidence_ids=["ev-deal-3.1", "ev-sales-mint", "ev-charge-C5"]),
]

REMITTANCE = Remittance(id=REMITTANCE_ID, counterparty="Northmart", invoice_id="INV-3102", expected=_m(48200),
                        received=_m(41350), taken=_m(6850), charge_count=6)


# ---------------------------------------------------------------- event builder

class _Run:
    def __init__(self, run_id: str, start: datetime, step_s: float = 1.0, first_id: int = 1):
        self.run_id, self.t, self.step = run_id, start, timedelta(seconds=step_s)
        self.first_id = first_id  # > 1 when the events continue an earlier fixture's run
        self.events: list[Any] = []

    def now(self) -> datetime:
        return self.t

    def add(self, type_: str, data: Any, gap: float = 1.0) -> None:
        self.t += self.step * gap
        payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
        self.events.append(EventAdapter.validate_python(
            {"id": self.first_id + len(self.events), "run_id": self.run_id, "at": self.t, "type": type_, "data": payload}))

    def log(self, text: str, level: str = "info", actor: str = "system", charge_id: str | None = None, gap: float = 1.0) -> None:
        self.add("log", LogLine(text=text, level=level, actor=actor, charge_id=charge_id), gap)

    def totals(self, disputed: int, accepted: int, waiting: int, undecided: int, questions: int, taken: int = 6850) -> None:
        self.add("totals", Totals(taken=_m(taken), disputed=_m(disputed), accepted=_m(accepted), waiting=_m(waiting),
                                  undecided=_m(undecided), questions=questions), gap=0)

    def decide(self, charge_id: str, decision: str, gate_row: int, reason: str, disputed: int = 0, accepted: int = 0,
               waiting: int = 0, rule_id: str | None = None) -> Decision:
        d = Decision(charge_id=charge_id, decision=decision, disputed=_m(disputed), accepted=_m(accepted),
                     waiting=_m(waiting), gate_row=gate_row, rule_id=rule_id, decided_by="gate",
                     decided_at=self.t + self.step, reason=reason)
        self.add("decision", d)
        return d


MARCH_PLAN = [  # charge, decision, gate row, reason, disputed, accepted, waiting, running totals after
    ("C1", "split", 7, "Deal rate is $1.00, not $1.50: accept $1,200, dispute $600.", 600, 1200, 0, (600, 1200, 0, 5050, 0)),
    ("C2", "dispute", 7, "Week 2 was already paid on Mar 14.", 980, 0, 0, (1580, 1200, 0, 4070, 0)),
    ("C3", "accept", 5, "Matches the deal as extended by the broker's Mar 28 email.", 0, 330, 0, (1580, 1530, 0, 3740, 0)),
    ("C4", "dispute", 7, "Over the 5,000-bar cap.", 1540, 0, 0, (3120, 1530, 0, 2200, 0)),
    ("C5", "dispute", 7, "Mint isn't covered by the deal.", 1000, 0, 0, (4120, 1530, 0, 1200, 0)),
    ("C6", "ask", 4, "'At its discretion' and no saved rule: asking Dana.", 0, 0, 1200, (4120, 1530, 1200, 0, 1)),
]


def _detail(c: Charge, decision: Decision | None, rule: Rule | None = None) -> ChargeDetail:
    f = FINDINGS.get(c.id)
    r = REHEARSALS.get(c.id)
    ids = list(dict.fromkeys((f.evidence_ids if f else []) + (r.answer_evidence_ids if r else [])
                             + (["ev-rule-1", "ev-answer-Q-1"] if decision and decision.rule_id else [])))
    rule = rule if decision and rule and decision.rule_id == rule.id else None
    return ChargeDetail(charge=c, finding=f, decision=decision, rehearsal=r, rule=rule, evidence=[EVIDENCE[i] for i in ids])


REFUSAL_NOTE = "Hold this until I've seen the broker's Mar 28 email for the April 1 to 7 bars."


@cache
def march_run() -> RunFixture:
    return _march(MARCH_RUN, controller_approves=True)


@cache
def refused_run() -> RunFixture:
    """The same March run, but Sam refuses the credit memo: nothing posts and the totals don't move."""
    return _march(REFUSED_RUN, controller_approves=False)


def _march(run_id: str, controller_approves: bool) -> RunFixture:
    run = _Run(run_id, datetime(2026, 10, 24, 10, 30, 0, tzinfo=PDT))
    remittance = REMITTANCE.model_copy(update={"received_at": run.now()})  # the deposit is what starts the run
    run.add("run", RunInfo(run_id=run_id, kind="march", status="started", remittance=remittance, demo_mode=True))
    run.log("Northmart paid $41,350 on invoice INV-3102 for $48,200. $6,850 was taken out in 6 charges.")
    run.totals(0, 0, 0, 6850, 0)
    run.log("Reading the Spring Promo deal with two readers, Claude and Gemini.", actor="reader")
    run.log("Both readers agree on 6 terms. Every quote was found word for word in the deal.", "good", "reader")
    run.log("Broker Jordan Lee's Mar 28 email extends the promo through Apr 7, up to 500 more bars. Approved sender: applied.",
            "good", "reader")
    run.log("Northmart's Mar 30 email says the rate is $1.50. Northmart can't change the deal by email: shown as a claim, not applied.",
            "warn", "reader")

    decisions: dict[str, Decision] = {}
    charges = {c.id: c for c in MARCH_CHARGES}
    for cid, kind, row, reason, disp, acc, wait, tot in MARCH_PLAN:
        c = charges[cid]
        run.add("charge", c, gap=2)
        run.log(f"Checking {cid}: {c.description}, ${c.amount:,.0f} taken.", actor="investigator", charge_id=cid)
        run.add("finding", FINDINGS[cid], gap=3)
        if cid in REHEARSALS:
            run.log("Predicting Northmart's comeback before filing.", actor="negotiator", charge_id=cid)
            run.add("rehearsal", REHEARSALS[cid], gap=2)
        decisions[cid] = run.decide(cid, kind, row, reason, disp, acc, wait)
        run.totals(*tot)

    q = Question(id="Q-1", to_role="owner", charge_id="C6", channel="sms", sent_at=run.now() + run.step,
                 text="Northmart took a $1,200 display fee for March. The deal allows up to $1,500 'at its discretion'. "
                      "Notice came 20 days ahead. Accept or dispute? Tell me your rule and I'll remember it.")
    run.add("question", q)
    run.log("Texted Dana one question about C6.", actor="gate", charge_id="C6")

    run.add("dispute", _dispute("filed", run.now() + run.step, DISPUTE_LINES), gap=2)
    run.log("Filed dispute D-0417 on Northmart's portal: 4 lines, $4,120. Within the $5,000 limit Dana set.",
            "good", "negotiator")
    run.add("run", RunInfo(run_id=run_id, kind="march", status="waiting"))

    answered_at = run.now() + run.step * 10  # Dana takes a few seconds to text back
    run.add("answer", Answer(question_id="Q-1", from_role="owner", text="accept if notice is at least 14 days",
                             answered_at=answered_at, rule_id="rule-1"), gap=10)
    rule = _rule_1(learned_at=run.now() + run.step)
    run.add("rule", rule)
    run.log("Saved Rule #1 and texted Dana: \"Saved: accept display fees with 14+ days' notice. Reply UNDO to cancel.\"",
            "good", "gate")
    decisions["C6"] = run.decide("C6", "accept", 3, "Rule #1: 20 days' notice is at least 14, so accept.",
                                 accepted=1200, rule_id="rule-1")
    run.totals(4120, 2730, 0, 0, 1)

    memo_lines = [ApprovalLine(charge_id="C1", amount=_m(1200)), ApprovalLine(charge_id="C3", amount=_m(330)),
                  ApprovalLine(charge_id="C6", amount=_m(1200))]
    approval = Approval(id="AP-1", kind="credit_memo", amount=_m(2730), lines=memo_lines, proposed_by="bookkeeper",
                        approver_role="controller", status="pending", text="Approve credit memo of $2,730 (3 lines)?",
                        requested_at=run.now() + run.step)
    run.add("approval", approval, gap=2)
    run.log("Texted Sam (controller): approve a $2,730 credit memo? Nothing posts until Sam says yes.", actor="bookkeeper")
    if controller_approves:
        run.add("approval", approval.model_copy(update={"status": "approved", "decided_at": run.now() + run.step * 6}), gap=6)
        run.log("Sam approved. Posting to QuickBooks.", "good", "controller")
        run.add("ledger_post", credit_memo(posted_at=run.now() + run.step), gap=2)
        run.add("ledger_post", LedgerPost(
            id="LP-2", qbo_entity="invoice_note", qbo_id=None, amount=_m(4120), status="posted",
            note="$4,120 left open on INV-3102, disputed under D-0417.", posted_at=run.now() + run.step,
            lines=[LedgerLine(charge_id=ln.charge_id, description=f"{ln.ref}: {ln.reason}", amount=ln.amount)
                   for ln in DISPUTE_LINES]))
        run.log("QuickBooks: $2,730 credit memo posted; $4,120 stays open on INV-3102, tagged D-0417.", "good", "bookkeeper")
    else:
        run.add("approval", approval.model_copy(update={"status": "refused", "note": REFUSAL_NOTE,
                                                        "decided_at": run.now() + run.step * 6}), gap=6)
        run.log("Sam refused the $2,730 credit memo. Nothing posts to QuickBooks; Sam's note is on the card and the "
                "memo goes back to Dana.", "warn", "controller")

    run.add("portal_message", PortalMessage(
        id="PM-1", dispute_id=DISPUTE_ID, from_party="northmart", classification="claim_without_document",
        text="There was no unit cap on the Spring promo. The week 4 deduction stands.", charge_ids=["C4"],
        created_at=run.now() + run.step * 8), gap=8)
    run.log("Northmart replied on the portal: \"no cap\". It's a claim with no document.", "warn", "negotiator", "C4")
    run.add("portal_message", PortalMessage(
        id="PM-2", dispute_id=DISPUTE_ID, from_party="clawback",
        text=f"§3.2 of the signed deal says: \"{S32}\" Store sales for weeks 1 to 3 add up to 5,000 bars "
             "(1,200 + 980 + 2,820), so the cap was reached on Mar 21 and week 4's 1,540 bars aren't covered. "
             "If the cap was changed, please attach the signed amendment.",
        charge_ids=["C4"], evidence_ids=["ev-deal-3.2", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3", "ev-sales-w4"],
        created_at=run.now() + run.step * 3), gap=3)
    run.log("Answered with §3.2 and weeks 1 to 3 sales, and asked for the signed amendment.", "good", "negotiator", "C4")
    run.add("run", RunInfo(run_id=run_id, kind="march", status="finished"))

    details = {c.id: _detail(c, decisions[c.id], rule) for c in MARCH_CHARGES}
    used = {e.id for d in details.values() for e in d.evidence}
    used |= {i for ln in DISPUTE_LINES for i in ln.evidence_ids}
    used |= {i for e in run.events if e.type == "portal_message" for i in e.data.evidence_ids}
    if controller_approves:
        used |= {"ev-approval-AP-1"}
    return RunFixture(run_id=run_id, events=run.events, charges=details,
                      evidence={i: EVIDENCE[i] for i in sorted(used)})


def credit_memo(posted_at: datetime) -> LedgerPost:
    """LP-1: what posts once Sam approves AP-1 (also returned by the stub POST /approvals/AP-1)."""
    return LedgerPost(
        id="LP-1", qbo_entity="credit_memo", qbo_id=None, amount=_m(2730), status="posted", approval_id="AP-1",
        note="Credit memo applied to INV-3102.", posted_at=posted_at,
        lines=[LedgerLine(charge_id="C1", description="Spring promo week 1, fair part", amount=_m(1200)),
               LedgerLine(charge_id="C3", description="Spring promo Apr 1 to 7 (broker extension)", amount=_m(330)),
               LedgerLine(charge_id="C6", description="Display fee March (Rule #1)", amount=_m(1200))])


# ---------------------------------------------------------------- the judge attaches amendment-1 (beat 3)
# Numbers from data/CLAUDE.md: the cap goes to 6,000, so 1,000 of week 4's 1,540 bars are covered.
# api/tests checks them against api/engine/allowed.py with the amendment term added.

AMENDMENT_ATTACHED = "Attached: Amendment No. 1, signed by both parties on Mar 20. It raises the cap to 6,000 units."
AMENDMENT_REPLY = (
    "Thanks. The signed amendment raises the §3.2 cap to 6,000 units, so 1,000 of week 4's 1,540 bars are covered. "
    "We withdraw $1,000 of the week 4 line (C4) and keep $540 disputed."
)

FINDING_C4_AMENDED = Finding(
    id="F-C4", charge_id="C4", type="over_cap", expected=_m(1000), taken=_m(1540), delta=_m(540),
    finding="Amendment No. 1 raises the cap to 6,000. Weeks 1 to 3 used 5,000, so 1,000 of week 4's 1,540 bars "
            "are covered; 540 aren't.",
    evidence_ids=["ev-amendment-1", "ev-deal-3.1", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3", "ev-sales-w4",
                  "ev-charge-C4"],
    confidence=0.97,
    math=[_p("6,000 cap", "ev-amendment-1"), _p(" − 5,000 sold by Mar 21 = 1,000 bars × "), _p("$1.00", "ev-deal-3.1"),
          _p(" = $1,000 allowed · took "), _p("$1,540", "ev-charge-C4"), _p(" → $540 too much")])

DISPUTE_LINE_C4_AMENDED = DisputeLine(
    charge_id="C4", ref="NM-2236", amount=_m(540), reason="Over the 6,000-unit cap set by Amendment No. 1.",
    clause_ref="§3.2 (Amendment No. 1)", quote=A32,
    math="1,200 + 980 + 2,820 = 5,000 by Mar 21; 1,000 more bars reach the 6,000 cap; 540 bars after it",
    evidence_ids=["ev-amendment-1", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3", "ev-sales-w4", "ev-charge-C4"])


def _dispute(status: str, filed_at: datetime | None, lines: list[DisputeLine]) -> Dispute:
    return Dispute(id=DISPUTE_ID, remittance_id=REMITTANCE_ID, counterparty="Northmart", lines=lines,
                   total=sum((ln.amount for ln in lines), _m(0)), status=status, approved_by="policy", filed_at=filed_at)


def filed_dispute() -> Dispute:
    return next(e.data for e in march_run().events if e.type == "dispute")


def amended_dispute() -> Dispute:
    filed = filed_dispute()
    lines = [DISPUTE_LINE_C4_AMENDED if ln.charge_id == "C4" else ln for ln in filed.lines]
    return _dispute("answered", filed.filed_at, lines)


@cache
def amendment_run() -> RunFixture:
    """Continues the March run (same run_id, ids after its last event): what streams after the judge attaches
    amendment-1 on the portal. Only C4 changes, so `charges` holds C4 alone."""
    march = march_run()
    last = march.events[-1]
    run = _Run(MARCH_RUN, last.at + timedelta(seconds=20), first_id=last.id + 1)
    run.add("portal_message", PortalMessage(
        id="PM-3", dispute_id=DISPUTE_ID, from_party="northmart", text=AMENDMENT_ATTACHED,
        attachment_doc_id="amendment-1", classification="new_document", charge_ids=["C4"], created_at=run.now()), gap=0)
    run.log("Northmart attached Amendment No. 1. It's signed by both parties, so it counts: the §3.2 cap is now "
            "6,000 bars.", "good", "reader", "C4")
    run.log("Both readers agree on the new cap. The quote was found word for word in the amendment.", "good", "reader", "C4")
    run.add("finding", FINDING_C4_AMENDED, gap=3)
    decision = run.decide("C4", "split", 7, "Signed Amendment No. 1 raises the cap to 6,000: accept $1,000, keep $540 "
                                            "disputed.", disputed=540, accepted=1000)
    run.totals(3120, 3730, 0, 0, 1)
    run.add("dispute", amended_dispute(), gap=2)
    run.add("portal_message", PortalMessage(
        id="PM-4", dispute_id=DISPUTE_ID, from_party="clawback", text=AMENDMENT_REPLY, charge_ids=["C4"],
        evidence_ids=["ev-amendment-1", "ev-sales-w1", "ev-sales-w2", "ev-sales-w3", "ev-sales-w4"],
        created_at=run.now() + run.step))
    run.log("Conceded $1,000 of C4 and kept $540 disputed. D-0417 now totals $3,120.", "good", "negotiator", "C4")
    run.add("run", RunInfo(run_id=MARCH_RUN, kind="march", status="finished"))

    c4 = next(c for c in MARCH_CHARGES if c.id == "C4")
    detail = _detail(c4, decision).model_copy(
        update={"finding": FINDING_C4_AMENDED,
                "evidence": [EVIDENCE[i] for i in dict.fromkeys(FINDING_C4_AMENDED.evidence_ids
                                                                 + REHEARSALS["C4"].answer_evidence_ids)]})
    used = {e.id for e in detail.evidence} | {i for ln in amended_dispute().lines for i in ln.evidence_ids}
    used |= {i for e in run.events if e.type == "portal_message" for i in e.data.evidence_ids}
    return RunFixture(run_id=MARCH_RUN, events=run.events, charges={"C4": detail},
                      evidence={i: EVIDENCE[i] for i in sorted(used)})


@cache
def april_run() -> RunFixture:
    run = _Run(APRIL_RUN, datetime(2026, 10, 24, 10, 40, 0, tzinfo=PDT))
    run.add("run", RunInfo(run_id=APRIL_RUN, kind="april", status="started", demo_mode=True))
    run.log("April: Northmart took 2 display fees, $2,000 in all.")
    run.totals(0, 0, 0, 2000, 0, taken=2000)
    run.log("§5.4 is a discretion clause. Checking saved rules before asking anyone.", actor="gate")
    decisions: dict[str, Decision] = {}
    plan = [("A1", "accept", "Rule #1: 18 days' notice is at least 14, so accept.", 0, 1200, (0, 1200, 0, 800, 0)),
            ("A2", "dispute", "Rule #1: 5 days' notice is under 14, so dispute.", 800, 0, (800, 1200, 0, 0, 0))]
    for c, (cid, kind, reason, disp, acc, tot) in zip(APRIL_CHARGES, plan):
        run.add("charge", c, gap=2)
        run.add("finding", FINDINGS[cid], gap=3)
        run.log(f"Matched Rule #1 (learned Oct 24, approved by Dana) for {cid}.", "good", "gate", cid)
        decisions[cid] = run.decide(cid, kind, 3, reason, disp, acc, rule_id="rule-1")
        run.totals(*tot, taken=2000)
    run.log("0 questions asked. Both fees decided by Rule #1.", "good", "gate")
    run.add("run", RunInfo(run_id=APRIL_RUN, kind="april", status="finished"))
    rule = next(e.data for e in march_run().events if e.type == "rule")  # learned in March, applied here
    details = {c.id: _detail(c, decisions[c.id], rule) for c in APRIL_CHARGES}
    used = sorted({e.id for d in details.values() for e in d.evidence})
    return RunFixture(run_id=APRIL_RUN, events=run.events, charges=details, evidence={i: EVIDENCE[i] for i in used})


@cache
def coach() -> CoachResponse:
    return CoachResponse(draft_doc_id="summer-draft", redlines=[
        Redline(clause_ref="§5.4",
                original_quote="Northmart may charge a display fee of up to $1,500 per month at its discretion.",
                suggested_text="Northmart may charge a display fee of up to $1,500 per month, with written notice to "
                               "Supplier at least 14 days before the end of that month.",
                reason="In March this clause needed a question to Dana to settle a $1,200 fee. A set notice period "
                       "makes the answer automatic.",
                dollars_at_stake=_m(1200), finding_ids=["F-C6"]),
        Redline(clause_ref="§3.2",
                original_quote="The promotional allowance applies to a maximum of 6,000 units in total.",
                suggested_text="The promotional allowance applies to a maximum of 6,000 units in total, including any "
                               "units added by an extension. Units over the cap are not covered unless a signed "
                               "amendment raises it.",
                reason="In March, $1,540 was taken for bars sold after the cap.",
                dollars_at_stake=_m(1540), finding_ids=["F-C4"]),
        Redline(clause_ref="§3.1",
                original_quote="Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and "
                               "Peak Bar Chocolate sold between May 1 and May 31, 2026.",
                suggested_text="Supplier will fund a promotional allowance of $1.00 per unit on the products listed by "
                               "item number in Schedule A, sold between May 1 and May 31, 2026. No other products "
                               "are covered.",
                reason="In March, $1,000 was taken for Mint, which the deal never covered.",
                dollars_at_stake=_m(1000), finding_ids=["F-C5"]),
    ])


COACH_QUOTE_OFFSETS = {"§5.4": (1893, 1972), "§3.2": (1010, 1081), "§3.1": (863, 1004)}  # into summer-draft.md

_AUDIT_ACTIONS = {  # event type -> (actor, action, object_ref)
    "decision": lambda d: ("gate", "decision", f"charge:{d.charge_id}"),
    "question": lambda d: ("gate", "question_sent", f"question:{d.id}"),
    "answer": lambda d: ("owner:Dana", "answer_received", f"question:{d.question_id}"),
    "rule": lambda d: ("owner:Dana", "rule_saved", f"rule:{d.id}"),
    "dispute": lambda d: ("negotiator", "dispute_filed", f"dispute:{d.id}"),
    "approval": lambda d: ("bookkeeper", "approval_requested", f"approval:{d.id}") if d.status == "pending"
    else ("controller:Sam", f"credit_memo_{d.status}", f"approval:{d.id}"),
    "ledger_post": lambda d: ("bookkeeper", f"qbo_{d.qbo_entity}_posted", f"ledger:{d.id}"),
    "portal_message": lambda d: ("northmart" if d.from_party == "northmart" else "negotiator", "portal_message",
                                 f"portal:{d.id}"),
}


@cache
def audit_chain_rows() -> tuple[audit_chain.AuditEntry, ...]:
    """The March run's audit log, chained by api/engine/audit_chain.py. Money stays as strings in evidence."""
    chain = audit_chain.AuditChain()
    for ev in march_run().events:
        if ev.type in _AUDIT_ACTIONS:
            actor, action, ref = _AUDIT_ACTIONS[ev.type](ev.data)
            chain.append(actor, action, ref, {"event_id": ev.id, **ev.data.model_dump(mode="python")}, at=ev.at)
    return chain.entries


def audit() -> list[AuditEntry]:
    return [AuditEntry.model_validate(e.as_row()) for e in audit_chain_rows()]


def eval_report() -> EvalReport:
    return EvalReport(status="not_run", cases=30)


def summary() -> Summary:
    last_totals = [e for e in march_run().events if e.type == "totals"][-1].data
    dispute = next(e.data for e in march_run().events if e.type == "dispute")
    return Summary(totals=last_totals, open_disputes=[dispute], pending_question=None)


# ---------------------------------------------------------------- write web/fixtures

def _dump(obj: Any) -> str:
    if isinstance(obj, (list, tuple)):
        data = [o.model_dump(mode="json") for o in obj]
    else:
        data = obj.model_dump(mode="json")
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def fixture_files() -> dict[str, str]:
    from api import contracts as c

    schema_models = [c.RunFixture, c.ChargeDetail, c.Evidence, c.CoachResponse, c.EvalReport, c.AuditEntry,
                     c.AuditVerify, c.Summary, c.PortalMessage, c.ScenarioResponse, c.AnswerResponse,
                     c.StartRunResponse, c.Dispute, c.ApprovalDecisionRequest, c.ApprovalDecisionResponse,
                     c.InboxResponse, c.PortalPreset, c.ScenarioRequest, c.ScenarioExample]
    schema = {m.__name__: m.model_json_schema(mode="serialization") for m in schema_models}
    return {
        "run-events.json": _dump(march_run()),
        "refusal-events.json": _dump(refused_run()),
        "amendment-events.json": _dump(amendment_run()),
        "april-events.json": _dump(april_run()),
        "coach.json": _dump(coach()),
        "audit.json": _dump(audit()),
        "schema.json": json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
    }


def write_fixtures(out: Path = WEB_FIXTURES) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in fixture_files().items():
        p = out / name
        p.write_text(text)
        paths.append(p)
    return paths


if __name__ == "__main__":
    for p in write_fixtures():
        print(f"wrote {p.relative_to(REPO)}")
