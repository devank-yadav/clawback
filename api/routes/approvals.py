"""Controller approvals: the in-app Yes / No buttons (fallback for the SMS reply). Stub: decides AP-1 once."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.contracts import Approval, ApprovalDecisionRequest, ApprovalDecisionResponse
from api.stubs import fixtures

router = APIRouter(tags=["approvals"])

_approvals: dict[str, Approval] = {}


def reset() -> None:
    _approvals.clear()
    for e in fixtures.march_run().events:
        if e.type == "approval" and e.data.status == "pending":
            _approvals[e.data.id] = e.data


reset()


@router.post("/approvals/{approval_id}", response_model=ApprovalDecisionResponse)
def decide(approval_id: str, req: ApprovalDecisionRequest) -> ApprovalDecisionResponse:
    """Approve posts the credit memo; refuse posts nothing and keeps the note for the card."""
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
