"""Autopilot: the limits a supplier's owner sets once, on Settings, so the agents run without being driven.

- run_on_arrival: a payment that comes in (the bank or QuickBooks pollers, "Check for new payments", a distributor's
  portal) starts the agents at once, instead of waiting for "Run the agents". On by default.
- send_disputes_under: a dispute whose total is at or under this is emailed to the distributor without the owner's
  review (still only within policy.yaml's auto_dispute_limit, and only if it passes every check). None: always review.
- post_fair_under: a credit memo for fair charges at or under this posts to QuickBooks without asking (an account's own
  auto-post limit, set by ticking the box on an approval, still wins). None: always ask.
- digest_email / digest_weekly: where the weekly summary goes (api/digest.py), and whether it goes every Monday.

Kept per supplier in a JSON file in the state folder (CLAWBACK_STATE_DIR, default ./state, a docker volume on the VM),
so a restart or a redeploy keeps them. A demo reset leaves them alone: they are the owner's settings, not run state.
"""

import json
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from api.contracts import Contract, Money

_lock = threading.Lock()


class Autopilot(Contract):
    run_on_arrival: bool = True
    send_disputes_under: Money | None = None
    post_fair_under: Money | None = None
    digest_email: str | None = None
    digest_weekly: bool = True
    digest_last_sent: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


def _file() -> Path:
    return Path(os.getenv("CLAWBACK_STATE_DIR", "state")) / "autopilot.json"


def _load() -> dict[str, dict]:
    try:
        return json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}


def get(supplier_id: str) -> Autopilot:
    with _lock:
        raw = _load().get(supplier_id)
    return Autopilot.model_validate(raw) if raw else Autopilot()


def save(supplier_id: str, settings: Autopilot) -> Autopilot:
    with _lock:
        data = _load()
        data[supplier_id] = json.loads(settings.model_dump_json())
        path = _file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)
    return settings


def update(supplier_id: str, by: str | None, **changes) -> Autopilot:
    current = get(supplier_id)
    return save(supplier_id, current.model_copy(update={**changes, "updated_by": by, "updated_at": datetime.now(timezone.utc)}))


def every() -> dict[str, Autopilot]:
    with _lock:
        return {sid: Autopilot.model_validate(raw) for sid, raw in _load().items()}


def of_account(account) -> Autopilot:
    """The settings of the supplier an account belongs to."""
    from api import suppliers

    return get(suppliers.supplier_of(account))


def sends_dispute(account, total: Decimal) -> bool:
    limit = of_account(account).send_disputes_under
    return limit is not None and total <= limit
