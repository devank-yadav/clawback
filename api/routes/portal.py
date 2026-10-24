"""Mock Northmart portal. Stub: the thread starts as the fixture run's exchange; replies are canned."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.contracts import PortalMessage, PortalReplyRequest
from api.stubs import fixtures

router = APIRouter(tags=["portal"])

_threads: dict[str, list[PortalMessage]] = {}

AMENDMENT_REPLY = (
    "Thanks. The signed amendment raises the §3.2 cap to 6,000 units, so 1,000 of week 4's 1,540 bars are covered. "
    "We withdraw $1,000 of the week 4 line (C4) and keep $540 disputed."
)
STUB_REPLY = "(stub) Received. Live answers arrive when the Negotiator is wired up."


def reset() -> None:
    _threads.clear()
    _threads[fixtures.DISPUTE_ID] = [e.data for e in fixtures.march_run().events if e.type == "portal_message"]


reset()


def _thread(dispute_id: str) -> list[PortalMessage]:
    if dispute_id not in _threads:
        raise HTTPException(404, f"unknown dispute {dispute_id}")
    return _threads[dispute_id]


@router.get("/portal/disputes/{dispute_id}/messages", response_model=list[PortalMessage])
def list_messages(dispute_id: str) -> list[PortalMessage]:
    return _thread(dispute_id)


@router.post("/portal/disputes/{dispute_id}/messages", response_model=list[PortalMessage])
def post_message(dispute_id: str, req: PortalReplyRequest) -> list[PortalMessage]:
    """Adds Northmart's message and Clawback's reply; returns both."""
    thread = _thread(dispute_id)
    now = datetime.now(timezone.utc)
    amendment = req.attachment_doc_id == "amendment-1"
    theirs = PortalMessage(id=f"PM-{len(thread) + 1}", dispute_id=dispute_id, from_party="northmart", text=req.text,
                           attachment_doc_id=req.attachment_doc_id, created_at=now,
                           classification="new_document" if amendment else None, charge_ids=["C4"] if amendment else [])
    ours = PortalMessage(id=f"PM-{len(thread) + 2}", dispute_id=dispute_id, from_party="clawback",
                         text=AMENDMENT_REPLY if amendment else STUB_REPLY, created_at=now,
                         charge_ids=["C4"] if amendment else [])
    thread += [theirs, ours]
    return [theirs, ours]
