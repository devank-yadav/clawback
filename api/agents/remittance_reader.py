"""Remittance Reader (Claude): a remittance advice -> the payment's header and its deduction lines, each with the
exact printed line it came from.

A remittance advice is the statement a distributor sends with a payment: the invoice, what it paid, and every
deduction with the distributor's own code ("PROMO ALLOW", "SHORTAGE", "PRICE DIFF", "SPOILS"). Claude returns strict
JSON (structured outputs) -> Pydantic validation into typed lines (one retry with the error appended; what still fails
goes to a person) -> code checks in api/remittance.py (each quote found in the text, every number on a line printed in
its quote, the lines adding up to what the payment is short). The reader never adds anything up and never decides.

Run it on a file: python -m api.remittance peak-bar data/samples/remittances/northmart-march-2026.pdf
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import Field, model_validator

from api.agents import claude
from api.agents.claude import Strict
from api.contracts import Contract, Money, Rate

SERVICE = "claude-remittance"  # fixtures in data/fixtures/claude-remittance/
PROMPT = (Path(__file__).parent / "prompts" / "remittance_reader.md").read_text()

# PA promo allowance · DF display or discretionary fee · SH shortage · PR price mismatch · SP spoilage
Code = Literal["PA", "DF", "SH", "PR", "SP", "UNKNOWN"]


# What the model fills in. Money and dates are strings (as in the Deal Reader); code types them below.
class LLMLine(Strict):
    ref: str | None
    code_text: str
    code: Code
    description: str
    product: str | None
    units: int | None
    rate: str | None
    amount: str
    period_start: str | None
    period_end: str | None
    line_ref: str | None
    exact_quote: str


class LLMRemittance(Strict):
    payer: str | None
    payment_ref: str | None
    payment_date: str | None
    invoice_id: str | None
    gross: str | None
    paid: str | None
    lines: list[LLMLine]
    unclear: list[str]


class ReadLine(Contract):
    """One deduction line, typed. Nothing here is checked against the text yet: api/remittance.py does that."""

    ref: str | None
    code_text: str
    code: Code
    description: str
    product: str | None
    units: int | None = Field(ge=0)
    rate: Rate | None = Field(ge=0)
    amount: Money = Field(gt=0)  # positive, even when the remittance prints it negative
    period_start: date | None
    period_end: date | None
    line_ref: str | None
    exact_quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def _period_in_order(self) -> "ReadLine":
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError(f"{self.ref or self.description}: period_end is before period_start")
        return self


class ReadRemittance(Contract):
    payer: str | None
    payment_ref: str | None
    payment_date: date | None
    invoice_id: str | None
    gross: Money | None = Field(ge=0)
    paid: Money | None = Field(ge=0)
    lines: list[ReadLine]
    unclear: list[str] = []


@dataclass
class ReadResult:
    value: ReadRemittance | None  # None: the answer failed validation twice, or the call failed; a person reads it
    source: Literal["live", "fixture"]
    attempts: int
    errors: list[str] = field(default_factory=list)


def system_prompt(brand: str, distributor: str, products: list[str]) -> str:
    return PROMPT.format(brand=brand, distributor=distributor, products=", ".join(products))


def user_message(text: str, invoice_id: str, expected: Decimal, received: Decimal) -> str:
    return (f"Context (what the supplier expects; not part of the document):\n"
            f"Invoice: {invoice_id}\nInvoiced: {expected:.2f}\nPayment received: {received:.2f}\n\n"
            f"<remittance>\n{text}\n</remittance>")


def _typed(raw: dict) -> ReadRemittance:
    """LLM JSON -> typed lines. Raises ValidationError (an unreadable amount or date) for the one retry."""
    return ReadRemittance.model_validate(LLMRemittance.model_validate(raw).model_dump())


def read(text: str, *, brand: str, distributor: str, products: list[str], invoice_id: str, expected: Decimal,
         received: Decimal, client: anthropic.Anthropic | None = None) -> ReadResult:
    """Read one remittance. Tries live first, as the scenario box does: a brand's own remittance has no recording
    yet; the saved answer for the same text is the fallback (DEMO_MODE replays the sample)."""
    ans = claude.ask(SERVICE, system_prompt(brand, distributor, products),
                     user_message(text, invoice_id, expected, received), LLMRemittance, _typed, client,
                     live_first=True)
    return ReadResult(ans.value, ans.source, ans.attempts, ans.errors)
