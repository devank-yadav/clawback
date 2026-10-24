"""Negotiator (Claude), part 1: rehearse the comeback before filing (docs/design.md, Agents > 3).

Code check after: the answer cites at least one evidence ID from the input, and its quotes and dollar figures
pass the outbound filter. No answer -> the charge goes to Ask instead of being filed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import anthropic

from api.agents import claude
from api.agents.claude import Strict
from api.agents.investigator import engine_payload, evidence_for, evidence_payload, invented_numbers
from api.contracts import Charge, Evidence, Finding, Rehearsal, Term
from api.engine import outbound_filter, quote_check
from api.engine.types import Allowance

REHEARSAL_SERVICE = "claude-rehearsal"
REHEARSAL_PROMPT = (Path(__file__).parent / "prompts" / "rehearsal.md").read_text()


class LLMRehearsal(Strict):
    predicted_rebuttal: str
    answer: str
    answer_evidence_ids: list[str]


def rehearse(charge: Charge, finding: Finding, allowance: Allowance, evidence: dict[str, Evidence],
             terms: Sequence[Term], client: anthropic.Anthropic | None = None) -> Rehearsal:
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

    ans = claude.ask(REHEARSAL_SERVICE, REHEARSAL_PROMPT, user, LLMRehearsal, check, client, charge_id=charge.id)
    return ans.value or Rehearsal(charge_id=charge.id, predicted_rebuttal="", answer="", answer_evidence_ids=[],
                                  answered=False)
