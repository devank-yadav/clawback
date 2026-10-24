"""Audit log and its hash-chain check."""

from fastapi import APIRouter

from api.contracts import AuditEntry, AuditVerify
from api.engine import audit_chain
from api.stubs import fixtures

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditEntry])
def audit_log() -> list[AuditEntry]:
    return fixtures.audit()


@router.get("/audit/verify", response_model=AuditVerify)
def verify() -> AuditVerify:
    check = audit_chain.verify(fixtures.audit_chain_rows())
    return AuditVerify(ok=check.ok, checked=check.checked, broken_at=check.broken_at, reason=check.reason)
