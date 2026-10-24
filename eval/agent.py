"""Eval in agent mode (F12): the 30 planted charges with the readers and agents in the loop.

Run: python eval/run.py --mode agent [--cases E01,E02] [--estimate]
     DEMO_MODE=true python eval/run.py --mode agent   (replays a recorded run for free)

Engine mode hands the engine the deal terms straight from each row (and, for the "readers disagree" cases, a
disputed term taken from the answer key). Agent mode gives the system only what a real run gets:
- the deal as a document: a short signed agreement in the Spring deal's wording, written from the row's deal
  columns; where the row has clause_text, that clause is the deal's rate clause (promo cases) or fee clause (fees);
- the email, if the row has one, as its own document from its sender (approved or not by config/policy.yaml);
- the store sales, prior payments, notice date and saved rules from the same build_case() engine mode uses.
Both Deal Readers read the documents, then the engine, the Investigator, the rehearsal (for a would-be dispute)
and the gate decide, as in api/scenario.py. The answer key is used only to score. Every AI answer is recorded,
so a second run in DEMO_MODE costs nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from email.utils import format_datetime

from api import adapters, documents, evidence as evidence_mod
from api.agents import investigator, negotiator, readers
from api.contracts import Charge, Evidence, Finding, MathPart, PriorPayment, SalesRow, Term
from api.engine import gate
from api.engine import types as eng
from api.engine.allowed import compute_allowed, split_products


@dataclass
class AgentCase:
    case_id: str
    tag: str
    deal_text: str
    email: tuple[str, str, datetime] | None  # (sender, the email as a document, when it was sent)
    case: object  # eval/run.py's Case: charge, sales, priors, rules (its terms and finding are not used)


def _money_text(v: str) -> str:
    return f"${Decimal(v):,.2f}"


def _products_text(products: str) -> str:
    names = list(split_products(products))
    return " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " and " + names[-1]


def _span(start: date, end: date) -> str:
    return f"{start:%B} {start.day} and {end:%B} {end.day}, {end.year}"


def deal_text(row: dict[str, str]) -> str:
    """The case's deal as a signed agreement, in the wording the Spring deal uses."""
    cid = row["case_id"]
    out = [f"# Promotional Allowance Agreement EVAL-{cid}", "",
           "> FICTIONAL. Written for the Clawback eval; Peak Bar Co. and Northmart are invented.", "",
           'Between Peak Bar Co. ("Supplier") and Northmart ("Distributor").', ""]
    if row["code"] == "PA":
        start, end = date.fromisoformat(row["deal_start"]), date.fromisoformat(row["deal_end"])
        rate = row["clause_text"] or (
            f"Supplier will fund a promotional allowance of {_money_text(row['deal_rate'])} per unit on "
            f"{_products_text(row['deal_products'])} sold between {_span(start, end)}.")
        out += ["## 3. Promotional allowance", "", f"3.1 {rate}", ""]
        if row["deal_cap"]:
            out += [f"3.2 The promotional allowance applies to a maximum of {int(row['deal_cap']):,} units in total.", ""]
    else:
        fee = row["clause_text"] or (f"Northmart may charge a display fee of up to {_money_text(row['fee_max'])} per "
                                     "month at its discretion, with written notice to Supplier.")
        out += ["## 5. Fees", "", f"5.4 {fee}", ""]
    out += ["**Signed** by Dana Okafor for Peak Bar Co. and by Northmart's Category Manager."]
    return "\n".join(out) + "\n"


def email_text(row: dict[str, str]) -> tuple[str, datetime]:
    """The row's email as an .eml-style document, dated three days before the deal ends."""
    sent = datetime.combine(date.fromisoformat(row["deal_end"]) - timedelta(days=3), time(10, 0), tzinfo=timezone.utc)
    return (f"From: {row['doc_sender']}\nTo: dana@peakbar.example\nDate: {format_datetime(sent)}\n"
            f"Subject: Promo EVAL-{row['case_id']}\n\n{row['doc_text']}\n"), sent


def build(row: dict[str, str], key: dict[str, str], policy, ev) -> AgentCase:
    email = (row["doc_sender"], *email_text(row)) if row["doc_text"] else None
    return AgentCase(row["case_id"], key["reason"].split(":", 1)[0].strip(), deal_text(row), email,
                     ev.build_case(row, key, policy))


def _contract_charge(c: eng.Charge) -> Charge:
    return Charge(id=c.id, ref=c.ref, code=c.code, description=c.description, product="+".join(c.products) or None,
                  units=c.units, rate=c.rate, amount=c.amount, period_start=c.period_start, period_end=c.period_end,
                  notice_date=c.notice_date)


def _contract_sales(s: eng.SalesWeek) -> SalesRow:
    return SalesRow(week_start=s.week_start, week_end=s.week_end, product=s.product or "unknown",
                    promo_units=s.promo_units, total_units=s.total_units)


def _contract_prior(p: eng.PriorPayment) -> PriorPayment:
    return PriorPayment(ref=p.ref, paid_on=p.paid_on, promo_id=p.promo_id, product="+".join(p.products),
                        period_start=p.period_start, period_end=p.period_end, units=p.units, amount=p.amount)


def read_case(c: AgentCase, client=None) -> tuple[list[Term], list[str], tuple[str, str]]:
    """Both readers on the case's deal and email. Returns the merged terms, the disagreements and who read."""
    deal = documents.paste(c.deal_text)
    merged = readers.read_both(deal.id, client=client)
    terms, notes = list(merged.terms), list(merged.disagreements)
    if c.email:
        sender, text, sent = c.email
        doc = documents.paste(text, kind="email", sender=sender, received_at=sent)
        more = readers.read_both(doc.id, base_terms=merged.terms, client=client)
        terms += more.terms
        notes += more.disagreements
    return terms, notes, merged.models


def decide(c: AgentCase, policy, client=None):
    """One case through readers, engine, Investigator, rehearsal and gate. Returns (decision, notes)."""
    terms, notes, models = read_case(c, client)
    case = c.case
    charge = _contract_charge(case.charge)
    sales = [_contract_sales(s) for s in case.sales]
    priors = [_contract_prior(p) for p in case.priors]
    scope = next((t for t in terms if t.type == "product_scope" and t.status == "verified"), None)
    ev: dict[str, Evidence] = {**evidence_mod.from_terms(terms),
                               **evidence_mod.from_sales(sales, scope.params["products"] if scope else []),
                               **evidence_mod.from_charges([charge]), **evidence_mod.from_payments(priors)}
    if charge.notice_date:
        days = (charge.period_end - charge.notice_date).days
        ev[f"ev-notice-{charge.id}"] = Evidence(
            id=f"ev-notice-{charge.id}", kind="notice", label=f"Notice {evidence_mod.day(charge.notice_date)}",
            summary=f"Northmart gave written notice of this fee on {evidence_mod.day(charge.notice_date, year=True)}, {days} days "
                    "before the period ends.")
    a = compute_allowed(case.charge, [adapters.to_engine_term(t) for t in terms], case.sales, case.priors)
    inv = investigator.investigate(charge, a, ev, client)
    finding = (Finding(**inv.output.model_dump(), id=f"F-{charge.id}", expected=a.allowed, taken=a.taken,
                       delta=a.delta, math=[MathPart(text=s) for s in a.steps]) if inv.output else None)
    discretion = any(gate.uses_discretion(t, policy) for t in a.terms)
    rehearsal = None
    if finding and a.delta > policy.match_tolerance and not discretion and not a.missing:
        rehearsal = negotiator.rehearse(charge, finding, a, ev, terms, client)
    kinds = {ev[i].kind for i in (finding.evidence_ids if finding else [])} - {"charge"}
    f = eng.Finding(charge_id=charge.id, confidence=Decimal(str(finding.confidence)) if finding else Decimal(0),
                    evidence_ids=tuple(finding.evidence_ids) if finding else (), independent_sources=len(kinds),
                    comeback_answered=bool(rehearsal and rehearsal.answered),
                    type=finding.type if finding else "", finding=finding.finding if finding else "")
    d = gate.decide(case.charge, a, f, policy, case.rules)
    notes = notes + ([f"readers: {models[0]} + {models[1]}"] if models else [])
    if not finding:
        notes.append("Investigator gave no usable finding")
    return d, notes, models


def estimate(cases: list[AgentCase], policy, ev) -> dict:
    """What a live agent run would call, without calling anything: reads, findings and rehearsals, plus the
    characters of document text sent (the prompts and evidence add a few thousand tokens per call)."""
    reads = sum(2 * (1 + (1 if c.email else 0)) for c in cases)
    rehearsals = 0
    for c in cases:  # a rehearsal runs where the engine alone would dispute or split
        a = compute_allowed(c.case.charge, c.case.terms, c.case.sales, c.case.priors)
        d = gate.decide(c.case.charge, a, c.case.finding, policy, c.case.rules)
        rehearsals += d.kind in (eng.DecisionKind.DISPUTE, eng.DecisionKind.SPLIT) or d.gate_row == 8
    calls = reads + len(cases) + rehearsals
    return {"cases": len(cases), "reader_calls": reads, "investigator_calls": len(cases),
            "rehearsal_calls": rehearsals, "calls": calls,
            "document_chars": sum(len(c.deal_text) + (len(c.email[1]) if c.email else 0) for c in cases)}


def run(data_dir, only: set[str] | None = None, client=None, ev=None):
    """Score every case (or the ones in `only`). Returns (results, reader models used)."""
    from api.engine.policy import load_policy

    policy = load_policy()
    rows, key = ev.load(data_dir)
    results, models = [], set()
    for row in rows:
        if only and row["case_id"] not in only:
            continue
        k = key[row["case_id"]]
        exp = ev.Expected(eng.DecisionKind(k["expected_decision"]), eng.money(k["expected_disputed"]),
                          eng.money(k["expected_accepted"]), k["reason"])
        c = build(row, k, policy, ev)
        d, notes, used = decide(c, policy, client)
        models.add(used)
        r = ev.judge(c.case_id, c.tag, exp, d)
        r.notes += notes
        results.append(r)
    return results, sorted(models)


def misses_json(results) -> str:
    return json.dumps([{"case": r.case_id, "tag": r.tag, "verdict": r.verdict, "got": r.decision.value,
                        "expected": r.expected.decision.value, "gate_row": r.gate_row, "notes": r.notes}
                       for r in results if r.verdict != "correct"], indent=2)
