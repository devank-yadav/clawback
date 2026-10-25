"""The distributor's portal for live runs (Peak Bar's: Northmart): disputes, the judge's replies and Clawback's
answers (F9, beat 3).

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

from api import accounts, documents, evidence as evidence_mod, pipeline, adapters, rows, trace
from api.agents import investigator, negotiator, readers
from api.contracts import Dispute, DisputeLine, Finding, PortalMessage, PortalPreset
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

THREADS: dict[tuple[str, str], list[PortalMessage]] = {}  # (run id, dispute id): every run numbers from D-0417


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
    """The thread of the newest run that filed this dispute (an older run's D-0417 keeps its own)."""
    found = find(dispute_id)
    return THREADS.setdefault((found[0].id if found else "", dispute_id), [])


def _message(dispute_id: str, from_party: str, text: str, thread_of: pipeline.Run | None = None, **kw) -> PortalMessage:
    t = THREADS.setdefault((thread_of.id, dispute_id), []) if thread_of else thread(dispute_id)
    m = PortalMessage(id=f"PM-{dispute_id}-{len(t) + 1}", dispute_id=dispute_id, from_party=from_party, text=text,
                      created_at=datetime.now().astimezone(), **kw)
    t.append(m)
    return m


def post(dispute_id: str, text: str, attachment_doc_id: str | None = None,
         client: anthropic.Anthropic | None = None, agree_charge_ids: list[str] | None = None) -> list[PortalMessage]:
    """The distributor's reply and Clawback's answer (if one goes out). Both also stream on the run, and the supplier
    is told (api/dispute_email.notify_reply)."""
    from api import dispute_email

    run, dispute = find(dispute_id)
    with accounts.using(run.account), trace.run_context(run.id):  # the run's files; AI calls traced to the run
        if agree_charge_ids and not attachment_doc_id:
            got = _agreed(run, dispute, text, agree_charge_ids)
        else:
            got = _post(run, dispute, text, attachment_doc_id, client)
    dispute_email.notify_reply(run, dispute, got, "the portal")
    return got


def _agreed(run: pipeline.Run, dispute: Dispute, text: str, charge_ids: list[str], deliver=None) -> list[PortalMessage]:
    """The desk accepted these lines with the portal's Accept action: an agreement, by code, and a thank-you."""
    lines = {ln.charge_id: ln for ln in dispute.lines}
    cids = [c for c in dict.fromkeys(charge_ids) if c in lines]
    theirs = _message(dispute.id, "northmart", text, classification="agrees" if cids else "other", charge_ids=cids)
    run.emit("portal_message", theirs)
    if not cids:
        run.log(f"{run.distributor}'s reply on {dispute.id} names no line of it: held for {run.name('owner')}.", "warn",
                "negotiator")
        return [theirs]
    named = ", ".join(f"{lines[c].ref} ({c})" for c in cids)
    total = totals.total_of(lines[c].amount for c in cids)
    ours = _send(run, dispute, f"Thank you for accepting {named}, ${total:,.2f} of {dispute.id}.", cids,
                 [i for c in cids for i in lines[c].evidence_ids][:3], deliver)
    run.log(f"{run.distributor} accepted {named} on {dispute.id}.", "good", "negotiator")
    return [theirs] + ([ours] if ours else [])


def _deliver_portal(run: pipeline.Run, dispute: Dispute, text: str, charge_ids: list[str],
                    evidence_ids: list[str]) -> PortalMessage | None:
    """Clawback's answer on the portal: posted at once (an email reply instead waits for the admin, dispute_email)."""
    ours = _message(dispute.id, "clawback", text, charge_ids=charge_ids, evidence_ids=evidence_ids)
    run.emit("portal_message", ours)
    return ours


def _post(run: pipeline.Run, dispute: Dispute, text: str, attachment_doc_id: str | None, client, deliver=None,
          channel: str = "portal", email_message_id: str | None = None) -> list[PortalMessage]:
    """The distributor's reply and Clawback's answer. `deliver` sends the answer (the portal's posts it; the email
    channel's drafts it for the admin and returns None); `channel` marks where the reply came from."""
    dispute_id, them = dispute.id, run.distributor
    deliver = deliver or _deliver_portal
    via = {"channel": channel, "email_message_id": email_message_id}
    if attachment_doc_id:
        theirs = _message(dispute_id, "northmart", text, attachment_doc_id=attachment_doc_id,
                          classification="new_document", **via)
        run.emit("portal_message", theirs)
        ours = _new_document(run, dispute, attachment_doc_id, client, deliver)
        return [theirs] + ([ours] if ours else [])
    draft = negotiator.answer_reply(dispute, text, run.evidence, run.terms, client, account=run.account)
    theirs = _message(dispute_id, "northmart", text, classification=draft.classification if draft else "other",
                      charge_ids=draft.charge_ids if draft else [], **via)
    run.emit("portal_message", theirs)
    owner = run.name("owner")
    if draft is None or draft.classification == "other" or not draft.answer:
        run.log(f"{them}'s reply on {dispute_id} needs a person: held for {owner}.", "warn", "negotiator")
        return [theirs]
    ours = deliver(run, dispute, draft.answer, draft.charge_ids, draft.evidence_ids)
    if ours is None:
        return [theirs]
    if draft.classification == "agrees":
        run.log(f"{them} agreed on {', '.join(draft.charge_ids)}.", "good", "negotiator")
    else:
        run.log(f"{them} replied \"{draft.claim or text}\" with no document. Answered with the evidence and "
                "asked for the signed change.", "good", "negotiator")
    return [theirs, ours]


def _new_document(run: pipeline.Run, dispute: Dispute, doc_id: str, client, deliver=None,
                  keep_status: bool = False) -> PortalMessage | None:
    """A document that may change the deal under an open dispute. keep_status: the document came from the supplier's
    own Drive before the dispute was sent, so a recomputed dispute stays the admin's draft (api/drive.py)."""
    owner, policy, them = run.name("owner"), load_policy(), run.distributor
    if doc_id not in run.account.docs:
        run.log(f"{them} attached a document Clawback doesn't have ({doc_id}): held for {owner}.", "warn", "negotiator")
        return None
    deal = [t for t in run.terms if t.source_doc_id == run.account.config.deal_docs[0]]
    r = readers.read_both(doc_id, base_terms=deal, client=client)
    if not documents.can_change_deal(r.doc):
        msg = (f"Thanks. The attached document isn't signed by both parties or sent by {run.account.brand.name}'s "
               f"approved representatives, so under §6.1 it doesn't change the deal. {dispute.id} stands.")
        return _send(run, dispute, msg, [], [], deliver)
    new_terms = [t for t in r.terms if t.status == "verified"]
    if not new_terms:
        why = "; ".join(r.disagreements) or "no quote was found word for word"
        run.log(f"No term in {doc_id} was verified by both readers ({why}): held for {owner}.", "warn", "reader")
        return None
    run.log(f"Read {doc_id}: signed by both parties, {len(new_terms)} term(s) verified. Recomputing {dispute.id}.",
            "good", "reader")
    run.terms += new_terms
    run.evidence.update(evidence_mod.from_terms(new_terms))
    eng_terms = [adapters.to_engine_term(t) for t in run.terms]
    sales = [adapters.to_engine_sales(x) for x in rows.sales(account=run.account)]
    payments = [adapters.to_engine_prior(p) for p in rows.prior_payments(account=run.account)]
    conceded: list[tuple[str, Decimal]] = []
    for ln in dispute.lines:
        before = run.decisions[ln.charge_id]
        a = compute_allowed(run.engine_charge(run.charges[ln.charge_id]), eng_terms, sales, payments)
        if a.allowed == run.allowances[ln.charge_id].allowed:
            continue
        run.allowances[ln.charge_id] = a
        _refresh_finding(run, ln.charge_id, a, client)
        after = pipeline._decide(run, ln.charge_id, policy)
        if (given := gate.concession(before, after)) > 0:
            conceded.append((ln.charge_id, given))
    if not conceded:
        msg = f"Thanks for the document. It doesn't change any line on {dispute.id}, which stands."
        return _send(run, dispute, msg, [], [], deliver)
    lines = [ln.model_copy(update={"amount": run.decisions[ln.charge_id].disputed,
                                   "math": " ".join(run.allowances[ln.charge_id].steps)})
             for ln in dispute.lines if run.decisions[ln.charge_id].disputed > 0]
    total = totals.total_of(ln.amount for ln in lines)
    run.emit("dispute", dispute.model_copy(update={"lines": lines, "total": total,
                                                   "status": dispute.status if keep_status else "answered"}))
    cap = next((t.params.get("max_units") for t in new_terms if t.type == "unit_cap"), None)
    parts = [f"we withdraw ${amt:,.0f} of {run.charges[cid].ref} ({cid}) and keep "
             f"${run.decisions[cid].disputed:,.0f} disputed" for cid, amt in conceded]
    msg = (f"Thanks for the signed amendment{f', which raises the cap to {int(cap):,} units' if cap else ''}. "
           f"Under it, {'; '.join(parts)}. {dispute.id} now totals ${total:,.0f}.")
    ours = _send(run, dispute, msg, [cid for cid, _ in conceded],
                 [evidence_mod.clause_id(t) for t in new_terms], deliver)
    run.log(f"Conceded ${totals.total_of(a for _, a in conceded):,.0f} after {them}'s signed amendment.", "good",
            "negotiator")
    pipeline._request_credit_memo(run, policy, conceded)
    return ours


def _refresh_finding(run: pipeline.Run, charge_id: str, a, client) -> None:
    """New terms, new numbers: the Investigator explains the charge again so the card stays true."""
    inv = investigator.investigate(run.charges[charge_id], a, run.evidence, client, account=run.account)
    old = run.eng_findings[charge_id]
    if inv.output:
        f = Finding(**inv.output.model_dump(), id=f"F-{charge_id}", expected=a.allowed, taken=a.taken, delta=a.delta,
                    math=evidence_mod.math_parts(a.steps, a.terms, run.charges[charge_id], run.terms, run.evidence))
        run.findings[charge_id] = f
        run.emit("finding", f)
        kinds = {run.evidence[i].kind for i in f.evidence_ids} - {"charge"}
        run.eng_findings[charge_id] = old.__class__(
            charge_id=charge_id, confidence=Decimal(str(f.confidence)), evidence_ids=tuple(f.evidence_ids),
            independent_sources=len(kinds), comeback_answered=old.comeback_answered, type=f.type, finding=f.finding)


def outbound_context(run: pipeline.Run, dispute: Dispute) -> outbound_filter.OutboundContext:
    """What a message to the distributor about this dispute may say: the run's engine numbers and verified terms."""
    amounts = [x for cid in run.charges if cid in run.decisions and cid in run.allowances
               for x in (run.decisions[cid].disputed, run.decisions[cid].accepted, run.allowances[cid].allowed,
                         run.charges[cid].amount)]
    amounts += [dispute.total, totals.total_of(ln.amount for ln in dispute.lines)]
    amounts += [e.data.total for e in run.events if e.type == "dispute"]
    return outbound_filter.OutboundContext.build(
        amounts=amounts, terms=[t.model_dump(mode="json") for t in run.terms if t.status == "verified"],
        findings=[ln.quote for ln in dispute.lines if ln.quote] + [ln.reason for ln in dispute.lines])


def _send(run: pipeline.Run, dispute: Dispute, text: str, charge_ids: list[str], evidence_ids: list[str],
          deliver=None) -> PortalMessage | None:
    """Every outgoing message passes the outbound filter; one built by code that fails is held, never sent."""
    result = outbound_filter.check_message(text, outbound_context(run, dispute))
    if not result.ok:
        run.log(f"Held a message to {run.distributor} for {run.name('owner')}: {result.feedback()}", "warn",
                "negotiator")
        return None
    return (deliver or _deliver_portal)(run, dispute, text, charge_ids, evidence_ids)
