"""The decision gate (F5): docs/design.md, "Decision gate". Nine rows, first matching row wins."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable

from api.engine.rules import evaluate, find_rule
from api.engine.types import (
    Allowance,
    Charge,
    Decision,
    DecisionKind,
    Finding,
    Policy,
    Rule,
    Term,
    TermStatus,
    Totals,
    money,
)

ZERO = money(0)


def uses_discretion(term: Term, policy: Policy) -> bool:
    """The reader's flag, or a policy discretion word in the quote (whole words only)."""
    if term.discretion:
        return True
    quote = term.exact_quote.lower()
    return any(re.search(rf"\b{re.escape(w.lower())}\b", quote) for w in policy.discretion_words)


def decide(
    charge: Charge,
    allowance: Allowance,
    finding: Finding | None,
    policy: Policy,
    rules: Iterable[Rule] = (),
) -> Decision:
    def out(kind: DecisionKind, row: int, reason: str, disputed=ZERO, accepted=ZERO, rule_id=None) -> Decision:
        return Decision(charge.id, kind, money(disputed), money(accepted), row, rule_id, reason)

    taken, allowed, delta = allowance.taken, allowance.allowed, allowance.delta

    # Row 1: a term the charge depends on failed the quote check.
    if any(t.status == TermStatus.REJECTED for t in allowance.terms):
        return out(DecisionKind.SKIP, 1, "Can't verify the deal: a term's quote was not found in the source.")

    # Row 2: the two readers disagree on a term.
    if any(t.status == TermStatus.DISPUTED for t in allowance.terms):
        return out(DecisionKind.ASK, 2, "The two deal readers disagree on a term this charge depends on.")

    # Rows 3 and 4: discretion.
    discretion = [t for t in allowance.terms if uses_discretion(t, policy)]
    if discretion:
        rule = find_rule(rules, discretion[0].type, charge.counterparty)
        if rule is None:
            return out(DecisionKind.ASK, 4, "The deal leaves this to discretion and no saved rule covers it.")
        verdict = evaluate(rule, allowance.facts)
        if verdict == DecisionKind.ACCEPT:
            if delta > policy.match_tolerance:  # e.g. a fee above the deal's maximum: accept only up to it
                return out(DecisionKind.SPLIT, 3, f"Applied {rule.id}; the part above the deal is disputed.",
                           disputed=delta, accepted=allowed, rule_id=rule.id)
            return out(DecisionKind.ACCEPT, 3, f"Applied {rule.id}.", accepted=taken, rule_id=rule.id)
        if verdict == DecisionKind.DISPUTE:
            return out(DecisionKind.DISPUTE, 3, f"Applied {rule.id}.", disputed=taken, rule_id=rule.id)
        return out(DecisionKind.ASK, 3, f"{rule.id} says to ask.", rule_id=rule.id)

    # Not in the design table: with a required term missing the amount means nothing, so it can only be Ask (row 9).
    if allowance.missing:
        return out(DecisionKind.ASK, 9, f"Deal is missing: {', '.join(allowance.missing)}.")

    # Row 5: within tolerance.
    if abs(delta) <= policy.match_tolerance:
        return out(DecisionKind.ACCEPT, 5, "Matches the deal.", accepted=taken)

    # Row 6: taken less than allowed. Accept and never ask for more.
    if delta < 0:
        return out(DecisionKind.ACCEPT, 6, f"Charged ${-delta:,} less than the deal allows; noted, not claimed.", accepted=taken)

    # Rows 7 and 8: a well-supported overcharge.
    supported = (
        finding is not None
        and finding.confidence >= policy.confidence_floor
        and finding.independent_sources >= 2
        and finding.comeback_answered
    )
    if supported:
        if delta > policy.auto_dispute_limit:
            return out(DecisionKind.ASK, 8, f"Overcharge of ${delta:,} is above the ${policy.auto_dispute_limit:,} auto-dispute limit.")
        kind = DecisionKind.SPLIT if allowed > 0 else DecisionKind.DISPUTE
        return out(kind, 7, f"Deal allows ${allowed:,}; ${delta:,} disputed.", disputed=delta, accepted=allowed)

    # Row 9: anything else.
    return out(DecisionKind.ASK, 9, "Not enough support to dispute automatically.")


def decide_by_owner(charge: Charge, allowance: Allowance, choice: DecisionKind, policy: Policy,
                    gate_row: int, cap_at_deal: bool) -> Decision:
    """The owner settles one charge (ACCEPT or DISPUTE, no rule saved). With cap_at_deal (a discretion fee),
    accepting never accepts more than the deal's maximum: the part above it stays disputed, as with a rule
    (row 3). Otherwise accepting takes the owner at their word and accepts the whole charge."""
    taken, allowed, delta = allowance.taken, allowance.allowed, allowance.delta
    if choice == DecisionKind.DISPUTE:
        return Decision(charge.id, DecisionKind.DISPUTE, money(taken), ZERO, gate_row, None, "Owner chose to dispute.")
    if choice != DecisionKind.ACCEPT:
        raise ValueError(f"owner decides accept or dispute, not {choice}")
    if cap_at_deal and delta > policy.match_tolerance:
        return Decision(charge.id, DecisionKind.SPLIT, money(delta), money(allowed), gate_row, None,
                        "Owner accepted; the part above the deal is disputed.")
    return Decision(charge.id, DecisionKind.ACCEPT, ZERO, money(taken), gate_row, None, "Owner chose to accept.")


def summarize(decisions: Iterable[Decision]) -> Totals:
    decisions = list(decisions)
    return Totals(
        disputed=money(sum((d.disputed for d in decisions), ZERO)),
        accepted=money(sum((d.accepted for d in decisions), ZERO)),
        questions=sum(1 for d in decisions if d.kind == DecisionKind.ASK),
        skipped=sum(1 for d in decisions if d.kind == DecisionKind.SKIP),
    )


def concession(before: Decision, after: Decision) -> Decimal:
    """What the Negotiator gives back after a valid new document: the drop in the disputed amount."""
    return max(ZERO, money(before.disputed - after.disputed))


def needs_controller(amount: Decimal, policy: Policy) -> bool:
    """Credit memos above the policy limit need the controller (never the owner or an agent)."""
    return money(amount) > policy.controller_approval_over
