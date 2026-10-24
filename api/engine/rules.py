"""Saved owner rules: exact-match fallback (term type + counterparty) and condition evaluation.
Moss semantic matching (F16) will sit in front of find_rule; this stays as the fallback."""

from __future__ import annotations

import operator
import re
from typing import Any, Iterable, Mapping

from api.engine.types import DecisionKind, Rule, TermType

_CONDITION = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "!=": operator.ne, ">": operator.gt, "<": operator.lt}


def find_rule(rules: Iterable[Rule], term_type: TermType, counterparty: str) -> Rule | None:
    """First active rule with the same term type and counterparty (case-insensitive)."""
    for rule in rules:
        if (
            rule.status == "active"
            and rule.term_type == term_type
            and rule.counterparty.strip().lower() == counterparty.strip().lower()
        ):
            return rule
    return None


def parse_condition(condition: str) -> tuple[str, str, float]:
    m = _CONDITION.match(condition)
    if not m:
        raise ValueError(f"unsupported rule condition: {condition!r}")
    return m.group(1), m.group(2), float(m.group(3))


def evaluate(rule: Rule, facts: Mapping[str, Any]) -> DecisionKind:
    """rule.decision if the condition holds; rule.else_decision if not, or if the fact is unknown."""
    fact, op, value = parse_condition(rule.condition)
    seen = facts.get(fact)
    if seen is None:
        return rule.else_decision
    return rule.decision if _OPS[op](float(seen), value) else rule.else_decision
