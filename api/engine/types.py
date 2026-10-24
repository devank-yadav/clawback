"""Plain dataclasses the engine works on. api/contracts.py maps onto these; the engine never imports Pydantic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

CENT = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Decimal dollars rounded to the cent. Floats go through str() so 0.1 stays 0.1."""
    if isinstance(value, float):
        value = str(value)
    return Decimal(value).quantize(CENT)


class TermType(StrEnum):
    PROMO_RATE = "promo_rate"
    PRODUCT_SCOPE = "product_scope"
    UNIT_CAP = "unit_cap"
    DATE_RANGE = "date_range"
    FEE_DISCRETION = "fee_discretion"
    AMENDMENT = "amendment"
    FEE_SCHEDULE = "fee_schedule"
    DISPUTE_WINDOW = "dispute_window"
    NOTICE_PERIOD = "notice_period"


class TermStatus(StrEnum):
    VERIFIED = "verified"
    REJECTED = "rejected"  # quote not found in the source
    DISPUTED = "disputed"  # the two readers disagree


class DecisionKind(StrEnum):
    DISPUTE = "dispute"
    ACCEPT = "accept"
    SPLIT = "split"
    ASK = "ask"
    SKIP = "skip"


@dataclass(frozen=True)
class Term:
    """A merged, checked deal term. Params by type:
    promo_rate {"rate"} · product_scope {"products"} · unit_cap {"max_units"} · date_range {"start", "end"}
    · fee_discretion {"max_fee"} · amendment {"extra_units"} over effective_from..effective_to
    · fee_schedule {"fee_code", "basis", "rate", "min", "max", "per", "tiers", "requires_proof"} (see allowed.py,
    "Fee schedules") · dispute_window {"days", "from"} · notice_period {"days"}.
    noticed_on: when the other side gave notice of the document that states this term (a policy change); a change
    applies no earlier than noticed_on + the deal's notice_period days.
    """

    id: str
    type: TermType
    params: Mapping[str, Any] = field(default_factory=dict)
    exact_quote: str = ""
    effective_from: date | None = None
    effective_to: date | None = None
    discretion: bool = False
    status: TermStatus = TermStatus.VERIFIED
    source_doc_id: str = ""
    # False for anything from a sender not on the approved list: a claim, never applied.
    source_approved: bool = True
    noticed_on: date | None = None


@dataclass(frozen=True)
class Charge:
    id: str
    ref: str
    code: str  # PA promotional allowance, DF display fee, SH shortage, PR price mismatch, SP spoilage
    description: str
    products: tuple[str, ...]
    units: int
    rate: Decimal
    amount: Decimal
    period_start: date
    period_end: date
    counterparty: str = "Northmart"
    notice_date: date | None = None  # display fees only
    line_ref: str | None = None  # SH / PR: the delivery line the charge points to
    deducted_on: date | None = None  # when the money was taken; the dispute window counts from here


@dataclass(frozen=True)
class SalesWeek:
    week_start: date
    week_end: date
    product: str
    promo_units: int
    total_units: int = 0


@dataclass(frozen=True)
class PriorPayment:
    ref: str
    paid_on: date
    promo_id: str
    products: tuple[str, ...]
    period_start: date
    period_end: date
    units: int
    amount: Decimal


@dataclass(frozen=True)
class Delivery:
    """One proof-of-delivery line: units shipped, units the store signed for, and the unit price invoiced."""

    line_ref: str
    product: str
    shipped_units: int
    received_units: int
    unit_price: Decimal
    received_by: str = ""
    received_at: date | None = None


@dataclass(frozen=True)
class AgreedPrice:
    """One row of the agreed price list. effective_to None: still in effect."""

    product: str
    agreed_price: Decimal
    effective_from: date
    effective_to: date | None = None
    source_doc: str = ""


@dataclass(frozen=True)
class OpsTerm:
    """An operations term from the deal, e.g. spoils_allowance_pct = "1.0". REJECTED when its quote isn't found word for
    word in source_doc: the engine then treats it as missing."""

    key: str
    value: str
    source_doc: str = ""
    quote: str = ""
    status: TermStatus = TermStatus.VERIFIED


@dataclass(frozen=True)
class OpsData:
    """An account's operations records, for SH, PR and SP charges."""

    deliveries: tuple[Delivery, ...] = ()
    prices: tuple[AgreedPrice, ...] = ()
    terms: tuple[OpsTerm, ...] = ()


@dataclass(frozen=True)
class FeeLine:
    """One line of the other side's backup for a fee charge, keyed by the charge's ref (deduction_ref).
    base_amount is what a percent fee is taken on (the MCB amount, a retailer invoice's total, landed cost);
    pass_through is cost charged on at cost beside the fee (landed cost of goods credited to a retailer);
    group is the invoice, PO or incident the fee's min and max apply to; on is the purchase/invoice date the fee
    schedule in effect is picked by; days drives tiers (days late, say); proof_doc names the backup document."""

    deduction_ref: str
    on: date
    group: str = ""
    base_amount: Decimal = Decimal(0)
    pass_through: Decimal = Decimal(0)
    units: int = 0
    cartons: int = 0
    days: int | None = None
    proof_doc: str = ""
    description: str = ""


@dataclass(frozen=True)
class FeeData:
    """An account's fee backup and dates, for charges priced by a fee_schedule term.
    codes maps a charge code to the fee_code the deal uses ("MCBF" -> "MCB"); a code equal to the fee_code needs
    no entry. proof_docs are the documents that exist; a requires_proof line whose proof_doc isn't one is unproven.
    as_of is the day the dispute would be filed; invoice_date is for a dispute_window counted from the invoice."""

    lines: tuple[FeeLine, ...] = ()
    codes: Mapping[str, str] = field(default_factory=dict)
    proof_docs: frozenset[str] = frozenset()
    as_of: date | None = None
    invoice_date: date | None = None


@dataclass(frozen=True)
class Rule:
    """An owner answer turned into a rule. condition is "<fact> <op> <number>", e.g. "notice_days >= 14";
    decision applies when it holds, else_decision when it doesn't (or the fact is unknown)."""

    id: str
    pattern_text: str
    term_type: TermType
    counterparty: str
    condition: str
    decision: DecisionKind
    else_decision: DecisionKind
    approver: str = "owner"
    learned_at: date | None = None
    source_question_id: str = ""
    status: str = "active"  # active · pending · undone
    label: str = ""  # "Rule #1", for reasons people read; id when empty


@dataclass(frozen=True)
class RuleMatch:
    """A saved rule Moss found for a clause's wording (F16): its id and how similar the wording is, 0 to 1."""

    rule_id: str
    similarity: Decimal


@dataclass(frozen=True)
class Policy:
    auto_dispute_limit: Decimal
    controller_approval_over: Decimal
    confidence_floor: Decimal
    match_tolerance: Decimal
    rule_match_similarity: Decimal
    reminder_after_minutes: int
    discretion_words: tuple[str, ...]
    approved_amendment_senders: tuple[str, ...]
    dispute_window_warn_days: int = 14  # this close to the end of a dispute window, the reason says "file by"


@dataclass(frozen=True)
class Finding:
    """The Investigator's output plus the Negotiator's rehearsal result, as the gate needs them."""

    charge_id: str
    confidence: Decimal
    evidence_ids: tuple[str, ...] = ()
    independent_sources: int = 0
    comeback_answered: bool = False
    type: str = ""
    finding: str = ""


@dataclass(frozen=True)
class Allowance:
    """What allowed.py works out for one charge."""

    charge_id: str
    taken: Decimal
    allowed: Decimal
    delta: Decimal  # taken - allowed
    covered_units: int = 0
    terms: tuple[Term, ...] = ()  # every term the amount depends on
    missing: tuple[str, ...] = ()  # required terms not found; the gate sends these to Ask
    facts: Mapping[str, Any] = field(default_factory=dict)  # e.g. notice_days, for rules; line_refs for SH / PR / SP
    steps: tuple[str, ...] = ()  # plain-English trail for the evidence card
    # The part of `allowed` that doesn't depend on a discretion clause (landed cost under a discretionary admin fee).
    # None: all of it does (a display fee), so a rule that disputes the fee disputes the whole charge.
    firm: Decimal | None = None


@dataclass(frozen=True)
class Decision:
    charge_id: str
    kind: DecisionKind
    disputed: Decimal
    accepted: Decimal
    gate_row: int
    rule_id: str | None = None
    reason: str = ""
    rule_similarity: Decimal | None = None  # the Moss match that picked rule_id; None when the exact match did


@dataclass(frozen=True)
class Totals:
    disputed: Decimal
    accepted: Decimal
    questions: int
    skipped: int
