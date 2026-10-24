"""Mock Northmart portal. A dispute filed by a live run (api/pipeline.py) is answered by api/disputes.py.

Without a live run, the fixture thread plays: it starts as the fixture run's exchange and replies are canned.

Attaching amendment-1 plays the fixture concession (web/fixtures/amendment-events.json): the dispute's C4 line
drops to $540, and the run's event stream and GET /charges/C4 show the new decision.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api import disputes
from api.auth import limit
from api.contracts import Dispute, PortalMessage, PortalPreset, PortalReplyRequest
from api.stubs import fixtures

router = APIRouter(tags=["portal"])

STUB_REPLY = "(stub) Received. Live answers arrive when the Negotiator is wired up."

_threads: dict[str, list[PortalMessage]] = {}
_disputes: dict[str, Dispute] = {}
_amendment_attached = False


def reset() -> None:
    global _amendment_attached
    _amendment_attached = False
    disputes.reset()
    _threads.clear()
    _threads[fixtures.DISPUTE_ID] = [e.data for e in fixtures.march_run().events if e.type == "portal_message"]
    _disputes.clear()
    _disputes[fixtures.DISPUTE_ID] = fixtures.filed_dispute()


reset()


def amendment_attached() -> bool:
    return _amendment_attached


def _thread(dispute_id: str) -> list[PortalMessage]:
    if dispute_id not in _threads:
        raise HTTPException(404, f"unknown dispute {dispute_id}")
    return _threads[dispute_id]


@router.get("/portal/presets", response_model=list[PortalPreset])
def presets() -> list[PortalPreset]:
    return disputes.PRESETS


@router.get("/portal/disputes/{dispute_id}", response_model=Dispute)
def get_dispute(dispute_id: str) -> Dispute:
    if live := disputes.find(dispute_id):
        return live[1]
    if dispute_id not in _disputes:
        raise HTTPException(404, f"unknown dispute {dispute_id}")
    return _disputes[dispute_id]


@router.get("/portal/disputes/{dispute_id}/messages", response_model=list[PortalMessage])
def list_messages(dispute_id: str) -> list[PortalMessage]:
    if disputes.find(dispute_id):
        return disputes.thread(dispute_id)
    return _thread(dispute_id)


@router.post("/portal/disputes/{dispute_id}/messages", response_model=list[PortalMessage],
             dependencies=[Depends(limit("ai"))])
def post_message(dispute_id: str, req: PortalReplyRequest) -> list[PortalMessage]:
    """Adds Northmart's message and Clawback's reply; returns both (or only Northmart's when it's held)."""
    global _amendment_attached
    if disputes.find(dispute_id):
        return disputes.post(dispute_id, req.text, req.attachment_doc_id)
    thread = _thread(dispute_id)
    now = datetime.now(timezone.utc)
    ids = {"id": f"PM-{len(thread) + 1}"}, {"id": f"PM-{len(thread) + 2}"}
    if req.attachment_doc_id == "amendment-1" and not _amendment_attached:
        _amendment_attached = True
        _disputes[dispute_id] = fixtures.amended_dispute()
        canned = [e.data for e in fixtures.amendment_run().events if e.type == "portal_message"]
        theirs = canned[0].model_copy(update={**ids[0], "text": req.text, "created_at": now})
        ours = canned[1].model_copy(update={**ids[1], "created_at": now})
    else:
        theirs = PortalMessage(**ids[0], dispute_id=dispute_id, from_party="northmart", text=req.text,
                               attachment_doc_id=req.attachment_doc_id, created_at=now)
        ours = PortalMessage(**ids[1], dispute_id=dispute_id, from_party="clawback", text=STUB_REPLY, created_at=now)
    thread += [theirs, ours]
    return [theirs, ours]
