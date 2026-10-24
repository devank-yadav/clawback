"""Negotiator (Claude) (docs/design.md, Agents > 3).

Part 1, rehearse before filing: the answer must cite an evidence ID and pass the outbound filter, or the charge
goes to Ask instead of being filed. Part 2, answer Northmart's portal replies that come without a document
(api/disputes.py handles a signed document in code): same checks, one retry, then the message is held.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import anthropic

from api import accounts
from api.agents import claude, prompts
from api.agents.claude import Strict
from api.agents.investigator import engine_payload, evidence_for, evidence_payload, invented_numbers
from api.contracts import Charge, Dispute, Evidence, Finding, Rehearsal, Term
from api.engine import outbound_filter, quote_check
from api.engine.types import Allowance

REHEARSAL_SERVICE = "claude-rehearsal"


class LLMRehearsal(Strict):
    predicted_rebuttal: str
    answer: str
    answer_evidence_ids: list[str]


def rehearse(charge: Charge, finding: Finding, allowance: Allowance, evidence: dict[str, Evidence],
             terms: Sequence[Term], client: anthropic.Anthropic | None = None, live_first: bool = False,
             account: accounts.Account | str | None = None) -> Rehearsal:
    items = evidence_for(charge, evidence)
    user = json.dumps({"charge": charge.model_dump(mode="json", exclude={"remittance_id"}),
                       "finding": {"text": finding.finding, "type": finding.type, "evidence_ids": finding.evidence_ids},
                       "engine": engine_payload(allowance), "evidence": evidence_payload(items)}, indent=1, default=str)
    ids = {e.id for e in items}
    ctx = outbound_filter.OutboundContext.build(
        amounts=quote_check.numbers_in(user),  # engine numbers and data values: everything the agent was given
        terms=[t.model_dump(mode="json") for t in terms if t.status == "verified"],
        findings=[finding.finding] + [e.quote.text for e in items if e.quote])

    def check(raw: dict) -> Rehearsal:
        r = LLMRehearsal.model_validate(raw)
        problems = []
        if not r.answer_evidence_ids:
            problems.append("cite at least one evidence ID")
        if unknown := [i for i in r.answer_evidence_ids if i not in ids]:
            problems.append(f"evidence IDs not in the input: {unknown}")
        if invented := invented_numbers(r.answer, user):
            problems.append(f"numbers in the answer that aren't in the input: {[str(n) for n in invented]}")
        filtered = outbound_filter.check_message(r.answer, ctx)
        if not filtered.ok:
            problems.append("outbound filter:\n" + filtered.feedback())
        if problems:
            raise ValueError("; ".join(problems))
        return Rehearsal(charge_id=charge.id, predicted_rebuttal=r.predicted_rebuttal, answer=r.answer,
                         answer_evidence_ids=r.answer_evidence_ids, answered=True)

    ans = claude.ask(REHEARSAL_SERVICE, prompts.render("rehearsal", account), user, LLMRehearsal, check, client,
                     live_first=live_first, charge_id=charge.id)
    return ans.value or Rehearsal(charge_id=charge.id, predicted_rebuttal="", answer="", answer_evidence_ids=[],
                                  answered=False)


# ---------------------------------------------------------------- part 2: answer Northmart's portal replies

REPLY_SERVICE = "claude-portal-reply"


class LLMReply(Strict):
    classification: Literal["claim_without_document", "agrees", "other"]
    charge_ids: list[str]
    claim: str | None
    answer: str
    answer_evidence_ids: list[str]


@dataclass
class ReplyDraft:
    classification: str
    charge_ids: list[str]
    claim: str | None
    answer: str
    evidence_ids: list[str]


def answer_reply(dispute: Dispute, text: str, evidence: dict[str, Evidence], terms: Sequence[Term],
                 client: anthropic.Anthropic | None = None,
                 account: accounts.Account | str | None = None) -> ReplyDraft | None:
    """Classify a Northmart reply that has no attachment and draft the answer. None: the answer failed its
    checks twice (or the call failed), so the message is held for the owner. Tries live first even in DEMO_MODE."""
    items = [e for e in evidence.values() if e.kind != "charge" or e.id.removeprefix("ev-charge-") in
             {ln.charge_id for ln in dispute.lines}]
    user = json.dumps({"dispute": {"id": dispute.id, "lines": [ln.model_dump(mode="json") for ln in dispute.lines]},
                       "northmart_reply": text, "evidence": evidence_payload(items)}, indent=1, default=str)
    ids, lines = {e.id for e in items}, {ln.charge_id for ln in dispute.lines}
    ctx = outbound_filter.OutboundContext.build(
        amounts=quote_check.numbers_in(user.replace(text, "")),  # Northmart's own numbers aren't ours to repeat
        terms=[t.model_dump(mode="json") for t in terms if t.status == "verified"],
        findings=[ln.reason for ln in dispute.lines] + [e.quote.text for e in items if e.quote])

    def check(raw: dict) -> ReplyDraft:
        r = LLMReply.model_validate(raw)
        problems = []
        if unknown := [c for c in r.charge_ids if c not in lines]:
            problems.append(f"charge IDs not on the dispute: {unknown}")
        if unknown := [i for i in r.answer_evidence_ids if i not in ids]:
            problems.append(f"evidence IDs not in the input: {unknown}")
        if r.classification == "claim_without_document" and not (r.answer.strip() and r.answer_evidence_ids):
            problems.append("a claim needs an answer that cites evidence")
        if r.answer.strip():
            if invented := invented_numbers(r.answer, user.replace(text, "")):
                problems.append(f"numbers in the answer that aren't ours: {[str(n) for n in invented]}")
            filtered = outbound_filter.check_message(r.answer, ctx)
            if not filtered.ok:
                problems.append("outbound filter:\n" + filtered.feedback())
        if problems:
            raise ValueError("; ".join(problems))
        return ReplyDraft(r.classification, r.charge_ids, r.claim, r.answer.strip(), r.answer_evidence_ids)

    return claude.ask(REPLY_SERVICE, prompts.render("portal_reply", account), user, LLMReply, check, client,
                      live_first=True, dispute_id=dispute.id).value
