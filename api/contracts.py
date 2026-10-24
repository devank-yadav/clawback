"""Clawback contracts: every object and event shape shared by the API, the agents and the web app.

This file is the source of truth (web/CLAUDE.md defers to it). Owner: Devank.

Wire conventions
- Money is Decimal in Python and a JSON number in dollars with at most 2 decimals (4120.0 means $4,120.00).
  Only api/engine/ computes amounts; everything else copies them.
- Dates are ISO strings: `date` as YYYY-MM-DD, `datetime` with a UTC offset.
- IDs are short readable strings: charges "C1".."C6" and "A1".."A2", findings "F-C1", evidence "ev-...",
  questions "Q-1", rules "rule-1" (shown as Rule #1), approvals "AP-1", disputes "D-0417", ledger posts "LP-1".
- The engine (api/engine/types.py) uses plain dataclasses with the same term params and rule conditions;
  routes map between the two. Keep param names here equal to the engine's.
- Server-sent events (GET /runs/{id}/events): each message is `id: <event.id>` plus one `data:` line holding the
  whole Event as JSON. There is no `event:` line, so EventSource.onmessage receives every type; switch on
  `type`. Reconnect with Last-Event-ID to resume after that id.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, TypeAdapter, field_validator, model_validator

CENT = Decimal("0.01")


def _to_cents(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


Money = Annotated[
    Decimal,
    AfterValidator(_to_cents),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]
Rate = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- shared vocab

Role = Literal["owner", "controller"]
Actor = Literal[
    "system", "reader", "investigator", "gate", "negotiator", "bookkeeper", "coach",
    "owner", "controller", "northmart", "policy",
]
TermType = Literal["promo_rate", "product_scope", "unit_cap", "date_range", "fee_discretion", "amendment"]
TermStatus = Literal["pending", "verified", "rejected", "disputed"]
FindingType = Literal[
    "rate_over", "duplicate", "outside_dates", "amended_by_email", "over_cap",
    "product_not_covered", "discretionary_fee", "matches_deal",
]
DecisionKind = Literal["dispute", "accept", "split", "ask", "skip"]
GateRow = Annotated[int, Field(ge=1, le=9)]  # row number in the decision-gate table, docs/design.md


# ---------------------------------------------------------------- documents and terms

DocumentKind = Literal["deal", "email", "amendment", "notice", "draft"]


class Document(Contract):
    id: str  # "spring-promo", "broker-2026-03-28"
    kind: DocumentKind
    path: str  # relative to data/, e.g. "deals/spring-promo.md"
    sender: str | None = None
    approved_sender: bool = False  # sender is in config/policy.yaml approved_amendment_senders
    signed_by_both: bool = False
    received_at: datetime | None = None
    sha256: str | None = None


class PromoRateParams(Contract):
    rate: Rate
    unit: Literal["unit"] = "unit"


class ProductScopeParams(Contract):
    products: list[str]


class UnitCapParams(Contract):
    max_units: int


class DateRangeParams(Contract):
    start: date
    end: date


class FeeDiscretionParams(Contract):
    max_fee: Money
    fee: str | None = None  # "display fee"
    per: Literal["month", "promotion"] = "month"
    requires_written_notice: bool = False


class AmendmentParams(Contract):
    """Extra units over the term's effective_from..effective_to (the broker's extension). A changed cap or
    rate is read as a new unit_cap or promo_rate term with a later effective_from instead."""

    extra_units: int


TERM_PARAMS: dict[str, type[Contract]] = {
    "promo_rate": PromoRateParams,
    "product_scope": ProductScopeParams,
    "unit_cap": UnitCapParams,
    "date_range": DateRangeParams,
    "fee_discretion": FeeDiscretionParams,
    "amendment": AmendmentParams,
}


class ReaderTerm(Contract):
    """One term as a Deal Reader returns it. `params` must match TERM_PARAMS[type]."""

    type: TermType
    params: dict[str, Any]
    effective_from: date | None = None
    effective_to: date | None = None
    exact_quote: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    discretion: bool = False
    source_doc_id: str

    @model_validator(mode="after")
    def _check_params(self) -> "ReaderTerm":
        TERM_PARAMS[self.type].model_validate(self.params)
        if self.char_end < self.char_start:
            raise ValueError("char_end is before char_start")
        return self

    def typed_params(self) -> Contract:
        return TERM_PARAMS[self.type].model_validate(self.params)


class ReaderOutput(Contract):
    """Strict JSON the Deal Reader (Claude or Gemini) must return for one document."""

    terms: list[ReaderTerm]
    unclear: list[str] = []


class Term(ReaderTerm):
    """A stored term: one row per reader, plus the merged row once both readers agree and the quote is found."""

    id: str
    reader: Literal["claude", "gemini", "merged"]
    status: TermStatus = "pending"


# ---------------------------------------------------------------- money in, data rows

class Remittance(Contract):
    id: str
    counterparty: str
    invoice_id: str | None
    expected: Money
    received: Money
    taken: Money
    charge_count: int
    received_at: datetime | None = None
    nessie_tx_id: str | None = None


class Charge(Contract):
    id: str  # "C1"
    remittance_id: str | None = None
    ref: str  # Northmart's reference, "NM-2229"
    code: str  # "PA" promotional allowance, "DF" display fee
    description: str
    product: str | None  # "Original+Chocolate", "Mint", None for fees
    units: int
    rate: Rate
    amount: Money
    period_start: date
    period_end: date
    notice_date: date | None = None  # display fees: when Northmart's written notice came

    @field_validator("product", mode="before")
    @classmethod
    def _none_product(cls, v: Any) -> Any:
        return None if isinstance(v, str) and v.strip().lower() in ("", "none") else v


class PriorPayment(Contract):
    ref: str
    paid_on: date
    promo_id: str
    product: str
    period_start: date
    period_end: date
    units: int
    amount: Money


class SalesRow(Contract):
    week_start: date
    week_end: date
    product: str
    promo_units: int
    total_units: int


class PromoPlan(Contract):
    promo_id: str
    products: list[str]
    rate: Rate
    starts: date
    ends: date
    cap: int


# ---------------------------------------------------------------- evidence ("Why?")

EvidenceKind = Literal["clause", "email", "claim", "notice", "sales", "charge", "prior_payment", "rule", "person", "approval"]


class Quote(Contract):
    """The drawer shows context_before + text (highlighted) + context_after: the sentence inside its paragraph."""

    doc_id: str
    text: str  # the exact sentence; whitespace in the source may differ (the quote check normalizes it)
    char_start: int
    char_end: int
    context_before: str = ""  # source text from the paragraph's start up to char_start, as written (line breaks kept)
    context_after: str = ""  # source text from char_end to the paragraph's end


class Evidence(Contract):
    """The source behind a number: a deal sentence, a data row, an email, a rule or a person's answer."""

    id: str
    kind: EvidenceKind
    label: str  # chip text, e.g. "§3.2 cap", "Week 1 sales"
    summary: str  # one plain sentence for the drawer
    quote: Quote | None = None
    rows: list[dict[str, str | int | float | None]] = []  # raw data rows (CSV columns as keys)
    sender: str | None = None
    approved_sender: bool | None = None
    sent_at: datetime | None = None
    rule_id: str | None = None
    approval_id: str | None = None
    person: str | None = None  # "Dana Okafor (owner)"


class MathPart(Contract):
    """One piece of the math line on a card. Parts with an evidence_id are clickable."""

    text: str
    evidence_id: str | None = None


# ---------------------------------------------------------------- agents and engine outputs

class InvestigatorOutput(Contract):
    """Strict JSON the Investigator must return. It never computes amounts."""

    charge_id: str
    finding: str
    type: FindingType
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    open_questions: list[str] = []

    @field_validator("finding")
    @classmethod
    def _short(cls, v: str) -> str:
        if len(v.split()) > 25:
            raise ValueError("finding must be 25 words or fewer")
        return v


class Finding(InvestigatorOutput):
    """Investigator output joined with the engine's numbers for that charge."""

    id: str  # "F-C1"
    expected: Money  # what the deal allows (engine)
    taken: Money
    delta: Money  # taken - expected (engine)
    readers_agree: bool = True
    math: list[MathPart] = []


class Rehearsal(Contract):
    """Negotiator, before filing: the comeback it predicts and the answer it would give."""

    charge_id: str
    predicted_rebuttal: str
    answer: str
    answer_evidence_ids: list[str]
    answered: bool  # False sends the charge to Ask instead of filing


class Decision(Contract):
    charge_id: str
    decision: DecisionKind
    disputed: Money = Decimal(0)
    accepted: Money = Decimal(0)
    waiting: Money = Decimal(0)  # amount held for a person (Ask)
    gate_row: GateRow
    rule_id: str | None = None
    decided_by: Actor
    decided_at: datetime
    reason: str  # short plain sentence for the card


# ---------------------------------------------------------------- people: questions, rules, approvals

class Question(Contract):
    id: str
    to_role: Role
    charge_id: str | None
    text: str
    channel: Literal["sms", "inbox"] = "sms"
    sent_at: datetime
    answer: str | None = None
    answered_at: datetime | None = None
    rule_id: str | None = None


class Answer(Contract):
    question_id: str
    from_role: Role
    text: str
    answered_at: datetime
    rule_id: str | None = None


class Rule(Contract):
    id: str  # "rule-1"
    label: str  # "Rule #1"
    pattern_text: str  # what Moss matches new clauses against
    term_type: TermType
    counterparty: str
    condition: str  # "<fact> <op> <number>", e.g. "notice_days >= 14" (api/engine/rules.py parses it)
    decision: Literal["accept", "dispute", "ask"]  # when the condition holds
    else_decision: Literal["accept", "dispute", "ask"]  # when it doesn't, or the fact is unknown
    summary: str  # "Accept display fees with 14+ days' notice; otherwise dispute."
    approver: str  # "Dana Okafor"
    approver_role: Role
    learned_at: datetime
    source_question_id: str | None
    status: Literal["pending", "active", "undone"] = "active"


class ApprovalLine(Contract):
    charge_id: str
    amount: Money


class Approval(Contract):
    id: str
    kind: Literal["credit_memo", "dispute_over_limit", "closed_period"]
    amount: Money
    lines: list[ApprovalLine] = []
    proposed_by: Actor
    approver_role: Role
    status: Literal["pending", "approved", "refused"]
    text: str  # what the approver was asked
    note: str | None = None  # the approver's note, shown on the card when they refuse
    requested_at: datetime
    decided_at: datetime | None = None


class ApprovalDecisionRequest(Contract):
    """POST /approvals/{id}: the controller's in-app Yes / No (the fallback for the SMS reply)."""

    approve: bool
    note: str | None = None  # shown on the card when they refuse


class ApprovalDecisionResponse(Contract):
    approval: Approval
    ledger_post: LedgerPost | None  # the credit memo that posted; None when refused (nothing posts)


# ---------------------------------------------------------------- the other side: disputes and the portal

class DisputeLine(Contract):
    charge_id: str
    ref: str
    amount: Money
    reason: str
    clause_ref: str | None  # "§3.2"
    quote: str | None
    math: str  # plain text, from the engine
    evidence_ids: list[str]


class Dispute(Contract):
    id: str  # "D-0417"
    remittance_id: str
    counterparty: str
    lines: list[DisputeLine]
    total: Money
    status: Literal["draft", "filed", "answered", "resolved", "withdrawn"]
    approved_by: Literal["policy", "owner"]
    filed_at: datetime | None


ReplyClass = Literal["new_document", "claim_without_document", "agrees", "other"]


class PortalMessage(Contract):
    id: str
    dispute_id: str
    from_party: Literal["northmart", "clawback"]
    text: str
    attachment_doc_id: str | None = None
    classification: ReplyClass | None = None  # set on Northmart messages by the Negotiator
    charge_ids: list[str] = []
    evidence_ids: list[str] = []
    created_at: datetime


class ReplyClassification(Contract):
    """Strict JSON the Negotiator returns for one portal reply."""

    classification: ReplyClass
    charge_ids: list[str]
    claim: str | None = None


# ---------------------------------------------------------------- books

class LedgerLine(Contract):
    charge_id: str | None
    description: str
    amount: Money


class LedgerPost(Contract):
    id: str
    qbo_entity: Literal["customer", "item", "invoice", "payment", "credit_memo", "invoice_note"]
    qbo_id: str | None
    qbo_url: str | None = None  # link to the record in the QuickBooks sandbox, set by the integration once posted
    amount: Money
    lines: list[LedgerLine] = []
    status: Literal["pending", "posted", "held", "failed", "voided"]
    approval_id: str | None = None
    note: str | None = None
    posted_at: datetime | None = None


# ---------------------------------------------------------------- run state

class Totals(Contract):
    """Meters. taken = disputed + accepted + waiting + undecided; a skipped charge's amount stays undecided."""

    taken: Money
    disputed: Money
    accepted: Money
    waiting: Money  # amount in Ask, waiting on a person
    undecided: Money
    questions: int  # questions asked to the owner this run
    skipped: int = 0  # charges whose deal term couldn't be verified


class RunInfo(Contract):
    run_id: str
    kind: Literal["march", "april", "scenario", "eval"]
    status: Literal["started", "waiting", "finished", "failed"]
    remittance: Remittance | None = None
    demo_mode: bool = False


class LogLine(Contract):
    text: str
    level: Literal["info", "good", "warn", "error"] = "info"
    actor: Actor = "system"
    charge_id: str | None = None


class ChargeDetail(Contract):
    """GET /charges/{id}: everything the evidence drawer shows."""

    charge: Charge
    finding: Finding | None
    decision: Decision | None
    rehearsal: Rehearsal | None
    rule: Rule | None = None  # the saved rule decision.rule_id names, for the RuleCard ("learned Oct 24, approved by Dana")
    evidence: list[Evidence]


# ---------------------------------------------------------------- events (SSE)

class _EventBase(Contract):
    id: int  # increasing per run; used as the SSE id
    run_id: str
    at: datetime


class RunEvent(_EventBase):
    type: Literal["run"]
    data: RunInfo


class LogEvent(_EventBase):
    type: Literal["log"]
    data: LogLine


class ChargeEvent(_EventBase):
    type: Literal["charge"]
    data: Charge


class FindingEvent(_EventBase):
    type: Literal["finding"]
    data: Finding


class RehearsalEvent(_EventBase):
    type: Literal["rehearsal"]
    data: Rehearsal


class DecisionEvent(_EventBase):
    type: Literal["decision"]
    data: Decision


class QuestionEvent(_EventBase):
    type: Literal["question"]
    data: Question


class AnswerEvent(_EventBase):
    type: Literal["answer"]
    data: Answer


class RuleEvent(_EventBase):
    type: Literal["rule"]
    data: Rule


class ApprovalEvent(_EventBase):
    type: Literal["approval"]
    data: Approval


class DisputeEvent(_EventBase):
    type: Literal["dispute"]
    data: Dispute


class PortalMessageEvent(_EventBase):
    type: Literal["portal_message"]
    data: PortalMessage


class LedgerPostEvent(_EventBase):
    type: Literal["ledger_post"]
    data: LedgerPost


class TotalsEvent(_EventBase):
    type: Literal["totals"]
    data: Totals


Event = Annotated[
    Union[
        RunEvent, LogEvent, ChargeEvent, FindingEvent, RehearsalEvent, DecisionEvent, QuestionEvent,
        AnswerEvent, RuleEvent, ApprovalEvent, DisputeEvent, PortalMessageEvent, LedgerPostEvent, TotalsEvent,
    ],
    Field(discriminator="type"),
]
EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)
EVENT_TYPES = (
    "run", "log", "charge", "finding", "rehearsal", "decision", "question", "answer", "rule",
    "approval", "dispute", "portal_message", "ledger_post", "totals",
)


class RunFixture(Contract):
    """web/fixtures/run-events.json and april-events.json: one recorded run plus what its drawer reads."""

    run_id: str
    events: list[Event]
    charges: dict[str, ChargeDetail]  # what GET /charges/{id} returns
    evidence: dict[str, Evidence]  # what GET /evidence/{id} returns


# ---------------------------------------------------------------- other endpoints

class StartRunRequest(Contract):
    remittance_id: str | None = None
    kind: Literal["march", "april"] = "march"


class StartRunResponse(Contract):
    run_id: str
    events_url: str


class AnswerRequest(Contract):
    text: str
    from_role: Role = "owner"


class AnswerResponse(Contract):
    answer: Answer
    rule: Rule | None


class PortalReplyRequest(Contract):
    text: str
    attachment_doc_id: str | None = None  # "amendment-1" when the judge attaches the signed amendment


class ScenarioCharge(Contract):
    description: str
    amount: Money
    units: int | None = None
    rate: Rate | None = None
    period_start: date | None = None
    period_end: date | None = None


class ScenarioRequest(Contract):
    clause: str
    charge: ScenarioCharge


class ScenarioResponse(Contract):
    stub: bool = False
    decision: Decision | None
    finding: Finding | None
    evidence: list[Evidence]
    message: str | None = None


class Redline(Contract):
    clause_ref: str
    original_quote: str
    suggested_text: str
    reason: str
    dollars_at_stake: Money
    finding_ids: list[str]


class CoachResponse(Contract):
    draft_doc_id: str
    redlines: list[Redline]


class EvalReport(Contract):
    status: Literal["not_run", "running", "done"]
    run_at: datetime | None = None
    cases: int
    correct: int | None = None
    amounts_correct: int | None = None
    asked: int | None = None
    wrong_automatic: int | None = None
    unnecessary_questions: int | None = None


class AuditEntry(Contract):
    """One audit_log row as api/engine/audit_chain.py writes it (the hash covers `at` as this exact string)."""

    id: int
    at: str
    actor: str  # "gate", "owner:Dana", "controller:Sam"
    action: str
    object_ref: str
    evidence: dict[str, Any] = {}
    prev_hash: str
    hash: str


class AuditVerify(Contract):
    ok: bool
    checked: int
    broken_at: int | None = None  # id of the first bad row
    reason: str = ""


class Summary(Contract):
    """GET /summary for the Fetch.ai agent (read-only)."""

    totals: Totals
    open_disputes: list[Dispute]
    pending_question: Question | None
