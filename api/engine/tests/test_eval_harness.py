"""eval/run.py (F12): the engine-mode score on data/eval/, and the scoring itself catches each kind of miss."""

import importlib.util
import os
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from api.engine.policy import load_policy
from api.engine.types import DecisionKind

ROOT = Path(__file__).resolve().parents[3]
DATA = Path(os.environ.get("CLAWBACK_DATA_DIR", ROOT / "data"))
_spec = importlib.util.spec_from_file_location("eval_run", ROOT / "eval" / "run.py")
ev = importlib.util.module_from_spec(_spec)
sys.modules["eval_run"] = ev  # dataclasses look their module up here
_spec.loader.exec_module(ev)

pytestmark = pytest.mark.skipif(not (DATA / "eval" / "charges-30.csv").exists(), reason=f"no eval set at {DATA}")
POLICY = load_policy()
K = DecisionKind


def _cases():
    rows, key = ev.load(DATA)
    out = {}
    for row in rows:
        k = key[row["case_id"]]
        exp = ev.Expected(K(k["expected_decision"]), Decimal(k["expected_disputed"]), Decimal(k["expected_accepted"]), k["reason"])
        out[row["case_id"]] = (ev.build_case(row, k, POLICY), exp)
    return out


def test_engine_mode_scores_30_of_30_with_no_wrong_actions():
    s = ev.summary(ev.run(DATA))
    assert s["cases"] == 30
    assert s["wrong_actions"] == 0
    assert s["correct"] == 30, ev.main(["--data", str(DATA)])
    assert s["asked"] == 6


def test_forgetting_rule_1_shows_as_unnecessary_questions():
    cases = _cases()
    for cid in ("E22", "E23"):
        case, exp = cases[cid]
        r = ev.score(replace(case, rules=[]), exp, POLICY)
        assert (r.decision, r.verdict) == (K.ASK, "unnecessary_question")


def test_applying_an_unsigned_claim_is_a_wrong_action():
    case, exp = _cases()["E12"]
    trusted = [replace(t, source_approved=True) for t in case.terms]
    r = ev.score(replace(case, terms=trusted), exp, POLICY)
    assert (r.decision, r.verdict) == (K.ACCEPT, "wrong_action")


def test_acting_where_readers_disagree_is_a_wrong_action():
    from api.engine.types import TermStatus
    case, exp = _cases()["E29"]
    agreed = [replace(t, status=TermStatus.VERIFIED) for t in case.terms]
    r = ev.score(replace(case, terms=agreed), exp, POLICY)
    assert r.verdict == "wrong_action"


def test_cli_exit_code(capsys):
    assert ev.main(["--data", str(DATA)]) == 0
    assert "30/30 correct" in capsys.readouterr().out
