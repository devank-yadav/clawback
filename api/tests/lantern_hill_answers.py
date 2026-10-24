"""Faked AI answers for the two accounts on KeHE's Vendor Policies & Procedures: Lantern Hill Soda Co. <- KeHE
Distributors and Peak Bar Co. <- KeHE Distributors (peak-bar-kehe, on its own copy of the policy). What both Deal
Readers, the Investigator, the rehearsal and the rule writer would return. Written by hand, not recorded: nothing here
was ever sent to a model. The tests feed them through the real code (the readers' JSON validation, the quote check,
the merge of the two reads, the engine and the gate), so every check after an agent still runs on them."""

from __future__ import annotations

NULLS = {"rate": None, "products": None, "start": None, "end": None, "max_units": None, "max_fee": None,
         "extra_units": None, "fee_code": None, "basis": None, "min": None, "max": None, "per": None, "tiers": None,
         "requires_proof": None, "applies_to": None, "requires_fault": None, "add_on": None, "days": None,
         "from": None, "pct": None}
GL, BO = "Lantern Hill Ginger Lime Soda", "Lantern Hill Blood Orange Soda"
# Per account: the brand, its promotion id and promoted items, its document id prefix, the policy copy it reads and
# KeHE's portal notice changing the Extra Performance charge (§10.7).
KEHE_ACCOUNTS = {
    "lantern-hill": {"brand": "Lantern Hill Soda Co.", "promo": "LH-OI-2603", "items": (GL, BO),
                     "docs": "lantern-hill", "policy": "kehe-vendor-policies-2015",
                     "notice": "lantern-hill-kehe-ep-admin-2026-03-02"},
    "peak-bar-kehe": {"brand": "Peak Bar Co.", "promo": "PB-OI-2603",
                      "items": ("Peak Bar Original", "Peak Bar Chocolate"),
                      "docs": "peak-bar-kehe", "policy": "kehe-vendor-policies-2015-peak-bar",
                      "notice": "peak-bar-kehe-ep-admin-2026-03-02"},
}


def term(type_, quote, discretion=False, effective_from=None, effective_to=None, **params) -> dict:
    return {"type": type_, "params": {**NULLS, **params}, "effective_from": effective_from,
            "effective_to": effective_to, "exact_quote": quote, "discretion": discretion}


Q_MCB = ("KeHE will charge a bi weekly processing fee of 5% of the MCB amount (with a minimum of $65 per purchasing "
         "Vendor/facility). MCB invoice backup will be provided through KeHE's Vendor Portal.")
Q_EP = ('KeHE will "pass through" these amounts to Vendor along with an administrative charge of 5% on the total '
        "amount of each invoice with a maximum of $175 per invoice.")
Q_FP = ("Free Placements will be processed and charged back to Vendor at KeHE's landed cost plus an 18% administrative "
        "fee depending on retailer relationship.")
Q_SPOILS = ("When and if Spoils occur, Vendor will only be held responsible for KeHE's landed cost of goods which have "
            "been credited to a retailer plus a $0.29 per unit processing fee or fixed retailer spoilage rate on product "
            "sales depending on retailer program.")
Q_WINDOW = ("If Vendor wishes to dispute any payment deductions, Vendor must send its detailed request electronically "
            "to vendorperformance@KeHEco.m within 180 days of KeHE's deduction from Vendor's invoice.")
Q_NOTICE = ("KeHE reserves the right to modify these Vendor Policies & Procedures at any time with at least thirty (30) "
            "days prior notice by posting changes on the Vendor Portal of the KeHE's website.")
Q_MARKETING = "In order for KeHE to provide Vendors and retailers with extensive marketing support, Vendor shall provide a 1.5% marketing allowance on all purchases."
POLICY_FROM = "2015-05-31"

POLICY = [
    term("fee_schedule", Q_MCB, effective_from=POLICY_FROM, fee_code="MCB", basis="percent", rate="5", min="65",
         per="incident", requires_proof=True),
    term("fee_schedule", Q_EP, effective_from=POLICY_FROM, fee_code="Extra Performance", basis="percent", rate="5",
         max="175", per="invoice", requires_proof=False),
    term("fee_schedule", Q_FP, discretion=True, effective_from=POLICY_FROM, fee_code="Free Placements",
         basis="percent", rate="18", per="incident", requires_proof=False),
    term("fee_schedule", Q_SPOILS, effective_from=POLICY_FROM, fee_code="Spoils", basis="per_unit", rate="0.29",
         per="incident", requires_proof=False),
    term("dispute_window", Q_WINDOW, effective_from=POLICY_FROM, days=180, **{"from": "deduction"}),
    term("notice_period", Q_NOTICE, effective_from=POLICY_FROM, days=30),
]
# Reader B also reads §6.10's marketing allowance as a fee. Reader A doesn't, so the merge marks it disputed; no
# charge in the month uses it.
POLICY_B = POLICY + [term("fee_schedule", Q_MARKETING, effective_from=POLICY_FROM, fee_code="Marketing Allowance",
                          basis="percent", rate="1.5", per="po", requires_proof=False)]
POLICY_UNCLEAR = ["§5.2 lumping and non-compliance fees: the rates are in KeHE's Inbound Routing Guide, not here."]


def submission(account: str) -> tuple[list[dict], list[dict]]:
    """Our promotion submission's terms and the broker's extension, for one of KEHE_ACCOUNTS."""
    a = KEHE_ACCOUNTS[account]
    first, second = a["items"]
    q_oi = (f"{a['brand']} offers KeHE an off-invoice allowance of $1.50 per case on {first} and {second} on purchase "
            "orders written between March 1 and March 28, 2026.")
    q_cap = "The allowance applies to a maximum of 4,000 cases in total."
    promotion = [
        term("promo_rate", q_oi, effective_from="2026-03-01", effective_to="2026-03-28", rate="1.50"),
        term("product_scope", q_oi, products=[first, second]),
        term("date_range", q_oi, start="2026-03-01", end="2026-03-28"),
        term("unit_cap", q_cap, max_units=4000),
    ]
    q_broker = (f"KeHE asked to extend promotion {a['promo']} from March 29 through April 4, same terms, up to 600 "
                "additional cases. Approved.")
    broker = [term("amendment", q_broker, effective_from="2026-03-29", effective_to="2026-04-04", extra_units=600)]
    return promotion, broker


PROMOTION, BROKER = submission("lantern-hill")
Q_OI, Q_CAP, Q_BROKER = PROMOTION[0]["exact_quote"], PROMOTION[3]["exact_quote"], BROKER[0]["exact_quote"]

Q_EP_NEW = ("Effective March 9, 2026, the Extra Performance administrative charge will be 7% on the total amount of "
            "each invoice with a maximum of $250 per invoice.")
EP_NOTICE = [term("fee_schedule", Q_EP_NEW, effective_from="2026-03-09", fee_code="Extra Performance",
                  basis="percent", rate="7", max="250", per="invoice", requires_proof=False)]


def readers(account: str) -> dict:
    """doc id -> (Reader A, Reader B), each {"terms", "unclear"} as the model would return it."""
    a = KEHE_ACCOUNTS[account]
    promotion, broker = submission(account)
    return {
        a["policy"]: ({"terms": POLICY, "unclear": POLICY_UNCLEAR}, {"terms": POLICY_B, "unclear": []}),
        f"{a['docs']}-promotion-2026-03": ({"terms": promotion, "unclear": []}, {"terms": promotion, "unclear": []}),
        f"{a['docs']}-broker-2026-03-24": ({"terms": broker, "unclear": []}, {"terms": broker, "unclear": []}),
        a["notice"]: ({"terms": EP_NOTICE, "unclear": []}, {"terms": EP_NOTICE, "unclear": []}),
    }



READERS = readers("lantern-hill")

# The Investigator plus the rehearsal on every charge: confident, two independent sources, the comeback answered.
FINDING = {"confidence": "0.95", "independent_sources": 2, "comeback_answered": True}

# The owner's answer to the Free Placements question, and what the rule writer makes of it.
OWNER_ANSWER = "Pay KeHE's 18% placement fee when it's $150 or less. Above that pay the landed cost and dispute the fee."
RULE = {"understood": True, "fact": "fee_amount", "op": "<=", "value": 150, "decision": "accept",
        "else_decision": "dispute",
        "summary": "Accept KeHE's free placement admin fee up to $150; above that, dispute the fee and pay the landed cost."}

# Reader B again, stating the same terms in other forms only: longer fee names, "%" and "$" signs, a percent as a
# fraction, a minimum of 0 for none, per and requires_proof left out, an empty tier list, the MCB quote without its
# backup sentence, and §6.6 without the discretion flag. Every one of these must still agree with Reader A.
Q_MCB_ONLY = ("KeHE will charge a bi weekly processing fee of 5% of the MCB amount (with a minimum of $65 per "
              "purchasing Vendor/facility).")
POLICY_B_VARIANT = [
    term("fee_schedule", Q_MCB_ONLY, effective_from=POLICY_FROM, fee_code="MCB processing fee", basis="percent",
         rate="5%", min="$65.00"),
    term("fee_schedule", Q_EP, fee_code="Extra Performance administrative charge", basis="percent", rate="0.05",
         max="175.00", per="invoice", requires_proof=False, tiers=[]),
    term("fee_schedule", Q_FP, discretion=False, effective_from=POLICY_FROM, fee_code="FREE PLACEMENTS",
         basis="percent", rate="18%", min="0"),
    term("fee_schedule", Q_SPOILS, effective_from=POLICY_FROM, fee_code="Spoils processing fee", basis="per_unit",
         rate="$0.29"),
    term("dispute_window", Q_WINDOW, days=180, **{"from": "deduction"}),
    term("notice_period", Q_NOTICE, days=30),
]
EP_NOTICE_VARIANT = [term("fee_schedule", Q_EP_NEW, effective_from="2026-03-09",
                          fee_code="Extra Performance admin charge", basis="percent", rate="7%", max="$250",
                          per="invoice")]


def readers_b_variant(account: str) -> dict:
    a, base = KEHE_ACCOUNTS[account], readers(account)
    return {
        **base,
        a["policy"]: (base[a["policy"]][0], {"terms": POLICY_B_VARIANT, "unclear": []}),
        a["notice"]: (base[a["notice"]][0], {"terms": EP_NOTICE_VARIANT, "unclear": []}),
    }


READERS_B_VARIANT = readers_b_variant("lantern-hill")
