"""Eval harness (F12): the scoreboard's numbers come from eval/run.py, never made up.

GET /eval/latest serves the summary the last `make eval` saved (eval/latest.json); before any run it reports
not_run. Those files stay local (gitignored), so `make publish-score` copies them into eval/published/, which is
committed and ships in the API image: the deployed scoreboard shows the same score. POST /eval/run runs the same harness in-process (engine mode, no AI calls) and saves the result.
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
PUBLISHED = RUN_PY.parent / "published"  # agent.json / engine.json: `make publish-score`
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
    return EvalReport(status="done", mode=s.get("mode", "engine"), run_at=s.get("run_at"), cases=s["cases"],
                      correct=s["correct"],
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
    """The agent-mode score when one has been saved (readers and agents in the loop: the real number), else
    engine mode's. `mode` on the report says which."""
    for path in (_harness().LATEST_AGENT, PUBLISHED / "agent.json", latest_path(), PUBLISHED / "engine.json"):
        try:
            return to_report(json.loads(path.read_text()))
        except FileNotFoundError:
            continue
    return EvalReport(status="not_run", cases=CASES)
