"""Suppliers: one brand (the user's workspace) tracking many distributors (docs/design.md, the supplier model).

Each distributor relationship is still one account (api/accounts.py); AccountConfig.supplier groups them, and an
account without one is its own supplier. Which distributors a supplier tracks is a choice the user makes on the home
page; it's kept in state/tracked.json (the VM's mounted state folder), and every relationship is tracked until
untracked. Statuses are plain words from the newest run's events, never money figures.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from api import accounts
from api.contracts import DistributorItem, SupplierItem

_lock = threading.Lock()


def supplier_of(a: accounts.Account) -> str:
    return a.config.supplier or a.id


def _file() -> Path:
    return Path(os.getenv("CLAWBACK_STATE_DIR", "state")) / "tracked.json"


def _untracked() -> dict[str, list[str]]:
    try:
        return json.loads(_file().read_text())
    except (OSError, ValueError):
        return {}


def set_tracked(supplier: str, account_id: str, tracked: bool) -> None:
    with _lock:
        data = _untracked()
        off = set(data.get(supplier, []))
        off.discard(account_id) if tracked else off.add(account_id)
        data[supplier] = sorted(off)
        try:
            _file().parent.mkdir(parents=True, exist_ok=True)
            _file().write_text(json.dumps(data, indent=1))
        except OSError:  # a read-only checkout: the choice lasts until the server restarts
            _MEMORY.update(data)


_MEMORY: dict[str, list[str]] = {}


def _off(supplier: str) -> set[str]:
    return set(_untracked().get(supplier, [])) | set(_MEMORY.get(supplier, []))


def status(a: accounts.Account) -> tuple[str, str, str | None]:
    """(status, plain label, newest run id) from the account's newest invoice-month run."""
    from api import overview

    now = overview.current_run(a)
    if not now.run_id:
        return "waiting_for_payment", "Waiting for the next payment", None
    runs = [e.data for e in now.events if e.type == "run"]
    if runs and runs[-1].status == "failed":
        return "stopped", "The agents stopped; open it to see why", now.run_id
    answered = {e.data.question_id for e in now.events if e.type == "answer"}
    open_questions = [e.data for e in now.events if e.type == "question" and e.data.id not in answered
                      and not getattr(e.data, "closed_at", None)]
    approvals = [e.data for e in now.events if e.type == "approval"]
    waiting = len(open_questions) + (1 if approvals and approvals[-1].status == "pending" else 0)
    if waiting:
        return "needs_you", f"{waiting} decision{'s' if waiting > 1 else ''} for you", now.run_id
    if runs and runs[-1].status in ("started",):
        return "checking", "Agents are checking a payment", now.run_id
    return "settled", "All settled", now.run_id


def items() -> list[SupplierItem]:
    groups: dict[str, list[accounts.Account]] = {}
    for a in accounts.every():
        groups.setdefault(supplier_of(a), []).append(a)
    out = []
    for sid, members in groups.items():
        home = next((a for a in members if a.id == sid), members[0])
        off = _off(sid)
        rows = []
        for a in members:
            st, label, run_id = status(a)
            rows.append(DistributorItem(account_id=a.id, distributor=a.distributor, tracked=a.id not in off,
                                        status=st, status_label=label, latest_run_id=run_id))
        rows.sort(key=lambda r: (not r.tracked, r.account_id != sid))
        out.append(SupplierItem(id=sid, brand=home.brand, distributors=rows))
    return out
