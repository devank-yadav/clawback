"""Fee-schedule wiring for an account with fees/fees.yaml (Lantern Hill Soda Co. <- KeHE Distributors is the first).
Everything else about the account is the usual data/accounts/<id>/ layout (api/accounts.py); this adds what the fee
engine needs and the pipeline passes to compute_allowed():

    fees/fees.yaml                  codes (charge code -> the fee_code the deal names), policy_changes (documents that
                                    change the policy: they apply no sooner than their notice date + notice_period),
                                    as_of (the day a dispute would be filed), invoice_date, older_charges
    fees/backup.csv                 FeeBackupRow lines, keyed by the charge's ref
    purchases/purchase-orders.csv   po, written_on, product, cases: what off-invoice (OI) allowances are counted on
    charges/<older_charges>         deductions taken from earlier payments, reviewed with this one (not in its total)

No AI here and no money math.
"""

from __future__ import annotations

import csv
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


def engine_terms(terms: list[Term], account: accounts.Account | str | None = None) -> list[eng.Term]:
    return [adapters.to_engine_term(t, noticed_on(t.source_doc_id, account)) for t in terms]


def fee_data(account: accounts.Account | str | None = None) -> eng.FeeData:
    a, c = _account(account), config(account)
    return eng.FeeData(
        lines=tuple(adapters.to_engine_fee_line(r) for r in backup(a)),
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
        day, cases = date.fromisoformat(r["written_on"]), int(r["cases"])
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
            summary=f"Purchase order written {d:%b} {d.day}: {int(r['cases']):,} cases of {r['product']}.",
            rows=[dict(r)])
    return out
