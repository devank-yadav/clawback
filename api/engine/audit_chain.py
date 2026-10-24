"""Append-only audit log with a sha256 hash chain (docs/design.md, F18 and the `audit_log` table).

Each entry's hash covers its own fields and the previous entry's hash, so editing, deleting or reordering any
past row breaks every hash after it. `verify` recomputes the chain from rows read back from the database.

Store `at` as the ISO string this module produces and `evidence` as JSON; the hash is computed over the
canonical JSON of {id, at, actor, action, object_ref, evidence, prev_hash}. Decimals in evidence are hashed as
strings, so keep money as strings in evidence ("1540.00") so the row hashes the same after a database round trip.
Truncating the newest rows is only caught if the caller keeps the head hash somewhere else (`expected_head`).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping

GENESIS = "0" * 64
FIELDS = ("id", "at", "actor", "action", "object_ref", "evidence", "prev_hash")


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable in audit evidence: {type(value).__name__}")


def canonical(row: Mapping[str, Any]) -> bytes:
    """Stable bytes for the hashed fields: sorted keys, no spaces, UTF-8."""
    body = {k: row[k] for k in FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default).encode()


def compute_hash(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(row)).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    id: int
    at: str
    actor: str        # e.g. "gate", "negotiator", "owner:Dana", "controller:Sam"
    action: str       # e.g. "decision", "dispute_filed", "credit_memo_approved"
    object_ref: str   # e.g. "charge:C4", "dispute:D-0417"
    evidence: dict[str, Any]
    prev_hash: str
    hash: str

    def as_row(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in (*FIELDS, "hash")}


@dataclass
class AuditChain:
    """In-memory chain. Only `append` adds rows; nothing edits or removes them."""
    _entries: list[AuditEntry] = field(default_factory=list)

    @property
    def entries(self) -> tuple[AuditEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].hash if self._entries else GENESIS

    def append(self, actor: str, action: str, object_ref: str, evidence: Mapping[str, Any] | None = None,
               at: datetime | str | None = None) -> AuditEntry:
        if at is None:
            at = datetime.now(timezone.utc)
        row = {
            "id": len(self._entries) + 1,
            "at": at.isoformat() if isinstance(at, datetime) else at,
            "actor": actor,
            "action": action,
            "object_ref": object_ref,
            # Round-trip through canonical JSON so later edits to the caller's dict can't touch the entry.
            "evidence": json.loads(json.dumps(copy.deepcopy(dict(evidence or {})), default=_default)),
            "prev_hash": self.head,
        }
        entry = AuditEntry(**row, hash=compute_hash(row))
        self._entries.append(entry)
        return entry


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    checked: int
    broken_at: int | None = None  # id of the first bad row (or of the position where a row is missing)
    reason: str = ""


def _get(row: AuditEntry | Mapping[str, Any], key: str) -> Any:
    return getattr(row, key) if isinstance(row, AuditEntry) else row[key]


def verify(rows: Iterable[AuditEntry | Mapping[str, Any]], expected_head: str | None = None) -> ChainCheck:
    """Walk rows in id order and recompute every hash. Returns the first break found."""
    prev = GENESIS
    n = 0
    for n, row in enumerate(rows, start=1):
        r = {k: _get(row, k) for k in (*FIELDS, "hash")}
        if r["id"] != n:
            return ChainCheck(False, n - 1, n, f"expected row id {n}, found {r['id']} (row missing or reordered)")
        if r["prev_hash"] != prev:
            return ChainCheck(False, n - 1, n, "prev_hash does not match the previous row's hash")
        if compute_hash(r) != r["hash"]:
            return ChainCheck(False, n - 1, n, "row content does not match its hash (row edited)")
        prev = r["hash"]
    if expected_head is not None and prev != expected_head:
        return ChainCheck(False, n, n + 1, "chain ends early: head hash differs from the saved head")
    return ChainCheck(True, n)


__all__ = ["GENESIS", "FIELDS", "canonical", "compute_hash", "AuditEntry", "AuditChain", "ChainCheck", "verify"]
