"""Clawback API. Until the pipeline lands, every route serves the fixture run in api/stubs/fixtures.py."""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import audit, demo, eval, portal, runs, scenario, webhooks

load_dotenv()

app = FastAPI(title="Clawback API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in ["http://localhost:3000", os.getenv("PUBLIC_BASE_URL")] if o],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (runs, portal, webhooks, scenario, eval, audit, demo):
    app.include_router(r.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "demo_mode": os.getenv("DEMO_MODE", "false").lower() == "true", "stub": True}
