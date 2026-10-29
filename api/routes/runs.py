"""Runs, the live event stream, the evidence drawer, owner answers and the read-only summary.

Live runs come from api/pipeline.py (POST /runs), each for one account (Peak Bar's by default). A run that is no
longer in memory (the API restarted) replays, read-only, from the events table (api/db/events.py). The recorded fake
runs (run-march-demo, run-april-demo, run-march-refused) still replay for screens built against web/fixtures.
"""

import asyncio
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.responses import StreamingResponse

from api.contracts import (
    AnswerRequest, AnswerResponse, ChargeDetail, Evidence, RunFixture, StartRunRequest, StartRunResponse, Summary,
)
from api import accounts, pipeline, tenancy
from api.tenancy import Caller, current_supplier
from api.auth import limit, require_role
from api.db import events as saved_events
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


def account_or_404(account_id: str, who: Caller = tenancy.EVERYONE) -> accounts.Account:
    """The account, if it exists and the caller's supplier owns it; 404 otherwise (api/tenancy.py)."""
    return tenancy.account_or_404(who, account_id)


def _start(kind: str | None, fixture: bool, account_id: str = accounts.DEFAULT,
           who: Caller = tenancy.EVERYONE) -> StartRunResponse:
    account = account_or_404(account_id, who)
    kind = kind or account.invoice.month
    if fixture:  # the recorded fake runs are Peak Bar's
        run_id = fixtures.MARCH_RUN if kind == "march" else fixtures.APRIL_RUN
    else:
        try:
            run_id = pipeline.start(kind, account=account).id
        except pipeline.UnknownMonth as e:
            raise HTTPException(422, str(e)) from None
    return StartRunResponse(run_id=run_id, events_url=f"/runs/{run_id}/events")


@router.post("/runs", response_model=StartRunResponse, dependencies=[Depends(limit("runs"))])
def start_run(req: StartRunRequest | None = None, who: Caller = Depends(current_supplier)) -> StartRunResponse:
    """A live run of one of the account's months: {"account": "peak-bar", "kind": "march"} (both optional)."""
    req = req or StartRunRequest()
    return _start(req.kind, req.fixture, req.account, who)


@router.post("/replay/april", response_model=StartRunResponse, dependencies=[Depends(limit("runs"))])
def replay_april(fixture: bool = Query(default=False), who: Caller = Depends(current_supplier)) -> StartRunResponse:
    return _start("april", fixture, who=who)


def _latest_live(has: str, who: Caller = tenancy.EVERYONE) -> pipeline.Run | None:
    """The newest live run this caller may see that holds this charge or evidence ID."""
    for run in reversed(tenancy.visible_runs(who)):
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
    who: Caller = Depends(current_supplier),
) -> StreamingResponse:
    if not tenancy.can_see_run(who, run_id):
        raise HTTPException(404, f"unknown run {run_id}")
    live = pipeline.RUNS.get(run_id)
    run = live or _runs().get(run_id)
    saved = None if run else await asyncio.to_thread(saved_events.load, run_id)  # a run from before a restart
    if run is None and saved is None:
        raise HTTPException(404, f"unknown run {run_id}")
    # A browser reconnect resends Last-Event-ID but keeps the ?after= it first opened with: the larger one wins.
    start_after = max(after or 0, last_event_id or 0)
    if live:
        pending = live.events_after
    elif saved is not None:  # read once: nothing adds to a run that isn't in memory
        pending = lambda sent: [e for e in saved if e.id > sent]  # noqa: E731
    else:
        pending = lambda sent: [e for e in _events(run) if e.id > sent]  # noqa: E731
    pace = 0 if live or saved else delay_ms  # a live run is paced by the work itself; a saved one replays at once

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
def charge_detail(charge_id: str, run_id: str | None = Query(default=None),
                  who: Caller = Depends(current_supplier)) -> ChargeDetail:
    if run_id and not tenancy.can_see_run(who, run_id):
        raise HTTPException(404, f"unknown charge {charge_id}")
    live = pipeline.RUNS.get(run_id) if run_id else _latest_live(charge_id, who)
    if live and charge_id in live.charges:
        return live.detail(charge_id)
    if not tenancy.can_see(who, accounts.DEFAULT):  # the recorded runs below are Peak Bar's
        raise HTTPException(404, f"unknown charge {charge_id}")
    if portal.amendment_attached() and charge_id in fixtures.amendment_run().charges:
        return fixtures.amendment_run().charges[charge_id]
    for run in _runs().values():
        if charge_id in run.charges:
            return run.charges[charge_id]
    raise HTTPException(404, f"unknown charge {charge_id}")


@router.get("/evidence/{evidence_id}", response_model=Evidence)
def evidence(evidence_id: str, run_id: str | None = Query(default=None),
             who: Caller = Depends(current_supplier)) -> Evidence:
    if run_id and not tenancy.can_see_run(who, run_id):
        raise HTTPException(404, f"unknown evidence {evidence_id}")
    live = pipeline.RUNS.get(run_id) if run_id else _latest_live(evidence_id, who)
    if live and evidence_id in live.evidence:
        return live.evidence[evidence_id]
    if not tenancy.can_see(who, accounts.DEFAULT):  # the recorded evidence below is Peak Bar's
        raise HTTPException(404, f"unknown evidence {evidence_id}")
    ev = fixtures.EVIDENCE.get(evidence_id)
    if ev is None:
        raise HTTPException(404, f"unknown evidence {evidence_id}")
    return ev


@router.post("/questions/{question_id}/answer", response_model=AnswerResponse,
             dependencies=[Depends(require_role("owner"))])
def answer_question(question_id: str, req: AnswerRequest, who: Caller = Depends(current_supplier)) -> AnswerResponse:
    in_run = pipeline.QUESTIONS.get(question_id)
    if not (tenancy.can_see_run(who, in_run[0]) if in_run else tenancy.can_see(who, accounts.DEFAULT)):
        raise HTTPException(404, f"no open question {question_id}")
    if question_id in pipeline.QUESTIONS:
        q = pipeline.RUNS[in_run[0]].questions.get(question_id)
        # In the app, a second answer is a stale screen (answered by text, the weekly email or another tab): say so
        # instead of a 200 that changes nothing. UNDO still works, as it does by text.
        if q is not None and q.answer is not None and req.text.strip().upper() != "UNDO":
            raise HTTPException(409, f"{question_id} was already answered: “{q.answer}”")
        try:
            ans, rule = pipeline.answer(question_id, req.text, req.from_role, save_rule=req.save_rule)
        except pipeline.QuestionClosed as e:
            raise HTTPException(409, f"{e}; answer the newer run's question") from e
        return AnswerResponse(answer=ans, rule=rule)
    run = fixtures.march_run()
    answer = next((e.data for e in run.events if e.type == "answer" and e.data.question_id == question_id), None)
    if answer is None:
        raise HTTPException(404, f"no open question {question_id}")
    rule = next((e.data for e in run.events if e.type == "rule"), None)
    return AnswerResponse(answer=answer.model_copy(update={"text": req.text, "from_role": req.from_role}), rule=rule)


@router.get("/summary", response_model=Summary)
def summary(authorization: str | None = Header(default=None),
            account: str = Query(default=accounts.DEFAULT)) -> Summary:
    """The account's newest invoice-month run (Peak Bar's March by default); Peak Bar's recorded run before any."""
    token = os.getenv("CLAWBACK_READONLY_TOKEN")
    if not token:
        raise HTTPException(503, "CLAWBACK_READONLY_TOKEN is not set")
    if authorization != f"Bearer {token}":
        raise HTTPException(401, "bad token")
    found = account_or_404(account)
    run = pipeline.latest(found.invoice.month, found)
    if run:
        return pipeline.summary_of(run)
    if found.id != accounts.DEFAULT:
        raise HTTPException(404, f"no live {found.invoice.month} run for {found.id} yet")
    return fixtures.summary()


def latest_run_id(account: accounts.Account, kind: str | None = None) -> str | None:
    """The account's newest run of this kind (its invoice month by default): live, else saved before a restart."""
    kind = kind or account.invoice.month
    run = pipeline.latest(kind, account)
    return run.id if run else saved_events.latest_run(kind, account.id)


@router.get("/runs/latest", response_model=StartRunResponse)
def latest_run(kind: str | None = Query(default=None, description="the account's invoice month if left out"),
               account: str = Query(default=accounts.DEFAULT),
               who: Caller = Depends(current_supplier)) -> StartRunResponse:
    """The account's newest live run (the payment screen finds the run Nessie's deposit started); with none in memory,
    the newest saved one (the API restarted)."""
    found = account_or_404(account, who)
    run_id = latest_run_id(found, kind)
    if run_id is None:
        raise HTTPException(404, f"no live {kind or found.invoice.month} run for {found.id} yet")
    return StartRunResponse(run_id=run_id, events_url=f"/runs/{run_id}/events")
