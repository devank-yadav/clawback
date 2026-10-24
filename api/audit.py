"""The audit log for live runs (F18): every decision, question, answer, rule, approval, ledger post, dispute and
portal message, appended to the engine's hash chain (api/engine/audit_chain.py) the moment its event is emitted.

One chain for every run, like the audit_log table it becomes with the database (D3). Rows are never edited or
removed by the app; the head hash is kept apart from the rows, so verify() catches an edited row, a reordered
or missing one, and the newest rows being cut off.
"""

from __future__ import annotations

import threading
from typing import Any

from api import accounts
from api.engine import audit_chain

AUDITED = ("decision", "question", "answer", "rule", "approval", "ledger_post", "dispute", "portal_message")

_lock = threading.Lock()
_chain = audit_chain.AuditChain()
_head = audit_chain.GENESIS  # saved apart from the rows (in production: somewhere the rows can't reach)


def describe(ev: Any, account: accounts.Account | str | None = None) -> tuple[str, str, str]:
    """(actor, action, object_ref) for an audited event of a run of this account (people are "owner:Dana")."""
    a, d = accounts.resolve(account), ev.data

    def _person(role: str) -> str:
        return f"{role}:{a.first_name(role)}"

    match ev.type:
        case "decision":
            return (_person("owner") if d.decided_by == "owner" else "gate", f"decision_{d.decision}", f"charge:{d.charge_id}")
        case "question":
            return "gate", "question_asked", f"question:{d.id}"
        case "answer":
            return _person(d.from_role), "answer_received", f"question:{d.question_id}"
        case "rule":
            return _person("owner"), "rule_saved" if d.status == "active" else f"rule_{d.status}", f"rule:{d.id}"
        case "approval":
            if d.status == "pending":
                return "bookkeeper", "approval_requested", f"approval:{d.id}"
            if d.status == "approved" and d.note and d.note.startswith("Within policy"):
                return "policy", "credit_memo_approved", f"approval:{d.id}"
            return _person("controller"), f"credit_memo_{d.status}", f"approval:{d.id}"
        case "ledger_post":
            return "bookkeeper", f"qbo_{d.qbo_entity}_{d.status}", f"ledger:{d.id}"
        case "dispute":
            return "negotiator", f"dispute_{d.status}", f"dispute:{d.id}"
        case "portal_message":
            return ("northmart" if d.from_party == "northmart" else "negotiator"), "portal_message", f"portal:{d.id}"
    raise ValueError(f"not an audited event: {ev.type}")


def record(ev: Any, account: accounts.Account | str | None = None) -> audit_chain.AuditEntry | None:
    """Append an emitted event to the chain if it's one the audit log keeps. The evidence is the event itself."""
    global _head
    if ev.type not in AUDITED:
        return None
    actor, action, ref = describe(ev, account)
    evidence = {"run_id": ev.run_id, "event_id": ev.id, "data": ev.data.model_dump(mode="python")}
    with _lock:
        entry = _chain.append(actor, action, ref, evidence, at=ev.at)
        _head = entry.hash
    return entry


def entries() -> tuple[audit_chain.AuditEntry, ...]:
    return _chain.entries


def verify(rows=None) -> audit_chain.ChainCheck:
    """Recompute the chain over the stored rows (or given ones) and compare its end with the saved head."""
    return audit_chain.verify(_chain.entries if rows is None else rows, expected_head=_head)


def reset() -> None:
    global _chain, _head
    with _lock:
        _chain, _head = audit_chain.AuditChain(), audit_chain.GENESIS
