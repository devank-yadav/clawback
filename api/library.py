"""Connections (where payments, records and contracts come from, as they really are on this server) and the contract
library (each distributor's signed deal, locked, with the terms the agents read highlighted where they sit)."""

from __future__ import annotations

import os

from api import accounts, documents
from api.contracts import Connection, ContractLibrary, LibraryDocument, LibraryTerm
from api.integrations import nessie, replay, sms

QBO_KEYS = ("QBO_CLIENT_ID", "QBO_CLIENT_SECRET", "QBO_REALM_ID", "QBO_REFRESH_TOKEN")


def connections() -> list[Connection]:
    qbo = all(os.getenv(k) for k in QBO_KEYS)
    demo = replay.demo_mode()
    return [
        Connection(id="quickbooks", name="QuickBooks", brings="Invoices, payments received, credit memos",
                   status="connected" if qbo and not demo else "not_connected",
                   detail="Sandbox company; credit memos post only after your approval" if qbo and not demo
                   else "Not connected on this server: postings are simulated and say so"),
        Connection(id="bank", name="Bank (Capital One)", brings="Deposits: a short payment starts the agents",
                   status="connected" if nessie.configured() else "not_connected",
                   detail="Checked every 5 seconds for new deposits" if nessie.configured()
                   else "Not connected: use “Send a test payment” on Agents"),
        Connection(id="upload", name="Upload", brings="Remittance advice, contracts and records as files",
                   status="ready", detail="PDF, CSV or text; the Payment reader checks every line adds up"),
        Connection(id="texts", name="Texts to you", brings="Your one question and approvals by WhatsApp or SMS",
                   status="connected" if sms.configured("owner") else "not_connected",
                   detail="A reply answers it" if sms.configured("owner") else "Not connected: decisions wait in the app"),
        Connection(id="inbox", name="Remittance inbox", brings="Remittances and broker emails, read automatically",
                   status="coming_soon", detail="A forwarding address per distributor"),
        Connection(id="portals", name="Distributor portals", brings="Walmart Retail Link, KeHE CONNECT, UNFI",
                   status="coming_soon", detail="Deduction exports pulled on a schedule"),
        Connection(id="edi", name="EDI 820", brings="Remittance advice lines straight from the distributor",
                   status="coming_soon", detail="The standard payment-and-remittance message"),
        Connection(id="drive", name="Google Drive / DocuSign", brings="Signed contracts",
                   status="coming_soon", detail="Import once; the signed original stays locked"),
    ]


def _label(t) -> str:
    p = t.params
    if t.type == "promo_rate":
        return f"${p.get('rate')} per unit"
    if t.type == "unit_cap":
        return f"at most {int(p.get('max_units', 0)):,} units"
    if t.type == "product_scope":
        return "covers " + ", ".join(p.get("products", []))
    if t.type == "date_range":
        return f"{p.get('start')} to {p.get('end')}"
    if t.type == "fee_discretion":
        return f"fee up to ${p.get('max_fee')}, at their discretion"
    if t.type == "amendment":
        return f"+{p.get('extra_units')} units, {t.effective_from} to {t.effective_to}"
    if t.type == "fee_schedule":
        return f"{p.get('fee_code')}: {p.get('rate')}{'%' if p.get('basis') == 'percent' else ''} {p.get('basis', '')}".strip()
    if t.type == "dispute_window":
        return f"{p.get('days')} days to dispute"
    if t.type == "notice_period":
        return f"{p.get('days')} days' notice"
    return t.type.replace("_", " ")


TITLE = {"deal": "Signed deal", "amendment": "Signed amendment", "email": "Email", "notice": "Notice",
         "draft": "Next deal (draft)"}


def library(account: accounts.Account) -> ContractLibrary:
    from api import pipeline

    run = pipeline.latest(account=account)
    terms = [t for t in (run.terms if run else []) if t.reader == "merged" or t.status in ("rejected", "disputed")]
    out = []
    with accounts.using(account):
        for doc_id in account.docs:
            try:
                doc, text = documents.load(doc_id)
            except Exception:  # noqa: BLE001 - a file that can't be read isn't shown
                continue
            mine = [LibraryTerm(type=t.type, quote=t.exact_quote, char_start=t.char_start, char_end=t.char_end,
                                status=t.status, discretion=t.discretion, label=_label(t))
                    for t in terms if t.source_doc_id == doc_id and 0 <= t.char_start < t.char_end <= len(text)]
            out.append(LibraryDocument(
                id=doc.id, title=f"{TITLE.get(doc.kind, 'Document')} · {doc.id.replace('-', ' ')}", kind=doc.kind,
                locked=doc.kind in ("deal", "amendment") or doc.signed_by_both, sender=doc.sender,
                approved_sender=doc.approved_sender, text=text,
                terms=sorted({(m.char_start, m.char_end, m.type): m for m in mine}.values(), key=lambda m: m.char_start)))
    order = {"deal": 0, "amendment": 1, "email": 2, "notice": 3, "draft": 4}
    out.sort(key=lambda d: (order.get(d.kind, 5), d.id))
    return ContractLibrary(read_in_run=run.id if run and terms else None, documents=out)
