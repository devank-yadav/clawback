"""The admin's approvals: the in-app Yes / No buttons (fallback for the SMS reply), and "Post fair charges like these
automatically from now on" (auto_post), which saves the account's auto-post limit at the memo's amount.

A live run's approvals (AP-run-…) are decided in api/pipeline.py; the recorded fixture's AP-1 still works for
screens built against web/fixtures.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api import accounts, pipeline, tenancy
from api.auth import require_role
from api.contracts import Approval, ApprovalDecisionRequest, ApprovalDecisionResponse, InboxResponse
from api.stubs import fixtures
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["approvals"])

_approvals: dict[str, Approval] = {}


def reset() -> None:
    _approvals.clear()
    for e in fixtures.march_run().events:
        if e.type == "approval" and e.data.status == "pending":
            _approvals[e.data.id] = e.data


reset()


@router.post("/approvals/{approval_id}", response_model=ApprovalDecisionResponse,
             dependencies=[Depends(require_role("owner"))])
def decide(approval_id: str, req: ApprovalDecisionRequest, who: Caller = Depends(current_supplier)) -> ApprovalDecisionResponse:
    """Approve posts the credit memo to QuickBooks; refuse posts nothing and keeps the note for the card."""
    found = pipeline.find_approval(approval_id)
    if found and not tenancy.can_see(who, found[0].account):
        raise HTTPException(404, f"unknown approval {approval_id}")
    if not found and not tenancy.can_see(who, accounts.DEFAULT):  # the recorded fixture's AP-1 is Peak Bar's
        raise HTTPException(404, f"unknown approval {approval_id}")
    if found:
        try:
            approval, posts = pipeline.decide_approval(approval_id, req.approve, req.note, req.auto_post)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        memo = next((p for p in posts if p.qbo_entity == "credit_memo"), None)
        return ApprovalDecisionResponse(approval=approval, ledger_post=memo, ledger_posts=posts)
    approval = _approvals.get(approval_id)
    if approval is None:
        raise HTTPException(404, f"unknown approval {approval_id}")
    if approval.status != "pending":
        raise HTTPException(409, f"{approval_id} is already {approval.status}")
    now = datetime.now(timezone.utc)
    decided = approval.model_copy(update={"status": "approved" if req.approve else "refused", "note": req.note,
                                          "decided_at": now})
    _approvals[approval_id] = decided
    return ApprovalDecisionResponse(approval=decided,
                                    ledger_post=fixtures.credit_memo(posted_at=now) if req.approve else None)


@router.get("/inbox", response_model=InboxResponse)
def inbox(who: Caller = Depends(current_supplier)) -> InboxResponse:
    """What waits on the admin (Dana) right now (the /inbox screen, and the fallback when texts don't arrive)."""
    only = tenancy.supplier_filter(who)
    questions, approvals = pipeline.inbox(only)
    return InboxResponse(questions=questions, approvals=approvals, messages=pipeline.owner_messages(only))
