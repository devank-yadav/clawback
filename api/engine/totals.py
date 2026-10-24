"""The board's meters and the remittance totals. Plain sums over engine results; nothing else adds money."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal

from api.engine.types import Charge, Decision, DecisionKind, money

ZERO = Decimal(0)


def taken(charges: Iterable[Charge]) -> Decimal:
    return money(sum((c.amount for c in charges), ZERO))


def remittance_short(expected: Decimal, received: Decimal) -> Decimal:
    return money(money(expected) - money(received))


def meters(charges: Mapping[str, Charge], decisions: Mapping[str, Decision]) -> dict[str, Decimal | int]:
    """taken = disputed + accepted + waiting + undecided. A charge in Ask is waiting; skipped stays undecided."""
    total = taken(charges.values())
    disputed = money(sum((d.disputed for d in decisions.values()), ZERO))
    accepted = money(sum((d.accepted for d in decisions.values()), ZERO))
    waiting = money(sum((charges[cid].amount for cid, d in decisions.items() if d.kind == DecisionKind.ASK), ZERO))
    return {"taken": total, "disputed": disputed, "accepted": accepted, "waiting": waiting,
            "undecided": money(total - disputed - accepted - waiting),
            "skipped": sum(1 for d in decisions.values() if d.kind == DecisionKind.SKIP)}


def total_of(amounts: Iterable[Decimal]) -> Decimal:
    """For dispute totals and credit memos: the sum of their lines."""
    return money(sum((money(a) for a in amounts), ZERO))
