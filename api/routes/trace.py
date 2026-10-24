"""GET /runs/{run_id}/trace: every AI and outside call a run made, in order (api/trace.py).

The "How Clawback decided" panel reads it. ?charge_id=C1 keeps one charge's calls. The trace lives in memory, so a
run from before a restart (or one this API never ran) is a 404; a live run that hasn't called out yet is [].
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
