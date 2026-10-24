"""An account's other data rows (api/accounts.py layout): its history, and the files the shortage, price mismatch and
spoilage checks read. Plain Pydantic rows from the CSVs, files only (the seeded tables are api/rows.py's).

- history/invoices.csv      invoice, date, amount, status
- history/remittances.csv   date, invoice, paid, deducted
- history/deductions.csv    month, ref, code, description, amount, outcome, recovered
- deliveries/pod.csv        line_ref, product, shipped_units, received_units, unit_price, received_by, received_at
- pricing/price-list.csv    product, agreed_price, effective_from, effective_to, source_doc
- terms/ops-terms.csv       key, value, source_doc, quote

A missing file means no rows; a blank cell is unset (None, or 0 for an amount); extra columns are ignored.
ops(account) bundles the last three for the run (the engine builds its OpsData from them).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from api import accounts
from api.contracts import Money, Rate

R = TypeVar("R", bound="Row")


class Row(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _blank_is_unset(cls, data: Any) -> Any:
        if isinstance(data, dict):  # a blank cell takes the field's default (None, or 0 for an amount)
            return {k: v for k, v in data.items() if v is not None and not (isinstance(v, str) and not v.strip())}
        return data


# ---------------------------------------------------------------- history

class InvoiceHistory(Row):
    invoice: str
    date: date
    amount: Money
    status: str | None = None  # "paid", "short paid", ...


class RemittanceHistory(Row):
    date: date
    invoice: str
    paid: Money
    deducted: Money = Decimal("0.00")


class DeductionHistory(Row):
    month: str  # "2026-02" (also read: "2026-02-28", "february", "February 2026")
    ref: str
    code: str  # PA, DF, SH, PR, SP
    description: str | None = None
    amount: Money
    outcome: str | None = None  # "open" (or "disputed", "pending") is still in dispute; anything else is settled
    recovered: Money = Decimal("0.00")


# ---------------------------------------------------------------- deliveries, pricing, ops terms

class DeliveryLine(Row):
    line_ref: str
    product: str
    shipped_units: int
    received_units: int
    unit_price: Rate
    received_by: str | None = None
    received_at: date | datetime | None = None


class PriceListRow(Row):
    product: str
    agreed_price: Rate
    effective_from: date | None = None
    effective_to: date | None = None
    source_doc: str | None = None


class OpsTerm(Row):
    key: str  # "shortage_claim_days"
    value: str
    source_doc: str | None = None
    quote: str | None = None


@dataclass(frozen=True)
class Ops:
    """What a run hands the engine for SH / PR / SP charges."""

    deliveries: tuple[DeliveryLine, ...] = ()
    prices: tuple[PriceListRow, ...] = ()
    terms: tuple[OpsTerm, ...] = ()


FILES: dict[type[Row], str] = {
    InvoiceHistory: "history/invoices.csv",
    RemittanceHistory: "history/remittances.csv",
    DeductionHistory: "history/deductions.csv",
    DeliveryLine: "deliveries/pod.csv",
    PriceListRow: "pricing/price-list.csv",
    OpsTerm: "terms/ops-terms.csv",
}


def read(model: type[R], account: accounts.Account | str | None = None, data: Path | None = None) -> list[R]:
    """One file's rows. `data` reads another folder laid out like an account's (tests)."""
    path = (data or accounts.resolve(account).dir) / FILES[model]
    if not path.is_file():
        return []
    with open(path, newline="") as f:
        return [model.model_validate(r) for r in csv.DictReader(f)]


def invoices(account: accounts.Account | str | None = None) -> list[InvoiceHistory]:
    return read(InvoiceHistory, account)


def remittances(account: accounts.Account | str | None = None) -> list[RemittanceHistory]:
    return read(RemittanceHistory, account)


def deductions(account: accounts.Account | str | None = None) -> list[DeductionHistory]:
    return read(DeductionHistory, account)


def deliveries(account: accounts.Account | str | None = None) -> list[DeliveryLine]:
    return read(DeliveryLine, account)


def price_list(account: accounts.Account | str | None = None) -> list[PriceListRow]:
    return read(PriceListRow, account)


def ops_terms(account: accounts.Account | str | None = None) -> list[OpsTerm]:
    return read(OpsTerm, account)


def ops(account: accounts.Account | str | None = None) -> Ops:
    return Ops(tuple(deliveries(account)), tuple(price_list(account)), tuple(ops_terms(account)))
