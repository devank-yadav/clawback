"""The judge's scenario box (F14): a pasted clause and a charge, decided the way a real run decides it.

The clause is read by the Deal Reader and checked word for word; its terms replace the Spring deal's terms of the
same type (the rest of the deal still applies). The charge then goes through the engine, the Investigator, the
rehearsal (if it would be disputed) and the gate with the owner's saved rules, against the demo's store sales and
prior payments. Every Claude call tries live first (20 s), then a recorded answer; the examples are recorded.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import anthropic

from api import adapters, evidence as evidence_mod, pipeline, rows
from api.agents import investigator, negotiator, readers
from api.contracts import (
    Charge, Finding, MathPart, Rehearsal, ScenarioCharge, ScenarioExample, ScenarioRequest, ScenarioResponse,
)
from api.engine import gate
from api.engine import types as eng
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy

PROMO_START, PROMO_END = date(2026, 3, 1), date(2026, 3, 31)

EXAMPLES = [
    ScenarioExample(id="higher-cap", label="A higher cap", request=ScenarioRequest(
        clause="The promotional allowance applies to a maximum of 6,500 units in total.",
        charge=ScenarioCharge(description="Spring promo week 4", amount=Decimal("1540.00"), units=1540,
                              rate=Decimal("1.00"), period_start=date(2026, 3, 22), period_end=date(2026, 3, 31)))),
    ScenarioExample(id="lower-rate", label="A lower rate", request=ScenarioRequest(
        clause="Supplier will fund a promotional allowance of $0.75 per unit on Peak Bar Original and Peak Bar "
               "Chocolate sold between March 1 and March 31, 2026.",
        charge=ScenarioCharge(description="Spring promo week 1", amount=Decimal("1200.00"), units=1200,
                              rate=Decimal("1.00"), period_start=date(2026, 3, 1), period_end=date(2026, 3, 7)))),
    ScenarioExample(id="slotting-fee", label="A fee at Northmart's discretion", request=ScenarioRequest(
        clause="Northmart may charge a display fee of up to $900 per month at its discretion, with written notice "
               "to Supplier.",
        charge=ScenarioCharge(description="Display fee (notice Mar 25)", amount=Decimal("900.00"), code="DF",
                              notice_date=date(2026, 3, 25)))),
]


def _charge(c: ScenarioCharge) -> Charge:
    code = c.code or ("PA" if c.units and c.rate else "DF")
    return Charge(id="S1", ref="SCENARIO", code=code, description=c.description,
                  product=c.product or ("Original+Chocolate" if code == "PA" else None), units=c.units or 1,
                  rate=c.rate if c.rate is not None else c.amount, amount=c.amount,
                  period_start=c.period_start or PROMO_START, period_end=c.period_end or PROMO_END,
                  notice_date=c.notice_date)


def run(req: ScenarioRequest, client: anthropic.Anthropic | None = None) -> ScenarioResponse:
    policy = load_policy()
    pasted = readers.read_text_both(req.clause, client)
    if not pasted.terms:
        return ScenarioResponse(decision=None, finding=None, evidence=[], unclear=pasted.unclear,
                                message="The clause didn't state a term Clawback reads (rate, products, dates, cap, a "
                                        "fee or an extension), so nothing was decided.")
    # The rest of the Spring deal (and the broker's approved extension) still applies.
    deal = readers.read_both(pipeline.DEAL_DOCS[0], client=client)
    broker = readers.read_both(pipeline.DEAL_DOCS[1], base_terms=deal.terms, client=client)
    replaced = {t.type for t in pasted.terms}
    terms = pasted.terms + [t for t in deal.terms + broker.terms if t.status == "verified" and t.type not in replaced]
    charge = _charge(req.charge)
    sales, payments = rows.sales(), rows.prior_payments()
    evidence = evidence_mod.build(terms, [charge], sales, payments)
    a = compute_allowed(adapters.to_engine_charge(charge), [adapters.to_engine_term(t) for t in terms],
                        [adapters.to_engine_sales(r) for r in sales], [adapters.to_engine_prior(p) for p in payments])
    inv = investigator.investigate(charge, a, evidence, client, live_first=True)
    finding = (Finding(**inv.output.model_dump(), id="F-S1", expected=a.allowed, taken=a.taken, delta=a.delta,
                       math=[MathPart(text=s) for s in a.steps]) if inv.output else None)
    discretion = any(gate.uses_discretion(t, policy) for t in a.terms)
    rehearsal = None
    if finding and a.delta > policy.match_tolerance and not discretion and not a.missing:
        rehearsal = negotiator.rehearse(charge, finding, a, evidence, terms, client, live_first=True)
    kinds = {evidence[i].kind for i in (finding.evidence_ids if finding else [])} - {"charge"}
    eng_finding = eng.Finding(charge_id="S1", confidence=Decimal(str(finding.confidence)) if finding else Decimal(0),
                              evidence_ids=tuple(finding.evidence_ids) if finding else (), independent_sources=len(kinds),
                              comeback_answered=bool(rehearsal and rehearsal.answered),
                              type=finding.type if finding else "", finding=finding.finding if finding else "")
    rules = [r for r in pipeline.RULES if r.status == "active"]
    d = gate.decide(adapters.to_engine_charge(charge), a, eng_finding, policy, [adapters.to_engine_rule(r) for r in rules])
    decision = adapters.to_contract_decision(d, waiting=charge.amount if d.kind == eng.DecisionKind.ASK else Decimal(0),
                                             decided_by="gate", decided_at=pipeline._now())
    rule = next((r for r in rules if r.id == d.rule_id), None)
    cited = list(dict.fromkeys((finding.evidence_ids if finding else [])
                               + (rehearsal.answer_evidence_ids if rehearsal and rehearsal.answered else [])
                               + [evidence_mod.clause_id(t) for t in pasted.terms if t.status == "verified"]))
    return ScenarioResponse(decision=decision, finding=finding, terms=pasted.terms, unclear=pasted.unclear,
                            rehearsal=rehearsal if rehearsal and rehearsal.answered else None, rule=rule,
                            evidence=[evidence[i] for i in cited if i in evidence], message=_say(d, rule))


def _say(d: eng.Decision, rule) -> str:
    """One plain sentence for the box, from the gate's numbers."""
    k = eng.DecisionKind
    if d.kind == k.SPLIT:
        head = f"Split: ${d.accepted:,.2f} is fair, ${d.disputed:,.2f} is disputed."
    elif d.kind == k.DISPUTE:
        head = f"Dispute all ${d.disputed:,.2f}."
    elif d.kind == k.ACCEPT:
        head = f"Accept ${d.accepted:,.2f}."
    elif d.kind == k.SKIP:
        head = "Skip: Clawback can't verify the clause."
    else:
        head = "Ask the owner."
    return f"{head} {d.reason}" + (f" ({rule.label}, learned from {rule.approver.split()[0]}.)" if rule else "")
