"""Runs, the live event stream, the evidence drawer, owner answers and the read-only summary."""

import asyncio
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.contracts import (
    AnswerRequest, AnswerResponse, ChargeDetail, Evidence, RunFixture, StartRunRequest, StartRunResponse, Summary,
)
from api.stubs import fixtures

router = APIRouter(tags=["runs"])


def _runs() -> dict[str, RunFixture]:
    return {f.run_id: f for f in (fixtures.march_run(), fixtures.april_run())}


def _start(kind: str) -> StartRunResponse:
    run_id = fixtures.MARCH_RUN if kind == "march" else fixtures.APRIL_RUN
    return StartRunResponse(run_id=run_id, events_url=f"/runs/{run_id}/events")


@router.post("/runs", response_model=StartRunResponse)
def start_run(req: StartRunRequest | None = None) -> StartRunResponse:
    return _start((req or StartRunRequest()).kind)


@router.post("/replay/april", response_model=StartRunResponse)
def replay_april() -> StartRunResponse:
    return _start("april")


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    request: Request,
    last_event_id: int | None = Header(default=None),
    after: int | None = Query(default=None, description="Same as Last-Event-ID, for curl and tests"),
    delay_ms: int = Query(default=400, ge=0, le=5000),
    keepalive: bool = Query(default=True, description="Hold the stream open after the last event"),
) -> StreamingResponse:
    run = _runs().get(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id}")
    start_after = after if after is not None else (last_event_id or 0)

    async def stream() -> AsyncIterator[str]:
        yield "retry: 2000\n\n"
        for ev in run.events:
            if ev.id <= start_after:
                continue
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            yield f"id: {ev.id}\ndata: {ev.model_dump_json()}\n\n"
        while keepalive and not await request.is_disconnected():
            await asyncio.sleep(15)
            yield ": keep-alive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/charges/{charge_id}", response_model=ChargeDetail)
def charge_detail(charge_id: str) -> ChargeDetail:
    for run in _runs().values():
        if charge_id in run.charges:
            return run.charges[charge_id]
    raise HTTPException(404, f"unknown charge {charge_id}")


@router.get("/evidence/{evidence_id}", response_model=Evidence)
def evidence(evidence_id: str) -> Evidence:
    ev = fixtures.EVIDENCE.get(evidence_id)
    if ev is None:
        raise HTTPException(404, f"unknown evidence {evidence_id}")
    return ev


@router.post("/questions/{question_id}/answer", response_model=AnswerResponse)
def answer_question(question_id: str, req: AnswerRequest) -> AnswerResponse:
    run = fixtures.march_run()
    answer = next((e.data for e in run.events if e.type == "answer" and e.data.question_id == question_id), None)
    if answer is None:
        raise HTTPException(404, f"no open question {question_id}")
    rule = next((e.data for e in run.events if e.type == "rule"), None)
    return AnswerResponse(answer=answer.model_copy(update={"text": req.text, "from_role": req.from_role}), rule=rule)


@router.get("/summary", response_model=Summary)
def summary(authorization: str | None = Header(default=None)) -> Summary:
    token = os.getenv("CLAWBACK_READONLY_TOKEN")
    if not token:
        raise HTTPException(503, "CLAWBACK_READONLY_TOKEN is not set")
    if authorization != f"Bearer {token}":
        raise HTTPException(401, "bad token")
    return fixtures.summary()
