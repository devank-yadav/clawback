"""Clawback API: live runs (api/pipeline.py), plus the recorded fake run for screens built against web/fixtures."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import pipeline
from api.db import events as saved_events, state as saved_state
from api.integrations import nessie, qbo_source, replay
from api.routes import accounts, approvals, suppliers, audit, db, demo, eval, payments, portal, runs, scenario, trace, webhooks
from api.routes import remittance as remittance_routes
from api.routes import auth as auth_routes
from api.routes import dispute_mail
from api.routes import drive as drive_routes
from api import drive

load_dotenv()
log = logging.getLogger("clawback")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Bring back the saved rules and audit chain (api/db/state.py), and start the pollers that can run: Nessie's (F15;
    keys set, not DEMO_MODE, NESSIE_POLL not "off") and QuickBooks' payments (api/integrations/qbo_source.py; the QBO_*
    keys, not DEMO_MODE, QBO_POLL not "off"). The remittance inbox is a webhook (POST /webhooks/inbound-email)."""
    saved_state.restore()
    client = nessie.client()
    if client and not replay.demo_mode() and os.getenv("NESSIE_POLL", "on").lower() != "off":
        nessie.poller = nessie.Poller(client, pipeline.start_for_deposit)
        nessie.poller.start()
        log.info("nessie poller started")
    if qbo_source.start_poller(lambda p: pipeline.start_for_deposit(p, account=p.account_id)):
        log.info("quickbooks payments poller started")
    if drive.start_poller():
        log.info("google drive poller started")
    yield
    if drive.poller:
        drive.poller.stop()
    if nessie.poller:
        nessie.poller.stop()
    if qbo_source.poller:
        qbo_source.poller.stop()
    saved_events.flush(timeout=5)  # the last events reach the table before a restart


app = FastAPI(title="Clawback API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ["http://localhost:3000", os.getenv("PUBLIC_BASE_URL")] if o],
    allow_credentials=True,  # the session cookie (api/routes/auth.py); origins stay explicit
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (runs, payments, portal, approvals, webhooks, scenario, eval, audit, demo, db, trace, accounts, suppliers):
    app.include_router(r.router)
app.include_router(remittance_routes.router)  # bring in a remittance advice (api/remittance.py)
app.include_router(auth_routes.router)  # sign-in (api/users.py)
app.include_router(drive_routes.router)  # Google Drive: Sync now, status (api/drive.py)
app.include_router(dispute_mail.router)  # dispute email: review, send, thread (api/dispute_email.py)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "demo_mode": replay.demo_mode(), "nessie_poller": bool(nessie.poller and nessie.poller.running),
            "qbo_poller": bool(qbo_source.poller and qbo_source.poller.running)}
