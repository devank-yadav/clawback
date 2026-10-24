"""The Northmart portal for live runs: disputes, the judge's replies and Clawback's answers (F9, beat 3).

A reply with a document attached goes back through the Deal Reader. If the document can change the deal
(signed by both parties, or from an approved sender), the engine recomputes the lines and the Negotiator concedes
the difference in a message built from engine numbers. A reply with no document goes to the Negotiator agent
(api/agents/negotiator.answer_reply); a claim gets the evidence and a request for the signed change, agreement
gets a thank-you, and anything else, or an answer that fails its checks twice, is held for the owner.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import anthropic

from api import documents, evidence as evidence_mod, pipeline, adapters, rows
from api.agents import investigator, negotiator, reader
from api.contracts import Dispute, DisputeLine, Finding, MathPart, PortalMessage, PortalPreset
from api.engine import gate, outbound_filter, totals
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy

PRESETS = [
    PortalPreset(id="no-cap", label="There was no cap", expect="claim_without_document", charge_ids=["C4"],
                 text="There was no unit cap on the Spring promo. The week 4 deduction stands."),
    PortalPreset(id="rate", label="The rate was $1.50", expect="claim_without_document", charge_ids=["C1"],
                 text="Per our call on Mar 30, the Spring promo rate is $1.50 per unit, so week 1 is correct."),
    PortalPreset(id="not-a-repeat", label="Week 2 isn't a repeat", expect="claim_without_document", charge_ids=["C2"],
                 text="NM-2231 is a new claim for week 2, not a repeat of NM-2178."),
    PortalPreset(id="agree-mint", label="Agree on Mint", expect="agrees", charge_ids=["C5"],
                 text="Agreed, Mint wasn't part of the Spring promo. We'll credit the Mint deduction back."),
    PortalPreset(id="amendment", label="Attach signed amendment", expect="new_document", charge_ids=["C4"],
                 attachment_doc_id="amendment-1",
                 text="The cap was raised to 6,000 units. The signed amendment is attached."),
]

THREADS: dict[str, list[PortalMessage]] = {}


def reset() -> None:
    THREADS.clear()


def find(dispute_id: str) -> tuple[pipeline.Run, Dispute] | None:
    """The newest live run that filed this dispute, and the dispute as it stands now."""
    for run in reversed(list(pipeline.RUNS.values())):
        latest = [e.data for e in run.events if e.type == "dispute" and e.data.id == dispute_id]
        if latest:
            return run, latest[-1]
    return None


def thread(dispute_id: str) -> list[PortalMessage]:
    return THREADS.setdefault(dispute_id, [])


def _message(dispute_id: str, from_party: str, text: str, **kw) -> PortalMessage:
    t = thread(dispute_id)
    m = PortalMessage(id=f"PM-{dispute_id}-{len(t) + 1}", dispute_id=dispute_id, from_party=from_party, text=text,
                      created_at=datetime.now().astimezone(), **kw)
    t.append(m)
    return m


def post(dispute_id: str, text: str, attachment_doc_id: str | None = None,
         client: anthropic.Anthropic | None = None) -> list[PortalMessage]:
    """Northmart's reply and Clawback's answer (if one goes out). Both also stream on the run."""
    run, dispute = find(dispute_id)
    if attachment_doc_id:
        theirs = _message(dispute_id, "northmart", text, attachment_doc_id=attachment_doc_id,
                          classification="new_document")
        run.emit("portal_message", theirs)
        ours = _new_document(run, dispute, attachment_doc_id, client)
        return [theirs] + ([ours] if ours else [])
    draft = negotiator.answer_reply(dispute, text, run.evidence, run.terms, client)
    theirs = _message(dispute_id, "northmart", text, classification=draft.classification if draft else "other",
                      charge_ids=draft.charge_ids if draft else [])
    run.emit("portal_message", theirs)
    owner = pipeline.OWNER.split()[0]
    if draft is None or draft.classification == "other" or not draft.answer:
        run.log(f"Northmart's reply on {dispute_id} needs a person: held for {owner}.", "warn", "negotiator")
        return [theirs]
    ours = _message(dispute_id, "clawback", draft.answer, charge_ids=draft.charge_ids,
                    evidence_ids=draft.evidence_ids)
    run.emit("portal_message", ours)
    if draft.classification == "agrees":
        run.log(f"Northmart agreed on {', '.join(draft.charge_ids)}.", "good", "negotiator")
    else:
        run.log(f"Northmart replied \"{draft.claim or text}\" with no document. Answered with the evidence and "
                "asked for the signed change.", "good", "negotiator")
    return [theirs, ours]


def _new_document(run: pipeline.Run, dispute: Dispute, doc_id: str, client) -> PortalMessage | None:
    owner, policy = pipeline.OWNER.split()[0], load_policy()
    if doc_id not in documents.PATHS:
        run.log(f"Northmart attached a document Clawback doesn't have ({doc_id}): held for {owner}.", "warn", "negotiator")
        return None
    deal = [t for t in run.terms if t.source_doc_id == pipeline.DEAL_DOCS[0]]
    r = reader.read_document(doc_id, base_terms=deal, client=client)
    if not documents.can_change_deal(r.doc):
        msg = (f"Thanks. The attached document isn't signed by both parties or sent by Peak Bar Co.'s approved "
               f"representatives, so under §6.1 it doesn't change the deal. {dispute.id} stands.")
        return _send(run, dispute, msg, [], [])
    new_terms = [t for t in r.terms if t.status == "verified"]
    if not new_terms:
        run.log(f"No term in {doc_id} could be verified word for word: held for {owner}.", "warn", "reader")
        return None
    run.log(f"Read {doc_id}: signed by both parties, {len(new_terms)} term(s) verified. Recomputing {dispute.id}.",
            "good", "reader")
    run.terms += new_terms
    run.evidence.update(evidence_mod.from_terms(new_terms))
    eng_terms = [adapters.to_engine_term(t) for t in run.terms]
    sales = [adapters.to_engine_sales(x) for x in rows.sales()]
    payments = [adapters.to_engine_prior(p) for p in rows.prior_payments()]
    conceded: list[tuple[str, Decimal]] = []
    for ln in dispute.lines:
        before = run.decisions[ln.charge_id]
        a = compute_allowed(adapters.to_engine_charge(run.charges[ln.charge_id]), eng_terms, sales, payments)
        if a.allowed == run.allowances[ln.charge_id].allowed:
            continue
        run.allowances[ln.charge_id] = a
        _refresh_finding(run, ln.charge_id, a, client)
        after = pipeline._decide(run, ln.charge_id, policy)
        if (given := gate.concession(before, after)) > 0:
            conceded.append((ln.charge_id, given))
    if not conceded:
        msg = f"Thanks for the document. It doesn't change any line on {dispute.id}, which stands."
        return _send(run, dispute, msg, [], [])
    lines = [ln.model_copy(update={"amount": run.decisions[ln.charge_id].disputed,
                                   "math": " ".join(run.allowances[ln.charge_id].steps)})
             for ln in dispute.lines if run.decisions[ln.charge_id].disputed > 0]
    total = totals.total_of(ln.amount for ln in lines)
    run.emit("dispute", dispute.model_copy(update={"lines": lines, "total": total, "status": "answered"}))
    cap = next((t.params.get("max_units") for t in new_terms if t.type == "unit_cap"), None)
    parts = [f"we withdraw ${amt:,.0f} of {run.charges[cid].ref} ({cid}) and keep "
             f"${run.decisions[cid].disputed:,.0f} disputed" for cid, amt in conceded]
    msg = (f"Thanks for the signed amendment{f', which raises the cap to {int(cap):,} units' if cap else ''}. "
           f"Under it, {'; '.join(parts)}. {dispute.id} now totals ${total:,.0f}.")
    ours = _send(run, dispute, msg, [cid for cid, _ in conceded],
                 [evidence_mod.clause_id(t) for t in new_terms])
    run.log(f"Conceded ${totals.total_of(a for _, a in conceded):,.0f} after Northmart's signed amendment.", "good",
            "negotiator")
    pipeline._request_credit_memo(run, policy, conceded)
    return ours


def _refresh_finding(run: pipeline.Run, charge_id: str, a, client) -> None:
    """New terms, new numbers: the Investigator explains the charge again so the card stays true."""
    inv = investigator.investigate(run.charges[charge_id], a, run.evidence, client)
    old = run.eng_findings[charge_id]
    if inv.output:
        f = Finding(**inv.output.model_dump(), id=f"F-{charge_id}", expected=a.allowed, taken=a.taken, delta=a.delta,
                    math=[MathPart(text=s) for s in a.steps])
        run.findings[charge_id] = f
        run.emit("finding", f)
        kinds = {run.evidence[i].kind for i in f.evidence_ids} - {"charge"}
        run.eng_findings[charge_id] = old.__class__(
            charge_id=charge_id, confidence=Decimal(str(f.confidence)), evidence_ids=tuple(f.evidence_ids),
            independent_sources=len(kinds), comeback_answered=old.comeback_answered, type=f.type, finding=f.finding)


def _send(run: pipeline.Run, dispute: Dispute, text: str, charge_ids: list[str], evidence_ids: list[str]) -> PortalMessage | None:
    """Every outgoing message passes the outbound filter; one built by code that fails is held, never sent."""
    amounts = [x for cid in run.charges for x in (run.decisions[cid].disputed, run.decisions[cid].accepted,
                                                  run.allowances[cid].allowed, run.charges[cid].amount)]
    amounts += [dispute.total, totals.total_of(ln.amount for ln in dispute.lines)]
    amounts += [e.data.total for e in run.events if e.type == "dispute"]
    ctx = outbound_filter.OutboundContext.build(amounts=amounts,
                                                terms=[t.model_dump(mode="json") for t in run.terms if t.status == "verified"])
    result = outbound_filter.check_message(text, ctx)
    if not result.ok:
        run.log(f"Held a message to Northmart for {pipeline.OWNER.split()[0]}: {result.feedback()}", "warn", "negotiator")
        return None
    ours = _message(dispute.id, "clawback", text, charge_ids=charge_ids, evidence_ids=evidence_ids)
    run.emit("portal_message", ours)
    return ours
