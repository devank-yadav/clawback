"""The run (D6): a short payment -> every charge decided, streamed as events (docs/design.md, Architecture).

Readers -> quote check -> engine -> Investigator -> rehearsal -> gate -> one question per Ask -> the owner's
answer becomes a rule -> waiting charges are decided again -> dispute lines and the credit memo approval.
Runs, questions and rules live in memory until the database lands (D3). Only api/engine/ computes amounts.

Every run belongs to one account (api/accounts.py): its files, its people (texts name its owner and controller),
its distributor, its invoice and its dispute numbers. A run's kind is one of the account's months: the invoice
month's run has the remittance (Peak Bar's March); a later month replays with the saved rules (Peak Bar's April).
Saved rules belong to the account whose owner answered.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import anthropic

from api import accounts, account_rows, adapters, audit, evidence as evidence_mod, replies, rows
from api.agents import investigator, negotiator, reader, readers, rule_writer
from api.contracts import (
    Answer, Approval, ApprovalLine, LedgerLine, LedgerPost, Charge, ChargeDetail, Decision, Dispute, DisputeLine, Event, EventAdapter,
    Evidence, Finding, LogLine, Question, Rehearsal, Remittance, Rule, RunInfo, Term, Totals,
)
from api.db import events as saved_events
from api.engine import gate, totals
from api.engine import types as eng
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy
from api.integrations import moss, qbo, replay, sms

log = logging.getLogger("clawback.pipeline")

# The scenario's facts (the invoice, the people, the deal's documents, the first dispute number) come from the run's
# account.yaml. Each run numbers its own disputes from its month's block (Account.dispute_start), so a second run of
# the same payment files D-0417 again and the portal finds the newest one, and April's never takes D-0417.


class UnknownMonth(ValueError):
    """The account has no charges/<month>.csv for this kind of run."""


def _now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class Run:
    id: str
    kind: str  # one of the account's months
    account: accounts.Account | None = None  # None: Peak Bar
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
    reader_models: tuple[str, str] = ("claude", "claude-b")  # who read the deal; Devpost claims two models only if "gemini"
    disagreements: dict[str, str] = field(default_factory=dict)  # term type -> what each reader read
    deposit: Any = None  # the Nessie deposit that started this run, if one did
    texts: list[tuple[str, str]] = field(default_factory=list)  # (role, SMS body) sent back; the webhook replies with them
    replaced_by: str | None = None  # a newer run of the same payment; this one stops asking people
    ops: account_rows.Ops = field(default_factory=account_rows.Ops)  # deliveries, prices, ops terms (SH/PR/SP charges)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.account = accounts.resolve(self.account or accounts.DEFAULT)

    @property
    def distributor(self) -> str:
        return self.account.distributor.name

    def name(self, role: str) -> str:
        """The owner's or the controller's first name: Dana, Sam."""
        return self.account.first_name(role)

    def engine_charge(self, charge: Charge) -> eng.Charge:
        return adapters.to_engine_charge(charge, self.distributor)

    def emit(self, type_: str, data: Any) -> Any:
        with self.lock:
            ev = EventAdapter.validate_python({"id": len(self.events) + 1, "run_id": self.id, "at": _now(),
                                               "type": type_, "data": data.model_dump(mode="json")})
            self.events.append(ev)
            audit.record(ev, self.account)  # decisions, questions, answers, rules, approvals, postings, disputes...
            saved_events.record(ev, self.account.id)  # the events table, off this thread, so a restart can replay it
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
        rule = next((x for x in rules_of(self.account) if d and x.id == d.rule_id), None)
        found = [self.evidence[i] for i in ids if i in self.evidence]
        # The drawer leads with the deal's sentence and ends with the charge row; the rest keep the cited order.
        found.sort(key=lambda e: 0 if e.kind == "clause" else 2 if e.kind == "charge" else 1)
        return ChargeDetail(charge=self.charges[charge_id], finding=f, decision=d, rehearsal=r, rule=rule,
                            evidence=found)


RUNS: dict[str, Run] = {}
RULES: list[Rule] = []  # saved owner rules, every account's; ids are unique, labels count within an account
RULE_ACCOUNTS: dict[str, str] = {}  # rule id -> the account whose owner it belongs to (Peak Bar if not listed)
QUESTIONS: dict[str, tuple[str, str]] = {}  # question id -> (run id, charge id)
_counter = {"question": 0}
_state = threading.Lock()


def rules_of(account: accounts.Account | str | None = None) -> list[Rule]:
    """One account's saved rules, oldest first."""
    account_id = accounts.resolve(account).id
    return [r for r in RULES if RULE_ACCOUNTS.get(r.id, accounts.DEFAULT) == account_id]


def reset() -> None:
    with _state:
        RUNS.clear(), RULES.clear(), RULE_ACCOUNTS.clear(), QUESTIONS.clear()
        _counter.update(question=0)
    qbo.reset()
    sms.outbox.clear()
    audit.reset()
    _deposit_runs.clear()


class QuestionClosed(ValueError):
    pass


def is_open(q: Question) -> bool:
    return q.answer is None and q.closed_at is None


def start(kind: str | None = None, client: anthropic.Anthropic | None = None, background: bool = True,
          deposit: Any = None, account: accounts.Account | str | None = None) -> Run:
    """A new run of one of the account's months (Peak Bar's by default; its invoice month by default). `deposit` is the
    Nessie deposit that triggered it (api/integrations/nessie.Deposit), if any. It replaces older runs of the same
    account's payment: their open questions close and they ask nobody again. Raises UnknownMonth for a month the
    account has no charges for, and accounts.UnknownAccount for an account that isn't there."""
    account = accounts.resolve(account or accounts.DEFAULT)
    kind = kind or account.invoice.month
    if kind not in account.months:
        raise UnknownMonth(f"{account.id} has no {kind} charges (its months: {', '.join(account.months)})")
    run = Run(id=f"run-{kind}-{uuid.uuid4().hex[:8]}", kind=kind, account=account, deposit=deposit)
    with _state:
        older = [r for r in RUNS.values() if r.kind == kind and r.account.id == account.id and r.replaced_by is None]
        RUNS[run.id] = run
        for old in older:
            old.replaced_by = run.id
    for old in older:
        _close_questions(old)
    work = lambda: _guarded(run, client)  # noqa: E731
    threading.Thread(target=work, daemon=True).start() if background else work()
    return run


def _guarded(run: Run, client) -> None:
    try:
        with accounts.using(run.account):  # what takes no account (the evidence builders) reads this run's files
            _process(run, client)
    except Exception as e:  # noqa: BLE001 - a crash shows on the board instead of hanging the stream
        log.exception("run %s failed", run.id)
        run.log(f"The run stopped: {type(e).__name__}: {e}", "error")
        run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="failed", demo_mode=replay.demo_mode()))
        run.done = True


def _meters(run: Run) -> Totals:
    eng_charges = {cid: run.engine_charge(c) for cid, c in run.charges.items()}
    m = totals.meters(eng_charges, run.decisions)
    return Totals(taken=m["taken"], disputed=m["disputed"], accepted=m["accepted"], waiting=m["waiting"],
                  undecided=m["undecided"], questions=sum(1 for q in run.questions.values()), skipped=m["skipped"])


READER_NAMES = {"claude": "Claude", "gemini": "Gemini", "claude-b": "a second Claude read"}


def _read_terms(run: Run, client) -> list[Term]:
    """Both readers on every deal document; a term counts only when they agree and its quote is found."""
    terms: list[Term] = []
    deal_docs = run.account.config.deal_docs
    for doc_id in deal_docs:
        r = readers.read_both(doc_id, base_terms=[t for t in terms if t.source_doc_id == deal_docs[0]], client=client)
        run.reader_models = r.models
        verified = [t for t in r.terms if t.status == "verified"]
        rejected = [t for t in r.terms if t.status == "rejected"]
        disputed = [t for t in r.terms if t.status == "disputed"]
        if not reader.documents.can_change_deal(r.doc) and verified:
            run.log(f"{r.doc.sender} says: {verified[0].exact_quote} That sender can't change the deal: shown as a claim, "
                    "not applied.", "warn", "reader")
        else:
            second = READER_NAMES[r.models[1]] + (f" ({r.model_ids[1]})" if r.model_ids[1] else "")
            if r.models[1] == "claude-b":  # the key set means Gemini was tried and failed, not that it's missing
                second += " (Gemini didn't answer)" if os.getenv("GEMINI_API_KEY") else " (Gemini isn't set up)"
            run.log(f"Read {doc_id} with {READER_NAMES[r.models[0]]} and {second}: "
                    f"{len(verified)} terms agreed, every quote found word for word."
                    + (f" {len(rejected)} rejected: quote not found." if rejected else ""),
                    "good" if verified and not rejected and not disputed else "warn", "reader")
        for note in r.disagreements:
            run.disagreements[note.split(":", 1)[0]] = note.split(":", 1)[1].strip()
            run.log(f"The readers disagree on {note}. Charges that depend on it go to a person.", "warn", "reader")
        for line in r.unclear:
            run.log(f"Reader left this for a person to review: {line}", "warn", "reader")
        terms += r.terms
    return terms


def _rule_evidence(rule: Rule, account: accounts.Account) -> Evidence:
    return Evidence(id=f"ev-{rule.id}", kind="rule", label=rule.label,
                    summary=f"{rule.summary} Learned from {account.first_name('owner')}'s answer.", rule_id=rule.id,
                    person=f"{account.brand.owner.name} (owner)")


def _process(run: Run, client) -> None:
    policy, account, inv, them = load_policy(), run.account, run.account.invoice, run.distributor
    # Stable IDs: agent requests (and their recorded fixture keys) must not change from run to run.
    remittance_id = f"REM-{inv.id}" if run.kind == inv.month else f"REM-{run.kind.upper()}"
    charges = [c.model_copy(update={"remittance_id": remittance_id}) for c in rows.charges(run.kind, account=account)]
    run.charges = {c.id: c for c in charges}
    eng_charges = {c.id: run.engine_charge(c) for c in charges}
    taken = totals.taken(eng_charges.values())
    remittance = None
    if run.kind == inv.month:
        dep = run.deposit
        remittance = Remittance(id=remittance_id, counterparty=them, invoice_id=inv.id,
                                expected=inv.expected, received=dep.amount if dep else inv.received, taken=taken,
                                charge_count=len(charges), received_at=_now(), nessie_tx_id=dep.id if dep else None)
    run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="started", remittance=remittance,
                            demo_mode=replay.demo_mode()))
    if remittance:
        short = totals.remittance_short(inv.expected, remittance.received)
        if run.deposit:
            run.log(f"Nessie: {them}'s deposit of ${remittance.received:,.0f} arrived (deposit {run.deposit.id}).",
                    actor="system")
        run.log(f"{them} paid ${remittance.received:,.0f} on invoice {inv.id} for ${inv.expected:,.0f}. "
                f"${taken:,.0f} was taken out in {len(charges)} charges.",
                "info" if short == taken else "warn")
    else:
        run.log(f"{them} took {len(charges)} charges, ${taken:,.0f} in all.")
    run.emit("totals", _meters(run))

    run.log("Reading the deal and the emails about it.", actor="reader")
    run.terms = _read_terms(run, client)
    sales_rows, prior_rows = rows.sales(account=account), rows.prior_payments(account=account)
    run.evidence = evidence_mod.build(run.terms, charges, sales_rows, prior_rows)
    run.ops = account_rows.ops(account)  # for the shortage, price and spoilage math (api/engine)
    eng_terms = [adapters.to_engine_term(t) for t in run.terms]
    sales = [adapters.to_engine_sales(r) for r in sales_rows]
    payments = [adapters.to_engine_prior(p) for p in prior_rows]

    for c in charges:
        run.emit("charge", c)
        run.log(f"Checking {c.id}: {c.description}, ${c.amount:,.0f} taken.", actor="investigator", charge_id=c.id)
        a = compute_allowed(eng_charges[c.id], eng_terms, sales, payments)
        run.allowances[c.id] = a
        found = investigator.investigate(c, a, run.evidence, client, account=account)
        if found.output:
            f = Finding(**found.output.model_dump(), id=f"F-{c.id}", expected=a.allowed, taken=a.taken, delta=a.delta,
                        math=evidence_mod.math_parts(a.steps, a.terms, c, run.terms, run.evidence))
            run.findings[c.id] = f
            run.emit("finding", f)
            kinds = {run.evidence[i].kind for i in f.evidence_ids} - {"charge"}
        else:
            run.log(f"Couldn't explain {c.id} from the evidence, so a person decides.", "warn", "investigator", c.id)
            kinds = set()
        discretion = any(gate.uses_discretion(t, policy) for t in a.terms)
        if found.output and a.delta > policy.match_tolerance and not discretion and not a.missing:
            run.log(f"Predicting {them}'s comeback before filing.", actor="negotiator", charge_id=c.id)
            r = negotiator.rehearse(c, run.findings[c.id], a, run.evidence, run.terms, client, account=account)
            run.rehearsals[c.id] = r
            if r.answered:
                run.emit("rehearsal", r)
            else:
                run.log(f"No solid answer to {them}'s likely comeback on {c.id}, so it isn't filed.", "warn",
                        "negotiator", c.id)
        o = found.output
        run.eng_findings[c.id] = eng.Finding(
            charge_id=c.id, confidence=Decimal(str(o.confidence)) if o else Decimal(0),
            evidence_ids=tuple(o.evidence_ids) if o else (), independent_sources=len(kinds),
            comeback_answered=run.rehearsals.get(c.id, Rehearsal(charge_id=c.id, predicted_rebuttal="", answer="",
                                                                 answer_evidence_ids=[], answered=False)).answered,
            type=o.type if o else "", finding=o.finding if o else "")
        _decide(run, c.id, policy)
    # A rule saved by an earlier run opens from this run's cards too. Added after the agents ran, so their
    # requests (and DEMO_MODE fixture keys) don't change.
    for rule in (r for r in rules_of(account) if any(d.rule_id == r.id for d in run.decisions.values())):
        run.evidence.setdefault(f"ev-{rule.id}", _rule_evidence(rule, account))
    _after_decisions(run, policy)


def rule_matches(a: eng.Allowance, policy: eng.Policy, rules: list[eng.Rule], live_first: bool = False) -> moss.Outcome:
    """Moss's candidate rules for the discretion clause this charge depends on (F16), for the gate's rows 3 and 4.
    Moss isn't asked when no active rule exists, there's no discretion clause, or a term failed its checks (rows 1
    and 2 come first). No matches leaves the gate to the exact match on clause type and counterparty."""
    term = next((t for t in a.terms if gate.uses_discretion(t, policy)), None)
    if term is None or not rules or any(t.status != eng.TermStatus.VERIFIED for t in a.terms):
        return moss.Outcome()
    return moss.search(term.exact_quote, live_first)


def _decide(run: Run, charge_id: str, policy: eng.Policy) -> eng.Decision:
    c, a = run.charges[charge_id], run.allowances[charge_id]
    rules = [adapters.to_engine_rule(r) for r in rules_of(run.account) if r.status == "active"]
    found = rule_matches(a, policy, rules)
    if found.error:
        run.log(f"Moss didn't answer ({found.error}); matching saved rules by clause type and counterparty instead.",
                "warn", "gate", charge_id)
    d = gate.decide(run.engine_charge(c), a, run.eng_findings[charge_id], policy, rules, found.matches)
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
        how = ("same clause type and counterparty" if d.rule_similarity is None
               else f"matched by Moss, similarity {d.rule_similarity:.2f}")
        run.log(f"Applied {rule.label} (learned {evidence_mod.day(rule.learned_at)}, approved by {rule.approver.split()[0]}; "
                f"{how}) to {charge_id}.", "good", "gate", charge_id)
    if d.kind == eng.DecisionKind.ASK and not any(q.charge_id == charge_id for q in run.questions.values()):
        _ask_owner(run, charge_id)  # one question per charge per run, never a second
    run.emit("totals", _meters(run))
    return d


def _close_questions(run: Run) -> None:
    """A newer run of the same payment replaced this one: its open questions close, so a text or an inbox answer
    lands on the run people are looking at (a reload, or two tabs, would otherwise leave two open)."""
    for qid, q in list(run.questions.items()):
        if is_open(q):
            run.questions[qid] = closed = q.model_copy(update={"closed_at": _now()})
            run.emit("question", closed)
            run.log(f"Closed {qid}: a newer run ({run.replaced_by}) replaced this one and asks there.", "warn", "gate",
                    q.charge_id)


def _ask_owner(run: Run, charge_id: str) -> None:
    c, a = run.charges[charge_id], run.allowances[charge_id]
    term = next((t for t in a.terms if t.discretion or t.type == eng.TermType.FEE_DISCRETION), a.terms[0] if a.terms else None)
    days = a.facts.get("notice_days")
    split = next((t for t in a.terms if t.status == eng.TermStatus.DISPUTED and t.type.value in run.disagreements), None)
    if split:  # gate row 2: the two readers read the deal differently, so a person settles this charge
        text = (f"{run.distributor} took ${c.amount:,.0f}: {c.description}. Clawback's two readers disagree on the "
                f"deal's {split.type.value.replace('_', ' ')}: {run.disagreements[split.type.value]}. Reply ACCEPT or "
                "DISPUTE for this charge.")
    else:
        text = (f"{run.distributor} took ${c.amount:,.0f}: {c.description}. "
                + (f"The deal says: \"{term.exact_quote}\" " if term else "")
                + (f"Notice came {days} days ahead. " if days is not None else "")
                + "Accept or dispute? Tell me your rule and I'll remember it.")
    with _state:
        _counter["question"] += 1
        qid = f"Q-{_counter['question']}"
        replaced_by = run.replaced_by
    if replaced_by:  # still deciding when a newer run started: the question is born closed and nobody is texted
        q = Question(id=qid, to_role="owner", charge_id=charge_id, text=text, channel="inbox", sent_at=_now(),
                     closed_at=_now())
        run.questions[qid] = q
        QUESTIONS[qid] = (run.id, charge_id)
        run.emit("question", q)
        run.log(f"Didn't ask {run.name('owner')} about {charge_id}: a newer run ({replaced_by}) replaced this one.",
                "warn",
                "gate", charge_id)
        return
    status = sms.send("owner", text)
    q = Question(id=qid, to_role="owner", charge_id=charge_id, text=text, channel="sms" if status == "sent" else "inbox",
                 sent_at=_now())
    run.questions[qid] = q
    QUESTIONS[qid] = (run.id, charge_id)
    run.emit("question", q)
    run.log(f"Asked {run.name('owner')} one question about {charge_id}" + (" by text." if status == "sent" else
            f" in the inbox (text {status})."), actor="gate", charge_id=charge_id)
    if run.replaced_by:  # a newer run started while the text was going out
        _close_questions(run)


def _remember(run: Run, rule: Rule) -> None:
    """Index a new rule in Moss (F16), so a differently worded clause still finds it."""
    saved = moss.index_rule(rule.id, rule.pattern_text, rule.term_type, rule.counterparty, rule.label)
    if saved.error:
        run.log(f"Moss couldn't index {rule.label} ({saved.error}); it still matches by clause type and counterparty.",
                "warn", "gate")
    elif saved.used:
        run.log(f"Indexed {rule.label} in Moss, so a differently worded clause still finds it.", actor="gate")


def _forget(run: Run, rule: Rule) -> None:
    """Drop an undone rule from Moss. Only active rules can match, so a failure here changes no decision."""
    dropped = moss.drop_rule(rule.id)
    if dropped.error:
        run.log(f"Moss couldn't drop {rule.label} ({dropped.error}); it's undone, so it can't match anyway.", "warn",
                "gate")
    elif dropped.used:
        run.log(f"Dropped {rule.label} from Moss.", actor="gate")


def _tell(run: Run, role: str, text: str, level: str = "info", charge_id: str | None = None) -> None:
    """Text someone first (not a reply: replies to their texts go back in the webhook's TwiML, via run.texts).
    The log says whether it went out or waits in the inbox."""
    status = sms.send(role, text)
    where = "Texted" if status == "sent" else f"In the inbox (text {status}) for"
    run.log(f"{where} {run.name(role)}: \"{text}\"", level, "gate" if role == "owner" else "bookkeeper", charge_id)


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
    if run.kind != run.account.invoice.month:  # a later month, replayed with the saved rules (Peak Bar's April)
        run.log("0 questions asked: every fee was decided by a saved rule." if not run.questions
                else f"{len(run.questions)} question(s) asked.", "good" if not run.questions else "info", "gate")
    run.emit("run", RunInfo(run_id=run.id, kind=run.kind, status="finished", demo_mode=replay.demo_mode()))
    run.done = True


# The clause a dispute line quotes, by what the finding is about: the cap for an over-cap charge, not the rate.
LINE_CLAUSE = {"over_cap": "unit_cap", "rate_over": "promo_rate", "product_not_covered": "product_scope",
               "outside_dates": "date_range", "discretionary_fee": "fee_discretion"}


def _line_clause(run: Run, charge_id: str, f: Finding | None) -> Evidence | None:
    """The deal sentence a dispute line quotes: the one its finding turns on (LINE_CLAUSE), else the first clause the
    Investigator cited."""
    want, by_id = LINE_CLAUSE.get(f.type if f else ""), {t.id: t for t in run.terms}
    term = next((by_id[t.id] for t in run.allowances[charge_id].terms if t.type.value == want and t.id in by_id), None)
    ev = run.evidence.get(evidence_mod.clause_id(term)) if term else None
    if ev and ev.kind == "clause":
        return ev
    return next((run.evidence[i] for i in (f.evidence_ids if f else []) if run.evidence[i].kind == "clause"), None)


def _file_dispute(run: Run, charge_ids: list[str], policy: eng.Policy) -> None:
    lines = []
    for cid in charge_ids:
        c, d, f = run.charges[cid], run.decisions[cid], run.findings.get(cid)
        clause = _line_clause(run, cid, f)
        lines.append(DisputeLine(charge_id=cid, ref=c.ref, amount=d.disputed, reason=f.finding if f else d.reason,
                                 clause_ref=clause.label if clause else None,
                                 quote=clause.quote.text if clause and clause.quote else None,
                                 math=" ".join(run.allowances[cid].steps), evidence_ids=list(f.evidence_ids) if f else []))
    total = totals.total_of(ln.amount for ln in lines)
    by_policy = total <= policy.auto_dispute_limit
    filed_before = len({e.data.id for e in run.events if e.type == "dispute"})
    dispute_id = f"D-{run.account.dispute_start(run.kind) + filed_before:04d}"
    run.emit("dispute", Dispute(id=dispute_id, remittance_id=next(iter(run.charges.values())).remittance_id or "",
                                counterparty=run.distributor, lines=lines, total=total,
                                status="filed" if by_policy else "draft", approved_by="policy" if by_policy else "owner",
                                filed_at=_now() if by_policy else None))
    run.log(f"Filed dispute {dispute_id}: {len(lines)} lines, ${total:,.0f}. Within the ${policy.auto_dispute_limit:,.0f} "
            f"limit {run.name('owner')} set." if by_policy else
            f"Dispute {dispute_id} is ${total:,.0f}, over the ${policy.auto_dispute_limit:,.0f} limit: held for "
            f"{run.name('owner')}.", "good" if by_policy else "warn", "negotiator")


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
        run.log(f"Credit memo of ${amount:,.0f} waits on {run.name('controller')} (controller). Nothing posts until "
                f"{run.name('controller')} says yes.", actor="bookkeeper")
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
    q, a, now, owner = run.questions[question_id], run.allowances[charge_id], _now(), run.name("owner")
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
        undone = replies.undo_rule(rules_of(run.account))
        if undone:
            RULES[:] = [undone if r.id == undone.id else r for r in RULES]
            run.emit("rule", undone)
            _forget(run, undone)
        run.texts.append(("owner", replies.undo_text(undone)))
        run.log(f"Texted {owner}: \"{replies.undo_text(undone)}\"", actor="gate", charge_id=charge_id)
        return ans, undone
    if q.closed_at is not None:  # UNDO above still works: rules belong to the owner, not to a run
        raise QuestionClosed(f"{question_id} closed: run {run.replaced_by} replaced {run.id}")
    if q.answer is not None:
        ans = record()
        run.texts.append(("owner", f"{charge_id} is already settled. Reply UNDO to cancel the rule."))
        run.log(f"{charge_id} is already settled; only UNDO changes it now.", actor="gate", charge_id=charge_id)
        return ans, None

    if reply.kind == "once":
        ans = record()
        run.questions[question_id] = q.model_copy(update={"answer": text, "answered_at": now})
        d = gate.decide_by_owner(run.engine_charge(run.charges[charge_id]), a, eng.DecisionKind(reply.decision),
                                 policy, run.decisions[charge_id].gate_row, cap_at_deal=term is not None)
        _record(run, charge_id, d, decided_by="owner")
        run.texts.append(("owner", replies.once_text(reply, charge_id)))
        run.log(f"Texted {owner}: \"{replies.once_text(reply, charge_id)}\"", actor="gate", charge_id=charge_id)
        _after_decisions(run, policy)
        return ans, None

    # Rule ids are unique across accounts; the label counts the account's own rules (Peak Bar's first is Rule #1).
    rule, echo, approver = None, "", run.account.brand.owner.name
    rule_id, number = f"rule-{len(RULES) + 1}", len(rules_of(run.account)) + 1
    if term and reply.kind == "rule":
        rule = replies.rule_from_reply(reply, rule_id=rule_id, pattern_text=term.exact_quote, term_type=term.type,
                                       counterparty=run.distributor, approver=approver, learned_at=now,
                                       source_question_id=question_id, subject=subject)
        rule = rule.model_copy(update={"label": f"Rule #{number}"})
        echo = replies.confirmation_text(reply, subject)
    elif term:  # the parser couldn't read it: Claude tries, and code still checks the condition
        rule = rule_writer.write_rule(q, text, term, run.distributor, dict(a.facts), number, approver, now, client,
                                      account=run.account, rule_id=rule_id)
        echo = rule_writer.echo(rule) if rule else ""
    if rule is None:
        ans = record()
        why = reply.reason or "a rule needs a discretion clause; this one isn't"
        run.texts.append(("owner", replies.REASK_TEXT))
        run.log(f"Couldn't use \"{text}\" ({why}). Texted {owner}: \"{replies.REASK_TEXT}\"", "warn", "gate", charge_id)
        return ans, None

    ans = record(rule.id)
    RULES.append(rule)
    RULE_ACCOUNTS[rule.id] = run.account.id
    run.questions[question_id] = q.model_copy(update={"answer": text, "answered_at": now, "rule_id": rule.id})
    run.evidence[f"ev-{rule.id}"] = _rule_evidence(rule, run.account)
    run.emit("rule", rule)
    run.texts.append(("owner", echo))
    run.log(f"Saved {rule.label} and texted {owner}: \"{echo}\"", "good", "gate")
    _remember(run, rule)
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
    """The newest approval still waiting on this role, for an SMS reply that doesn't name one. A replaced run's
    approvals don't count: Sam's YES must not post an old run's memo while the newer run is still deciding."""
    for run in reversed([r for r in RUNS.values() if r.replaced_by is None]):
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
    the owner. A yes on an approved memo whose QuickBooks write failed retries the write (same request ids, so
    nothing posts twice). Raises KeyError if no live run asked for it, AlreadyDecided (a ValueError) if it was decided."""
    with _state:  # an SMS yes and an in-app yes arriving together decide it once
        found = find_approval(approval_id)
        if found is None:
            raise KeyError(approval_id)
        run, approval = found
        retry = approve and approval.status == "approved" and _write_failed(run, approval_id)
        if approval.status != "pending" and not retry:
            raise AlreadyDecided(approval)
        decided = approval if retry else approval.model_copy(update={
            "status": "approved" if approve else "refused", "note": note or None, "decided_at": _now()})
        if not retry:
            run.emit("approval", decided)
    sam = run.name("controller")
    if retry:
        run.log(f"{sam} approved again: retrying the QuickBooks write for the ${approval.amount:,.0f} credit memo.",
                actor="controller")
        return decided, _post_books(run, decided)
    if not approve:
        run.log(f"{sam} refused the ${approval.amount:,.0f} credit memo" + (f": \"{note}\"" if note else "")
                + ". Nothing posts to QuickBooks; the note is on the card and the memo goes back to "
                + f"{run.name('owner')}.",
                "warn", "controller")
        _tell(run, "owner", f"{sam} held the ${approval.amount:,.0f} credit memo" + (f": {note}" if note else "")
              + ". Nothing was posted to QuickBooks.", "warn")
        return decided, []
    run.log(f"{sam} approved the ${approval.amount:,.0f} credit memo. Posting to QuickBooks.", "good", "controller")
    return decided, _post_books(run, decided)


def _ledger_posts(run: Run, approval_id: str) -> dict[str, LedgerPost]:
    """The newest state of each QuickBooks write for this approval (a retry re-emits a post under the same id)."""
    latest: dict[str, LedgerPost] = {}
    for e in run.events:
        if e.type == "ledger_post" and e.data.approval_id == approval_id:
            latest[e.data.id] = e.data
    return latest


def _write_failed(run: Run, approval_id: str) -> bool:
    return any(p.status == "failed" for p in _ledger_posts(run, approval_id).values())


def failed_approval() -> str | None:
    """The newest approved memo whose QuickBooks write failed, for Sam's YES by text (it retries the write)."""
    for run in reversed([r for r in RUNS.values() if r.replaced_by is None]):
        ids = list(dict.fromkeys(e.data.id for e in run.events if e.type == "approval"))
        for approval_id in reversed(ids):
            if find_approval(approval_id)[1].status == "approved" and _write_failed(run, approval_id):
                return approval_id
    return None


def _open_dispute_lines(run: Run) -> list[DisputeLine]:
    latest: dict[str, Dispute] = {}
    for e in run.events:
        if e.type == "dispute":
            latest[e.data.id] = e.data
    return [ln for d in latest.values() if d.status != "withdrawn" for ln in d.lines]


def _post_books(run: Run, approval: Approval) -> list[LedgerPost]:
    """Write an approved credit memo to QuickBooks, apply it to the invoice and note the disputed balance. Each write
    shows as its own ledger post (the memo as LP-{approval}, the note as LP-{approval}-note), so a failure names the
    write that failed and the board never shows a posted memo as failed. Approving again retries what didn't post;
    request ids come from the approval id, so nothing posts twice."""
    books = qbo.books()
    sim = f" Simulated: {books.why}." if books.simulated else ""
    retry_hint = " Approve again to retry: the same request ids mean it posts once."
    invoice_no = run.account.config.qbo.invoice_no if run.kind == run.account.invoice.month else None
    lines = [LedgerLine(charge_id=ln.charge_id, amount=ln.amount,
                        description=f"{run.charges[ln.charge_id].ref}: {run.charges[ln.charge_id].description}")
             for ln in approval.lines]
    open_lines = _open_dispute_lines(run) if invoice_no else []
    total = totals.total_of(ln.amount for ln in open_lines)
    note = (f"Open ${total:,.2f} disputed with {run.distributor}: "
            + "; ".join(f"{ln.charge_id} {ln.ref} ${ln.amount:,.2f}" for ln in open_lines))
    note_lines = [LedgerLine(charge_id=ln.charge_id, description=f"{ln.ref}: {ln.reason}", amount=ln.amount)
                  for ln in open_lines]
    memo_id, note_id = f"LP-{approval.id}", f"LP-{approval.id}-note"
    done = {pid for pid, p in _ledger_posts(run, approval.id).items() if p.status == "posted"}
    posts: list[LedgerPost] = []
    step, memo = "memo", None
    try:
        if memo_id not in done:
            open_now = books.open_balance(invoice_no) if invoice_no else None
            if open_now is not None and open_now < approval.amount:  # the memo couldn't be applied and would sit there
                raise qbo.BooksError(f"{invoice_no} has only ${open_now:,.2f} open, less than this "
                                     f"${approval.amount:,.2f} memo, so nothing was posted. Run make reset between "
                                     "demo takes")
            memo = books.post_credit_memo(f"{approval.id}-memo", [qbo.Line(ln.charge_id, ln.description, ln.amount)
                                                                 for ln in lines],
                                          memo=f"Clawback {approval.id}: accepted deductions "
                                               f"{', '.join(ln.charge_id for ln in lines)}",
                                          customer=run.account.config.qbo.customer)
            if invoice_no:
                books.apply_to_invoice(f"{approval.id}-apply", invoice_no, memo.id, approval.amount)
            posts.append(LedgerPost(id=memo_id, qbo_entity="credit_memo", qbo_id=memo.id, amount=approval.amount,
                                    lines=lines, status="posted", approval_id=approval.id,
                                    note=(f"Applied to {invoice_no}." if invoice_no else
                                          "Left unapplied: this run has no invoice in QuickBooks.") + sim,
                                    posted_at=_now()))
        if open_lines and note_id not in done:
            step = "note"
            noted = books.note_open_balance(f"{approval.id}-note", invoice_no, note, total)
            posts.append(LedgerPost(id=note_id, qbo_entity="invoice_note", qbo_id=noted.id, amount=total,
                                    status="posted", approval_id=approval.id, note=note + sim, lines=note_lines,
                                    posted_at=_now()))
    except qbo.BooksError as e:
        if step == "note":
            posts.append(LedgerPost(id=note_id, qbo_entity="invoice_note", qbo_id=None, amount=total, lines=note_lines,
                                    status="failed", approval_id=approval.id,
                                    note=f"QuickBooks didn't take the open-balance note ({e})." + retry_hint))
        else:
            made = (f"Credit memo {memo.id} was created but not applied to {invoice_no} ({e})." if memo else
                    f"QuickBooks write failed ({e}).")
            posts.append(LedgerPost(id=memo_id, qbo_entity="credit_memo", qbo_id=memo.id if memo else None,
                                    amount=approval.amount, lines=lines, status="failed", approval_id=approval.id,
                                    note=made + retry_hint))
    for p in posts:
        run.emit("ledger_post", p)
    memo_post = next((p for p in posts if p.qbo_entity == "credit_memo"), None)
    note_post = next((p for p in posts if p.qbo_entity == "invoice_note"), None)
    posted_memo = (f"${approval.amount:,.0f} credit memo posted" + (f" and applied to {invoice_no}" if invoice_no else ""))
    if memo_post and memo_post.status == "failed":
        run.log(f"QuickBooks write failed for {approval.id}; nothing half-posted is shown as done. "
                f"{_sam_can_retry(run)}",
                "error", "bookkeeper")
    elif note_post and note_post.status == "failed":
        run.log("QuickBooks: " + (f"{posted_memo}, but " if memo_post else "") + "the open-balance note failed. "
                + _sam_can_retry(run), "warn", "bookkeeper")
    elif posts:
        parts = ([posted_memo] if memo_post else []) + (
            [f"${note_post.amount:,.0f} stays open, noted with the dispute lines"] if note_post else [])
        run.log("QuickBooks: " + "; ".join(parts) + (f" (simulated: {books.why})." if books.simulated else "."),
                "good", "bookkeeper")
    return posts


def _sam_can_retry(run: Run) -> str:
    return f"{run.name('controller')} can approve again to retry."


def inbox() -> tuple[list[Question], list[Approval]]:
    """Open owner questions and approvals waiting on the controller, across live runs (a replaced run's don't wait)."""
    questions = [q for run in RUNS.values() for q in run.questions.values() if is_open(q)]
    pending = []
    for run in (r for r in RUNS.values() if r.replaced_by is None):
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


_deposit_runs: dict[str, str] = {}  # Nessie deposit id -> the run it started


def start_for_deposit(deposit: Any, client: anthropic.Anthropic | None = None, background: bool = True,
                      account: accounts.Account | str | None = None) -> Run:
    """The invoice month's run for a deposit, once per deposit (the poller and the button can both see it). The
    account is the one the deposit's description names (accounts.for_deposit), Peak Bar if none does."""
    account = account or accounts.for_deposit(deposit.description) or accounts.DEFAULT
    with _state:
        if deposit.id in _deposit_runs:
            return RUNS[_deposit_runs[deposit.id]]
        _deposit_runs[deposit.id] = ""
    run = start(None, client, background, deposit=deposit, account=account)
    _deposit_runs[deposit.id] = run.id
    return run


def run_for_deposit(deposit_id: str) -> Run | None:
    """The run this Nessie deposit started, once it has one."""
    return RUNS.get(_deposit_runs.get(deposit_id) or "")


def latest(kind: str | None = None, account: accounts.Account | str | None = None) -> Run | None:
    """The account's newest live run (Peak Bar's by default), of this kind if one is given."""
    account_id = accounts.resolve(account or accounts.DEFAULT).id
    return next((r for r in reversed(list(RUNS.values()))
                 if r.account.id == account_id and (kind is None or r.kind == kind)), None)


def summary_of(run: Run):
    """GET /summary: totals, disputes still open, the question and approvals still waiting (read-only)."""
    from api.contracts import Summary

    totals_ = [e.data for e in run.events if e.type == "totals"]
    disputes: dict[str, Dispute] = {}
    approvals: dict[str, Approval] = {}
    for e in run.events:
        if e.type == "dispute":
            disputes[e.data.id] = e.data
        elif e.type == "approval":
            approvals[e.data.id] = e.data
    question = next((q for q in reversed(list(run.questions.values())) if is_open(q)), None)
    return Summary(totals=totals_[-1] if totals_ else _meters(run), run_id=run.id, pending_question=question,
                   open_disputes=[d for d in disputes.values() if d.status not in ("resolved", "withdrawn")],
                   pending_approvals=[a for a in approvals.values() if a.status == "pending"])
