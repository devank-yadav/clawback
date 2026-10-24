"""One full demo run from the command line: March, the owner's answer, then April.

`make record` runs it with RECORD_FIXTURES=1 so every AI answer is saved for DEMO_MODE; `make demo` replays.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from api import pipeline

OWNER_ANSWER = "accept if notice is at least 14 days"


def _print(run: pipeline.Run, since: int = 0) -> int:
    for e in run.events_after(since):
        d = e.data
        line = {
            "log": lambda: f"  {d.actor:12} {d.text}",
            "decision": lambda: f"  DECISION     {d.charge_id} {d.decision:8} disputed ${d.disputed:,.0f} accepted ${d.accepted:,.0f} (row {d.gate_row}{', ' + d.rule_id if d.rule_id else ''})",
            "finding": lambda: f"  FINDING      {d.charge_id} [{d.type}, {d.confidence:.2f}] {d.finding}",
            "rehearsal": lambda: f"  COMEBACK     {d.charge_id} \"{d.predicted_rebuttal}\" -> {d.answer}",
            "question": lambda: f"  QUESTION     {d.id} to {d.to_role}: {d.text}",
            "rule": lambda: f"  RULE         {d.label}: {d.condition} -> {d.decision}, else {d.else_decision}",
            "dispute": lambda: f"  DISPUTE      {d.id} ${d.total:,.0f} ({d.status}, {len(d.lines)} lines)",
            "approval": lambda: f"  APPROVAL     {d.text} [{d.status}]",
            "totals": lambda: None,
            "run": lambda: f"== {d.run_id}: {d.status}",
        }.get(e.type, lambda: None)()
        if line:
            print(line)
        since = e.id
    return since


def main() -> int:
    load_dotenv()
    march = pipeline.start("march", background=False)
    _print(march)
    discretion = [qid for qid, q in march.questions.items() if march.shown[q.charge_id].gate_row == 4]
    if not march.done and discretion:
        qid = discretion[0]
        print(f"\n  OWNER        replies to {qid}: \"{OWNER_ANSWER}\"")
        seen = len(march.events)
        pipeline.answer(qid, OWNER_ANSWER)
        _print(march, seen)
    t = [e.data for e in march.events if e.type == "totals"][-1]
    print(f"\nMarch: disputed ${t.disputed:,.0f} · accepted ${t.accepted:,.0f} · questions {t.questions}\n")
    april = pipeline.start("april", background=False)
    _print(april)
    t = [e.data for e in april.events if e.type == "totals"][-1]
    print(f"\nApril: disputed ${t.disputed:,.0f} · accepted ${t.accepted:,.0f} · questions {t.questions}")
    ok = march.done and april.done
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
