"""The run (D6): a short payment -> every charge decided, streamed as events (docs/design.md, Architecture).

Readers -> quote check -> engine -> Investigator -> rehearsal -> gate -> one question per Ask -> the owner's
answer becomes a rule -> waiting charges are decided again -> dispute lines and the credit memo approval.
Runs, questions and rules live in memory until the database lands (D3). Only api/engine/ computes amounts.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import anthropic

from api import adapters, evidence as evidence_mod, replies, rows
from api.agents import investigator, negotiator, reader, rule_writer
from api.contracts import (
    Answer, Approval, ApprovalLine, LedgerLine, LedgerPost, Charge, ChargeDetail, Decision, Dispute, DisputeLine, Event, EventAdapter,
    Evidence, Finding, LogLine, MathPart, Question, Rehearsal, Remittance, Rule, RunInfo, Term, Totals,
)
from api.engine import gate, totals
from api.engine import types as eng
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy
from api.integrations import qbo, replay, sms

log = logging.getLogger("clawback.pipeline")

# The demo scenario (data/CLAUDE.md): fixed by design, not computed here.
COUNTERPARTY = "Northmart"
OWNER = "Dana Okafor"
CONTROLLER = "Sam Reyes"
NAMES = {"owner": OWNER.split()[0], "controller": CONTROLLER.split()[0]}
INVOICE_ID = "INV-3102"
EXPECTED = Decimal("48200.00")
RECEIVED = Decimal("41350.00")
DEAL_DOCS = ["spring-promo", "broker-2026-03-28", "northmart-2026-03-30"]
FIRST_DISPUTE = 417  # D-0417


def _now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class Run:
    id: str
    kind: str
    events: list[Any] = field(default_factory=list)
    done: bool = False
    charges: dict[str, Charge] = field(default_factory=dict)
    terms: list[Term] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    allowances: dict[str, eng.Allowance] = field(default_factory=dict)
    findings: dict[str, Finding] = field(default_factory=dict)
    eng_findings: dict[str, eng.Finding] = field(default_factory=dict)
    rehearsals: dict[str, Rehearsal] = field(default_factory=dict)
    decisions: dict[str, eng.Decision] = field(default_factory=dict)
    shown: dict[str, Decision] = field(default_factory=dict)
    questions: dict[str, Question] = field(default_factory=dict)
    coach: Any = None  # the Deal Coach's redlines for this run, once asked for (POST /coach)
    texts: list[tuple[str, str]] = field(default_factory=list)  # (role, SMS body) sent back; the webhook replies with them
    lock: threading.Lock = field(default_factory=threading.Lock)

    def emit(self, type_: str, data: Any) -> Any:
        with self.lock:
            ev = EventAdapter.validate_python({"id": len(self.events) + 1, "run_id": self.id, "at": _now(),
                                               "type": type_, "data": data.model_dump(mode="json")})
            self.events.append(ev)
        return ev

    def log(self, text: str, level: str = "info", actor: str = "system", charge_id: str | None = None) -> None:
        self.emit("log", LogLine(text=text, level=level, actor=actor, charge_id=charge_id))

    def events_after(self, n: int) -> list[Event]:
        with self.lock:
            return [e for e in self.events if e.id > n]

    def detail(self, charge_id: str) -> ChargeDetail:
        f, r, d = self.findings.get(charge_id), self.rehearsals.get(charge_id), self.shown.get(charge_id)
        ids = list(dict.fromkeys((f.evidence_ids if f else []) + (r.answer_evidence_ids if r else [])
                                 + [f"ev-charge-{charge_id}"] + ([f"ev-{d.rule_id}"] if d and d.rule_id else [])))
        rule = next((x for x in RULES if d and x.id == d.rule_id), None)
        return ChargeDetail(charge=self.charges[charge_id], finding=f, decision=d, rehearsal=r, rule=rule,
                            evidence=[self.evidence[i] for i in ids if i in self.evidence])


RUNS: dict[str, Run] = {}
RULES: list[Rule] = []  # saved owner rules, shared by every run
QUESTIONS: dict[str, tuple[str, str]] = {}  # question id -> (run id, charge id)
_counter = {"question": 0, "dispute": 0}
_state = threading.Lock()


def reset() -> None:
    with _state:
        RUNS.clear(), RULES.clear(), QUESTIONS.clear()
        _counter.update(question=0, dispute=0)
    qbo.reset()
    sms.outbox.clear()


def start(kind: str = "march", client: anthropic.Anthropic | None = None, background: bool = True) -> Run:
    run = Run(id=f"run-{kind}-{uuid.uuid4().hex[:8]}", kind=kind)
    RUNS[run.id] = run
    work = lambda: _guarded(run, client)  # noqa: E731
    threading.Thread(target=work, daemon=True).start() if background else work()
    return run


def _guarded(run: Run, client) -> None:
    try:
        _process(run, client)
    except Exception as e:  # noqa: BLE001 - a crash shows on the board instead of hanging the stream
        log.exception("run %s failed", run.id)
        run.log(f"The run stopped: {type(e).__name__}: {e}", "error")
        run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="failed", demo_mode=replay.demo_mode()))
        run.done = True


def _meters(run: Run) -> Totals:
    eng_charges = {cid: adapters.to_engine_charge(c) for cid, c in run.charges.items()}
    m = totals.meters(eng_charges, run.decisions)
    return Totals(taken=m["taken"], disputed=m["disputed"], accepted=m["accepted"], waiting=m["waiting"],
                  undecided=m["undecided"], questions=sum(1 for q in run.questions.values()), skipped=m["skipped"])


def _read_terms(run: Run, client) -> list[Term]:
    terms: list[Term] = []
    for doc_id in DEAL_DOCS:
        r = reader.read_document(doc_id, base_terms=[t for t in terms if t.source_doc_id == DEAL_DOCS[0]], client=client)
        verified = [t for t in r.terms if t.status == "verified"]
        rejected = [t for t in r.terms if t.status == "rejected"]
        if not reader.documents.can_change_deal(r.doc) and verified:
            run.log(f"{r.doc.sender} says: {verified[0].exact_quote} That sender can't change the deal: shown as a claim, "
                    "not applied.", "warn", "reader")
        else:
            run.log(f"Read {doc_id}: {len(verified)} terms, every quote found word for word."
                    + (f" {len(rejected)} rejected: quote not found." if rejected else ""),
                    "good" if verified and not rejected else "warn", "reader")
        for line in r.unclear:
            run.log(f"Reader left this for a person to review: {line}", "warn", "reader")
        terms += r.terms
    return terms


def _rule_evidence(rule: Rule) -> Evidence:
    return Evidence(id=f"ev-{rule.id}", kind="rule", label=rule.label,
                    summary=f"{rule.summary} Learned from {OWNER.split()[0]}'s answer.", rule_id=rule.id,
                    person=f"{OWNER} (owner)")


def _process(run: Run, client) -> None:
    policy = load_policy()
    # Stable IDs: agent requests (and their DEMO_MODE fixture keys) must not change from run to run.
    remittance_id = f"REM-{INVOICE_ID}" if run.kind == "march" else f"REM-{run.kind.upper()}"
    charges = [c.model_copy(update={"remittance_id": remittance_id}) for c in rows.charges(run.kind)]
    run.charges = {c.id: c for c in charges}
    eng_charges = {c.id: adapters.to_engine_charge(c) for c in charges}
    taken = totals.taken(eng_charges.values())
    remittance = None
    if run.kind == "march":
        remittance = Remittance(id=remittance_id, counterparty=COUNTERPARTY, invoice_id=INVOICE_ID,
                                expected=EXPECTED, received=RECEIVED, taken=taken, charge_count=len(charges),
                                received_at=_now())
    run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="started", remittance=remittance,
                            demo_mode=replay.demo_mode()))
    if remittance:
        short = totals.remittance_short(EXPECTED, RECEIVED)
        run.log(f"{COUNTERPARTY} paid ${RECEIVED:,.0f} on invoice {INVOICE_ID} for ${EXPECTED:,.0f}. "
                f"${taken:,.0f} was taken out in {len(charges)} charges.",
                "info" if short == taken else "warn")
    else:
        run.log(f"{COUNTERPARTY} took {len(charges)} charges, ${taken:,.0f} in all.")
    run.emit("totals", _meters(run))

    run.log("Reading the deal and the emails about it.", actor="reader")
    run.terms = _read_terms(run, client)
    run.evidence = evidence_mod.build(run.terms, charges, rows.sales(), rows.prior_payments())
    eng_terms = [adapters.to_engine_term(t) for t in run.terms]
    sales = [adapters.to_engine_sales(r) for r in rows.sales()]
    payments = [adapters.to_engine_prior(p) for p in rows.prior_payments()]

    for c in charges:
        run.emit("charge", c)
        run.log(f"Checking {c.id}: {c.description}, ${c.amount:,.0f} taken.", actor="investigator", charge_id=c.id)
        a = compute_allowed(eng_charges[c.id], eng_terms, sales, payments)
        run.allowances[c.id] = a
        inv = investigator.investigate(c, a, run.evidence, client)
        if inv.output:
            f = Finding(**inv.output.model_dump(), id=f"F-{c.id}", expected=a.allowed, taken=a.taken, delta=a.delta,
                        math=[MathPart(text=s) for s in a.steps])
            run.findings[c.id] = f
            run.emit("finding", f)
            kinds = {run.evidence[i].kind for i in f.evidence_ids} - {"charge"}
        else:
            run.log(f"Couldn't explain {c.id} from the evidence, so a person decides.", "warn", "investigator", c.id)
            kinds = set()
        discretion = any(gate.uses_discretion(t, policy) for t in a.terms)
        if inv.output and a.delta > policy.match_tolerance and not discretion and not a.missing:
            run.log("Predicting Northmart's comeback before filing.", actor="negotiator", charge_id=c.id)
            r = negotiator.rehearse(c, run.findings[c.id], a, run.evidence, run.terms, client)
            run.rehearsals[c.id] = r
            if r.answered:
                run.emit("rehearsal", r)
            else:
                run.log(f"No solid answer to Northmart's likely comeback on {c.id}, so it isn't filed.", "warn",
                        "negotiator", c.id)
        o = inv.output
        run.eng_findings[c.id] = eng.Finding(
            charge_id=c.id, confidence=Decimal(str(o.confidence)) if o else Decimal(0),
            evidence_ids=tuple(o.evidence_ids) if o else (), independent_sources=len(kinds),
            comeback_answered=run.rehearsals.get(c.id, Rehearsal(charge_id=c.id, predicted_rebuttal="", answer="",
                                                                 answer_evidence_ids=[], answered=False)).answered,
            type=o.type if o else "", finding=o.finding if o else "")
        _decide(run, c.id, policy)
    # A rule saved by an earlier run opens from this run's cards too. Added after the agents ran, so their
    # requests (and DEMO_MODE fixture keys) don't change.
    for rule in (r for r in RULES if any(d.rule_id == r.id for d in run.decisions.values())):
        run.evidence.setdefault(f"ev-{rule.id}", _rule_evidence(rule))
    _after_decisions(run, policy)


def _decide(run: Run, charge_id: str, policy: eng.Policy) -> eng.Decision:
    c = run.charges[charge_id]
    rules = [adapters.to_engine_rule(r) for r in RULES if r.status == "active"]
    d = gate.decide(adapters.to_engine_charge(c), run.allowances[charge_id], run.eng_findings[charge_id], policy, rules)
    return _record(run, charge_id, d, decided_by="gate")


def _record(run: Run, charge_id: str, d: eng.Decision, decided_by: str) -> eng.Decision:
    """Store and show a decision; an Ask sends the owner one question (never a second for the same charge)."""
    c = run.charges[charge_id]
    run.decisions[charge_id] = d
    shown = adapters.to_contract_decision(d, waiting=c.amount if d.kind == eng.DecisionKind.ASK else Decimal(0),
                                          decided_by=decided_by, decided_at=_now())
    run.shown[charge_id] = shown
    run.emit("decision", shown)
    if d.rule_id:
        rule = next(r for r in RULES if r.id == d.rule_id)
        run.log(f"Applied {rule.label} (learned {rule.learned_at:%b %-d}, approved by {rule.approver.split()[0]}) to "
                f"{charge_id}.", "good", "gate", charge_id)
    if d.kind == eng.DecisionKind.ASK and not any(q.charge_id == charge_id for q in run.questions.values()):
        _ask_owner(run, charge_id)  # one question per charge per run, never a second
    run.emit("totals", _meters(run))
    return d


def _ask_owner(run: Run, charge_id: str) -> None:
    c, a = run.charges[charge_id], run.allowances[charge_id]
    term = next((t for t in a.terms if t.discretion or t.type == eng.TermType.FEE_DISCRETION), a.terms[0] if a.terms else None)
    days = a.facts.get("notice_days")
    text = (f"{COUNTERPARTY} took ${c.amount:,.0f}: {c.description}. "
            + (f"The deal says: \"{term.exact_quote}\" " if term else "")
            + (f"Notice came {days} days ahead. " if days is not None else "")
            + "Accept or dispute? Tell me your rule and I'll remember it.")
    with _state:
        _counter["question"] += 1
        qid = f"Q-{_counter['question']}"
    status = sms.send("owner", text)
    q = Question(id=qid, to_role="owner", charge_id=charge_id, text=text, channel="sms" if status == "sent" else "inbox",
                 sent_at=_now())
    run.questions[qid] = q
    QUESTIONS[qid] = (run.id, charge_id)
    run.emit("question", q)
    run.log(f"Asked {NAMES['owner']} one question about {charge_id}" + (" by text." if status == "sent" else
            f" in the inbox (text {status})."), actor="gate", charge_id=charge_id)


def _tell(run: Run, role: str, text: str, level: str = "info", charge_id: str | None = None) -> None:
    """Text someone first (not a reply: replies to their texts go back in the webhook's TwiML, via run.texts).
    The log says whether it went out or waits in the inbox."""
    status = sms.send(role, text)
    where = "Texted" if status == "sent" else f"In the inbox (text {status}) for"
    run.log(f"{where} {NAMES[role]}: \"{text}\"", level, "gate" if role == "owner" else "bookkeeper", charge_id)


def _after_decisions(run: Run, policy: eng.Policy) -> None:
    filed = {ln.charge_id for e in run.events if e.type == "dispute" for ln in e.data.lines}
    disputed = [cid for cid, d in run.decisions.items() if d.disputed > 0 and cid not in filed]
    if disputed:  # the first pass files D-0417; a line settled later (an owner's DISPUTE) gets its own
        _file_dispute(run, disputed, policy)
    if any(d.kind == eng.DecisionKind.ASK for d in run.decisions.values()):
        run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="waiting", demo_mode=replay.demo_mode()))
        return
    if not any(e.type == "approval" for e in run.events):
        _request_credit_memo(run, policy)
    if run.kind == "april":
        run.log("0 questions asked: every fee was decided by a saved rule." if not run.questions
                else f"{len(run.questions)} question(s) asked.", "good" if not run.questions else "info", "gate")
    run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="finished", demo_mode=replay.demo_mode()))
    run.done = True


def _file_dispute(run: Run, charge_ids: list[str], policy: eng.Policy) -> None:
    lines = []
    for cid in charge_ids:
        c, d, f = run.charges[cid], run.decisions[cid], run.findings.get(cid)
        clause = next((run.evidence[i] for i in (f.evidence_ids if f else []) if run.evidence[i].kind == "clause"), None)
        lines.append(DisputeLine(charge_id=cid, ref=c.ref, amount=d.disputed, reason=f.finding if f else d.reason,
                                 clause_ref=clause.label if clause else None,
                                 quote=clause.quote.text if clause and clause.quote else None,
                                 math=" ".join(run.allowances[cid].steps), evidence_ids=list(f.evidence_ids) if f else []))
    total = totals.total_of(ln.amount for ln in lines)
    by_policy = total <= policy.auto_dispute_limit
    with _state:
        dispute_id = f"D-{FIRST_DISPUTE + _counter['dispute']:04d}"
        _counter["dispute"] += 1
    run.emit("dispute", Dispute(id=dispute_id, remittance_id=next(iter(run.charges.values())).remittance_id or "",
                                counterparty=COUNTERPARTY, lines=lines, total=total,
                                status="filed" if by_policy else "draft", approved_by="policy" if by_policy else "owner",
                                filed_at=_now() if by_policy else None))
    run.log(f"Filed dispute {dispute_id}: {len(lines)} lines, ${total:,.0f}. Within the ${policy.auto_dispute_limit:,.0f} "
            f"limit {OWNER.split()[0]} set." if by_policy else
            f"Dispute {dispute_id} is ${total:,.0f}, over the ${policy.auto_dispute_limit:,.0f} limit: held for "
            f"{OWNER.split()[0]}.", "good" if by_policy else "warn", "negotiator")


def _request_credit_memo(run: Run, policy: eng.Policy, accepted: list[tuple[str, Decimal]] | None = None) -> None:
    """A credit memo for the accepted amounts (every accepted decision by default; a concession passes its own)."""
    if accepted is None:
        accepted = [(cid, d.accepted) for cid, d in run.decisions.items() if d.accepted > 0]
    if not accepted:
        return
    amount = totals.total_of(a for _, a in accepted)
    needs_sam = gate.needs_controller(amount, policy)
    n = len({e.data.id for e in run.events if e.type == "approval"}) + 1
    approval_id = f"AP-{run.id}" if n == 1 else f"AP-{run.id}-{n}"
    approval = Approval(id=approval_id, kind="credit_memo", amount=amount,
                        lines=[ApprovalLine(charge_id=cid, amount=a) for cid, a in accepted],
                        proposed_by="bookkeeper", approver_role="controller", status="pending",
                        text=f"Approve credit memo of ${amount:,.0f} ({len(accepted)} lines)?", requested_at=_now())
    if needs_sam:
        run.emit("approval", approval)
        run.log(f"Credit memo of ${amount:,.0f} waits on {NAMES['controller']} (controller). Nothing posts until "
                f"{NAMES['controller']} says yes.", actor="bookkeeper")
        _tell(run, "controller", f"{approval.text} Reply YES to approve, or NO with a note to hold it.")
        return
    approved = approval.model_copy(update={
        "status": "approved", "decided_at": _now(),
        "note": f"Within policy: credit memos up to ${policy.controller_approval_over:,.0f} post without the controller."})
    run.emit("approval", approved)
    run.log(f"Credit memo of ${amount:,.0f} is within policy; no controller needed.", actor="bookkeeper")
    _post_books(run, approved)


def answer(question_id: str, text: str, from_role: str = "owner",
           client: anthropic.Anthropic | None = None) -> tuple[Answer, Rule | None]:
    """The owner's reply (SMS or in-app). Code reads it first (api/replies.py):
    - a rule ("accept if notice is at least 14 days") is saved and the waiting charges are decided again;
    - ACCEPT or DISPUTE alone settles this charge only, and no rule is saved;
    - UNDO cancels the newest rule for next time (charges it already decided keep their decision);
    - anything else goes to Claude's rule writer; if that can't read it either, the owner is asked again.
    Returns the answer and the rule it saved or undid, if any."""
    run_id, charge_id = QUESTIONS[question_id]
    run, policy = RUNS[run_id], load_policy()
    q, a, now, owner = run.questions[question_id], run.allowances[charge_id], _now(), OWNER.split()[0]
    eng_term = next((t for t in a.terms if gate.uses_discretion(t, policy)), None)
    term = next((t for t in run.terms if eng_term and t.id == eng_term.id), None)
    subject = "display fees" if "display" in run.charges[charge_id].description.lower() else "these fees"
    reply = replies.parse_owner_reply(text)

    def record(rule_id: str | None = None) -> Answer:
        ans = Answer(question_id=question_id, from_role=from_role, text=text, answered_at=now, rule_id=rule_id)
        run.emit("answer", ans)
        return ans

    if reply.kind == "undo":
        ans = record()
        undone = replies.undo_rule(RULES)
        if undone:
            RULES[:] = [undone if r.id == undone.id else r for r in RULES]
            run.emit("rule", undone)
        run.texts.append(("owner", replies.undo_text(undone)))
        run.log(f"Texted {owner}: \"{replies.undo_text(undone)}\"", actor="gate", charge_id=charge_id)
        return ans, undone
    if q.answer is not None:
        ans = record()
        run.texts.append(("owner", f"{charge_id} is already settled. Reply UNDO to cancel the rule."))
        run.log(f"{charge_id} is already settled; only UNDO changes it now.", actor="gate", charge_id=charge_id)
        return ans, None

    if reply.kind == "once":
        ans = record()
        run.questions[question_id] = q.model_copy(update={"answer": text, "answered_at": now})
        d = gate.decide_by_owner(adapters.to_engine_charge(run.charges[charge_id]), a, eng.DecisionKind(reply.decision),
                                 policy, run.decisions[charge_id].gate_row, cap_at_deal=term is not None)
        _record(run, charge_id, d, decided_by="owner")
        run.texts.append(("owner", replies.once_text(reply, charge_id)))
        run.log(f"Texted {owner}: \"{replies.once_text(reply, charge_id)}\"", actor="gate", charge_id=charge_id)
        _after_decisions(run, policy)
        return ans, None

    rule, echo = None, ""
    if term and reply.kind == "rule":
        rule = replies.rule_from_reply(reply, rule_id=f"rule-{len(RULES) + 1}", pattern_text=term.exact_quote,
                                       term_type=term.type, counterparty=COUNTERPARTY, approver=OWNER, learned_at=now,
                                       source_question_id=question_id, subject=subject)
        echo = replies.confirmation_text(reply, subject)
    elif term:  # the parser couldn't read it: Claude tries, and code still checks the condition
        rule = rule_writer.write_rule(q, text, term, COUNTERPARTY, dict(a.facts), len(RULES) + 1, OWNER, now, client)
        echo = rule_writer.echo(rule) if rule else ""
    if rule is None:
        ans = record()
        why = reply.reason or "a rule needs a discretion clause; this one isn't"
        run.texts.append(("owner", replies.REASK_TEXT))
        run.log(f"Couldn't use \"{text}\" ({why}). Texted {owner}: \"{replies.REASK_TEXT}\"", "warn", "gate", charge_id)
        return ans, None

    ans = record(rule.id)
    RULES.append(rule)
    run.questions[question_id] = q.model_copy(update={"answer": text, "answered_at": now, "rule_id": rule.id})
    run.evidence[f"ev-{rule.id}"] = _rule_evidence(rule)
    run.emit("rule", rule)
    run.texts.append(("owner", echo))
    run.log(f"Saved {rule.label} and texted {owner}: \"{echo}\"", "good", "gate")
    for cid, d in list(run.decisions.items()):
        if d.kind == eng.DecisionKind.ASK:
            _decide(run, cid, policy)
    _after_decisions(run, policy)
    return ans, rule


# ---------------------------------------------------------------- controller approvals (F10)

def find_approval(approval_id: str) -> tuple[Run, Approval] | None:
    """The live run that asked for this approval, and the approval as it stands now (its newest event)."""
    for run in reversed(list(RUNS.values())):
        latest = [e.data for e in run.events if e.type == "approval" and e.data.id == approval_id]
        if latest:
            return run, latest[-1]
    return None


def pending_approval(role: str = "controller") -> str | None:
    """The newest approval still waiting on this role, for an SMS reply that doesn't name one."""
    for run in reversed(list(RUNS.values())):
        ids = list(dict.fromkeys(e.data.id for e in run.events if e.type == "approval"))
        for approval_id in reversed(ids):
            _, a = find_approval(approval_id)
            if a.status == "pending" and a.approver_role == role:
                return approval_id
    return None


class AlreadyDecided(ValueError):
    def __init__(self, approval: Approval):
        super().__init__(f"{approval.id} is already {approval.status}")
        self.approval = approval


def decide_approval(approval_id: str, approve: bool, note: str | None = None) -> tuple[Approval, list[LedgerPost]]:
    """The controller's yes or no on a run's credit memo (in-app or SMS). Yes posts it to QuickBooks (_post_books:
    the memo, applied to the invoice, plus the disputed-balance note); no posts nothing, keeps the note and tells
    the owner. Raises KeyError if no live run asked for it, AlreadyDecided (a ValueError) if it was decided."""
    with _state:  # an SMS yes and an in-app yes arriving together decide it once
        found = find_approval(approval_id)
        if found is None:
            raise KeyError(approval_id)
        run, approval = found
        if approval.status != "pending":
            raise AlreadyDecided(approval)
        decided = approval.model_copy(update={"status": "approved" if approve else "refused", "note": note or None,
                                              "decided_at": _now()})
        run.emit("approval", decided)
    sam = NAMES["controller"]
    if not approve:
        run.log(f"{sam} refused the ${approval.amount:,.0f} credit memo" + (f": \"{note}\"" if note else "")
                + f". Nothing posts to QuickBooks; the note is on the card and the memo goes back to {NAMES['owner']}.",
                "warn", "controller")
        _tell(run, "owner", f"{sam} held the ${approval.amount:,.0f} credit memo" + (f": {note}" if note else "")
              + ". Nothing was posted to QuickBooks.", "warn")
        return decided, []
    run.log(f"{sam} approved the ${approval.amount:,.0f} credit memo. Posting to QuickBooks.", "good", "controller")
    return decided, _post_books(run, decided)


def _open_dispute_lines(run: Run) -> list[DisputeLine]:
    latest: dict[str, Dispute] = {}
    for e in run.events:
        if e.type == "dispute":
            latest[e.data.id] = e.data
    return [ln for d in latest.values() if d.status != "withdrawn" for ln in d.lines]


def _post_books(run: Run, approval: Approval) -> list[LedgerPost]:
    """Write an approved credit memo to QuickBooks, apply it to the invoice and note the disputed balance.
    Request ids come from the approval id, so a retry never posts twice."""
    books = qbo.books()
    sim = " Simulated: QuickBooks keys aren't set yet." if books.simulated else ""
    invoice_no = INVOICE_ID if run.kind == "march" else None
    lines = [LedgerLine(charge_id=ln.charge_id, amount=ln.amount,
                        description=f"{run.charges[ln.charge_id].ref}: {run.charges[ln.charge_id].description}")
             for ln in approval.lines]
    posts: list[LedgerPost] = []
    try:
        memo = books.post_credit_memo(f"{approval.id}-memo", [qbo.Line(ln.charge_id, ln.description, ln.amount)
                                                             for ln in lines],
                                      memo=f"Clawback {approval.id}: accepted deductions "
                                           f"{', '.join(ln.charge_id for ln in lines)}")
        if invoice_no:
            books.apply_to_invoice(f"{approval.id}-apply", invoice_no, memo.id, approval.amount)
        posts.append(LedgerPost(id=f"LP-{approval.id}", qbo_entity="credit_memo", qbo_id=memo.id,
                                amount=approval.amount, lines=lines, status="posted", approval_id=approval.id,
                                note=(f"Applied to {invoice_no}." if invoice_no else
                                      "Left unapplied: this run has no invoice in QuickBooks.") + sim,
                                posted_at=_now()))
        open_lines = _open_dispute_lines(run) if invoice_no else []
        if open_lines:
            total = totals.total_of(ln.amount for ln in open_lines)
            note = (f"Open ${total:,.2f} disputed with {COUNTERPARTY}: "
                    + "; ".join(f"{ln.charge_id} {ln.ref} ${ln.amount:,.2f}" for ln in open_lines))
            noted = books.note_open_balance(f"{approval.id}-note", invoice_no, note, total)
            posts.append(LedgerPost(id=f"LP-{approval.id}-note", qbo_entity="invoice_note", qbo_id=noted.id,
                                    amount=total, status="posted", approval_id=approval.id, note=note + sim,
                                    lines=[LedgerLine(charge_id=ln.charge_id, description=f"{ln.ref}: {ln.reason}",
                                                      amount=ln.amount) for ln in open_lines], posted_at=_now()))
    except qbo.BooksError as e:
        posts.append(LedgerPost(id=f"LP-{approval.id}", qbo_entity="credit_memo", qbo_id=None, amount=approval.amount,
                                lines=lines, status="failed", approval_id=approval.id,
                                note=f"QuickBooks write failed ({e}). A retry uses the same request ids, so it posts once."))
    for p in posts:
        run.emit("ledger_post", p)
    if posts and posts[0].status == "posted":
        run.log(f"QuickBooks: ${approval.amount:,.0f} credit memo posted"
                + (f" and applied to {invoice_no}" if invoice_no else "")
                + (f"; ${posts[1].amount:,.0f} stays open, noted with the dispute lines" if len(posts) > 1 else "")
                + (" (simulated until the QuickBooks keys are set)." if books.simulated else "."), "good", "bookkeeper")
    else:
        run.log(f"QuickBooks write failed for {approval.id}; nothing half-posted is shown as done.", "error", "bookkeeper")
    return posts


def inbox() -> tuple[list[Question], list[Approval]]:
    """Open owner questions and approvals waiting on the controller, across live runs."""
    questions = [q for run in RUNS.values() for q in run.questions.values() if q.answer is None]
    pending = []
    for run in RUNS.values():
        latest: dict[str, Approval] = {}
        for e in run.events:
            if e.type == "approval":
                latest[e.data.id] = e.data
        pending += [a for a in latest.values() if a.status == "pending"]
    return questions, pending


def coach_costs(run: Run) -> list:
    """This run's costs for the Deal Coach: every disputed amount, and every fee that needed a question."""
    from api.agents.coach import Cost

    out, seen = [], set()
    for cid, d in run.decisions.items():
        f = run.findings.get(cid)
        if d.disputed > 0 and f:
            out.append(Cost(f.id, cid, run.charges[cid].ref, f.type, f.finding, d.disputed, "disputed"))
            seen.add(cid)
    for q in run.questions.values():
        f = run.findings.get(q.charge_id)
        if q.charge_id not in seen and f:
            out.append(Cost(f.id, q.charge_id, run.charges[q.charge_id].ref, f.type, f.finding,
                            run.charges[q.charge_id].amount, "needed a question to the owner"))
    return out
