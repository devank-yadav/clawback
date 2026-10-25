"""The parts of the API's answers the assistant reads, mirrored from api/contracts.py (Summary, AnswerResponse).

Extra fields are ignored, so the API can grow without breaking the agent. Money stays the API's number: it's
only ever formatted, never added up (tests/test_contract_sync.py checks these against the real contracts).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _Read(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Totals(_Read):
    taken: Decimal
    disputed: Decimal
    accepted: Decimal
    waiting: Decimal
    undecided: Decimal
    questions: int
    skipped: int = 0


class DisputeLine(_Read):
    charge_id: str
    amount: Decimal
    reason: str


class Dispute(_Read):
    id: str
    counterparty: str
    lines: list[DisputeLine]
    total: Decimal
    status: str


class Question(_Read):
    id: str
    charge_id: str | None = None
    text: str


class ApprovalLine(_Read):
    charge_id: str
    amount: Decimal


class Approval(_Read):
    id: str
    kind: str  # credit_memo, dispute_over_limit, closed_period
    amount: Decimal
    lines: list[ApprovalLine] = []
    approver_role: str  # owner (the admin; older runs said controller)
    status: str
    text: str


class Summary(_Read):
    totals: Totals
    open_disputes: list[Dispute] = []
    pending_question: Question | None = None
    pending_approvals: list[Approval] = []
    run_id: str | None = None  # None: the API has no live run yet and shows its recorded demo run


class Answer(_Read):
    question_id: str
    text: str
    rule_id: str | None = None


class Rule(_Read):
    id: str
    label: str  # "Rule #1"
    summary: str  # "Accept Northmart display fees with at least 14 days' notice; otherwise dispute."
    status: str  # pending, active, undone


class AnswerResponse(_Read):
    answer: Answer
    rule: Rule | None = None
