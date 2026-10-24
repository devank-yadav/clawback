"""An account's data rows: charges, store sales, prior payments and the promo plan, as api/contracts.py models.

The sibling of api/documents.py (which loads the text documents). Every loader reads one account (api/accounts.py):
the one it's given, else the current one (Peak Bar unless a run set another). charges(), sales(), prior_payments()
and promo_plan() read Postgres when the database is on (DATABASE_URL set, not DEMO_MODE, api/db/conn.py) and holds
the account's seeded rows, which api/db/reads.py gives back exactly as the files do; otherwise, or on any database
error, the account's files. The *_from_files loaders always read the files: the seed copies them in. `data` reads
another folder laid out like an account's (a test's own copy), always from its files.

Display-fee charges get their notice_date from the account's notices/. Matching is strict, because a wrong or
missing notice date silently flips Rule #1 (no date means "notice unknown", which disputes the fee):
- a notice that names the charge's ref (**Charge ref:**) is that charge's notice;
- a notice with no ref matches only if its fee amount and its "month ending" date equal the charge's amount
  and period end, and no other notice does;
- a notice that names the ref but states a different amount, or a fee with no notice or two, is a DataError.
A notice that states no fee ("… fee of $…") isn't a fee notice and is left out here.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from api import accounts
from api.contracts import Charge, PriorPayment, PromoPlan, SalesRow
from api.db import reads

FEE_CODES = frozenset({"DF"})

SALES_FILE = "sales/store-sales.csv"
PRIOR_FILE = "payments/prior.csv"
PLAN_FILE = "plan/promo-plan.csv"

_REF = re.compile(r"\*\*Charge ref:\*\*\s*(\S+)")
_FEE = re.compile(r"\bfee of \$([\d,]+(?:\.\d\d)?)")  # "will charge a display fee of $1,200.00"
_MONTH_END = re.compile(r"month ending ([A-Z][a-z]+ \d{1,2}, \d{4})")

AccountRef = accounts.Account | str | None


class DataError(ValueError):
    """The data files disagree with each other in a way the pipeline must not guess around."""


def charge_file(month: str) -> str:
    """One month's charges in an account's folder: charges/march.csv."""
    return f"charges/{month}.csv"


def _folder(data: Path | None, account: AccountRef) -> Path:
    return data if data is not None else accounts.resolve(account).dir


def _csv(rel: str, folder: Path) -> list[dict[str, str]]:
    if not (folder / rel).is_file():
        return []  # a missing file means no rows
    with open(folder / rel, newline="") as f:
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


def notices(data: Path | None = None, *, account: AccountRef = None) -> list[Notice]:
    out = []
    for p in sorted((_folder(data, account) / "notices").glob("*.md")):
        path, doc_id, text = f"notices/{p.name}", p.stem, p.read_text()
        fee = _FEE.search(text)
        if not fee:
            continue
        when = _notice_date(text, path)
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


# ---------------------------------------------------------------- rows: Postgres when it's on, else the files

def charges(month: str, data: Path | None = None, *, account: AccountRef = None) -> list[Charge]:
    """One month's charges ("march" or "april" for Peak Bar), display fees with their notice date attached."""
    return _database_or(lambda: charges_from_files(month, data, account=account), data, account, "charges",
                        charge_file(month))


def sales(data: Path | None = None, *, account: AccountRef = None) -> list[SalesRow]:
    return _database_or(lambda: sales_from_files(data, account=account), data, account, "store_sales")


def prior_payments(data: Path | None = None, *, account: AccountRef = None) -> list[PriorPayment]:
    return _database_or(lambda: prior_payments_from_files(data, account=account), data, account, "prior_payments")


def promo_plan(data: Path | None = None, *, account: AccountRef = None) -> list[PromoPlan]:
    return _database_or(lambda: promo_plan_from_files(data, account=account), data, account, "promo_plan")


def _database_or(files, data: Path | None, account: AccountRef, table: str, *args):
    if data is None:
        got = reads.load(table, accounts.resolve(account).id, *args)  # None: no database, it failed, or no rows
        if got is not None:
            return got
    return files()


# ---------------------------------------------------------------- rows from the files

def charges_from_files(month: str, data: Path | None = None, *, account: AccountRef = None) -> list[Charge]:
    folder = _folder(data, account)
    pool = notices(folder)
    out = []
    for r in _csv(charge_file(month), folder):
        c = Charge(id=r["charge_id"], ref=r["ref"], code=r["code"], description=r["description"], product=r["product"],
                   units=int(r["units"]), rate=Decimal(r["rate"]), amount=Decimal(r["amount"]),
                   period_start=date.fromisoformat(r["period_start"]), period_end=date.fromisoformat(r["period_end"]),
                   line_ref=(r.get("line_ref") or "").strip() or None)
        if c.code in FEE_CODES:
            c = c.model_copy(update={"notice_date": notice_for(c, pool).notice_date})
        out.append(c)
    return out


def sales_from_files(data: Path | None = None, *, account: AccountRef = None) -> list[SalesRow]:
    return [SalesRow(week_start=date.fromisoformat(r["week_start"]), week_end=date.fromisoformat(r["week_end"]),
                     product=r["product"], promo_units=int(r["promo_units"]), total_units=int(r["total_units"]))
            for r in _csv(SALES_FILE, _folder(data, account))]


def prior_payments_from_files(data: Path | None = None, *, account: AccountRef = None) -> list[PriorPayment]:
    return [PriorPayment(ref=r["ref"], paid_on=date.fromisoformat(r["paid_on"]), promo_id=r["promo_id"],
                         product=r["product"], period_start=date.fromisoformat(r["period_start"]),
                         period_end=date.fromisoformat(r["period_end"]), units=int(r["units"]),
                         amount=Decimal(r["amount"]))
            for r in _csv(PRIOR_FILE, _folder(data, account))]


def promo_plan_from_files(data: Path | None = None, *, account: AccountRef = None) -> list[PromoPlan]:
    return [PromoPlan(promo_id=r["promo_id"], products=_products(r["product"]), rate=Decimal(r["rate"]),
                      starts=date.fromisoformat(r["starts"]), ends=date.fromisoformat(r["ends"]), cap=int(r["cap"]))
            for r in _csv(PLAN_FILE, _folder(data, account))]
