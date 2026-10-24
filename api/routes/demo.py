"""Demo controls. A reset undoes Clawback's QuickBooks writes (the sandbox goes back to INV-3102 with $6,850 open;
in DEMO_MODE or without keys, the stand-in forgets its own), then clears the in-memory portal thread, approvals,
runs, open questions and saved rules, and forgets the saved runs (their rows leave the events table), so GET
/runs/latest finds none until the next run. The seeded tables aren't touched."""

from dataclasses import asdict

from fastapi import APIRouter

from api import pipeline
from api.db import events as saved_events
from api.integrations import qbo
from api.routes import approvals, portal

router = APIRouter(tags=["demo"])


@router.post("/demo/reset")
def reset() -> dict:
    try:
        undone, error = qbo.books().undo_demo_writes(), None  # before pipeline.reset(), which drops the books
    except Exception as e:  # noqa: BLE001 - a QuickBooks failure still resets the demo; a second reset finishes the job
        undone, error = [], f"{type(e).__name__}: {e}"
    portal.reset()
    approvals.reset()
    pipeline.reset()  # live runs, open questions and saved rules
    saved_events.reset()  # and the saved runs, which GET /runs/latest would otherwise fall back to
    return {"ok": error is None, "stub": False, "quickbooks": [asdict(u) for u in undone],
            **({"error": error} if error else {})}
