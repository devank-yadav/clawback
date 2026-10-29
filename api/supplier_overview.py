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
- done_for_you: the last few things the agents did without asking, each with why they were allowed to (the owner's
  Settings limit, a limit set when approving a memo, policy.yaml, a saved rule) and what the owner can take back
  (POST /autopilot/undo): a limit cleared so the next one asks, or a rule undone. A sent email stays sent.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from api import accounts, dispute_email, pipeline, suppliers, tenancy
from api.contracts import (
    AutoAction, AutoUndo, NeedsYou, OpenDispute, OverviewLink, QuickChoice, OverviewTotals, RecentItem,
    RecoveredEvidence, SupplierOverview,
)
from api.engine import gate, question_risk, totals as totals_mod
from api.engine.policy import load_policy

RANK = {"high": 0, "medium": 1, "low": 2}
RECENT = 8
DONE_FOR_YOU = 6


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
    """Each tracked account's newest live run (not replaced), oldest first: the same run the Distributors page shows
    for it (GET /accounts/{id}/runs, its first run not replaced), so Home's totals are those rows added up."""
    ids = {a.id for a in tracked}
    newest: dict[str, pipeline.Run] = {}
    for run in pipeline.RUNS.values():
        if run.account.id in ids and run.replaced_by is None:
            newest[run.account.id] = run
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


def _usd(v: Decimal) -> str:
    """$1,200 or $2,283.20: cents only when there are some (plain titles; the exact figure is in `amount`)."""
    return f"${v:,.0f}" if v == v.to_integral_value() else f"${v:,.2f}"


def _short(text: str, n: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# The same choices the app offers for a question (web/components/console/Review.tsx choicesFor).
def choices_for(code: str, has_clause: bool = True) -> list[QuickChoice]:
    """A question's one-tap answers. The notice rule is offered only when the deal has a verified discretion clause
    for the fee (pipeline._answer hangs the rule on it): without one, that answer can't become a rule and the owner
    would just be asked again."""
    rule = [QuickChoice(label="Accept when notice is at least 14 days", text="accept if notice is at least 14 days",
                        rule=True)] if code == "DF" and has_clause else []
    return [*rule, QuickChoice(label="Accept this one", text="accept" if code == "DF" else "accept it this time"),
            QuickChoice(label="Dispute this one", text="dispute it")]


def _needs_you(runs: list[pipeline.Run]) -> list[NeedsYou]:
    out: list[NeedsYou] = []
    policy = load_policy()
    for run in runs:
        a, them = run.account, run.distributor
        payment = a.invoice.received if run.kind == a.invoice.month else None
        for q in run.questions.values():
            if not pipeline.is_open(q):
                continue
            c = run.charges.get(q.charge_id) if q.charge_id else None
            title = f"{them} kept {_usd(c.amount)} for “{c.description}”. Is that fair?" if c else q.text
            allowed = run.allowances.get(q.charge_id or "")
            has_clause = allowed is not None and any(gate.uses_discretion(t, policy) for t in allowed.terms)
            out.append(NeedsYou(kind="question", account_id=a.id, distributor=them, title=title,
                                target_id=q.id, choices=choices_for(c.code if c else "", has_clause),
                                detail=q.risk.reason if q.risk else None, amount=c.amount if c else None,
                                risk_level=q.risk.level if q.risk else _level(c.amount if c else None, payment),
                                since=q.sent_at, link=OverviewLink(page="question", run_id=run.id)))
        for d, first_at in _latest_disputes(run).values():
            if d.status not in ("ready_to_send", "draft"):
                continue
            mail = next((x for x in dispute_email.emails_of(run.id, d.id) if x.kind == "dispute"), None)
            if mail and mail.status in ("sent", "outbox"):
                continue
            held = bool(mail and mail.status == "held")
            title = (f"Your {_usd(d.total)} dispute to {them} needs an edit before it can go" if held
                     else f"Your {_usd(d.total)} dispute to {them} is ready to send")
            lines = len(d.lines)
            out.append(NeedsYou(kind="dispute_email", account_id=a.id, distributor=them, title=title,
                                detail=f"{lines} charge{'s' if lines != 1 else ''} the contract doesn’t allow, each with "
                                       "its proof. Nothing goes out until you send it.", amount=d.total,
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
            d = _latest_disputes(run)[dispute_id][0]
            out.append(NeedsYou(kind="reply_email", account_id=a.id, distributor=them,
                                title=(f"{them} pushed back on your {_usd(d.total)} dispute. Answer them?"
                                       if m.classification == "claim_without_document" else
                                       f"{them} sent a document about your {_usd(d.total)} dispute. Answer them?"
                                       if m.classification == "new_document" else
                                       f"{them} replied on your {_usd(d.total)} dispute. Answer them?"),
                                detail=f"“{_short(m.text)}”", amount=d.total, risk_level="medium",
                                since=m.created_at, link=OverviewLink(page="dispute", run_id=run.id,
                                                                      dispute_id=dispute_id)))
        for x in replies:
            out.append(NeedsYou(kind="reply_email", account_id=a.id, distributor=them,
                                title=(f"Your answer to {them} needs an edit before it can go" if x.status == "held"
                                       else f"Your answer to {them} is ready to send"),
                                detail="The Negotiator drafted it from the contract and the data.",
                                risk_level="medium", since=None,
                                link=OverviewLink(page="dispute", run_id=run.id, dispute_id=x.dispute_id)))
        latest_ap = {}
        for e in run.events:
            if e.type == "approval":
                latest_ap[e.data.id] = e.data
        for ap in latest_ap.values():
            if ap.status != "pending":
                continue
            out.append(NeedsYou(kind="approval", account_id=a.id, distributor=them,
                                title=f"Send {_usd(ap.amount)} of {them}’s fair charges to QuickBooks?",
                                target_id=ap.id, choices=[QuickChoice(label=f"Send {_usd(ap.amount)} to QuickBooks")],
                                detail="A credit memo for what the contract allows. The disputed money stays open.",
                                amount=ap.amount,
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
            agreed = totals_mod.total_of(ev.amount for ev in recovered(run) if ev.dispute_id == d.id)
            out.append(OpenDispute(dispute_id=d.id, account_id=run.account.id, distributor=run.distributor,
                                   run_id=run.id, amount=totals_mod.total_of([d.total, -agreed]), total=d.total,
                                   agreed=agreed, status=d.status, filed_at=d.filed_at,
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
                                      text=f"Dispute {d.id} filed with {them}, ${d.total:,.2f}",
                                      link=OverviewLink(page="dispute", run_id=run.id, dispute_id=d.id)))
    return sorted(out, key=lambda r: r.at, reverse=True)[:RECENT]


def _done_for_you(runs: list[pipeline.Run]) -> list[AutoAction]:
    from api import autopilot

    out: list[AutoAction] = []
    for run in runs:
        a, them = run.account, run.distributor
        settings = autopilot.of_account(a)
        stop = "It’s already done: this only means the next one waits for you."
        sent = set()
        for e in run.events:
            d = e.data
            if e.type != "dispute" or d.status != "filed" or d.approved_by != "policy" or d.id in sent:
                continue
            sent.add(d.id)
            limit = settings.send_disputes_under
            if limit is not None and d.total <= limit:
                why, undo = (f"Under the {_usd(limit)} limit you set in Settings",
                             AutoUndo(kind="disputes", label="Ask me first next time", note=stop))
            elif dispute_email.auto_send():
                why, undo = "This server sends disputes within policy on their own (policy.yaml)", None
            else:
                why, undo = "You let disputes this size send on their own then; now you’re asked first", None
            out.append(AutoAction(at=e.at, kind="dispute_sent", account_id=a.id, distributor=them, amount=d.total,
                                  text=f"Sent your {_usd(d.total)} dispute to {them}", why=why, undo=undo,
                                  link=OverviewLink(page="dispute", run_id=run.id, dispute_id=d.id)))
        latest_ap = {}
        for e in run.events:
            if e.type == "approval":
                latest_ap[e.data.id] = (e.at, e.data)
        for at, ap in latest_ap.values():
            auto = ap.posted_by_auto_post
            if ap.status != "approved" or auto is None:
                continue
            if auto.approval_id == "settings":
                why = f"Under the {_usd(auto.limit)} limit you set in Settings"
                undo = (AutoUndo(kind="memos_settings", label="Ask me first next time", note=stop)
                        if settings.post_fair_under is not None else None)
            elif auto.approval_id == "policy":
                why, undo = f"Under the {_usd(auto.limit)} limit in policy.yaml", None
            else:
                why = f"Under the {_usd(auto.limit)} limit you set when you approved {auto.approval_id}"
                undo = (AutoUndo(kind="memos_account", label="Ask me first next time", note=stop, account_id=a.id)
                        if a.id in pipeline.AUTO_POST else None)
            out.append(AutoAction(at=ap.decided_at or at, kind="memo_posted", account_id=a.id, distributor=them,
                                  amount=ap.amount, text=f"Sent {_usd(ap.amount)} of {them}’s fair charges to QuickBooks",
                                  why=why, undo=undo, link=OverviewLink(page="approval", run_id=run.id)))
        rules = {r.id: r for r in pipeline.rules_of(a)}
        decided = {}
        for e in run.events:
            if e.type == "decision":
                decided[e.data.charge_id] = e.data  # the newest decision of each charge
        asked = {q.charge_id for q in run.questions.values()}  # the owner answered these: not done without asking
        for cid, d in decided.items():
            rule = rules.get(d.rule_id or "")
            if rule is None or d.decided_by != "gate" or cid in asked:
                continue
            c = run.charges[cid]
            verb = "Disputed" if d.disputed > 0 else "Accepted"
            undo = (AutoUndo(kind="rule", label=f"Undo {rule.label}", account_id=a.id, rule_id=rule.id,
                             note="Decisions it already made keep theirs; the agents ask you again next time.")
                    if rule.status == "active" else None)
            out.append(AutoAction(at=d.decided_at, kind="rule_applied", account_id=a.id, distributor=them,
                                  amount=c.amount, text=f"{verb} {them}’s {_usd(c.amount)} “{c.description}”",
                                  why=f"By {rule.label}: {rule.summary}", undo=undo,
                                  link=OverviewLink(page="run", run_id=run.id)))
    return sorted(out, key=lambda x: x.at, reverse=True)[:DONE_FOR_YOU]


def overview(who: tenancy.Caller) -> SupplierOverview:
    tracked = _tracked(who)
    runs = _runs(tracked)
    return SupplierOverview(supplier=who.supplier_id, distributors=len(tracked), totals=_totals(runs),
                            needs_you=_needs_you(runs), open_disputes=_open_disputes(runs), recent=_recent(runs),
                            done_for_you=_done_for_you(runs))
