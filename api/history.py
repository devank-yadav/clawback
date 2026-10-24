"""A distributor relationship's runs of the agents, newest first (GET /accounts/{id}/runs): the ones in memory and
the ones saved to Postgres before a restart, each summed up from its own events. Nothing is computed here: the
totals are the run's last totals event."""

from __future__ import annotations

from api import accounts
from api.contracts import RunSummary

SAVED = ("SELECT run_id FROM events WHERE account_id = %s AND type = 'run' GROUP BY run_id HAVING min(at) > %s "
         "ORDER BY min(at) DESC LIMIT %s")


def _summary(run_id: str, events: list, replaced: bool) -> RunSummary | None:
    runs = [e for e in events if e.type == "run"]
    if not runs:
        return None
    info = runs[-1].data
    remittance = next((e.data.remittance for e in runs if e.data.remittance), None)
    totals = [e.data for e in events if e.type == "totals"]
    t = totals[-1] if totals else None
    charges = sum(1 for e in events if e.type == "charge")
    return RunSummary(
        run_id=run_id, kind=info.kind, status=info.status, started_at=runs[0].at, replaced=replaced,
        invoice_id=remittance.invoice_id if remittance else None, taken=remittance.taken if remittance else None,
        charges=remittance.charge_count if remittance else charges,
        disputed=t.disputed if t else None, accepted=t.accepted if t else None, waiting=t.waiting if t else None,
        questions=sum(1 for e in events if e.type == "question"))


def runs(account: accounts.Account, limit: int = 30) -> list[RunSummary]:
    from api import pipeline
    from api.db import events as saved_events

    out: dict[str, RunSummary] = {}
    for run in list(pipeline.RUNS.values()):
        if run.account.id == account.id:
            s = _summary(run.id, list(run.events), run.replaced_by is not None)
            if s:
                out[run.id] = s
    ids = saved_events._read(lambda db: db.execute(SAVED, (account.id, saved_events._reset_at or saved_events.EPOCH, limit)).fetchall()) or []
    for (run_id,) in ids:
        if run_id in out:
            continue
        evs = saved_events.load(run_id)
        s = _summary(run_id, evs or [], False) if evs else None
        if s:
            out[run_id] = s
    ordered = sorted(out.values(), key=lambda s: s.started_at, reverse=True)[:limit]
    # Every run of the same month older than the newest one was replaced by it.
    seen: set[str] = set()
    for s in ordered:
        if s.kind in seen:
            s.replaced = True
        seen.add(s.kind)
    return ordered
