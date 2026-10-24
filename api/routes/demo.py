"""Demo controls. Stub: resets the in-memory portal thread and approvals only (no database or QuickBooks yet)."""

from fastapi import APIRouter

from api import pipeline
from api.routes import approvals, portal

router = APIRouter(tags=["demo"])


@router.post("/demo/reset")
def reset() -> dict:
    portal.reset()
    approvals.reset()
    pipeline.reset()  # live runs, open questions and saved rules
    return {"ok": True, "stub": True}
