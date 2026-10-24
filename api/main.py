"""Clawback API: live runs (api/pipeline.py), plus the recorded fake run for screens built against web/fixtures."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import pipeline
from api.db import events as saved_events
from api.integrations import nessie, replay
from api.routes import approvals, audit, db, demo, eval, payments, portal, runs, scenario, trace, webhooks

load_dotenv()
log = logging.getLogger("clawback")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the Nessie poller (F15) when it can run: keys set, not DEMO_MODE, NESSIE_POLL not "off"."""
    client = nessie.client()
    if client and not replay.demo_mode() and os.getenv("NESSIE_POLL", "on").lower() != "off":
        nessie.poller = nessie.Poller(client, pipeline.start_for_deposit)
        nessie.poller.start()
        log.info("nessie poller started")
    yield
    if nessie.poller:
        nessie.poller.stop()
    saved_events.flush(timeout=5)  # the last events reach the table before a restart


app = FastAPI(title="Clawback API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ["http://localhost:3000", os.getenv("PUBLIC_BASE_URL")] if o],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (runs, payments, portal, approvals, webhooks, scenario, eval, audit, demo, db, trace):
    app.include_router(r.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "demo_mode": replay.demo_mode(), "nessie_poller": bool(nessie.poller and nessie.poller.running)}
