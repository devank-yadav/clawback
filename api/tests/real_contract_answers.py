"""Faked AI answers for the two accounts on real supplier agreements: Copperline Home Co. <- Walmart (the 2013 Supplier
Agreement) and Fizzwick Toys Co. <- Five Below (its 2023 and 2025 Vendor Agreements). What both Deal Readers would
return, written by hand, not recorded: nothing here was ever sent to a model. Each quote is the account's clause key
(data/accounts/<id>/terms/fee-terms.csv), cut from the filing, so the tests' quote check runs on the real text.
The Investigator and the rehearsal answers are built per request in test_real_contract_accounts.py."""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path

from api.tests.lantern_hill_answers import term

ACCOUNTS = Path(__file__).resolve().parents[2] / "data" / "accounts"


@cache
def quotes(account: str) -> dict[str, str]:
    with (ACCOUNTS / account / "terms" / "fee-terms.csv").open(newline="") as f:
        return {r["key"]: r["quote"] for r in csv.DictReader(f)}


def fee(account: str, key: str, fee_code: str, basis: str, rate: str | None, per: str, effective_from=None,
        discretion=False, **params) -> dict:
    defaults = {"min": None, "max": None, "tiers": None, "requires_proof": False, "applies_to": None,
                "requires_fault": False, "add_on": False}
    return term("fee_schedule", quotes(account)[key], discretion=discretion, effective_from=effective_from,
                fee_code=fee_code, basis=basis, rate=rate, per=per, **(defaults | params))


def both(terms: list[dict]) -> tuple[dict, dict]:
    """Both readers return the same terms."""
    return {"terms": terms, "unclear": []}, {"terms": terms, "unclear": []}


NOTHING = both([])

# ---- Copperline Home Co. <- Walmart -------------------------------------------------------------------------------

WM, WM_FROM = "copperline", "2013-04-18"  # the agreement's effective date, on its first page
WALMART = [
    fee(WM, "sa_rate", "New Store/Club Discount", "percent", "10", "po", WM_FROM, applies_to="new store"),
    fee(WM, "nw_rate", "New Distribution Center", "percent", "10", "po", WM_FROM, applies_to="new distribution center"),
    fee(WM, "dm_rate", "Defective/Returned Mdse. Allowance", "percent", "1.5", "invoice", WM_FROM),
    fee(WM, "rj_allowance", "Rejection", "percent", "10", "incident", WM_FROM, requires_fault=True),
    fee(WM, "fn_fines", "Assessment of monetary fines", "as_assessed", None, "incident", WM_FROM, discretion=True,
        requires_fault=True),
    fee(WM, "rt_handling", "Return Policy", "percent", "10", "incident", WM_FROM),
    fee(WM, "in_rate", "Interest", "annual_percent", "12", "incident", WM_FROM),
]
COPPERLINE = {
    "walmart-supplier-agreement-2013": both(WALMART),
    "copperline-item-setup-2026": NOTHING,
    "copperline-walmart-rejection-2026-03-18": NOTHING,
    "copperline-walmart-fine-2026-03-26": NOTHING,
    "copperline-walmart-fine-2026-03-27": NOTHING,
    "copperline-return-center-claim-2026-03-05": NOTHING,
    "copperline-walmart-interest-2026-03-31": NOTHING,
}

# ---- Fizzwick Toys Co. <- Five Below ------------------------------------------------------------------------------
# Neither excerpt states the date it starts: fees.yaml `governs` dates each version from our signed acceptance.

FB = "fizzwick"
DOC_TIERS = [{"from_days": 1, "to_days": 7, "rate": "100"}, {"from_days": 8, "to_days": 12, "rate": "200"},
             {"from_days": 13, "to_days": None, "rate": "250"}]


def five_below(v: str, overage: dict, missed: dict) -> list[dict]:
    q = quotes(FB)
    return [
        fee(FB, f"admin_{v}", "administrative fee", "flat", "100", "po", add_on=True),
        overage,
        fee(FB, f"carton_marking_{v}", "Incorrect carton marking", "percent", "3", "po", max="750"),
        fee(FB, f"late_shipment_{v}", "Late Shipment (arrive after the cancel date because of late booking)", "percent",
            "5", "po", requires_fault=True),
        fee(FB, f"backorder_{v}", "Receipt of backorder (shortship)", "percent", "5", "po"),
        fee(FB, f"inner_pack_{v}", "Incorrect inner pack or master pack", "percent", "3", "po", max="750"),
        missed,
        fee(FB, f"appt_48h_{v}", "Appointment not made 48 hours in advance of requested appt date", "flat", "150", "po",
            requires_fault=True),
        # The Violation Summary and the Document Instructions each price late documents: two rules for one fee.
        fee(FB, f"docs_late_table_{v}", "Documents not uploaded", "per_unit", None, "incident", tiers=DOC_TIERS),
        fee(FB, f"docs_late_section_{v}", "Documents not uploaded", "per_unit", "150", "incident"),
        term("dispute_window", q[f"dispute_window_{v}"], days=90, **{"from": "deduction"}),
        term("quantity_variance", q[f"variance_{v}"], discretion=True, pct="5"),
    ]


FB_2023 = five_below(
    "2023",
    fee(FB, "overage_2023", "Overage quantity received", "percent", "5", "po"),
    fee(FB, "missed_appt_2023", "Missed/Late/Unappointed Appointments w/o communication", "percent", "3", "po",
        max="750", requires_fault=True))
FB_2025 = five_below(
    "2025",
    fee(FB, "overage_2025", "Overage quantity received", "percent", "3", "po", max="750"),
    fee(FB, "missed_appt_2025", "Missed/Late/Unappointed Appointments w/o communication", "percent", "5", "po",
        max="750", requires_fault=True))
FIZZWICK = {
    "five-below-vendor-agreement-2023-excerpt": both(FB_2023),
    "five-below-vendor-agreement-2025-excerpt": both(FB_2025),
    "fizzwick-vendor-agreement-acceptance-2026": NOTHING,
    "fizzwick-forsyth-reschedule-2026-03-11": NOTHING,
}

READERS = {"copperline": COPPERLINE, "fizzwick": FIZZWICK}
