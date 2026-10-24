"""GET /runs/{run_id}/trace: every AI and outside call a run made, in order (api/trace.py).

The "How Clawback decided" panel reads it. ?charge_id=C1 keeps one charge's calls. GET /runs/{run_id}/trace/summary
adds them up: calls by agent and model, tokens, AI time, the run's wall time and the cost (config/pricing.yaml).
The trace lives in memory, so a run from before a restart (or one this API never ran) is a 404; a live run that
hasn't called out yet is [].
"""

from fastapi import APIRouter, HTTPException, Query

from api import pipeline, trace

router = APIRouter(tags=["trace"])


@router.get("/runs/{run_id}/trace", response_model=list[trace.TraceEntry])
def run_trace(run_id: str, charge_id: str | None = Query(default=None, description="Only this charge's calls, e.g. C1")
              ) -> list[trace.TraceEntry]:
    if run_id not in pipeline.RUNS and not trace.known(run_id):
        raise HTTPException(404, f"no trace for run {run_id}: unknown here, or from before the API restarted")
    return trace.trace_for(run_id, charge_id)


@router.get("/runs/{run_id}/trace/summary", response_model=trace.TraceSummary)
def run_trace_summary(run_id: str) -> trace.TraceSummary:
    run = pipeline.RUNS.get(run_id)
    if run is None and not trace.known(run_id):
        raise HTTPException(404, f"no trace for run {run_id}: unknown here, or from before the API restarted")
    events = run.events_after(0) if run else []
    started = events[0].at if events else None
    decided = next((e.at for e in events if e.type == "run" and e.data.status != "started"), None)
    return trace.summarize(run_id, started, decided)
