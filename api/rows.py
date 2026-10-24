"""Data rows under data/: charges, store sales, prior payments and the promo plan, as api/contracts.py models.

The sibling of api/documents.py (which loads the text documents). The seed copies these into Postgres; until
then the pipeline and tests read them straight from the files.

Display-fee charges get their notice_date from data/notices/. Matching is strict, because a wrong or missing
notice date silently flips Rule #1 (no date means "notice unknown", which disputes the fee):
- a notice that names the charge's ref (**Charge ref:**) is that charge's notice;
- a notice with no ref matches only if its fee amount and its "month ending" date equal the charge's amount
  and period end, and no other notice does;
- a notice that names the ref but states a different amount, or a fee with no notice or two, is a DataError.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from api import documents
from api.contracts import Charge, PriorPayment, PromoPlan, SalesRow

DATA = documents.DATA
FEE_CODES = frozenset({"DF"})

CHARGE_FILES = {"march": "charges/northmart-march.csv", "april": "charges/northmart-april.csv"}

_REF = re.compile(r"\*\*Charge ref:\*\*\s*(\S+)")
_FEE = re.compile(r"\bfee of \$([\d,]+(?:\.\d\d)?)")  # "will charge a display fee of $1,200.00"
_MONTH_END = re.compile(r"month ending ([A-Z][a-z]+ \d{1,2}, \d{4})")


class DataError(ValueError):
    """The data files disagree with each other in a way the pipeline must not guess around."""


def _csv(rel: str, data: Path) -> list[dict[str, str]]:
    with open(data / rel, newline="") as f:
        return list(csv.DictReader(f))


def _products(text: str) -> list[str]:
    return [p.strip() for p in text.replace(";", "+").split("+") if p.strip()]


# ---------------------------------------------------------------- notices

@dataclass(frozen=True)
class Notice:
    doc_id: str
    notice_date: date
    amount: Decimal
    month_ending: date | None
    ref: str | None  # the charge ref the notice names, if it names one


def notices(data: Path = DATA) -> list[Notice]:
    out = []
    for p in sorted((data / "notices").glob("*.md")):
        path, doc_id, text = f"notices/{p.name}", p.stem, p.read_text()
        when = _notice_date(text, path)
        fee = _FEE.search(text)
        if not fee:
            raise DataError(f"{path}: no 'display fee of $…' sentence to read the amount from")
        end = _MONTH_END.search(text)
        ref = _REF.search(text)
        out.append(Notice(
            doc_id=doc_id,
            notice_date=when,
            amount=Decimal(fee.group(1).replace(",", "")).quantize(Decimal("0.01")),
            month_ending=datetime.strptime(end.group(1), "%B %d, %Y").date() if end else None,
            ref=ref.group(1) if ref else None,
        ))
    return out


def _notice_date(text: str, path: str) -> date:
    m = re.search(r"\*\*Notice date:\*\*\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if not m:
        raise DataError(f"{path}: no **Notice date:** line")
    return datetime.strptime(m.group(1), "%B %d, %Y").date()


def notice_for(charge: Charge, pool: list[Notice]) -> Notice:
    """The one notice behind a display-fee charge. See the module docstring for the rules."""
    by_ref = [n for n in pool if n.ref == charge.ref]
    if len(by_ref) > 1:
        raise DataError(f"{charge.id} ({charge.ref}): {len(by_ref)} notices name this ref")
    if by_ref:
        n = by_ref[0]
        if n.amount != charge.amount:
            raise DataError(f"{charge.id} ({charge.ref}): notice {n.doc_id} says ${n.amount}, charge is ${charge.amount}")
        return n
    loose = [n for n in pool if n.ref is None and n.amount == charge.amount and n.month_ending == charge.period_end]
    if len(loose) == 1:
        return loose[0]
    if not loose:
        raise DataError(f"{charge.id} ({charge.ref}): no notice for a ${charge.amount} fee ending {charge.period_end}")
    raise DataError(f"{charge.id} ({charge.ref}): {len(loose)} notices without a ref fit; add **Charge ref:** lines")


# ---------------------------------------------------------------- rows

def charges(month: str, data: Path = DATA) -> list[Charge]:
    """One month's charges ("march" or "april"), display fees with their notice date attached."""
    pool = notices(data)
    out = []
    for r in _csv(CHARGE_FILES[month], data):
        c = Charge(id=r["charge_id"], ref=r["ref"], code=r["code"], description=r["description"], product=r["product"],
                   units=int(r["units"]), rate=Decimal(r["rate"]), amount=Decimal(r["amount"]),
                   period_start=date.fromisoformat(r["period_start"]), period_end=date.fromisoformat(r["period_end"]))
        if c.code in FEE_CODES:
            c = c.model_copy(update={"notice_date": notice_for(c, pool).notice_date})
        out.append(c)
    return out


def sales(data: Path = DATA) -> list[SalesRow]:
    return [SalesRow(week_start=date.fromisoformat(r["week_start"]), week_end=date.fromisoformat(r["week_end"]),
                     product=r["product"], promo_units=int(r["promo_units"]), total_units=int(r["total_units"]))
            for r in _csv("sales/store-sales.csv", data)]


def prior_payments(data: Path = DATA) -> list[PriorPayment]:
    return [PriorPayment(ref=r["ref"], paid_on=date.fromisoformat(r["paid_on"]), promo_id=r["promo_id"],
                         product=r["product"], period_start=date.fromisoformat(r["period_start"]),
                         period_end=date.fromisoformat(r["period_end"]), units=int(r["units"]),
                         amount=Decimal(r["amount"]))
            for r in _csv("payments/prior.csv", data)]


def promo_plan(data: Path = DATA) -> list[PromoPlan]:
    return [PromoPlan(promo_id=r["promo_id"], products=_products(r["product"]), rate=Decimal(r["rate"]),
                      starts=date.fromisoformat(r["starts"]), ends=date.fromisoformat(r["ends"]), cap=int(r["cap"]))
            for r in _csv("plan/promo-plan.csv", data)]
