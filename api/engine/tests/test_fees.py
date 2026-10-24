"""Fee-schedule charges (a % with a minimum and a cap, per unit, per carton, per PO or flat, tiered by days), the
notice period a change needs, and the dispute window. Every number is worked by hand in the comment beside it."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from api.engine.allowed import applies_from, compute_allowed
from api.engine.gate import decide, decide_by_owner, summarize
from api.engine.policy import load_policy
from api.engine.tests import scenario as s
from api.engine.types import Charge, DecisionKind, FeeData, FeeLine, Rule, Term, TermStatus, TermType

POLICY = load_policy()
K = DecisionKind
D = date
T = TermType

Q_MCB = ("KeHE will charge a bi weekly processing fee of 5% of the MCB amount (with a minimum of $65 per purchasing "
         "Vendor/facility).")
Q_EP = ('KeHE will "pass through" these amounts to Vendor along with an administrative charge of 5% on the total '
        "amount of each invoice with a maximum of $175 per invoice.")
Q_SPOILS = ("When and if Spoils occur, Vendor will only be held responsible for KeHE's landed cost of goods which have "
            "been credited to a retailer plus a $0.29 per unit processing fee or fixed retailer spoilage rate on product "
            "sales depending on retailer program.")
Q_FP = ("Free Placements will be processed and charged back to Vendor at KeHE's landed cost plus an 18% administrative "
        "fee depending on retailer relationship.")
Q_WINDOW = ("If Vendor wishes to dispute any payment deductions, Vendor must send its detailed request electronically "
            "to vendorperformance@KeHEco.m within 180 days of KeHE's deduction from Vendor's invoice.")
Q_NOTICE = ("KeHE reserves the right to modify these Vendor Policies & Procedures at any time with at least thirty (30) "
            "days prior notice by posting changes on the Vendor Portal of the KeHE's website.")


def fee(tid, code, basis, rate=None, quote="", **params) -> Term:
    p = {"fee_code": code, "basis": basis, "rate": rate, **params}
    return Term(tid, T.FEE_SCHEDULE, {k: v for k, v in p.items() if v is not None}, quote, D(2015, 5, 31),
                source_doc_id="kehe-policies")


MCB = fee("T-mcb", "MCB", "percent", "5", Q_MCB, min="65", per="incident", requires_proof=True)
EP = fee("T-ep", "Extra Performance", "percent", "5", Q_EP, max="175", per="invoice")
SPOILS = fee("T-spoils", "Spoils", "per_unit", "0.29", Q_SPOILS)
FP = replace(fee("T-fp", "Free Placements", "percent", "18", Q_FP), discretion=True)
WINDOW = Term("T-window", T.DISPUTE_WINDOW, {"days": 180, "from": "deduction"}, Q_WINDOW, source_doc_id="kehe-policies")
NOTICE = Term("T-notice", T.NOTICE_PERIOD, {"days": 30}, Q_NOTICE, source_doc_id="kehe-policies")
POLICY_TERMS = [MCB, EP, SPOILS, FP, WINDOW, NOTICE]
PROOF = frozenset({"mcb-backup-0314"})
CODES = {"MCBF": "MCB", "EPA": "Extra Performance", "SPL": "Spoils", "FP": "Free Placements"}


def charge(cid, code, amount, ref=None, deducted_on=None) -> Charge:
    return Charge(cid, ref or f"KR-{cid}", code, f"{code} charge", (), 1, Decimal(amount), Decimal(amount),
                  D(2026, 3, 1), D(2026, 3, 31), counterparty="KeHE Distributors", deducted_on=deducted_on)


def line(c: Charge, on=D(2026, 3, 14), **kw) -> FeeLine:
    return FeeLine(c.ref, on, **{k: Decimal(str(v)) if k in ("base_amount", "pass_through") else v for k, v in kw.items()})


def run(c: Charge, lines, terms=POLICY_TERMS, rules=(), finding=None, **fee_kw):
    data = FeeData(lines=tuple(lines), codes=CODES, proof_docs=PROOF, **fee_kw)
    a = compute_allowed(c, terms, fees=data)
    return a, decide(c, a, s.strong_finding(c.id) if finding is None else finding, POLICY, rules)


def money(*values) -> tuple[Decimal, ...]:
    return tuple(Decimal(v) for v in values)


# --- Percent, with a minimum and a maximum ------------------------------------------------------------------------

def test_percent_below_the_minimum_is_raised_to_it():
    c = charge("M1", "MCBF", "65.00")
    a, d = run(c, [line(c, group="MCB 03/01-03/14", base_amount="940.00", proof_doc="mcb-backup-0314")])
    assert (a.allowed, a.delta) == money("65.00", "0.00")  # 5% of $940 = $47.00, minimum $65
    assert a.steps[0] == "Fee MCB 03/01-03/14: 5% of $940.00 = $47.00; minimum $65.00 -> $65.00."
    assert a.facts["fee_amount"] == Decimal("65.00") and a.terms == (MCB,)
    assert (d.kind, d.accepted, d.gate_row) == (K.ACCEPT, Decimal("65.00"), 5)


def test_percent_charged_at_the_wrong_rate():
    c = charge("M2", "MCBF", "312.00")
    a, d = run(c, [line(c, group="MCB 03/15-03/28", base_amount="3120.00", proof_doc="mcb-backup-0314")])
    assert (a.allowed, a.delta) == money("156.00", "156.00")  # 5% of $3,120 = $156; 10% was taken
    assert (d.kind, d.disputed, d.accepted, d.gate_row) == (K.SPLIT, Decimal("156.00"), Decimal("156.00"), 7)


def test_maximum_applies_per_invoice():
    c = charge("E1", "EPA", "360.00")
    a, d = run(c, [line(c, group="R-5512", base_amount="5400.00"), line(c, group="R-5530", base_amount="1800.00")])
    # R-5512: 5% of $5,400 = $270, max $175. R-5530: 5% of $1,800 = $90. $175 + $90 = $265.
    assert a.steps[:2] == ("Fee R-5512: 5% of $5,400.00 = $270.00; maximum $175.00 -> $175.00.",
                           "Fee R-5530: 5% of $1,800.00 = $90.00 -> $90.00.")
    assert (a.allowed, a.delta) == money("265.00", "95.00")
    assert (d.kind, d.disputed, d.accepted) == (K.SPLIT, Decimal("95.00"), Decimal("265.00"))


def test_lines_on_one_invoice_share_its_maximum():
    c = charge("E2", "EPA", "175.00")
    a, _ = run(c, [line(c, group="R-6001", base_amount="2000.00"), line(c, group="R-6001", base_amount="2000.00")])
    assert a.allowed == Decimal("175.00")  # 5% of $4,000 = $200 on one invoice, max $175 (not 2 x $100)


def test_minimum_per_month_groups_lines_by_month():
    t = fee("T-m", "MCB", "percent", "5", Q_MCB, min="65", per="month")
    c = charge("M3", "MCBF", "165.00")
    lines = [line(c, D(2026, 3, 3), base_amount="600.00"), line(c, D(2026, 3, 20), base_amount="500.00"),
             line(c, D(2026, 4, 2), base_amount="2000.00")]
    a, _ = run(c, lines, terms=[t])
    assert a.allowed == Decimal("165.00")  # March: 5% of $1,100 = $55, min $65. April: 5% of $2,000 = $100.


# --- Per unit, per carton, per PO, flat; costs passed through ------------------------------------------------------

def test_per_unit_fee_plus_landed_cost():
    c = charge("S1", "SPL", "381.60")
    a, d = run(c, [line(c, group="CR-88120", units=240, pass_through="264.00")])
    # 240 units x $0.29 = $69.60; landed cost $264.00; $333.60 allowed. $0.49 a unit was taken: 240 x $0.20 = $48.
    assert (a.allowed, a.delta, a.firm) == money("333.60", "48.00", "264.00")
    assert a.steps == ("Fee CR-88120: 240 units x $0.29 = $69.60 -> $69.60.", "Cost passed through at cost: $264.00.",
                       "Allowed: $333.60; taken $381.60.")
    assert (d.kind, d.disputed, d.accepted, d.gate_row) == (K.SPLIT, Decimal("48.00"), Decimal("333.60"), 7)


def test_per_carton():
    t = fee("T-c", "Cut Cases", "per_carton", "2.50", "A $2.50 per carton fee applies.")
    c = charge("X1", "Cut Cases", "30.00")
    a, d = run(c, [line(c, cartons=12)], terms=[t])
    assert a.allowed == Decimal("30.00") and d.kind == K.ACCEPT  # 12 x $2.50; the code needs no mapping


def test_per_po_charges_once_per_po():
    t = fee("T-po", "PO Fee", "per_po", "25", "A $25 fee applies per PO.", per="po")
    c = charge("X2", "PO Fee", "75.00")
    a, d = run(c, [line(c, group="PO-1"), line(c, group="PO-1"), line(c, group="PO-2")], terms=[t])
    assert (a.allowed, a.delta) == money("50.00", "25.00")  # two POs x $25
    assert d.kind == K.SPLIT


def test_flat_fee_per_month():
    t = fee("T-f", "Listing", "flat", "150", "A $150 listing fee applies each month.", per="month")
    c = charge("X3", "Listing", "300.00")
    a, _ = run(c, [line(c, D(2026, 3, 2)), line(c, D(2026, 3, 9)), line(c, D(2026, 4, 1))], terms=[t])
    assert a.allowed == Decimal("300.00")  # March $150 + April $150


# --- Tiers by days ----------------------------------------------------------------------------------------------

LATE = fee("T-late", "Late", "percent", None, "5% if 0-7 days late, 10% if 8-14, 15% after 15 days.",
           tiers=[{"from_days": 0, "to_days": 7, "rate": "5"}, {"from_days": 8, "to_days": 14, "rate": "10"},
                  {"from_days": 15, "to_days": None, "rate": "15"}], min="65")


def test_tier_by_days():
    c = charge("L1", "Late", "300.00")
    lines = [line(c, group="A", base_amount="1000", days=3), line(c, group="B", base_amount="1000", days=10),
             line(c, group="C", base_amount="1000", days=20)]
    a, d = run(c, lines, terms=[LATE])
    # A: 3 days, 5% = $50, lifted to the $65 minimum. B: 10 days, 10% = $100. C: 20 days, 15% = $150. $315 in all.
    assert a.steps[:3] == ("Fee A: 5% of $1,000.00 (3 days) = $50.00; minimum $65.00 -> $65.00.",
                           "Fee B: 10% of $1,000.00 (10 days) = $100.00 -> $100.00.",
                           "Fee C: 15% of $1,000.00 (20 days) = $150.00 -> $150.00.")
    assert (a.allowed, a.delta) == money("315.00", "-15.00")
    assert (d.kind, d.accepted, d.gate_row) == (K.ACCEPT, Decimal("300.00"), 6)  # less than allowed: never ask more


def test_tier_minimum_and_no_tier():
    c = charge("L2", "Late", "65.00")
    a, _ = run(c, [line(c, group="A", base_amount="1000", days=3)], terms=[LATE])
    assert a.allowed == Decimal("65.00")  # 5% of $1,000 = $50, minimum $65
    on_time = replace(LATE, params={**LATE.params, "tiers": [{"from_days": 1, "to_days": 7, "rate": "5"}]})
    a, d = run(c, [line(c, group="A", base_amount="1000", days=0)], terms=[on_time])
    assert a.allowed == Decimal("0.00")  # on time: no tier, no fee, and the minimum doesn't apply to nothing
    assert (d.kind, d.disputed) == (K.DISPUTE, Decimal("65.00"))


def test_tiers_without_days_ask():
    c = charge("L3", "Late", "100.00")
    a, d = run(c, [line(c, base_amount="1000")], terms=[LATE])
    assert a.missing and (d.kind, d.gate_row) == (K.ASK, 9)


# --- Proof ------------------------------------------------------------------------------------------------------

def test_fee_that_requires_proof_without_it_asks():
    c = charge("M4", "MCBF", "65.00")
    a, d = run(c, [line(c, group="MCB 03/15-03/28", base_amount="940.00")])
    assert a.allowed == Decimal("65.00") and a.facts["missing_proof"] == ("MCB 03/15-03/28",)
    assert (d.kind, d.gate_row) == (K.ASK, 9)
    assert d.reason == "The deal requires backup for this fee and none came for MCB 03/15-03/28."
    # A proof_doc that doesn't exist is no proof.
    _, d = run(c, [line(c, group="MCB 03/15-03/28", base_amount="940.00", proof_doc="made-up")])
    assert d.kind == K.ASK


# --- Missing pieces, rejected and disputed terms -----------------------------------------------------------------

def test_mapped_code_with_no_schedule_or_no_backup_asks():
    c = charge("M5", "MCBF", "65.00")
    a, d = run(c, [line(c, base_amount="940")], terms=[EP])
    assert a.missing == ("a fee_schedule term for MCB",) and d.kind == K.ASK
    a, d = run(c, [], terms=[MCB])
    assert a.missing == ("the backup for KR-M5",) and d.kind == K.ASK


def test_rejected_schedule_skips_and_disputed_asks():
    c = charge("M6", "MCBF", "65.00")
    lines = [line(c, base_amount="940", proof_doc="mcb-backup-0314")]
    _, d = run(c, lines, terms=[replace(MCB, status=TermStatus.REJECTED)])
    assert (d.kind, d.gate_row) == (K.SKIP, 1)
    _, d = run(c, lines, terms=[replace(MCB, status=TermStatus.DISPUTED)])
    assert (d.kind, d.gate_row) == (K.ASK, 2)


def test_unapproved_schedule_is_never_applied():
    c = charge("M7", "MCBF", "130.00")
    claim = replace(MCB, id="T-claim", params={**MCB.params, "rate": "10"}, source_approved=False,
                    effective_from=D(2026, 3, 1))
    a, _ = run(c, [line(c, base_amount="1300", proof_doc="mcb-backup-0314")], terms=[MCB, claim])
    assert a.allowed == Decimal("65.00")  # 5% of $1,300 = $65; the 10% from an unapproved sender doesn't count


# --- Notice period ----------------------------------------------------------------------------------------------

EP_NEW = replace(EP, id="T-ep-2026", params={**EP.params, "rate": "7", "max": "250"}, effective_from=D(2026, 3, 9),
                 noticed_on=D(2026, 3, 2), source_doc_id="kehe-notice-2026-03-02",
                 exact_quote="The Extra Performance administrative charge will be 7% of each invoice, up to $250 per invoice.")


def test_change_without_enough_notice_keeps_the_old_schedule():
    assert applies_from(EP_NEW, 30) == D(2026, 4, 1)  # noticed Mar 2 + 30 days, later than its stated Mar 9
    c = charge("E3", "EPA", "182.00")
    a, d = run(c, [line(c, D(2026, 3, 18), group="R-7004", base_amount="2600.00")], terms=POLICY_TERMS + [EP_NEW])
    # Mar 18 is before Apr 1: the old 5% applies, $130. 7% ($182) was taken: $52 over.
    assert (a.allowed, a.delta) == money("130.00", "52.00")
    assert a.facts["change_before_notice"] == ("T-ep-2026",)
    assert a.steps[0] == ("A Extra Performance change set to start Mar 9 was noticed Mar 2; with 30 days' notice it "
                          "applies only from Apr 1, so earlier purchases keep the earlier schedule.")
    assert EP_NEW in a.terms and NOTICE in a.terms
    assert (d.kind, d.disputed, d.accepted, d.gate_row) == (K.SPLIT, Decimal("52.00"), Decimal("130.00"), 7)


def test_change_applies_once_its_notice_has_run():
    c = charge("E4", "EPA", "182.00")
    a, _ = run(c, [line(c, D(2026, 4, 3), group="R-7100", base_amount="2600.00")], terms=POLICY_TERMS + [EP_NEW])
    assert a.allowed == Decimal("182.00") and "change_before_notice" not in a.facts  # 7% of $2,600
    early = replace(EP_NEW, noticed_on=D(2026, 2, 1))  # Feb 1 + 30 = Mar 3, before Mar 9: Mar 9 stands
    a, _ = run(c, [line(c, D(2026, 3, 18), group="R-7004", base_amount="2600.00")], terms=POLICY_TERMS + [early])
    assert a.allowed == Decimal("182.00")


def test_without_a_notice_period_a_change_starts_on_its_date():
    c = charge("E5", "EPA", "182.00")
    terms = [t for t in POLICY_TERMS if t.type != T.NOTICE_PERIOD] + [EP_NEW]
    a, _ = run(c, [line(c, D(2026, 3, 18), group="R-7004", base_amount="2600.00")], terms=terms)
    assert a.allowed == Decimal("182.00")


# --- Discretion: an admin fee "depending on retailer relationship" ------------------------------------------------

def fp_rule(condition="fee_amount <= 150") -> Rule:
    return Rule("rule-9", "Free placement admin fee charged depending on retailer relationship", T.FEE_SCHEDULE,
                "KeHE Distributors", condition, K.ACCEPT, K.DISPUTE, label="Rule #2")


def fp_charge():
    c = charge("F1", "FP", "1217.76")
    # 48 cases at a landed cost of $21.50 = $1,032.00; 18% of that = $185.76; $1,217.76 in all.
    return c, [line(c, group="FP-2207", base_amount="1032.00", pass_through="1032.00")]


def test_discretionary_fee_asks_once():
    c, lines = fp_charge()
    a, d = run(c, lines)
    assert (a.allowed, a.firm, a.facts["fee_amount"]) == money("1217.76", "1032.00", "185.76")
    assert (d.kind, d.gate_row) == (K.ASK, 4)


def test_rule_disputes_only_the_discretionary_part():
    c, lines = fp_charge()
    _, d = run(c, lines, rules=[fp_rule()])  # $185.76 > $150: dispute the fee, accept the landed cost
    assert (d.kind, d.disputed, d.accepted, d.gate_row, d.rule_id) == (
        K.SPLIT, Decimal("185.76"), Decimal("1032.00"), 3, "rule-9")
    _, d = run(c, lines, rules=[fp_rule("fee_amount <= 200")])
    assert (d.kind, d.accepted, d.gate_row) == (K.ACCEPT, Decimal("1217.76"), 3)


def test_rule_dispute_with_no_cost_under_the_fee_disputes_it_all():
    c = charge("F2", "FP", "185.76")
    _, d = run(c, [line(c, group="FP-2210", base_amount="1032.00")], rules=[fp_rule()])
    assert (d.kind, d.disputed) == (K.DISPUTE, Decimal("185.76"))


def test_owner_disputing_a_discretionary_fee_keeps_the_cost():
    c, lines = fp_charge()
    a, _ = run(c, lines)
    d = decide_by_owner(c, a, K.DISPUTE, POLICY, 4, cap_at_deal=True)
    assert (d.kind, d.disputed, d.accepted) == (K.SPLIT, Decimal("185.76"), Decimal("1032.00"))
    d = decide_by_owner(c, a, K.DISPUTE, POLICY, 4, cap_at_deal=False)
    assert (d.kind, d.disputed) == (K.DISPUTE, Decimal("1217.76"))


# --- Dispute window ---------------------------------------------------------------------------------------------

def test_past_the_window_accepts_with_a_note():
    # Deducted Oct 1, 2025 + 180 days = Mar 30, 2026; checked Apr 10: closed 11 days ago.
    c = charge("S2", "SPL", "381.60", deducted_on=D(2025, 10, 1))
    a, d = run(c, [line(c, D(2025, 9, 20), group="CR-80211", units=240, pass_through="264.00")], as_of=D(2026, 4, 10))
    assert (a.allowed, a.delta) == money("333.60", "48.00")
    assert (a.facts["dispute_window_closes"], a.facts["dispute_days_left"], a.facts["past_dispute_window"]) == (
        D(2026, 3, 30), -11, True)
    assert a.steps[-1] == ("Disputes are due within 180 days of the deduction (Oct 1, 2025): the window closed "
                           "Mar 30, 2026, 11 days ago.")
    assert WINDOW in a.terms
    assert (d.kind, d.accepted, d.disputed, d.gate_row) == (K.ACCEPT, Decimal("381.60"), Decimal("0.00"), 10)
    assert d.reason == ("Past the dispute window (it closed on Mar 30, 2026): accepted and noted; the deal allows "
                        "$333.60, $48.00 less.")


def test_past_the_window_a_fair_charge_is_just_accepted():
    c = charge("M8", "MCBF", "65.00", deducted_on=D(2025, 10, 1))
    _, d = run(c, [line(c, base_amount="940", proof_doc="mcb-backup-0314")], as_of=D(2026, 4, 10))
    assert (d.kind, d.gate_row) == (K.ACCEPT, 5)


def test_window_closing_soon_still_disputes_and_says_when():
    # Oct 15, 2025 + 180 = Apr 13, 2026; 3 days left on Apr 10.
    c = charge("S3", "SPL", "381.60", deducted_on=D(2025, 10, 15))
    a, d = run(c, [line(c, group="CR-80300", units=240, pass_through="264.00")], as_of=D(2026, 4, 10))
    assert a.facts["dispute_days_left"] == 3
    assert (d.kind, d.disputed, d.gate_row) == (K.SPLIT, Decimal("48.00"), 7)
    assert d.reason.endswith("File by Apr 13: the dispute window closes in 3 days.")
    _, far = run(c, [line(c, group="CR-80300", units=240, pass_through="264.00")], as_of=D(2026, 1, 10))
    assert "File by" not in far.reason


def test_window_from_the_invoice_and_without_dates():
    w = replace(WINDOW, params={"days": 30, "from": "invoice"})
    c = charge("S4", "SPL", "381.60")
    lines = [line(c, group="CR-1", units=240, pass_through="264.00")]
    a, d = run(c, lines, terms=[SPOILS, w], as_of=D(2026, 4, 10), invoice_date=D(2026, 3, 1))
    assert a.facts["dispute_window_closes"] == D(2026, 3, 31) and d.gate_row == 10
    a, _ = run(c, lines, terms=[SPOILS, w])  # no as_of: nothing recorded
    assert "dispute_days_left" not in a.facts


def test_window_applies_to_promo_charges_too():
    c1 = replace(s.march_charges()["C1"], deducted_on=D(2025, 9, 1))
    a = compute_allowed(c1, s.spring_terms() + [WINDOW], s.store_sales(), s.prior_payments(),
                        fees=FeeData(as_of=D(2026, 4, 1)))
    d = decide(c1, a, s.strong_finding("C1"), POLICY)
    assert (a.delta, d.kind, d.accepted, d.gate_row) == (Decimal("600.00"), K.ACCEPT, Decimal("1800.00"), 10)


def test_peak_bar_unchanged_with_fee_data_present():
    """The six March charges decide exactly as before when the fee machinery is in the call."""
    out = []
    for c in s.march_charges().values():
        a = compute_allowed(c, s.spring_terms(), s.store_sales(), s.prior_payments(), fees=FeeData(as_of=D(2026, 4, 10)))
        out.append(decide(c, a, s.strong_finding(c.id), POLICY, [s.rule_1()]))
    t = summarize(out)
    assert (t.disputed, t.accepted) == money("4120.00", "2730.00")
