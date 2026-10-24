"""One full demo run from the command line: March, the owner's answer, then April.

`make record` runs it with RECORD_FIXTURES=1 so every AI answer is saved for DEMO_MODE; `make demo` replays.
--portal also sends the judge's preset replies on D-0417 (claims, an agreement, then the signed amendment).
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
            "ledger_post": lambda: f"  QUICKBOOKS   {d.qbo_entity} ${d.amount:,.0f} {d.status} ({d.qbo_id}) {d.note or ''}",
            "totals": lambda: None,
            "run": lambda: f"== {d.run_id}: {d.status}",
        }.get(e.type, lambda: None)()
        if line:
            print(line)
        since = e.id
    return since


def _portal(march: pipeline.Run) -> None:
    """The judge's preset replies on the Northmart portal, the signed amendment last."""
    from api import disputes

    for p in disputes.PRESETS:
        print(f"  NORTHMART    [{p.label}] {p.text}" + (f" (attached {p.attachment_doc_id})" if p.attachment_doc_id else ""))
        for m in disputes.post("D-0417", p.text, p.attachment_doc_id)[1:]:
            print(f"  CLAWBACK     {m.text}")
    t = [e.data for e in march.events if e.type == "totals"][-1]
    print(f"\nAfter the portal: disputed ${t.disputed:,.0f} · accepted ${t.accepted:,.0f}\n")


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
    pending = [a for a in pipeline.inbox()[1] if a.id.startswith(f"AP-{march.id}")]
    if pending:
        print(f"\n  CONTROLLER   replies YES to \"{pending[0].text}\"")
        seen = len(march.events)
        pipeline.decide_approval(pending[0].id, True)
        _print(march, seen)
    t = [e.data for e in march.events if e.type == "totals"][-1]
    print(f"\nMarch: disputed ${t.disputed:,.0f} · accepted ${t.accepted:,.0f} · questions {t.questions}\n")
    if "--portal" in sys.argv:
        _portal(march)
    april = pipeline.start("april", background=False)
    _print(april)
    t = [e.data for e in april.events if e.type == "totals"][-1]
    print(f"\nApril: disputed ${t.disputed:,.0f} · accepted ${t.accepted:,.0f} · questions {t.questions}")
    ok = march.done and april.done
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
