"""Deal Coach (Claude): redlines for next month's draft, each tied to what this month cost (docs/design.md,
Agents > 4). Code check after: each original quote is found word for word in the draft, each cited finding
exists, and dollars_at_stake is the cited costs added up by code (the engine's numbers). Suggestions only:
Clawback never sends them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import anthropic

from api import documents, evidence as evidence_mod
from api.agents import claude
from api.agents.claude import Strict
from api.agents.investigator import invented_numbers
from api.contracts import CoachResponse, Redline
from api.engine import quote_check, totals

SERVICE = "claude-coach"
PROMPT = (Path(__file__).parent / "prompts" / "coach.md").read_text()
DRAFT = "summer-draft"
_SECTION = re.compile(r"(\d+\.\d+)\s+$")


class LLMRedline(Strict):
    original_quote: str
    suggested_text: str
    reason: str
    finding_ids: list[str]


class LLMCoach(Strict):
    redlines: list[LLMRedline]


@dataclass(frozen=True)
class Cost:
    finding_id: str
    charge_id: str
    ref: str
    type: str
    finding: str
    dollars: Decimal  # engine numbers: the disputed amount, or the fee that needed a question
    why: str  # "disputed" or "needed a question to the owner"


def coach(costs: list[Cost], client: anthropic.Anthropic | None = None) -> CoachResponse:
    doc, draft = documents.load(DRAFT)
    by_id = {c.finding_id: c for c in costs}
    user = json.dumps({"costs": [{"finding_id": c.finding_id, "charge": f"{c.charge_id} ({c.ref})", "type": c.type,
                                  "what_went_wrong": c.finding, "cost": f"${c.dollars:,.2f} {c.why}"} for c in costs],
                       "draft": draft}, indent=1)

    def check(raw: dict) -> list[Redline]:
        out, problems, used = LLMCoach.model_validate(raw), [], set()
        redlines = []
        for i, r in enumerate(out.redlines, 1):
            span = quote_check.find_quote(draft, r.original_quote)
            if span is None:
                problems.append(f"redline {i}: original_quote is not in the draft word for word")
                continue
            if not r.finding_ids or (unknown := [f for f in r.finding_ids if f not in by_id]):
                problems.append(f"redline {i}: cite finding IDs from the input (got {r.finding_ids})")
                continue
            if again := used & set(r.finding_ids):
                problems.append(f"redline {i}: {sorted(again)} already used by another redline")
            used |= set(r.finding_ids)
            if invented := invented_numbers(r.reason, user):
                problems.append(f"redline {i}: numbers in the reason that aren't in the input: {[str(n) for n in invented]}")
            section = _SECTION.search(draft[max(0, span[0] - 12):span[0]])
            redlines.append(Redline(
                clause_ref=f"§{section.group(1)}" if section else "draft", original_quote=r.original_quote,
                suggested_text=r.suggested_text, reason=r.reason, finding_ids=r.finding_ids,
                dollars_at_stake=totals.total_of(by_id[f].dollars for f in r.finding_ids),
                quote=evidence_mod.quote_in(doc.id, draft, span[0], span[1], r.original_quote)))
        if problems:
            raise ValueError("; ".join(problems))
        return redlines

    ans = claude.ask(SERVICE, PROMPT, user, LLMCoach, check, client, draft=DRAFT)
    return CoachResponse(draft_doc_id=DRAFT, redlines=ans.value or [])
