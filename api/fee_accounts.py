"""Fee-schedule wiring for an account with fees/fees.yaml (Lantern Hill Soda Co. <- KeHE Distributors is the first).
Everything else about the account is the usual data/accounts/<id>/ layout (api/accounts.py); this adds what the fee
engine needs and the pipeline passes to compute_allowed():

    fees/fees.yaml                  codes (charge code -> the fee_code the deal names), policy_changes (documents that
                                    change the policy: they apply no sooner than their notice date + notice_period),
                                    as_of (the day a dispute would be filed), invoice_date, older_charges
    fees/backup.csv                 FeeBackupRow lines, keyed by the charge's ref
    purchases/purchase-orders.csv   po, written_on, product, cases (or units): what off-invoice (OI) allowances are
                                    counted on. Optional columns: po_type (the PO's type, for a fee that applies only
                                    to one type), and received_units, for a quantity fee's variance from the order
    deliveries/appointments.csv     optional: po, cause ("carrier", "retailer", "supplier" or blank): who the delivery
                                    log says caused a miss, for a fee that is a remedy for the supplier's failure
    charges/<older_charges>         deductions taken from earlier payments, reviewed with this one (not in its total)

fees.yaml may also give `governs` (a contract version's first purchase date, for its terms that state none: which
version governs a PO is set by the date it was written) and `quantity_codes` (charge codes for over or short shipped
quantities, whose lines carry their variance from the order).

No AI here and no money math.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path

import yaml

from api import accounts, adapters, documents
from api.contracts import Charge, Evidence, FeeBackupRow, SalesRow, Term
from api.engine import types as eng


def _account(account: accounts.Account | str | None) -> accounts.Account:
    return accounts.resolve(account)


def has_fees(account: accounts.Account | str | None = None) -> bool:
    return (_account(account).dir / "fees" / "fees.yaml").is_file()


@cache
def _config(folder: Path) -> dict:
    return yaml.safe_load((folder / "fees" / "fees.yaml").read_text()) or {}


def config(account: accounts.Account | str | None = None) -> dict:
    return _config(_account(account).dir)


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _date(value) -> date | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _charges(path: Path) -> list[Charge]:
    return [Charge.model_validate({k: v for k, v in r.items() if k != "charge_id"} | {"id": r["charge_id"]})
            for r in _csv(path)]


def charges(account: accounts.Account | str | None = None, month: str | None = None) -> list[Charge]:
    """The month's charges, read from the file with their deducted_on dates."""
    a = _account(account)
    return _charges(a.dir / "charges" / f"{month or a.invoice.month}.csv")


def older_charges(account: accounts.Account | str | None = None) -> list[Charge]:
    """Deductions taken from earlier payments and reviewed with this one (fees.yaml older_charges)."""
    rel = config(account).get("older_charges")
    return _charges(_account(account).dir / rel) if rel else []


def backup(account: accounts.Account | str | None = None) -> list[FeeBackupRow]:
    return [FeeBackupRow.model_validate(r) for r in _csv(_account(account).dir / "fees" / "backup.csv")]


def purchases(account: accounts.Account | str | None = None) -> list[dict[str, str]]:
    return _csv(_account(account).dir / "purchases" / "purchase-orders.csv")


def noticed_on(doc_id: str, account: accounts.Account | str | None = None) -> date | None:
    """A policy-change document's notice date (fees.yaml policy_changes); None for every other document."""
    if doc_id not in config(account).get("policy_changes", []):
        return None
    received = documents.load(doc_id)[0].received_at
    return received.date() if received else None


def governs_from(doc_id: str, account: accounts.Account | str | None = None) -> date | None:
    """The first purchase date a contract version governs (fees.yaml governs), for its terms that state none."""
    return _date((config(account).get("governs") or {}).get(doc_id, {}).get("from"))


def engine_terms(terms: list[Term], account: accounts.Account | str | None = None) -> list[eng.Term]:
    out = []
    for t in terms:
        start = governs_from(t.source_doc_id, account)
        if start and t.effective_from is None:
            t = t.model_copy(update={"effective_from": start})
        out.append(adapters.to_engine_term(t, noticed_on(t.source_doc_id, account)))
    return out


def appointments(account: accounts.Account | str | None = None) -> list[dict[str, str]]:
    return _csv(_account(account).dir / "deliveries" / "appointments.csv")


def _units(r: dict[str, str]) -> int:
    return int(r.get("cases") or r["units"])


def _enrich(line: eng.FeeLine, pos: dict[str, dict], causes: dict[str, str], quantity_refs: set[str]) -> eng.FeeLine:
    """Our side's records for the line's purchase order (its group): the PO's type, who caused a delivery miss, and
    for a quantity fee how far the delivery was from the order."""
    po = pos.get(line.group, {})
    variance = None
    if line.deduction_ref in quantity_refs and po.get("received_units"):
        ordered = _units(po)
        variance = (abs(Decimal(po["received_units"]) - ordered) * 100 / ordered).quantize(Decimal("0.01"))
    return replace(line, po_type=po.get("po_type", ""), caused_by=causes.get(line.group, ""), variance_pct=variance)


def fee_data(account: accounts.Account | str | None = None) -> eng.FeeData:
    a, c = _account(account), config(account)
    pos = {r["po"]: r for r in purchases(a)}
    causes = {r["po"]: (r.get("cause") or "").strip().lower() for r in appointments(a)}
    quantity = set(c.get("quantity_codes") or [])
    quantity_refs = {ch.ref for ch in charges(a) + older_charges(a) if ch.code in quantity}
    return eng.FeeData(
        lines=tuple(_enrich(adapters.to_engine_fee_line(r), pos, causes, quantity_refs) for r in backup(a)),
        codes=dict(c.get("codes", {})),
        proof_docs=frozenset(a.docs),
        as_of=_date(c.get("as_of")),
        invoice_date=_date(c.get("invoice_date")),
    )


def sales_rows(account: accounts.Account | str | None = None) -> list[SalesRow]:
    """Each purchase order as a one-day row (written_on to written_on, cases as the promoted units), so the promo
    engine counts an off-invoice allowance by the date its PO was written (KeHE policy §6.2) and caps it in that
    order."""
    out = []
    for r in purchases(account):
        day, cases = date.fromisoformat(r["written_on"]), _units(r)
        out.append(SalesRow(week_start=day, week_end=day, product=r["product"], promo_units=cases, total_units=cases))
    return out


def evidence(account: accounts.Account | str | None = None) -> dict[str, Evidence]:
    """The backup behind each fee charge (ev-backup-<ref>) and each purchase order (ev-po-<po>), for the evidence card
    and the agents to cite."""
    out: dict[str, Evidence] = {}
    by_ref: dict[str, list[FeeBackupRow]] = {}
    for r in backup(account):
        by_ref.setdefault(r.deduction_ref, []).append(r)
    for ref, lines in by_ref.items():
        total = sum((r.base_amount for r in lines), Decimal(0))
        cost = sum((r.pass_through for r in lines), Decimal(0))
        parts = [f"{len(lines)} backup line{'s' if len(lines) > 1 else ''}"]
        if total:
            parts.append(f"${total:,.2f} the fee is taken on")
        if cost:
            parts.append(f"${cost:,.2f} cost at cost")
        out[f"ev-backup-{ref}"] = Evidence(
            id=f"ev-backup-{ref}", kind="backup", label=f"Backup {ref}", summary="Deduction backup: " + ", ".join(parts) + ".",
            rows=[{k: (float(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, date) else v)
                   for k, v in r.model_dump().items()} for r in lines])
    for r in purchases(account):
        d = date.fromisoformat(r["written_on"])
        out[f"ev-po-{r['po']}"] = Evidence(
            id=f"ev-po-{r['po']}", kind="sales", label=f"PO {r['po']}",
            summary=f"Purchase order written {d:%b} {d.day}: {_units(r):,} {'cases' if r.get('cases') else 'units'} "
                    f"of {r['product']}" + (f" ({r['po_type']})" if r.get("po_type") else "") + ".",
            rows=[dict(r)])
    # The delivery log is what the engine reads to excuse a fee that's a remedy for the supplier's own failure; without
    # it in the evidence the Investigator can't see who caused the miss and won't vouch for the dispute (live, W6 and
    # F5 asked "the delivery log the engine relied on is not among the cited evidence").
    for r in appointments(account):
        cause = (r.get("cause") or "").strip().lower()
        summary = f"Delivery log for PO {r['po']}: " + (
            f"late or missed, caused by the {cause}." if (r.get("late_or_missed") or "").strip().lower() == "yes" and cause
            else f"cause recorded: {cause}." if cause else "no miss recorded.")
        if (r.get("note") or "").strip():
            summary += f" {r['note'].strip()}"
        out[delivery_id(r["po"])] = Evidence(id=delivery_id(r["po"]), kind="delivery", label=f"Delivery log PO {r['po']}",
                                             summary=summary, rows=[dict(r)])
    return out


def delivery_id(po: str) -> str:
    return f"ev-delivery-{po.strip()}"
