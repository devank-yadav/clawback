"""Investigator (Claude): one charge -> a one-line finding, its type, cited evidence and a confidence
(docs/design.md, Agents > 2). Code check after: every cited ID exists and every number in the finding
already appears in the input. Failures retry once, then the charge goes to Ask.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import anthropic

from api.agents import claude
from api.agents.claude import Strict
from api.contracts import Charge, Evidence, FindingType, InvestigatorOutput
from api.engine import quote_check
from api.engine.types import Allowance

SERVICE = "claude-investigator"
PROMPT = (Path(__file__).parent / "prompts" / "investigator.md").read_text()


class LLMFinding(Strict):
    finding: str
    type: FindingType
    evidence_ids: list[str]
    confidence: float
    open_questions: list[str]


@dataclass
class Investigation:
    output: InvestigatorOutput | None
    source: str
    errors: list[str]


def evidence_for(charge: Charge, evidence: dict[str, Evidence]) -> list[Evidence]:
    """Everything in the run except charges of other kinds. The same promo's other lines stay: a cap runs across
    weeks, and without them the Investigator can't see that week 1 is charged in this same payment (C1), so it
    doubts the cap on C4 and its confidence drops below the floor."""
    return [e for e in evidence.values() if e.kind != "charge" or e.id == f"ev-charge-{charge.id}"
            or (e.rows and e.rows[0].get("code") == charge.code)]


def evidence_payload(items: list[Evidence]) -> list[dict]:
    return [{"id": e.id, "kind": e.kind, "label": e.label, "summary": e.summary,
             "quote": e.quote.text if e.quote else None, "rows": e.rows} for e in items]


def engine_payload(a: Allowance) -> dict:
    return {"allowed": str(a.allowed), "taken": str(a.taken), "delta": str(a.delta), "covered_units": a.covered_units,
            "steps": list(a.steps), "facts": dict(a.facts), "missing": list(a.missing)}


def invented_numbers(text: str, source: str) -> list[Decimal]:
    """Numbers in `text` that appear nowhere in `source` (compared by value)."""
    seen = set(quote_check.numbers_in(source))
    return [n for n in quote_check.numbers_in(text) if n not in seen]


def investigate(charge: Charge, allowance: Allowance, evidence: dict[str, Evidence],
                client: anthropic.Anthropic | None = None, live_first: bool = False) -> Investigation:
    items = evidence_for(charge, evidence)
    user = json.dumps({"charge": charge.model_dump(mode="json", exclude={"remittance_id"}), "engine": engine_payload(allowance),
                       "evidence": evidence_payload(items)}, indent=1, default=str)
    ids = {e.id for e in items}

    def check(raw: dict) -> InvestigatorOutput:
        out = InvestigatorOutput.model_validate({**raw, "charge_id": charge.id})
        problems = []
        if not out.evidence_ids:
            problems.append("cite at least one evidence ID")
        if unknown := [i for i in out.evidence_ids if i not in ids]:
            problems.append(f"evidence IDs not in the input: {unknown}")
        if invented := invented_numbers(out.finding, user):
            problems.append(f"numbers in the finding that aren't in the input: {[str(n) for n in invented]}")
        if problems:
            raise ValueError("; ".join(problems))
        return out

    ans = claude.ask(SERVICE, PROMPT, user, LLMFinding, check, client, live_first=live_first, charge_id=charge.id)
    return Investigation(ans.value, ans.source, ans.errors)
