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

from api import adapters, evidence as evidence_mod, rows
from api.agents import investigator, negotiator, reader, rule_writer
from api.contracts import (
    Answer, Approval, ApprovalLine, Charge, ChargeDetail, Decision, Dispute, DisputeLine, Event, EventAdapter,
    Evidence, Finding, LogLine, MathPart, Question, Rehearsal, Remittance, Rule, RunInfo, Term, Totals,
)
from api.engine import gate, totals
from api.engine import types as eng
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy
from api.integrations import replay

log = logging.getLogger("clawback.pipeline")

# The demo scenario (data/CLAUDE.md): fixed by design, not computed here.
COUNTERPARTY = "Northmart"
OWNER = "Dana Okafor"
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
    _after_decisions(run, policy)


def _decide(run: Run, charge_id: str, policy: eng.Policy) -> eng.Decision:
    c = run.charges[charge_id]
    rules = [adapters.to_engine_rule(r) for r in RULES if r.status == "active"]
    d = gate.decide(adapters.to_engine_charge(c), run.allowances[charge_id], run.eng_findings[charge_id], policy, rules)
    run.decisions[charge_id] = d
    shown = adapters.to_contract_decision(d, waiting=c.amount if d.kind == eng.DecisionKind.ASK else Decimal(0),
                                          decided_by="gate", decided_at=_now())
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
    q = Question(id=qid, to_role="owner", charge_id=charge_id, text=text, channel="sms", sent_at=_now())
    run.questions[qid] = q
    QUESTIONS[qid] = (run.id, charge_id)
    run.emit("question", q)
    run.log(f"Asked {OWNER.split()[0]} one question about {charge_id}.", actor="gate", charge_id=charge_id)


def _after_decisions(run: Run, policy: eng.Policy) -> None:
    disputed = [cid for cid, d in run.decisions.items() if d.disputed > 0]
    if disputed and not any(e.type == "dispute" for e in run.events):
        _file_dispute(run, disputed, policy)
    if any(d.kind == eng.DecisionKind.ASK for d in run.decisions.values()):
        run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="waiting", demo_mode=replay.demo_mode()))
        return
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


def _request_credit_memo(run: Run, policy: eng.Policy) -> None:
    accepted = [(cid, d.accepted) for cid, d in run.decisions.items() if d.accepted > 0]
    if not accepted:
        return
    amount = totals.total_of(a for _, a in accepted)
    needs_sam = gate.needs_controller(amount, policy)
    run.emit("approval", Approval(id=f"AP-{run.id}", kind="credit_memo", amount=amount,
                                  lines=[ApprovalLine(charge_id=cid, amount=a) for cid, a in accepted],
                                  proposed_by="bookkeeper", approver_role="controller",
                                  status="pending" if needs_sam else "approved",
                                  text=f"Approve credit memo of ${amount:,.0f} ({len(accepted)} lines)?",
                                  requested_at=_now()))
    run.log(f"Asked Sam (controller) to approve a ${amount:,.0f} credit memo. Nothing posts until Sam says yes."
            if needs_sam else f"Credit memo of ${amount:,.0f} is within policy; no controller needed.", actor="bookkeeper")


def answer(question_id: str, text: str, from_role: str = "owner",
           client: anthropic.Anthropic | None = None) -> tuple[Answer, Rule | None]:
    """The owner's reply (SMS or in-app). A reply Clawback understands becomes a rule and the waiting charges
    are decided again; otherwise the question stays open."""
    run_id, charge_id = QUESTIONS[question_id]
    run, policy = RUNS[run_id], load_policy()
    q = run.questions[question_id]
    a = run.allowances[charge_id]
    learned = _now()
    eng_term = next((t for t in a.terms if gate.uses_discretion(t, policy)), None)
    if eng_term is None:  # not a discretion clause: nothing to learn a rule from
        ans = Answer(question_id=question_id, from_role=from_role, text=text, answered_at=learned)
        run.emit("answer", ans)
        run.log(f"Recorded {OWNER.split()[0]}'s answer on {charge_id}; it isn't a discretion clause, so no rule.",
                actor="gate", charge_id=charge_id)
        return ans, None
    term = next(t for t in run.terms if t.id == eng_term.id)
    rule = rule_writer.write_rule(q, text, term, COUNTERPARTY, dict(a.facts), len(RULES) + 1, OWNER, learned, client)
    ans = Answer(question_id=question_id, from_role=from_role, text=text, answered_at=learned,
                 rule_id=rule.id if rule else None)
    run.emit("answer", ans)
    if rule is None:
        run.log(f"Couldn't turn \"{text}\" into a rule; the question stays open.", "warn", "gate", charge_id)
        return ans, None
    RULES.append(rule)
    run.questions[question_id] = q.model_copy(update={"answer": text, "answered_at": learned, "rule_id": rule.id})
    run.evidence[f"ev-{rule.id}"] = Evidence(id=f"ev-{rule.id}", kind="rule", label=rule.label,
                                             summary=f"{rule.summary} Learned from {OWNER.split()[0]}'s answer.",
                                             rule_id=rule.id, person=f"{OWNER} (owner)")
    run.emit("rule", rule)
    run.log(f"Saved {rule.label} and texted {OWNER.split()[0]}: \"{rule_writer.echo(rule)}\"", "good", "gate")
    for cid, d in list(run.decisions.items()):
        if d.kind == eng.DecisionKind.ASK:
            _decide(run, cid, policy)
    _after_decisions(run, policy)
    return ans, rule
