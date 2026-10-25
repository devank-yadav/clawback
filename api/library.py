"""Connections (where payments, records and contracts come from, as they really are on this server) and the contract
library (each distributor's signed deal, locked, with the terms the agents read highlighted where they sit)."""

from __future__ import annotations

from datetime import datetime, timezone

from api import accounts, documents, drive, inbound_email, sources
from api.contracts import Connection, ContractLibrary, LibraryDocument, LibraryTerm
from api.integrations import nessie, qbo_source, replay, sms


def _seen(source: str, account: accounts.Account | None) -> dict:
    """What a source has seen (api/sources.py), for the account in view."""
    s, item = sources.state(source), sources.last(source, account.id if account else None)
    return {"checked_at": s.checked_at, "problem": s.error, "last_seen": item.text if item else None,
            "last_seen_at": item.at if item else None, "run_id": item.run_id if item else None}


def _quickbooks(account: accounts.Account | None, demo: bool) -> Connection:
    invoice = account.config.qbo.invoice_no if account else "the distributor's invoice"
    live = qbo_source.configured() and not demo
    watching = bool(qbo_source.poller and qbo_source.poller.running)
    if not live:
        detail = ("Not connected on this server: payments recorded there aren't watched, and postings are simulated "
                  "and say so" if not demo else "DEMO_MODE: nothing reaches QuickBooks; postings are simulated and say so")
    elif watching:
        detail = (f"A payment recorded against {invoice} starts the agents (checked every {qbo_source.POLL_S:.0f} "
                  "seconds); credit memos post only after your approval")
    else:
        detail = "Sandbox company; credit memos post only after your approval. Payments aren't watched (QBO_POLL=off)"
    return Connection(id="quickbooks", name="QuickBooks", brings="Invoices, payments received, credit memos",
                      status="connected" if live else "not_connected", detail=detail,
                      **(_seen("quickbooks", account) if live else {}))


def _bank(account: accounts.Account | None, demo: bool) -> Connection:
    live = nessie.configured() and not demo
    watching = bool(nessie.poller and nessie.poller.running)
    if not live:
        detail = "Not connected: use “Send a test payment” on Agents" if not demo else \
            "DEMO_MODE: “Send a test payment” starts the run directly"
    elif watching:
        named = f" (“{account.config.nessie_description}”)" if account else ""
        detail = f"Checked every {nessie.POLL_S:.0f} seconds; a deposit that names this invoice{named} starts the agents"
    else:
        detail = "Connected, not watching (NESSIE_POLL=off): “Send a test payment” posts the deposit and starts the run"
    return Connection(id="bank", name="Bank (Capital One)", brings="Deposits: a short payment starts the agents",
                      status="connected" if live else "not_connected", detail=detail,
                      **(_seen("bank", account) if live else {}))


def _inbox(account: accounts.Account | None) -> Connection:
    to = inbound_email.address(account) if account else None
    live = inbound_email.configured() and bool(to or not account)
    if live:
        detail = ("Forward remittance advice here (a PDF, text or EDI 820 attachment): it's read and checked like an "
                  "upload, and starts the agents if it adds up. A broker's email from an approved sender can change "
                  "the deal; anyone else's is a claim")
    else:
        detail = "Not set up on this server: upload the remittance instead"
    return Connection(id="inbox", name="Remittance inbox", brings="Remittances and broker emails, read automatically",
                      status="connected" if live else "not_connected", detail=detail, address=to if live else None,
                      **(_seen("inbox", account) if live else {}))


def _drive() -> Connection:
    """Google Drive (api/drive.py): watching the shared folder, or how to connect it."""
    if not drive.configured():
        return Connection(id="drive", name="Google Drive", brings="Contracts, promotions, remittances, correspondence",
                          status="not_connected",
                          detail="Not connected: share your Clawback folder with the service account "
                                 "(GOOGLE_SERVICE_ACCOUNT_JSON, DRIVE_ROOT_FOLDER_ID). Upload works meanwhile")
    s = drive.STATUS
    if s.changed_at:
        mins = int((datetime.now(timezone.utc) - s.changed_at).total_seconds() // 60)
        ago = "just now" if mins < 1 else f"{mins} min ago"
        detail = f"Watching the shared folder · last change {ago} · {s.files} files"
    elif s.checked_at:
        detail = f"Watching the shared folder · no changes yet · {s.files} files"
    else:
        detail = "Connected; the first look is on its way"
    return Connection(id="drive", name="Google Drive", brings="Contracts, promotions, remittances, correspondence",
                      status="connected", detail=detail, checked_at=s.checked_at, problem=s.problem, last_seen=s.last,
                      last_seen_at=s.changed_at)


def _edi(account: accounts.Account | None) -> Connection:
    """The 820 needs no keys: it comes in through the upload or the inbox, and plain code reads it (api/edi820.py)."""
    inbox = " or email it to the remittance inbox" if inbound_email.configured() and (
        account is None or inbound_email.address(account)) else ""
    return Connection(id="edi", name="EDI 820", brings="Remittance advice lines straight from the distributor",
                      status="ready",
                      detail=f"Upload the 820 file{inbox}: plain code reads its RMR and ADX segments (no AI), then "
                             "every line is checked like any remittance and the run starts if they add up. A direct "
                             "VAN or AS2 feed isn't connected")


def connections(account: accounts.Account | None = None) -> list[Connection]:
    """Every place information comes from, as it is on this server; the three that start runs say what they've seen
    for the account in view."""
    demo = replay.demo_mode()
    return [
        _quickbooks(account, demo),
        _bank(account, demo),
        Connection(id="upload", name="Upload", brings="Remittance advice, contracts and records as files",
                   status="ready", detail="PDF, CSV, text or an EDI 820; the Payment reader checks every line adds up"),
        Connection(id="texts", name="Texts to you", brings="Your one question and approvals by WhatsApp or SMS",
                   status="connected" if sms.configured("owner") else "not_connected",
                   detail="A reply answers it" if sms.configured("owner") else "Not connected: decisions wait in the app"),
        _inbox(account),
        _edi(account),
        Connection(id="portals", name="Distributor portals", brings="Walmart Retail Link, KeHE CONNECT, UNFI",
                   status="coming_soon", detail="Deduction exports pulled on a schedule"),
        _drive(),
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
            v = drive.current_version(account.id, doc_id)
            source = "drive" if doc_id in account.drive or v else "inbox" if doc_id in account.inbound else "data"
            out.append(LibraryDocument(
                version=v.version if v else None, updated_at=v.seen_at if v else None, source=source,
                id=doc.id, title=f"{TITLE.get(doc.kind, 'Document')} · {doc.id.replace('-', ' ')}", kind=doc.kind,
                locked=doc.kind in ("deal", "amendment") or doc.signed_by_both, sender=doc.sender,
                approved_sender=doc.approved_sender, text=text,
                terms=sorted({(m.char_start, m.char_end, m.type): m for m in mine}.values(), key=lambda m: m.char_start)))
    order = {"deal": 0, "amendment": 1, "email": 2, "notice": 3, "draft": 4}
    out.sort(key=lambda d: (order.get(d.kind, 5), d.id))
    return ContractLibrary(read_in_run=run.id if run and terms else None, documents=out)
