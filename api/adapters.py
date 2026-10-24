"""Map api/contracts.py objects onto the engine's plain dataclasses (api/engine/types.py) and back."""

from __future__ import annotations

from datetime import datetime

from api import contracts
from api.engine import types as eng


def to_engine_term(t: contracts.Term) -> eng.Term:
    return eng.Term(
        id=t.id, type=eng.TermType(t.type), params=dict(t.params), exact_quote=t.exact_quote,
        effective_from=t.effective_from, effective_to=t.effective_to, discretion=t.discretion,
        status=eng.TermStatus(t.status) if t.status != "pending" else eng.TermStatus.DISPUTED,
        source_doc_id=t.source_doc_id, source_approved=t.source_approved,
    )


def _products(text: str | None) -> tuple[str, ...]:
    return tuple(p.strip() for p in (text or "").replace(";", "+").split("+") if p.strip())


def to_engine_charge(c: contracts.Charge, counterparty: str = "Northmart") -> eng.Charge:
    return eng.Charge(
        id=c.id, ref=c.ref, code=c.code, description=c.description, products=_products(c.product), units=c.units,
        rate=c.rate, amount=c.amount, period_start=c.period_start, period_end=c.period_end,
        counterparty=counterparty, notice_date=c.notice_date,
    )


def to_engine_sales(r: contracts.SalesRow) -> eng.SalesWeek:
    return eng.SalesWeek(r.week_start, r.week_end, r.product, r.promo_units, r.total_units)


def to_engine_prior(p: contracts.PriorPayment) -> eng.PriorPayment:
    return eng.PriorPayment(p.ref, p.paid_on, p.promo_id, _products(p.product), p.period_start, p.period_end,
                            p.units, p.amount)


def to_engine_rule(r: contracts.Rule) -> eng.Rule:
    return eng.Rule(id=r.id, pattern_text=r.pattern_text, term_type=eng.TermType(r.term_type),
                    counterparty=r.counterparty, condition=r.condition, decision=eng.DecisionKind(r.decision),
                    else_decision=eng.DecisionKind(r.else_decision), approver=r.approver_role,
                    learned_at=r.learned_at.date() if isinstance(r.learned_at, datetime) else r.learned_at,
                    source_question_id=r.source_question_id or "", status=r.status)


def to_contract_decision(d: eng.Decision, waiting, decided_by: str, decided_at: datetime) -> contracts.Decision:
    return contracts.Decision(charge_id=d.charge_id, decision=d.kind.value, disputed=d.disputed, accepted=d.accepted,
                              waiting=waiting, gate_row=d.gate_row, rule_id=d.rule_id, decided_by=decided_by,
                              decided_at=decided_at, reason=d.reason)
