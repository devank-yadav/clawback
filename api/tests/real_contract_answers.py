"""Faked AI answers for the accounts on real supplier agreements: Copperline Home Co. and Peak Bar Co. <- Walmart (the
2013 Supplier Agreement), Fizzwick Toys Co. and Peak Bar Co. <- Five Below (its 2023 and 2025 Vendor Agreements); Peak
Bar's accounts read their own copies of the filings. What both Deal Readers would
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

# ---- Walmart: Copperline Home Co., Peak Bar Co. ---------------------------------------------------------------------

WM_FROM = "2013-04-18"  # the agreement's effective date, on its first page


def walmart(wm: str, contract: str, ours: list[str]) -> dict:
    """wm's two readers, by document: the agreement's fees; nothing in our item setup or Walmart's notices (ours)."""
    fees = [
        fee(wm, "sa_rate", "New Store/Club Discount", "percent", "10", "po", WM_FROM, applies_to="new store"),
        fee(wm, "nw_rate", "New Distribution Center", "percent", "10", "po", WM_FROM,
            applies_to="new distribution center"),
        fee(wm, "dm_rate", "Defective/Returned Mdse. Allowance", "percent", "1.5", "invoice", WM_FROM),
        fee(wm, "rj_allowance", "Rejection", "percent", "10", "incident", WM_FROM, requires_fault=True),
        fee(wm, "fn_fines", "Assessment of monetary fines", "as_assessed", None, "incident", WM_FROM, discretion=True,
            requires_fault=True),
        fee(wm, "rt_handling", "Return Policy", "percent", "10", "incident", WM_FROM),
        fee(wm, "in_rate", "Interest", "annual_percent", "12", "incident", WM_FROM),
    ]
    return {contract: both(fees), **{d: NOTHING for d in ours}}


COPPERLINE = walmart("copperline", "walmart-supplier-agreement-2013", [
    "copperline-item-setup-2026", "copperline-walmart-rejection-2026-03-18", "copperline-walmart-fine-2026-03-26",
    "copperline-walmart-fine-2026-03-27", "copperline-return-center-claim-2026-03-05",
    "copperline-walmart-interest-2026-03-31"])
PEAK_BAR_WALMART = walmart("peak-bar-walmart", "walmart-supplier-agreement-2013-peak-bar", [
    "peak-bar-walmart-item-setup-2026", "peak-bar-walmart-rejection-2026-03-18", "peak-bar-walmart-fine-2026-03-26",
    "peak-bar-walmart-fine-2026-03-27", "peak-bar-walmart-return-center-claim-2026-03-05",
    "peak-bar-walmart-interest-2026-03-31"])

# ---- Five Below: Fizzwick Toys Co., Peak Bar Co. ------------------------------------------------------------------
# Neither excerpt states the date it starts: fees.yaml `governs` dates each version from our signed acceptance.

DOC_TIERS = [{"from_days": 1, "to_days": 7, "rate": "100"}, {"from_days": 8, "to_days": 12, "rate": "200"},
             {"from_days": 13, "to_days": None, "rate": "250"}]


def five_below_version(fb: str, v: str, overage: dict, missed: dict) -> list[dict]:
    q = quotes(fb)
    return [
        fee(fb, f"admin_{v}", "administrative fee", "flat", "100", "po", add_on=True),
        overage,
        fee(fb, f"carton_marking_{v}", "Incorrect carton marking", "percent", "3", "po", max="750"),
        fee(fb, f"late_shipment_{v}", "Late Shipment (arrive after the cancel date because of late booking)", "percent",
            "5", "po", requires_fault=True),
        fee(fb, f"backorder_{v}", "Receipt of backorder (shortship)", "percent", "5", "po"),
        fee(fb, f"inner_pack_{v}", "Incorrect inner pack or master pack", "percent", "3", "po", max="750"),
        missed,
        fee(fb, f"appt_48h_{v}", "Appointment not made 48 hours in advance of requested appt date", "flat", "150", "po",
            requires_fault=True),
        # The Violation Summary and the Document Instructions each price late documents: two rules for one fee.
        fee(fb, f"docs_late_table_{v}", "Documents not uploaded", "per_unit", None, "incident", tiers=DOC_TIERS),
        fee(fb, f"docs_late_section_{v}", "Documents not uploaded", "per_unit", "150", "incident"),
        term("dispute_window", q[f"dispute_window_{v}"], days=90, **{"from": "deduction"}),
        term("quantity_variance", q[f"variance_{v}"], discretion=True, pct="5"),
    ]


def five_below(fb: str, copy: str = "") -> dict:
    """fb's two readers, by document: each version's fees (copy: the suffix of the account's own excerpt files)."""
    fb_2023 = five_below_version(
        fb, "2023",
        fee(fb, "overage_2023", "Overage quantity received", "percent", "5", "po"),
        fee(fb, "missed_appt_2023", "Missed/Late/Unappointed Appointments w/o communication", "percent", "3", "po",
            max="750", requires_fault=True))
    fb_2025 = five_below_version(
        fb, "2025",
        fee(fb, "overage_2025", "Overage quantity received", "percent", "3", "po", max="750"),
        fee(fb, "missed_appt_2025", "Missed/Late/Unappointed Appointments w/o communication", "percent", "5", "po",
            max="750", requires_fault=True))
    return {
        f"five-below-vendor-agreement-2023-excerpt{copy}": both(fb_2023),
        f"five-below-vendor-agreement-2025-excerpt{copy}": both(fb_2025),
        f"{fb}-vendor-agreement-acceptance-2026": NOTHING,
        f"{fb}-forsyth-reschedule-2026-03-11": NOTHING,
    }


FIZZWICK = five_below("fizzwick")
PEAK_BAR_FIVE_BELOW = five_below("peak-bar-five-below", "-peak-bar")

READERS = {"copperline": COPPERLINE, "fizzwick": FIZZWICK, "peak-bar-walmart": PEAK_BAR_WALMART,
           "peak-bar-five-below": PEAK_BAR_FIVE_BELOW}
