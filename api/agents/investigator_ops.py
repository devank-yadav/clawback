"""Operations Investigator (Claude): one shortage, price-mismatch or spoilage charge (SH, PR, SP) -> a one-line
finding, its type, cited evidence and a confidence, as the Investigator does for promo charges (docs/design.md,
Agents > 2), but read against the proof of delivery, the agreed price list and the deal's operations terms.

The same code checks follow: every cited ID exists and every number in the finding already appears in the input,
plus the type must belong to the charge's code. Failures retry once, then the charge goes to Ask; confidence below
the policy floor sends it to Ask at the gate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import anthropic

from api.agents import claude
from api.agents.claude import Strict
from api.agents.investigator import Investigation, engine_payload, evidence_payload, invented_numbers
from api.contracts import Charge, Evidence, InvestigatorOutput
from api.engine.allowed import OPS_CODES
from api.engine.types import Allowance
from api.evidence import pod_id, price_id

SERVICE = "claude-investigator-ops"
PROMPT = (Path(__file__).parent / "prompts" / "investigator_ops.md").read_text()

OpsFindingType = Literal[
    "shortage_not_supported", "shortage_confirmed", "price_mismatch", "price_matches",
    "spoilage_over_allowance", "spoilage_within_allowance",
]
TYPES_BY_CODE = {
    "SH": ("shortage_not_supported", "shortage_confirmed"),
    "PR": ("price_mismatch", "price_matches"),
    "SP": ("spoilage_over_allowance", "spoilage_within_allowance"),
}


class LLMOpsFinding(Strict):
    finding: str
    type: OpsFindingType
    evidence_ids: list[str]
    confidence: float
    open_questions: list[str]


def handles(charge: Charge) -> bool:
    """SH, PR and SP charges come here; everything else goes to api/agents/investigator.py."""
    return charge.code in OPS_CODES


def system_prompt(brand: str, distributor: str) -> str:
    return PROMPT.format(brand=brand, distributor=distributor)


def evidence_for(charge: Charge, allowance: Allowance, evidence: Mapping[str, Evidence]) -> list[Evidence]:
    """The charge's own row, the delivery lines the engine used, the agreed price of that line's product (PR), and
    every ops term. Deal clauses, sales and other charges don't bear on a delivery."""
    keep = {f"ev-charge-{charge.id}", *(pod_id(r) for r in allowance.facts.get("line_refs", ()))}
    if product := allowance.facts.get("product"):
        keep.add(price_id(product))
    return [e for e in evidence.values() if e.id in keep or e.kind == "policy"]


def investigate(charge: Charge, allowance: Allowance, evidence: Mapping[str, Evidence],
                client: anthropic.Anthropic | None = None, live_first: bool = False, *,
                brand: str = "Peak Bar Co.", distributor: str = "Northmart") -> Investigation:
    if not handles(charge):
        raise ValueError(f"the operations Investigator handles {sorted(OPS_CODES)} charges, not {charge.code}")
    items = evidence_for(charge, allowance, evidence)
    user = json.dumps({"charge": charge.model_dump(mode="json", exclude={"remittance_id"}), "engine": engine_payload(allowance),
                       "evidence": evidence_payload(items)}, indent=1, default=str)
    ids = {e.id for e in items}
    types = TYPES_BY_CODE[charge.code]

    def check(raw: dict) -> InvestigatorOutput:
        out = InvestigatorOutput.model_validate({**raw, "charge_id": charge.id})
        problems = []
        if not out.evidence_ids:
            problems.append("cite at least one evidence ID")
        if unknown := [i for i in out.evidence_ids if i not in ids]:
            problems.append(f"evidence IDs not in the input: {unknown}")
        if invented := invented_numbers(out.finding, user):
            problems.append(f"numbers in the finding that aren't in the input: {[str(n) for n in invented]}")
        if out.type not in types:
            problems.append(f"type {out.type} doesn't fit a {charge.code} charge; use one of {list(types)}")
        if problems:
            raise ValueError("; ".join(problems))
        return out

    ans = claude.ask(SERVICE, system_prompt(brand, distributor), user, LLMOpsFinding, check, client,
                     live_first=live_first, charge_id=charge.id)
    return Investigation(ans.value, ans.source, ans.errors)
