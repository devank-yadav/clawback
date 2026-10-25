"""Audit log and its hash-chain check: the live runs' chain (api/audit.py), or the recorded fake run's before any."""

from fastapi import Depends, APIRouter

from api import accounts, audit, tenancy
from api.contracts import AuditEntry, AuditVerify
from api.engine import audit_chain
from api.stubs import fixtures
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["audit"])


def _mine(who: Caller, entry) -> bool:
    """An entry of one of the caller's runs (each entry's evidence names its run)."""
    if who.everything:
        return True
    run_id = (entry.evidence or {}).get("run_id")
    return bool(run_id) and tenancy.can_see_run(who, run_id)


@router.get("/audit", response_model=list[AuditEntry])
def audit_log(who: Caller = Depends(current_supplier)) -> list[AuditEntry]:
    if audit.entries():
        return [AuditEntry.model_validate(e.as_row()) for e in audit.entries() if _mine(who, e)]
    return fixtures.audit() if tenancy.can_see(who, accounts.DEFAULT) else []


@router.get("/audit/verify", response_model=AuditVerify)
def verify(who: Caller = Depends(current_supplier)) -> AuditVerify:
    """The "Verify chain" button: recompute every hash; an edited, missing or reordered row breaks it."""
    check = audit.verify() if audit.entries() else audit_chain.verify(fixtures.audit_chain_rows())
    return AuditVerify(ok=check.ok, checked=check.checked, broken_at=check.broken_at, reason=check.reason)
