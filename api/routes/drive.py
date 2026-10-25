"""Google Drive (api/drive.py): POST /drive/sync is "Sync now"; GET /drive/status is what the poller last saw.

The shared folder holds every supplier's folders, so a sync looks at all of them; what it reports back is only the
caller's (api/tenancy.py)."""

import asyncio

from fastapi import APIRouter, Depends, Query

from api import drive, tenancy
from api.auth import require_role
from api.contracts import Contract
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["drive"])


class DriveChange(Contract):
    account_id: str
    file: str
    doc_id: str
    version: int
    kind: str
    did: str
    run_id: str | None = None


class DriveSync(Contract):
    ok: bool
    detail: str
    changes: list[DriveChange]


class DriveStatus(Contract):
    configured: bool
    watching: bool
    checked_at: str | None
    changed_at: str | None
    files: int
    problem: str | None
    last: str | None


@router.post("/drive/sync", response_model=DriveSync, dependencies=[Depends(require_role("owner"))])
async def sync_now(full: bool = Query(default=False, description="walk the whole folder again"),
                   who: Caller = Depends(current_supplier)) -> DriveSync:
    result = await asyncio.to_thread(drive.sync, None, full)
    mine = [DriveChange(**o.__dict__) for o in result.outcomes if tenancy.can_see(who, o.account_id)]
    return DriveSync(ok=result.ok, detail=result.detail, changes=mine)


@router.get("/drive/status", response_model=DriveStatus)
def status(who: Caller = Depends(current_supplier)) -> DriveStatus:
    s = drive.STATUS
    return DriveStatus(configured=drive.configured(), watching=bool(drive.poller and drive.poller.running),
                       checked_at=s.checked_at.isoformat() if s.checked_at else None,
                       changed_at=s.changed_at.isoformat() if s.changed_at else None, files=s.files,
                       problem=s.problem, last=s.last if who.everything else None)
