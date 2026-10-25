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

from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, TypeAdapter, field_validator, model_serializer,
    model_validator,
)

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

def _one_admin(v: Any) -> Any:
    """One person, the admin (the brand's owner), decides everything; events saved before that said "controller"."""
    return "owner" if v == "controller" else v


Role = Annotated[Literal["owner"], BeforeValidator(_one_admin)]  # the admin: answers questions, approves memos
Actor = Annotated[Literal[
    "system", "reader", "investigator", "gate", "negotiator", "bookkeeper", "coach",
    "owner", "northmart", "policy",
], BeforeValidator(_one_admin)]
TermType = Literal["promo_rate", "product_scope", "unit_cap", "date_range", "fee_discretion", "amendment",
                   "fee_schedule", "dispute_window", "notice_period", "quantity_variance"]
TermStatus = Literal["pending", "verified", "rejected", "disputed"]
FindingType = Literal[
    "rate_over", "duplicate", "outside_dates", "amended_by_email", "over_cap",
    "product_not_covered", "discretionary_fee", "matches_deal",
    # operations charges (SH shortage, PR price mismatch, SP spoilage), from api/agents/investigator_ops.py
    "shortage_not_supported", "shortage_confirmed", "price_mismatch", "price_matches",
    "spoilage_over_allowance", "spoilage_within_allowance",
]
DecisionKind = Literal["dispute", "accept", "split", "ask", "skip"]
GateRow = Annotated[int, Field(ge=1, le=10)]  # row in the decision-gate table, docs/design.md (10: api/engine/gate.py)


# ---------------------------------------------------------------- documents and terms

DocumentKind = Literal["deal", "email", "amendment", "notice", "draft"]


class Document(Contract):
    id: str  # "spring-promo", "broker-2026-03-28"
    kind: DocumentKind
    path: str  # relative to data/, e.g. "accounts/peak-bar/deals/spring-promo.md"
    sender: str | None = None
    approved_sender: bool = False  # sender is in its account's approved_senders (data/accounts/<id>/account.yaml)
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


class FeeTier(Contract):
    """One band of a tiered fee: rate applies when the backup line's days fall in from_days..to_days (to_days None:
    and up). "5% if 0-7 days late, 10% if 8-14" is two tiers."""

    from_days: int
    to_days: int | None = None
    rate: Rate


class FeeScheduleParams(Contract):
    """How a fee is priced (api/engine/allowed.py, "Fee schedules"). rate is a percent for basis percent ("5" is
    5%) and annual_percent ("12" is 12% a year, for the backup line's days), else dollars per unit / carton / PO, or
    the flat fee; as_assessed is an amount the other side sets (a fine at its discretion), so it has no rate. min and
    max clamp each `per` group's fee."""

    fee_code: str  # the fee's name as the deal writes it: its defined abbreviation ("MCB") or its heading
    basis: Literal["percent", "per_unit", "per_po", "per_carton", "flat", "annual_percent", "as_assessed"]
    rate: Rate | None = None  # None only with tiers, or for as_assessed
    min: Money | None = None
    max: Money | None = None
    per: Literal["invoice", "po", "incident", "month"] = "incident"
    tiers: list[FeeTier] | None = None
    requires_proof: bool = False  # the deal says backup comes with the fee; without it the gate asks
    applies_to: str | None = None  # the only kind of purchase order the fee applies to ("new store"), else all
    requires_fault: bool = False  # a remedy for the supplier's own failure: not owed when the other side caused it
    add_on: bool = False  # charged in addition to every other fee for the same incident (an admin fee per PO)

    @model_validator(mode="after")
    def _rate_or_tiers(self) -> "FeeScheduleParams":
        if self.rate is None and not self.tiers and self.basis != "as_assessed":
            raise ValueError("a fee schedule needs a rate or tiers")
        return self


class DisputeWindowParams(Contract):
    """Disputes are due within `days` of the deduction or of the invoice."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    days: int
    from_: Literal["deduction", "invoice"] = Field("deduction", alias="from")


class NoticePeriodParams(Contract):
    """A change to the terms needs `days` of notice; it applies only to purchases on or after its effective date,
    and no sooner than `days` after the notice."""

    days: int


class QuantityVarianceParams(Contract):
    """The buyer may accept a delivery up to `pct` percent over or short of the order, at its discretion: a quantity
    fee on a delivery within it depends on that discretion."""

    pct: Rate


TERM_PARAMS: dict[str, type[Contract]] = {
    "promo_rate": PromoRateParams,
    "product_scope": ProductScopeParams,
    "unit_cap": UnitCapParams,
    "date_range": DateRangeParams,
    "fee_discretion": FeeDiscretionParams,
    "amendment": AmendmentParams,
    "fee_schedule": FeeScheduleParams,
    "dispute_window": DisputeWindowParams,
    "notice_period": NoticePeriodParams,
    "quantity_variance": QuantityVarianceParams,
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
    reader: Literal["claude", "gemini", "claude-b", "merged"]
    status: TermStatus = "pending"
    source_approved: bool = True  # False: the sender can't change the deal, so the term is a claim, never applied
    reasons: list[str] = []  # why the code check rejected or disputed it


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
    code: str  # "PA" promotional allowance, "DF" display fee, "SH" shortage, "PR" price mismatch, "SP" spoilage
    description: str
    product: str | None  # "Original+Chocolate", "Mint", None for fees
    units: int
    rate: Rate
    amount: Money
    period_start: date
    period_end: date
    notice_date: date | None = None  # display fees: when Northmart's written notice came
    line_ref: str | None = None  # SH / PR: the delivery line (DeliveryRow.line_ref) the charge points to
    deducted_on: date | None = None  # when the money was taken; a deal's dispute_window counts from here

    @field_validator("product", mode="before")
    @classmethod
    def _none_product(cls, v: Any) -> Any:
        return None if isinstance(v, str) and v.strip().lower() in ("", "none") else v

    @field_validator("line_ref", "deducted_on", mode="before")
    @classmethod
    def _none_line_ref(cls, v: Any) -> Any:
        return None if isinstance(v, str) and not v.strip() else v

    @model_serializer(mode="wrap")
    def _drop_empty_line_ref(self, handler):
        """A charge with no line_ref (or deducted_on) serializes exactly as before the field existed: charge rows
        reach the agents' requests, and so the DEMO_MODE fixture keys (api/integrations/replay.py)."""
        out = handler(self)
        if isinstance(out, dict):
            for name in ("line_ref", "deducted_on"):
                if getattr(self, name) is None:
                    out.pop(name, None)
        return out


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

EvidenceKind = Literal[
    "clause", "email", "claim", "notice", "sales", "charge", "prior_payment", "rule", "person", "approval",
    "delivery", "price", "policy",  # operations: proof of delivery, the agreed price list, ops terms (see "ops data")
    "backup",  # the other side's backup for a fee charge (see "fee data")
]


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
    closed_at: datetime | None = None  # a newer run of the same payment replaced this one; answer that run's question


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


class AutoPost(Contract):
    """The admin's standing yes: fair-charge credit memos up to `limit` post without asking (set by ticking "Post fair
    charges like these automatically from now on" when approving `approval_id`)."""

    limit: Money
    set_by: str  # "Dana Okafor"
    approval_id: str  # the memo the admin approved when setting it
    set_at: datetime


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
    sets_auto_post: AutoPost | None = None  # the admin approved this one and said to post ones like it from now on
    posted_by_auto_post: AutoPost | None = None  # posted without asking, by this standing yes (no one was asked)


class ApprovalDecisionRequest(Contract):
    """POST /approvals/{id}: the admin's in-app Yes / No (the fallback for the SMS reply)."""

    approve: bool
    note: str | None = None  # shown on the card when they refuse
    auto_post: bool = False  # with approve: fair-charge memos up to this one's amount post without asking from now on


class ApprovalDecisionResponse(Contract):
    approval: Approval
    ledger_post: LedgerPost | None  # the credit memo that posted; None when refused (nothing posts)
    ledger_posts: list[LedgerPost] = []  # everything that posted: the memo and the invoice's open-balance note


class InboxResponse(Contract):
    """GET /inbox: what waits on a person, for the in-app fallback to the texts."""

    questions: list[Question]  # open owner questions
    approvals: list[Approval]  # credit memos waiting on the admin
    messages: list[OwnerMessage] = []  # run summaries for the owner, newest first (the text's in-app copy)


class OwnerMessage(Contract):
    """The one text a run sends the owner once the gate has decided every charge it can."""

    id: str  # "MSG-<run id>"
    run_id: str
    account_id: str
    to_role: Literal["owner"] = "owner"
    text: str
    channel: Literal["sms", "inbox"]  # sms: the text went out; inbox: it waits here only
    sent_at: datetime


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
    # The distributor's dispute window (api/lookback.py): the last day to file this line, and days left from the
    # account's payment date. None on a line from before these were added.
    file_by: date | None = None
    days_left: int | None = None


class Dispute(Contract):
    id: str  # "D-0417"
    remittance_id: str
    counterparty: str
    lines: list[DisputeLine]
    total: Money
    # ready_to_send: drafted, waiting for the admin's "Review and send" (POST /disputes/{id}/send), which files it;
    # draft: an older run's over-limit dispute (still sendable the same way); filed: sent to the distributor.
    status: Literal["ready_to_send", "draft", "filed", "answered", "resolved", "withdrawn"]
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
    channel: Literal["portal", "email"] = "portal"  # where it was said: the portal, or an email (Phase E)
    email_message_id: str | None = None  # the email's Message-Id, for one that came or went by email


class DisputeEmail(Contract):
    """One email about a dispute (Phase E): the dispute email itself, or a reply to the distributor.

    held: the drafter's checks failed twice, or the admin's edit failed the outbound filter; the admin edits it.
    ready: checked, waiting for the admin to send. sent: Mailgun took it. outbox: recorded in the app instead of sent
    (no Mailgun keys, or DEMO_MODE). failed: Mailgun refused it; sending again retries."""

    id: str  # "EM-<run id>-D-0417" for the dispute email; "-R<n>" for a reply
    kind: Literal["dispute", "reply"]
    run_id: str
    account_id: str
    dispute_id: str
    to: str
    from_addr: str
    reply_to: str | None = None
    subject: str
    body: str
    attachments: list[str] = []
    in_reply_to: str | None = None
    status: Literal["held", "ready", "sent", "outbox", "failed"]
    written_by: Literal["claude", "template", "admin", "negotiator", "code"]
    problems: list[str] = []
    message_id: str | None = None
    sent_at: datetime | None = None
    detail: str | None = None  # how the send went ("Queued. Thank you.", "in the outbox (DEMO_MODE)", the error)
    portal_url: str | None = None
    charge_ids: list[str] = []
    evidence_ids: list[str] = []
    replying_to: str | None = None  # the distributor's message (PortalMessage id) a reply answers


class DisputeEmailEdit(Contract):
    """PUT /disputes/{id}/email: the admin's edit. Checked by the outbound filter before it's saved as ready."""

    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(max_length=20000)


class DisputeSendRequest(Contract):
    """POST /disputes/{id}/send and POST /disputes/{id}/replies/{email_id}/send: optionally the edit to send."""

    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)


class DisputeThread(Contract):
    """GET /disputes/{id}/thread: the dispute as it stands, every message on it (portal and email), and its emails."""

    dispute: Dispute
    run_id: str
    messages: list[PortalMessage]
    emails: list[DisputeEmail]


class DisputeSendResponse(Contract):
    """POST /disputes/{id}/send: the dispute (filed once the email went) and its email (sent, outbox or failed)."""

    dispute: Dispute
    email: DisputeEmail


class SupplierNotification(Contract):
    """GET /notifications: something the supplier should know, e.g. a distributor replied to a dispute."""

    id: str
    account_id: str
    run_id: str | None = None
    dispute_id: str | None = None
    text: str
    at: datetime


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
    value: RunValue | None = None  # set from the end of the gate's first pass on, so the final totals event has it


class RunValue(Contract):
    """What the run was worth (api/engine/value.py): the money it sorted, how fast, the AI it used, and the manual
    time it stands in for. Never computed by an AI."""

    disputed: Money
    accepted: Money
    questions: int
    charges: int
    seconds_to_decided: float | None  # the run's first event to the end of the gate's first pass
    ai_calls: int  # Claude and Gemini calls in the run's trace (a recorded answer counts too)
    ai_cost_usd: float | None  # the live calls at config/pricing.yaml prices (0 when all were recorded); None: unpriced
    manual_minutes: float | None  # charges x manual_minutes_per_charge; None while config/policy.yaml sets none
    manual_minutes_per_charge: float | None


class RunInfo(Contract):
    run_id: str
    kind: str  # an account month ("march", "april": Account.months in api/accounts.py), "scenario" or "eval"
    status: Literal["started", "waiting", "finished", "failed"]
    remittance: Remittance | None = None
    demo_mode: bool = False


class StageInfo(Contract):
    """A step of the run the board draws as a progress bar: reading the deal (a tick per document) and checking the
    charges (a tick per charge). The other steps have their own events (dispute, question, approval, ledger_post).
    Board-only: no agent sees it, so recorded requests don't change."""

    stage: Literal["read", "check"]
    status: Literal["started", "progress", "done"]
    done: int = 0  # documents read / charges decided so far
    total: int = 0
    label: str = ""  # what's happening now ("Reading the signed deal") or what just finished
    charge_id: str | None = None  # check: the charge being worked on
    items: list[str] = Field(default_factory=list)  # read: the quotes both readers agreed on, found word for word


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


class StageEvent(_EventBase):
    type: Literal["stage"]
    data: StageInfo


Event = Annotated[
    Union[
        RunEvent, LogEvent, ChargeEvent, FindingEvent, RehearsalEvent, DecisionEvent, QuestionEvent,
        AnswerEvent, RuleEvent, ApprovalEvent, DisputeEvent, PortalMessageEvent, LedgerPostEvent, TotalsEvent,
        StageEvent,
    ],
    Field(discriminator="type"),
]
EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)
EVENT_TYPES = (
    "run", "log", "charge", "finding", "rehearsal", "decision", "question", "answer", "rule",
    "approval", "dispute", "portal_message", "ledger_post", "totals", "stage",
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
    kind: str | None = None  # one of the account's months; None: its invoice month (Peak Bar: "march")
    account: str = "peak-bar"
    fixture: bool = False  # replay the recorded fake run (web/fixtures) instead of running the pipeline


class StartRunResponse(Contract):
    run_id: str
    events_url: str


class AnswerRequest(Contract):
    text: str
    from_role: Role = "owner"
    save_rule: bool = True  # False: settle this charge only; no rule is saved, so the next one like it asks again


class AnswerResponse(Contract):
    answer: Answer
    rule: Rule | None


class PortalReplyRequest(Contract):
    text: str
    attachment_doc_id: str | None = None  # "amendment-1" when the judge attaches the signed amendment


class PortalPreset(Contract):
    """GET /portal/presets: the replies the judge can pick on the Northmart portal."""

    id: str
    label: str  # button text
    text: str
    attachment_doc_id: str | None = None
    expect: ReplyClass  # how the Negotiator should read it (the acceptance test checks this)
    charge_ids: list[str] = []


class ScenarioCharge(Contract):
    description: str
    amount: Money
    code: Literal["PA", "DF"] | None = None  # promo allowance or display fee; guessed from units and rate if left out
    product: str | None = None  # "Original+Chocolate", "Mint"; promo charges default to the deal's two products
    units: int | None = None
    rate: Rate | None = None
    period_start: date | None = None  # defaults to the Spring promo month, Mar 1 to Mar 31, 2026
    period_end: date | None = None
    notice_date: date | None = None  # fees: when written notice came


class ScenarioRequest(Contract):
    clause: str  # replaces the matching part of the Spring deal for this one charge
    charge: ScenarioCharge


class ScenarioResponse(Contract):
    stub: bool = False
    decision: Decision | None
    finding: Finding | None
    evidence: list[Evidence]
    message: str | None = None
    terms: list[Term] = []  # what the clause said, each verified or rejected word for word
    rehearsal: Rehearsal | None = None
    rule: Rule | None = None  # a saved owner rule that decided it
    unclear: list[str] = []


class ScenarioExample(Contract):
    """GET /scenario/examples: ready-made cases for the scenario box (recorded, so they work offline)."""

    id: str
    label: str
    request: ScenarioRequest


class Redline(Contract):
    clause_ref: str
    original_quote: str
    suggested_text: str
    reason: str
    dollars_at_stake: Money  # the cited findings' costs, added up by code
    finding_ids: list[str]
    quote: Quote | None = None  # where original_quote sits in the draft, for striking it through in place


class CoachResponse(Contract):
    draft_doc_id: str
    redlines: list[Redline]


class EvalReport(Contract):
    status: Literal["not_run", "running", "done"]
    mode: Literal["engine", "agent"] | None = None  # engine: math and gate alone; agent: readers and agents in the loop
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
    actor: str  # "gate", "owner:Dana", "auto_post:Dana"
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
    pending_approvals: list[Approval] = []
    run_id: str | None = None  # the live run it describes; None: the recorded fake run


class PaymentResponse(Contract):
    """POST /payments/{account} (POST /payments/northmart is Peak Bar's): the payment screen's "Northmart pays"
    button."""

    via: Literal["nessie", "direct"]  # nessie: a real sandbox deposit was posted; direct: no Nessie, run started
    deposit_id: str | None
    run_id: str | None  # None while the poller hasn't seen the deposit yet: GET /runs/latest gives it
    message: str


# ---- ops data
# Operations records per account, for shortage (SH), price mismatch (PR) and spoilage (SP) charges. One model per
# CSV, columns as named: deliveries/pod.csv, pricing/price-list.csv, terms/ops-terms.csv. The engine reads them as
# api/engine/types.py OpsData (adapters.to_engine_ops); api/evidence.py turns them into "delivery", "price" and
# "policy" evidence.

def _blank_none(v: Any) -> Any:
    return None if isinstance(v, str) and not v.strip() else v


class DeliveryRow(Contract):
    """One proof-of-delivery line: what was shipped, what the store signed for, and the unit price invoiced."""

    line_ref: str  # "L-1001"; SH and PR charges point here with Charge.line_ref
    product: str
    shipped_units: int
    received_units: int
    unit_price: Rate  # the price invoiced per unit
    received_by: str | None = None  # who signed the delivery
    received_at: date | datetime | None = None  # a date, or a datetime with its offset

    @field_validator("received_by", "received_at", mode="before")
    @classmethod
    def _blank(cls, v: Any) -> Any:
        return _blank_none(v)


class PriceRow(Contract):
    """One row of the agreed price list: the price per unit for a product over a span of dates."""

    product: str
    agreed_price: Rate
    effective_from: date
    effective_to: date | None = None  # None: still in effect
    source_doc: str | None = None  # the document id the price comes from

    @field_validator("effective_to", "source_doc", mode="before")
    @classmethod
    def _blank(cls, v: Any) -> Any:
        return _blank_none(v)


class OpsTerm(Contract):
    """An operations term from a deal, e.g. key spoils_allowance_pct, value "1.0". It counts only when `quote` is found
    word for word in `source_doc` (a document id) and states the value; otherwise it's rejected, like a deal term."""

    key: str
    value: str
    source_doc: str
    quote: str

    @field_validator("value", mode="before")
    @classmethod
    def _text(cls, v: Any) -> Any:
        return str(v) if isinstance(v, (int, float, Decimal)) else v


# ---- accounts

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")


class Colors(Contract):
    primary: str  # "#b4462b"
    accent: str


class Person(Contract):
    name: str  # "Dana Okafor"; texts and the log use the first name
    email: str | None = None


class Brand(Contract):
    name: str  # "Peak Bar Co."
    kind: str  # "snack brand": the Deal Coach's prompt calls it "a small snack brand"
    city: str
    initials: str
    colors: Colors
    owner: Person  # the admin: answers the questions, approves credit memos, set the policy once
    controller: Person | None = None  # older account files name one; unused (the owner decides everything)


class Distributor(Contract):
    name: str  # "Northmart": the counterparty on charges, disputes and rules
    desk_email: str
    portal_name: str
    colors: Colors


class AccountInvoice(Contract):
    """The invoice the account's payment arrives for, and that payment (the remittance)."""

    id: str  # "INV-3102"
    expected: Money
    received: Money
    month: str  # lowercase month name, "march": its charges are charges/march.csv and its run's kind
    period_start: date
    period_end: date

    @field_validator("month")
    @classmethod
    def _month(cls, v: str) -> str:
        if v not in MONTHS:
            raise ValueError(f"month must be a lowercase month name ({', '.join(MONTHS)})")
        return v


class QboLine(Contract):
    item: str
    qty: int
    unit_price: Rate


class QboConfig(Contract):
    customer: str  # the customer in the one QuickBooks sandbox company
    invoice_no: str  # the invoice's DocNumber there
    lines: list[QboLine] = []  # optional: the invoice's lines; without them the seed writes one line for the total
    payment_date: date | None = None  # optional: the payment's date; the seed defaults to 20 days after period_end


class AccountConfig(Contract):
    """data/accounts/<id>/account.yaml. api/accounts.py loads and checks every one (ids, documents, invoices and
    dispute numbers must not clash across accounts)."""

    id: str  # the folder name, "peak-bar"
    supplier: str | None = None  # the supplier workspace it belongs to: the brand's account id, "peak-bar"
    brand: Brand
    distributor: Distributor
    invoice: AccountInvoice
    deal_docs: list[str] = Field(min_length=1)  # document ids, the signed deal first, then emails that may change it
    # Real contracts this account's deal is, under data/contracts/ (file names, read unedited); each is a document
    # whose id is its stem, e.g. KeHE's vendor policies for Lantern Hill.
    contracts: list[str] = []
    # The supplier (the user's brand workspace) this distributor relationship belongs to; one supplier tracks many
    # distributors. Unset: the account is its own supplier.
    supplier: str | None = None
    approved_senders: list[str]  # only these (or a document signed by both parties) can change the deal
    dispute_start: int = Field(ge=1)  # the invoice month files D-<start>; each later month starts 10 higher
    qbo: QboConfig
    nessie_description: str  # the Nessie deposit's description; the poller starts this account's run on it

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v or not all(c.islower() or c.isdigit() or c == "-" for c in v) or v[0] == "-":
            raise ValueError("id must be lowercase letters, digits and hyphens")
        return v

    @field_validator("approved_senders")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [s.strip().lower() for s in v]


class AccountListItem(Contract):
    """GET /accounts: one row per account."""

    id: str
    brand: Brand
    distributor: Distributor
    invoice: AccountInvoice
    latest_run_id: str | None  # the newest run of the invoice month (live, or saved before a restart)
    supplier: str = ""  # the supplier workspace this relationship belongs to (AccountConfig.supplier or its own id)


class AccountKpis(Contract):
    invoiced_6m: Money
    collected_6m: Money
    deducted_6m: Money
    recovered_6m: Money
    recovery_rate: float  # recovered_6m / deducted_6m, 0 to 1 (4 places); 0 when nothing was deducted
    open_disputes: int  # deductions still in dispute: history rows with an open outcome, plus this run's lines
    open_balance: Money  # still owed: open history deductions not yet recovered, plus the current invoice's balance
    wrongly_taken_6m: Money  # the lookback (api/lookback.py): past deductions the math says were wrongly taken
    lost_past_window: Money  # of those, still owed but the dispute window closed
    claimable_now: Money  # of those, still owed and still claimable (in dispute, or inside the window)


class MonthTotals(Contract):
    month: str  # "2026-03"
    invoiced: Money
    paid: Money
    deducted: Money
    recovered: Money


class DeductionTypeTotal(Contract):
    code: str  # PA, DF, SH, PR, SP
    label: str  # "Promotional allowance"
    count: int
    amount: Money


class RemittanceRow(Contract):
    date: date
    invoice: str
    paid: Money
    deducted: Money


class CurrentPayment(Contract):
    """The account's invoice and its payment (account.yaml), and the run deciding it, if one has started."""

    invoice: str
    expected: Money
    received: Money
    deducted: Money  # expected - received
    run_id: str | None
    status: Literal["waiting_for_payment", "started", "waiting", "finished", "failed"]
    value: RunValue | None = None  # the run's value, once the gate's first pass is done


LookbackStatus = Literal["claimable", "past_window", "settled", "fair", "not_checked"]


class LookbackRow(Contract):
    """One past deduction run through the engine (api/engine/lookback.py)."""

    ref: str
    month: str  # "2026-02"
    code: str
    description: str
    taken: Money
    allowed: Money | None  # None: not checked (DF needs the deal read; or the row lacks what its check needs)
    wrongly_taken: Money  # taken - allowed when over the $1 match tolerance, else 0
    outcome: str  # as history/deductions.csv says: accepted, written_off, recovered, open...
    recovered: Money
    deducted_on: date | None
    file_by: date | None  # deducted_on (else its month's last day) + the dispute window; None unless still owed
    days_left: int | None  # file_by - as_of; below zero once the window closed
    status: LookbackStatus
    note: str  # the engine's math in plain words, or why the row wasn't checked


class LookbackTotals(Contract):
    wrongly_taken: Money
    lost_past_window: Money  # still owed (wrongly_taken - recovered) on past_window rows
    claimable_now: Money  # still owed on claimable rows
    checked: int
    not_checked: int


class Lookback(Contract):
    """GET /accounts/{id}/lookback: the six-month window's past deductions checked by code, never by AI."""

    account_id: str
    as_of: date  # the account's payment date (qbo.payment_date, else invoice.period_end + 20 days)
    dispute_window_days: int  # terms/ops-terms.csv dispute_window_days (quote checked), else policy default_dispute_days
    rows: list[LookbackRow]  # in deduction order
    totals: LookbackTotals


class AccountOverview(Contract):
    """GET /accounts/{id}/overview, computed by code (api/overview.py) from history/ and the current run, never by AI.

    The window is the six months ending with the invoice month. `months` holds each month's invoices (by invoice date),
    remittances (by the month of the invoice they pay) and deductions (by their month); the current month adds the
    account's invoice, and once the payment arrived (a run started) its payment and the charges taken. Recovered money
    comes only from history: a dispute this run files has recovered nothing yet."""

    account: AccountListItem
    kpis: AccountKpis
    months: list[MonthTotals]  # oldest first, all six
    deductions_by_type: list[DeductionTypeTotal]  # in the window, largest amount first
    recent_remittances: list[RemittanceRow]  # newest first, at most six
    current: CurrentPayment


# ---- fee data
# The other side's backup for fee charges (fees/backup.csv), one row per line, keyed by the charge's ref. The engine
# reads them as api/engine/types.py FeeLine (adapters.to_engine_fee_line).

class FeeBackupRow(Contract):
    deduction_ref: str  # the charge's ref
    on: date  # the purchase, invoice or credit date; picks the fee schedule in effect
    group: str | None = None  # the invoice, PO or incident a fee's min and max apply to
    description: str | None = None
    base_amount: Money = Decimal(0)  # what a percent fee is taken on
    pass_through: Money = Decimal(0)  # cost charged on at cost (landed cost credited to a retailer)
    units: int = 0
    cartons: int = 0
    days: int | None = None  # for tiered fees (days late)
    proof_doc: str | None = None  # the backup document's id

    @field_validator("group", "description", "proof_doc", "days", mode="before")
    @classmethod
    def _blank(cls, v: Any) -> Any:
        return _blank_none(v)

    @field_validator("base_amount", "pass_through", "units", "cartons", mode="before")
    @classmethod
    def _zero(cls, v: Any) -> Any:
        return 0 if isinstance(v, str) and not v.strip() else v


# ---- suppliers: one brand (the user) tracking many distributors

RelationshipStatus = Literal["waiting_for_payment", "checking", "needs_you", "settled", "stopped"]


class DistributorItem(Contract):
    """One distributor a supplier sells through: its plain status, never a money figure (the workflow has those)."""

    account_id: str  # the relationship's account (data/accounts/<id>/)
    distributor: Distributor
    tracked: bool
    status: RelationshipStatus
    status_label: str  # "Agents are checking a payment", "1 decision for you", ...
    latest_run_id: str | None


class SupplierItem(Contract):
    """GET /suppliers: a supplier workspace and the distributors it sells through, tracked ones first."""

    id: str
    brand: Brand
    distributors: list[DistributorItem]


class TrackRequest(Contract):
    account_id: str
    tracked: bool


class LoginRequest(Contract):
    """POST /auth/login: a user's email (or the old admin ID in `username`) and password."""

    email: str | None = Field(default=None, max_length=200)
    username: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=200)

    @property
    def login(self) -> str:
        return (self.email or self.username or "").strip()


class SessionUser(Contract):
    """The signed-in person (GET /auth/me, POST /auth/login)."""

    id: str
    email: str
    name: str
    role: str  # "admin": answers the questions and approves the memos for their supplier


class SessionSupplier(Contract):
    """The signed-in person's supplier: the brand workspace, and the accounts (distributors) it owns."""

    id: str
    name: str
    account_ids: list[str] = Field(default_factory=list)


class LoginResponse(Contract):
    """Signed in: the session cookie is set. `code` is OWNER_TOKEN for scripts' X-Clawback-Role-Token (null where the
    site has none); the browser needs only the cookie."""

    role: Literal["owner"] = "owner"
    code: str | None = None
    user: SessionUser | None = None
    supplier: SessionSupplier | None = None


class MeResponse(Contract):
    """GET /auth/me. Signed in: user and supplier. Not signed in on an open laptop: both null and auth_required false
    (a signed-out caller where sign-in is on gets 401 instead)."""

    user: SessionUser | None = None
    supplier: SessionSupplier | None = None
    auth_required: bool = True


class RunSummary(Contract):
    """GET /accounts/{id}/runs: one past or current run of the agents, from its own events (newest first)."""

    run_id: str
    kind: str  # the month: "march", "april"
    status: Literal["started", "waiting", "finished", "failed"]
    started_at: datetime
    replaced: bool  # a newer run of the same payment replaced it (its open questions closed)
    invoice_id: str | None
    taken: Money | None  # what the distributor kept from the payment
    charges: int
    disputed: Money | None
    accepted: Money | None
    waiting: Money | None
    questions: int


class SavedDocument(Contract):
    """A document the agents read for this distributor. The signed deal and real contracts are locked: nobody edits
    them, agents included."""

    id: str
    kind: DocumentKind
    title: str
    sender: str | None
    locked: bool
    chars: int


class SavedRecords(Contract):
    label: str  # "Store sales", "Past payments", ...
    rows: int


class SavedOverview(Contract):
    """GET /accounts/{id}/saved: everything Clawback keeps for this distributor."""

    documents: list[SavedDocument]
    rules: list[Rule]
    records: list[SavedRecords]


class DocumentText(Contract):
    id: str
    title: str
    kind: DocumentKind
    locked: bool
    text: str


# ---- connections and the contract library

class Connection(Contract):
    """GET /connections: one place payments, records and contracts come from, as it really is on this server."""

    id: str
    name: str
    brings: str  # what it brings in
    status: Literal["connected", "not_connected", "ready", "coming_soon"]
    detail: str
    # What a source that starts runs (bank, QuickBooks, remittance inbox) has seen on this server (api/sources.py):
    checked_at: datetime | None = None  # its last poll, or the last email that reached it
    problem: str | None = None  # the last look's error, until a look works
    last_seen: str | None = None  # the newest thing it found for the account in view, in words
    last_seen_at: datetime | None = None
    run_id: str | None = None  # the run that started from it (or that it matched)
    address: str | None = None  # the remittance inbox's address for the account in view


class LibraryTerm(Contract):
    type: TermType
    quote: str
    char_start: int
    char_end: int
    status: TermStatus
    discretion: bool
    label: str  # "$1.00 per unit", "at most 5,000 units"


class LibraryDocument(Contract):
    id: str
    title: str
    kind: DocumentKind
    locked: bool  # signed: nobody edits it, agents included
    sender: str | None
    approved_sender: bool
    text: str
    terms: list[LibraryTerm]


class ContractLibrary(Contract):
    """GET /accounts/{id}/contract: the deal and what changes it, with the terms the agents read highlighted."""

    read_in_run: str | None  # the run whose readers produced the terms (None until the agents have read it)
    documents: list[LibraryDocument]
