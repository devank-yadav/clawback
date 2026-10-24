"""What one run was worth: the money it sorted, how fast, what the AI cost, and the manual work it stands in for.

Plain code, no AI. The amounts are the meters' (totals.py) and the AI numbers the run's trace (api/trace.py); this
module only puts them side by side. The manual comparison is charges x policy.yaml `manual_minutes_per_charge`, and
stays None while that key is unset: no made-up baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from api.engine.types import money


@dataclass(frozen=True)
class RunValue:
    disputed: Decimal
    accepted: Decimal
    questions: int
    charges: int
    seconds_to_decided: float | None  # the run's first event to the end of the gate's first pass
    ai_calls: int
    ai_cost_usd: Decimal | None  # None: a live call couldn't be priced
    manual_minutes: Decimal | None  # charges x manual_minutes_per_charge; None when the policy sets no figure
    manual_minutes_per_charge: Decimal | None


def run_value(disputed: Decimal, accepted: Decimal, questions: int, charges: int, *,
              seconds_to_decided: float | None = None, ai_calls: int = 0, ai_cost_usd: Decimal | float | None = None,
              manual_minutes_per_charge: Decimal | float | int | None = None) -> RunValue:
    per = None if manual_minutes_per_charge is None else Decimal(str(manual_minutes_per_charge))
    return RunValue(
        disputed=money(disputed), accepted=money(accepted), questions=questions, charges=charges,
        seconds_to_decided=None if seconds_to_decided is None else round(seconds_to_decided, 1),
        ai_calls=ai_calls,
        ai_cost_usd=None if ai_cost_usd is None else Decimal(str(ai_cost_usd)).quantize(Decimal("0.000001")),
        manual_minutes=None if per is None else per * charges,
        manual_minutes_per_charge=per,
    )
