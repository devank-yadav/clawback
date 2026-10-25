"""GET /overview: the signed-in supplier across all its tracked distributors (api/tenancy.py scopes it).

Nothing here does money math of its own: the totals are the runs' own totals events added up with
api/engine/totals.total_of, and every recovered dollar is a dispute line's amount with its evidence.

- totals: over each tracked distributor's newest run of each month (a run of the same payment replaces older ones,
  and each month is its own payment): taken, disputed, fair (the engine's accepted), waiting, and recovered.
- recovered counts only amounts with evidence: a dispute line the distributor agreed to in the thread (a portal or
  email message classified "agrees", naming the charge), each with {dispute_id, message_id, charge_id, amount}. A
  credit on a later remittance would count with its remittance_ref; no remittance reader reports credits yet, so
  none do today. A line Clawback withdrew (a signed amendment proved the charge) is not recovered: it moved to fair.
- needs_you: open questions (with their risk level), dispute emails waiting for "Review and send" (not yet sent),
  reply emails waiting, and pending approvals; high, medium, low, then oldest first. A dispute email's, reply's or
  approval's level comes from its amount on the same thresholds as a question's (policy.yaml question_risk).
- open_disputes: the newest version of each dispute not withdrawn or resolved, with the deal's dispute window.
- recent: the last 8 things that happened across distributors: runs decided, distributor replies, disputes sent.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from api import accounts, dispute_email, pipeline, suppliers, tenancy
from api.contracts import (
    NeedsYou, OpenDispute, OverviewLink, OverviewTotals, RecentItem, RecoveredEvidence, SupplierOverview,
)
from api.engine import question_risk, totals as totals_mod

RANK = {"high": 0, "medium": 1, "low": 2}
RECENT = 8


def _tracked(who: tenancy.Caller) -> list[accounts.Account]:
    out = []
    for a in accounts.every():
        if not tenancy.can_see(who, a):
            continue
        if a.id in suppliers._off(suppliers.supplier_of(a)):
            continue
        out.append(a)
    return out


def _runs(tracked: list[accounts.Account]) -> list[pipeline.Run]:
    """Each tracked account's newest live run of each month, oldest first."""
    ids = {a.id for a in tracked}
    newest: dict[tuple[str, str], pipeline.Run] = {}
    for run in pipeline.RUNS.values():
        if run.account.id in ids and run.replaced_by is None:
            newest[(run.account.id, run.kind)] = run
    return sorted(newest.values(), key=lambda r: r.started_at)


def _latest_disputes(run: pipeline.Run):
    return _latest_in(run.events)


def _latest_in(events):
    latest = {}
    for e in events:
        if e.type == "dispute":
            latest[e.data.id] = (e.data, latest.get(e.data.id, (None, e.at))[1])
    return latest  # dispute id -> (newest version, when it was first filed)


def recovered(run: pipeline.Run) -> list[RecoveredEvidence]:
    return recovered_in(run.events)


def recovered_in(events) -> list[RecoveredEvidence]:
    """Lines the distributor agreed to give back, each once, at the amount the line was disputed for."""
    disputes = _latest_in(events)
    lines = {(d.id, ln.charge_id): ln for d, _ in disputes.values() if d.status != "withdrawn" for ln in d.lines}
    out, seen = [], set()
    for e in events:
        m = e.data if e.type == "portal_message" else None
        if m is None or m.from_party != "northmart" or m.classification != "agrees":
            continue
        for cid in m.charge_ids:
            ln = lines.get((m.dispute_id, cid))
            if ln is None or (m.dispute_id, cid) in seen:
                continue
            seen.add((m.dispute_id, cid))
            out.append(RecoveredEvidence(dispute_id=m.dispute_id, message_id=m.id, charge_id=cid, amount=ln.amount))
    return out


def _totals(runs: list[pipeline.Run]) -> OverviewTotals:
    last = [t for t in ([e.data for e in r.events if e.type == "totals"][-1:] for r in runs) for t in t]
    evidence = [ev for r in runs for ev in recovered(r)]
    disputed = totals_mod.total_of(t.disputed for t in last)
    got = totals_mod.total_of(ev.amount for ev in evidence)
    return OverviewTotals(taken=totals_mod.total_of(t.taken for t in last), disputed=disputed,
                          fair=totals_mod.total_of(t.accepted for t in last),
                          waiting=totals_mod.total_of(t.waiting for t in last), recovered=got,
                          disputed_awaiting_reply=totals_mod.total_of([disputed, -got]), evidence=evidence)


def _level(amount: Decimal | None, payment: Decimal | None) -> str:
    if amount is None:
        return "low"
    f = question_risk.Facts(amount=amount, payment=payment, what="", distributor="")
    return question_risk.base_level(f, question_risk.load_thresholds())


def _needs_you(runs: list[pipeline.Run]) -> list[NeedsYou]:
    out: list[NeedsYou] = []
    for run in runs:
        a, them = run.account, run.distributor
        payment = a.invoice.received if run.kind == a.invoice.month else None
        for q in run.questions.values():
            if not pipeline.is_open(q):
                continue
            c = run.charges.get(q.charge_id) if q.charge_id else None
            out.append(NeedsYou(kind="question", account_id=a.id, distributor=them,
                                title=q.risk.reason if q.risk else q.text, amount=c.amount if c else None,
                                risk_level=q.risk.level if q.risk else _level(c.amount if c else None, payment),
                                since=q.sent_at, link=OverviewLink(page="question", run_id=run.id)))
        for d, first_at in _latest_disputes(run).values():
            if d.status not in ("ready_to_send", "draft"):
                continue
            mail = next((x for x in dispute_email.emails_of(run.id, d.id) if x.kind == "dispute"), None)
            if mail and mail.status in ("sent", "outbox"):
                continue
            state = "held: needs your edit" if mail and mail.status == "held" else "ready to review and send"
            out.append(NeedsYou(kind="dispute_email", account_id=a.id, distributor=them,
                                title=f"Dispute {d.id} to {them}, ${d.total:,.2f}: {state}", amount=d.total,
                                risk_level=_level(d.total, payment), since=first_at,
                                link=OverviewLink(page="dispute", run_id=run.id, dispute_id=d.id)))
        replies = [x for d in _latest_disputes(run) for x in dispute_email.emails_of(run.id, d)
                   if x.kind == "reply" and x.status in ("ready", "held")]
        drafted_for = {x.dispute_id for x in replies}
        for dispute_id in _latest_disputes(run):
            thread = dispute_email.thread(run, dispute_id)
            last_theirs = max((i for i, m in enumerate(thread) if m.from_party == "northmart"), default=None)
            if last_theirs is None or dispute_id in drafted_for:
                continue
            if any(m.from_party == "clawback" for m in thread[last_theirs + 1:]):
                continue
            m = thread[last_theirs]
            out.append(NeedsYou(kind="reply_email", account_id=a.id, distributor=them,
                                title=f"{them} replied on {dispute_id}: needs your answer", risk_level="medium",
                                since=m.created_at, link=OverviewLink(page="dispute", run_id=run.id,
                                                                      dispute_id=dispute_id)))
        for x in replies:
            out.append(NeedsYou(kind="reply_email", account_id=a.id, distributor=them,
                                title=f"Answer to {them} on {x.dispute_id}: "
                                      + ("held: needs your edit" if x.status == "held" else "ready to send"),
                                risk_level="medium", since=None,
                                link=OverviewLink(page="dispute", run_id=run.id, dispute_id=x.dispute_id)))
        latest_ap = {}
        for e in run.events:
            if e.type == "approval":
                latest_ap[e.data.id] = e.data
        for ap in latest_ap.values():
            if ap.status != "pending":
                continue
            out.append(NeedsYou(kind="approval", account_id=a.id, distributor=them, title=ap.text, amount=ap.amount,
                                risk_level=_level(ap.amount, payment), since=ap.requested_at,
                                link=OverviewLink(page="approval", run_id=run.id)))
    far = datetime.max.replace(tzinfo=None)
    return sorted(out, key=lambda n: (RANK[n.risk_level], (n.since.replace(tzinfo=None) if n.since else far)))


def _open_disputes(runs: list[pipeline.Run]) -> list[OpenDispute]:
    out = []
    for run in runs:
        for d, _ in _latest_disputes(run).values():
            if d.status in ("withdrawn", "resolved"):
                continue
            line = next((ln for ln in d.lines if ln.file_by), None)
            out.append(OpenDispute(dispute_id=d.id, account_id=run.account.id, distributor=run.distributor,
                                   run_id=run.id, amount=d.total, status=d.status, filed_at=d.filed_at,
                                   file_by=line.file_by if line else None, days_left=line.days_left if line else None))
    return out


def _recent(runs: list[pipeline.Run]) -> list[RecentItem]:
    out = []
    for run in runs:
        a, them = run.account, run.distributor
        sent, decided = set(), False
        for e in run.events:
            d = e.data
            if e.type == "run" and d.status in ("waiting", "finished") and not decided:
                decided = True  # once per run: when the gate first decided it
                out.append(RecentItem(at=e.at, kind="run_decided", account_id=a.id, distributor=them,
                                      text=f"Agents decided {them}'s {run.kind.capitalize()} payment",
                                      link=OverviewLink(page="run", run_id=run.id)))
            elif e.type == "portal_message" and d.from_party == "northmart":
                out.append(RecentItem(at=e.at, kind="reply", account_id=a.id, distributor=them,
                                      text=f"{them} replied on {d.dispute_id}",
                                      link=OverviewLink(page="dispute", run_id=run.id, dispute_id=d.dispute_id)))
            elif e.type == "dispute" and d.status == "filed" and d.id not in sent:
                sent.add(d.id)
                out.append(RecentItem(at=e.at, kind="sent", account_id=a.id, distributor=them,
                                      text=f"Dispute {d.id} sent to {them}, ${d.total:,.2f}",
                                      link=OverviewLink(page="dispute", run_id=run.id, dispute_id=d.id)))
    return sorted(out, key=lambda r: r.at, reverse=True)[:RECENT]


def overview(who: tenancy.Caller) -> SupplierOverview:
    tracked = _tracked(who)
    runs = _runs(tracked)
    return SupplierOverview(supplier=who.supplier_id, distributors=len(tracked), totals=_totals(runs),
                            needs_you=_needs_you(runs), open_disputes=_open_disputes(runs), recent=_recent(runs))
