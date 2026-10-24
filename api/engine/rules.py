"""Saved owner rules: which rule covers a clause, and condition evaluation.

match_rule takes Moss's semantic matches (F16, found by api/integrations/moss.py) and keeps the best one that clears
the policy's similarity and has the same term type and counterparty. find_rule, the exact match on term type +
counterparty, is the fallback when Moss has no such match (no key, a failed call, or only weak matches)."""

from __future__ import annotations

import operator
import re
from decimal import Decimal
from typing import Any, Iterable, Mapping

from api.engine.types import DecisionKind, Rule, RuleMatch, TermType

_CONDITION = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "!=": operator.ne, ">": operator.gt, "<": operator.lt}


def covers(rule: Rule, term_type: TermType, counterparty: str) -> bool:
    """An active rule with the same term type and counterparty (case-insensitive)."""
    return (
        rule.status == "active"
        and rule.term_type == term_type
        and rule.counterparty.strip().lower() == counterparty.strip().lower()
    )


def find_rule(rules: Iterable[Rule], term_type: TermType, counterparty: str) -> Rule | None:
    """First rule that covers the term type and counterparty."""
    return next((rule for rule in rules if covers(rule, term_type, counterparty)), None)


def match_rule(rules: Iterable[Rule], matches: Iterable[RuleMatch], term_type: TermType, counterparty: str,
               min_similarity: Decimal) -> tuple[Rule, Decimal] | None:
    """The most similar Moss match at or above min_similarity whose rule covers the term type and counterparty.
    A match naming no known rule is ignored."""
    by_id = {rule.id: rule for rule in rules}
    for m in sorted(matches, key=lambda m: m.similarity, reverse=True):
        rule = by_id.get(m.rule_id)
        if m.similarity >= min_similarity and rule is not None and covers(rule, term_type, counterparty):
            return rule, m.similarity
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
