"""Eval harness. Stub: reports not_run until eval/run.py exists; never shows a made-up score."""

from fastapi import APIRouter

from api.contracts import EvalReport
from api.stubs import fixtures

router = APIRouter(tags=["eval"])


@router.post("/eval/run", response_model=EvalReport)
def run_eval() -> EvalReport:
    return fixtures.eval_report()


@router.get("/eval/latest", response_model=EvalReport)
def latest() -> EvalReport:
    return fixtures.eval_report()
