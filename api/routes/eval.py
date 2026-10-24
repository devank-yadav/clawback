"""Eval harness (F12): the scoreboard's numbers come from eval/run.py, never made up.

GET /eval/latest serves the summary the last `make eval` saved (eval/latest.json); before any run it reports
not_run. POST /eval/run runs the same harness in-process (engine mode, no AI calls) and saves the result.
"""

import importlib.util
import json
import sys
from functools import cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.contracts import EvalReport

router = APIRouter(tags=["eval"])

RUN_PY = Path(__file__).resolve().parents[2] / "eval" / "run.py"
CASES = 30  # data/eval/charges-30.csv


@cache
def _harness():
    spec = importlib.util.spec_from_file_location("clawback_eval_run", RUN_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # its dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


def latest_path() -> Path:
    return _harness().LATEST


def to_report(s: dict) -> EvalReport:
    """eval/run.py's summary -> the contract the scoreboard reads."""
    return EvalReport(status="done", run_at=s.get("run_at"), cases=s["cases"], correct=s["correct"],
                      amounts_correct=s["correct_amounts"], asked=s["asked"], wrong_automatic=s["wrong_actions"],
                      unnecessary_questions=s["unnecessary_questions"])


@router.post("/eval/run", response_model=EvalReport)
def run_eval() -> EvalReport:
    ev = _harness()
    if not (ev.DEFAULT_DATA / "eval" / "charges-30.csv").exists():
        raise HTTPException(503, f"no eval set at {ev.DEFAULT_DATA / 'eval'}")
    return to_report(ev.save(ev.summary(ev.run(ev.DEFAULT_DATA)), latest_path()))


@router.get("/eval/latest", response_model=EvalReport)
def latest() -> EvalReport:
    try:
        return to_report(json.loads(latest_path().read_text()))
    except FileNotFoundError:
        return EvalReport(status="not_run", cases=CASES)
