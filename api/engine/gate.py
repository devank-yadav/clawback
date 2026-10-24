"""The decision gate (F5): docs/design.md, "Decision gate". Nine rows, first matching row wins, plus row 10 for a
deal's dispute window, checked right after rows 1 and 2:

10. The deal's dispute window has closed and the charge is more than the match tolerance off the deal (or can't be
    checked): Accept, with a note. The other side can refuse a late dispute outright, so filing only costs goodwill,
    and asking the owner can't bring the window back. The note says what the deal would have allowed, for next time.
    A window still open but closing within policy.dispute_window_warn_days doesn't ask either: the decision stands
    and its reason says the date to file by, since a question would eat into the days left.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from typing import Iterable

from api.engine.rules import evaluate, find_rule, match_rule
from api.engine.types import (
    Allowance,
    Charge,
    Decision,
    DecisionKind,
    Finding,
    Policy,
    Rule,
    RuleMatch,
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


def discretion_terms(allowance: Allowance, policy: Policy) -> list[Term]:
    """The discretionary terms the charge depends on. None when the engine found the fee isn't owed at all (out of its
    scope, or a remedy for a failure the supplier didn't make): no one's discretion can make it owed."""
    if allowance.facts.get("not_owed"):
        return []
    return [t for t in allowance.terms if uses_discretion(t, policy)]


def decide(
    charge: Charge,
    allowance: Allowance,
    finding: Finding | None,
    policy: Policy,
    rules: Iterable[Rule] = (),
    matches: Iterable[RuleMatch] = (),
) -> Decision:
    """`matches` are Moss's candidate rules for the charge's discretion clause (rows 3 and 4); without one that
    clears policy.rule_match_similarity, the exact match on term type + counterparty decides."""
    d = _decide(charge, allowance, finding, policy, rules, matches)
    left = allowance.facts.get("dispute_days_left")
    if left is not None and 0 <= left <= policy.dispute_window_warn_days and d.kind != DecisionKind.ACCEPT:
        closes = allowance.facts["dispute_window_closes"]
        d = replace(d, reason=f"{d.reason} File by {closes:%b} {closes.day}: the dispute window closes in {left} days.")
    return d


def _decide(
    charge: Charge,
    allowance: Allowance,
    finding: Finding | None,
    policy: Policy,
    rules: Iterable[Rule] = (),
    matches: Iterable[RuleMatch] = (),
) -> Decision:
    rules = list(rules)

    def out(kind: DecisionKind, row: int, reason: str, disputed=ZERO, accepted=ZERO, rule_id=None,
            similarity=None) -> Decision:
        return Decision(charge.id, kind, money(disputed), money(accepted), row, rule_id, reason, similarity)

    taken, allowed, delta = allowance.taken, allowance.allowed, allowance.delta

    # Row 1: a term the charge depends on failed the quote check.
    if any(t.status == TermStatus.REJECTED for t in allowance.terms):
        return out(DecisionKind.SKIP, 1, "Can't verify the deal: a term's quote was not found in the source.")

    # Row 2: the two readers disagree on a term.
    if any(t.status == TermStatus.DISPUTED for t in allowance.terms):
        return out(DecisionKind.ASK, 2, "The two deal readers disagree on a term this charge depends on.")

    # Row 10: the dispute window has closed.
    if allowance.facts.get("past_dispute_window") and (allowance.missing or delta > policy.match_tolerance):
        closed = allowance.facts.get("dispute_window_closes")
        when = f" on {closed:%b} {closed.day}, {closed.year}" if closed else ""
        note = "" if allowance.missing else f"; the deal allows ${allowed:,}, ${delta:,} less"
        return out(DecisionKind.ACCEPT, 10, f"Past the dispute window (it closed{when}): accepted and noted{note}.",
                   accepted=taken)

    # Rows 3 and 4: discretion.
    discretion = discretion_terms(allowance, policy)
    if discretion:
        term = discretion[0]
        matched = match_rule(rules, matches, term.type, charge.counterparty, policy.rule_match_similarity)
        rule, similarity = matched if matched else (find_rule(rules, term.type, charge.counterparty), None)
        if rule is None:
            return out(DecisionKind.ASK, 4, "The deal leaves this to discretion and no saved rule covers it.")
        verdict, name = evaluate(rule, allowance.facts), rule.label or rule.id
        if verdict == DecisionKind.ACCEPT:
            if delta > policy.match_tolerance:  # e.g. a fee above the deal's maximum: accept only up to it
                return out(DecisionKind.SPLIT, 3, f"Applied {name}; the part above the deal is disputed.",
                           disputed=delta, accepted=allowed, rule_id=rule.id, similarity=similarity)
            return out(DecisionKind.ACCEPT, 3, f"Applied {name}.", accepted=taken, rule_id=rule.id, similarity=similarity)
        if verdict == DecisionKind.DISPUTE:
            firm = min(taken, allowance.firm) if allowance.firm is not None else ZERO
            if firm > 0:  # only the discretionary part is disputed; the cost under it is owed either way
                return out(DecisionKind.SPLIT, 3, f"Applied {name}: the discretionary fee is disputed, the rest accepted.",
                           disputed=taken - firm, accepted=firm, rule_id=rule.id, similarity=similarity)
            return out(DecisionKind.DISPUTE, 3, f"Applied {name}.", disputed=taken, rule_id=rule.id, similarity=similarity)
        return out(DecisionKind.ASK, 3, f"{name} says to ask.", rule_id=rule.id, similarity=similarity)

    # A fee the deal says needs backup, and no backup came: a person looks before anything is accepted or filed.
    if allowance.facts.get("missing_proof"):
        return out(DecisionKind.ASK, 9, f"The deal requires backup for this fee and none came for "
                                        f"{', '.join(allowance.facts['missing_proof'])}.")

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
        firm = min(taken, allowance.firm) if cap_at_deal and allowance.firm is not None else ZERO
        if firm > 0:  # a discretionary fee on top of a cost: the owner disputes the fee, the cost stays owed
            return Decision(charge.id, DecisionKind.SPLIT, money(taken - firm), money(firm), gate_row, None,
                            "Owner chose to dispute the discretionary fee; the cost under it is accepted.")
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
