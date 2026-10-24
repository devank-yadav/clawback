"""Demo controls. A reset undoes Clawback's QuickBooks writes (the sandbox goes back to INV-3102 with $6,850 open;
in DEMO_MODE or without keys, the stand-in forgets its own), then clears the in-memory portal thread, approvals,
runs, open questions and saved rules, and forgets the saved runs (their rows leave the events table), so GET
/runs/latest finds none until the next run. The seeded tables aren't touched.

With CLAWBACK_ADMIN_TOKEN set (the deployed site), a reset needs `Authorization: Bearer <token>`, so nobody with
the public URL can wipe the demo mid-pitch. Laptops leave it unset."""

import hmac
import os
from dataclasses import asdict

from fastapi import APIRouter, Header, HTTPException

from api import pipeline
from api import auth
from api.db import events as saved_events
from api.integrations import qbo
from api.routes import approvals, portal

router = APIRouter(tags=["demo"])


@router.post("/demo/reset")
def reset(authorization: str | None = Header(default=None)) -> dict:
    token = os.getenv("CLAWBACK_ADMIN_TOKEN")
    if token and not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(401, "this reset needs the admin token: Authorization: Bearer <CLAWBACK_ADMIN_TOKEN>")
    try:
        undone, error = qbo.books().undo_demo_writes(), None  # before pipeline.reset(), which drops the books
    except Exception as e:  # noqa: BLE001 - a QuickBooks failure still resets the demo; a second reset finishes the job
        undone, error = [], f"{type(e).__name__}: {e}"
    portal.reset()
    approvals.reset()
    pipeline.reset()  # live runs, open questions and saved rules
    auth.reset()  # and the per-IP limits on live runs
    saved_events.reset()  # and the saved runs, which GET /runs/latest would otherwise fall back to
    return {"ok": error is None, "stub": False, "quickbooks": [asdict(u) for u in undone],
            **({"error": error} if error else {})}
