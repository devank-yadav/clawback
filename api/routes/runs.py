"""Runs, the live event stream, the evidence drawer, owner answers and the read-only summary.

Live runs come from api/pipeline.py (POST /runs). The recorded fake runs (run-march-demo, run-april-demo,
run-march-refused) still replay for screens built against web/fixtures.
"""

import asyncio
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from api.contracts import (
    AnswerRequest, AnswerResponse, ChargeDetail, Evidence, RunFixture, StartRunRequest, StartRunResponse, Summary,
)
from api import pipeline
from api.routes import portal
from api.stubs import fixtures

router = APIRouter(tags=["runs"])


def _runs() -> dict[str, RunFixture]:
    return {f.run_id: f for f in (fixtures.march_run(), fixtures.refused_run(), fixtures.april_run())}


def _events(run: RunFixture) -> list:
    """The run's events so far; the March run grows once the judge attaches amendment-1 on the portal."""
    if run.run_id == fixtures.MARCH_RUN and portal.amendment_attached():
        return run.events + fixtures.amendment_run().events
    return run.events


def _start(kind: str, fixture: bool) -> StartRunResponse:
    if fixture:
        run_id = fixtures.MARCH_RUN if kind == "march" else fixtures.APRIL_RUN
    else:
        run_id = pipeline.start(kind).id
    return StartRunResponse(run_id=run_id, events_url=f"/runs/{run_id}/events")


@router.post("/runs", response_model=StartRunResponse)
def start_run(req: StartRunRequest | None = None) -> StartRunResponse:
    req = req or StartRunRequest()
    return _start(req.kind, req.fixture)


@router.post("/replay/april", response_model=StartRunResponse)
def replay_april(fixture: bool = Query(default=False)) -> StartRunResponse:
    return _start("april", fixture)


def _latest_live(has: str) -> pipeline.Run | None:
    """The newest live run that holds this charge or evidence ID."""
    for run in reversed(list(pipeline.RUNS.values())):
        if has in run.charges or has in run.evidence:
            return run
    return None


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    request: Request,
    last_event_id: int | None = Header(default=None),
    after: int | None = Query(default=None, description="Same as Last-Event-ID, for curl and tests"),
    delay_ms: int = Query(default=400, ge=0, le=5000),
    keepalive: bool = Query(default=True, description="Hold the stream open after the last event"),
) -> StreamingResponse:
    live = pipeline.RUNS.get(run_id)
    run = live or _runs().get(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id}")
    start_after = after if after is not None else (last_event_id or 0)
    pending = (lambda sent: live.events_after(sent)) if live else (lambda sent: [e for e in _events(run) if e.id > sent])
    pace = 0 if live else delay_ms  # a live run is paced by the work itself

    async def stream() -> AsyncIterator[str]:
        yield "retry: 2000\n\n"
        sent, idle = start_after, 0
        while True:
            for ev in pending(sent):
                if pace:
                    await asyncio.sleep(pace / 1000)
                yield f"id: {ev.id}\ndata: {ev.model_dump_json()}\n\n"
                sent, idle = ev.id, 0
            if not keepalive or await request.is_disconnected():
                return
            await asyncio.sleep(0.25 if live else 1)  # live: the pipeline is still working; fixture: the amendment
            idle += 1
            if idle % 15 == 0:
                yield ": keep-alive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/charges/{charge_id}", response_model=ChargeDetail)
def charge_detail(charge_id: str, run_id: str | None = Query(default=None)) -> ChargeDetail:
    live = pipeline.RUNS.get(run_id) if run_id else _latest_live(charge_id)
    if live and charge_id in live.charges:
        return live.detail(charge_id)
    if portal.amendment_attached() and charge_id in fixtures.amendment_run().charges:
        return fixtures.amendment_run().charges[charge_id]
    for run in _runs().values():
        if charge_id in run.charges:
            return run.charges[charge_id]
    raise HTTPException(404, f"unknown charge {charge_id}")


@router.get("/evidence/{evidence_id}", response_model=Evidence)
def evidence(evidence_id: str, run_id: str | None = Query(default=None)) -> Evidence:
    live = pipeline.RUNS.get(run_id) if run_id else _latest_live(evidence_id)
    if live and evidence_id in live.evidence:
        return live.evidence[evidence_id]
    ev = fixtures.EVIDENCE.get(evidence_id)
    if ev is None:
        raise HTTPException(404, f"unknown evidence {evidence_id}")
    return ev


@router.post("/questions/{question_id}/answer", response_model=AnswerResponse)
def answer_question(question_id: str, req: AnswerRequest) -> AnswerResponse:
    if question_id in pipeline.QUESTIONS:
        ans, rule = pipeline.answer(question_id, req.text, req.from_role)
        return AnswerResponse(answer=ans, rule=rule)
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
    run = pipeline.latest("march")
    return pipeline.summary_of(run) if run else fixtures.summary()


@router.get("/runs/latest", response_model=StartRunResponse)
def latest_run(kind: str = Query(default="march")) -> StartRunResponse:
    """The newest live run (the payment screen finds the run Nessie's deposit started)."""
    run = pipeline.latest(kind)
    if run is None:
        raise HTTPException(404, f"no live {kind} run yet")
    return StartRunResponse(run_id=run.id, events_url=f"/runs/{run.id}/events")
