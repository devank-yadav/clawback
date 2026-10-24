"""Demo controls. Stub: resets the in-memory portal thread only (no database or QuickBooks yet)."""

from fastapi import APIRouter

from api.routes import portal

router = APIRouter(tags=["demo"])


@router.post("/demo/reset")
def reset() -> dict:
    portal.reset()
    return {"ok": True, "stub": True}
