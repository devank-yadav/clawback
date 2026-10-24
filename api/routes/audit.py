"""Audit log and its hash-chain check: the live runs' chain (api/audit.py), or the recorded fake run's before any."""

from fastapi import APIRouter

from api import audit
from api.contracts import AuditEntry, AuditVerify
from api.engine import audit_chain
from api.stubs import fixtures

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditEntry])
def audit_log() -> list[AuditEntry]:
    if audit.entries():
        return [AuditEntry.model_validate(e.as_row()) for e in audit.entries()]
    return fixtures.audit()


@router.get("/audit/verify", response_model=AuditVerify)
def verify() -> AuditVerify:
    """The "Verify chain" button: recompute every hash; an edited, missing or reordered row breaks it."""
    check = audit.verify() if audit.entries() else audit_chain.verify(fixtures.audit_chain_rows())
    return AuditVerify(ok=check.ok, checked=check.checked, broken_at=check.broken_at, reason=check.reason)
