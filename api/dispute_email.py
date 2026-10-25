"""Dispute email (Phase E): the admin reviews and sends each dispute by email, and the distributor's replies come
back by email and are answered.

1. Drafting. A run files each dispute as `ready_to_send` (api/pipeline._file_dispute). Its email is drafted when
   first asked for (GET /disputes/{id}/email): the email writer (api/agents/email_writer.py, Claude) writes it from
   the dispute's lines; code adds the subject ("Dispute: [Brand], Remittance [#], Deductions [refs], [Amount]"), the
   greeting and signature, and the outbound filter checks every figure and quote. A draft that fails twice is held;
   the admin edits it (PUT), which is checked again.
2. Sending. POST /disputes/{id}/send is the admin's approval: the email goes out through Mailgun
   (api/integrations/mailgun.py) from disputes@<MAILGUN_DOMAIN> with Reply-To d-<n>+<token>@<INBOUND_EMAIL_DOMAIN>,
   to the distributor's desk_email, with the dispute packet PDF attached; its Message-Id is saved; then the dispute
   is filed. No keys, or DEMO_MODE: the email goes to the in-app outbox instead. policy.yaml `auto_send: true` sends
   a dispute within the auto-dispute limit on its own (default off).
3. Replies. The remittance inbox (api/inbound_email.py) hands any email to d-<n>+<token>@, or one whose
   In-Reply-To / References names a Message-Id we sent, to on_reply(): it becomes a dispute message (not an account
   document) and goes through api/disputes._post: an attachment that is one of the account's documents is re-read,
   recomputed and conceded if valid; text gets the Negotiator's answer, drafted as a reply email for the admin to
   send (POST /disputes/{id}/replies/{email_id}/send); anything unclear is held for the owner. Each reply notifies
   the supplier in the app (GET /notifications) and by text to the admin (api/integrations/sms.py).
4. Saved. Emails, reply tokens, dispute messages and notifications are written to Postgres (migration 007) when
   there is a database; disputes themselves are already in the events table. Memory otherwise.

Emails and replies are data, never instructions.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

from api import accounts, disputes, lookback, packet, pipeline
from api.agents import email_writer
from api.contracts import Dispute, DisputeEmail, PortalMessage, SupplierNotification
from api.engine import outbound_filter
from api.integrations import mailgun, sms

log = logging.getLogger("clawback.dispute_email")

POLICY = Path(__file__).resolve().parents[1] / "config" / "policy.yaml"
ADDRESS = re.compile(r"\bd-(\d+)\+([a-z0-9]+)@", re.IGNORECASE)

EMAILS: dict[str, DisputeEmail] = {}
TOKENS: dict[str, tuple[str, str]] = {}  # reply token -> (run id, dispute id)
MESSAGE_IDS: dict[str, tuple[str, str]] = {}  # Message-Id we sent -> (run id, dispute id)
NOTIFICATIONS: list[SupplierNotification] = []
_lock = threading.RLock()


class NotReady(ValueError):
    """The email can't go: it's held (failed its checks) or was already sent."""


def auto_send() -> bool:
    """policy.yaml `auto_send`: a dispute within the auto-dispute limit is emailed without the admin's review."""
    try:
        return bool((yaml.safe_load(POLICY.read_text()) or {}).get("auto_send", False))
    except OSError:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- addresses

def token(run: pipeline.Run, dispute_id: str) -> str:
    with _lock:
        for t, where in TOKENS.items():
            if where == (run.id, dispute_id):
                return t
        t = secrets.token_hex(6)
        TOKENS[t] = (run.id, dispute_id)
    _save("INSERT INTO dispute_tokens (token, run_id, dispute_id, account_id) VALUES (%s, %s, %s, %s) "
          "ON CONFLICT (token) DO NOTHING", (t, run.id, dispute_id, run.account.id))
    return t


def reply_to(run: pipeline.Run, dispute_id: str) -> str | None:
    domain = (os.getenv("INBOUND_EMAIL_DOMAIN") or "").strip().lower()
    return f"{dispute_id.lower()}+{token(run, dispute_id)}@{domain}" if domain else None


def from_addr(account: accounts.Account) -> str:
    return f"{account.brand.name} <disputes@{mailgun.domain() or 'clawback.local'}>"


def portal_url(run: pipeline.Run, dispute_id: str) -> str | None:
    base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    return f"{base}/portal?dispute={dispute_id}&t={token(run, dispute_id)}" if base else None


# ---------------------------------------------------------------- finding a dispute

def latest(run: pipeline.Run, dispute_id: str) -> Dispute | None:
    found = [e.data for e in run.events if e.type == "dispute" and e.data.id == dispute_id]
    return found[-1] if found else None


def find(dispute_id: str, run_id: str | None = None, only=None) -> tuple[pipeline.Run, Dispute] | None:
    """The run (this one, else the newest whose account passes `only`) that filed the dispute, and the dispute now."""
    runs = [pipeline.RUNS[run_id]] if run_id and run_id in pipeline.RUNS else [] if run_id else \
        list(reversed(list(pipeline.RUNS.values())))
    for run in runs:
        if only is not None and not only(run.account):
            continue
        if (d := latest(run, dispute_id)) is not None:
            return run, d
    return None


# ---------------------------------------------------------------- 1. drafting

def _email_id(run: pipeline.Run, dispute_id: str) -> str:
    return f"EM-{run.id}-{dispute_id}"


def _check(e: DisputeEmail, run: pipeline.Run, dispute: Dispute) -> list[str]:
    if e.kind == "dispute":
        return email_writer.check_body(e.body, dispute, run.terms, run.account)
    result = outbound_filter.check_message(e.body, disputes.outbound_context(run, dispute))
    return [] if result.ok else ["outbound filter: " + result.feedback()]


def email_for(run: pipeline.Run, dispute: Dispute, client=None, redraft: bool = False) -> DisputeEmail:
    """The dispute's email, drafted the first time it's asked for (or again with redraft, unless it was sent)."""
    eid = _email_id(run, dispute.id)
    with _lock:
        have = EMAILS.get(eid)
    if have and (not redraft or have.status in ("sent", "outbox")):
        return have
    url = portal_url(run, dispute.id)
    with accounts.using(run.account):
        d = email_writer.draft(dispute, run.terms, run.account, client, portal_url=url)
    e = DisputeEmail(id=eid, kind="dispute", run_id=run.id, account_id=run.account.id, dispute_id=dispute.id,
                     to=run.account.distributor.desk_email, from_addr=from_addr(run.account),
                     reply_to=reply_to(run, dispute.id), subject=d.subject, body=d.body,
                     attachments=[f"{dispute.id}-packet.pdf"], status="held" if d.held else "ready",
                     written_by=d.written_by, problems=d.problems, portal_url=url,
                     charge_ids=[ln.charge_id for ln in dispute.lines])
    run.log(f"Drafted the {dispute.id} email to {run.distributor} ({'held: ' + d.problems[0][:120] if d.held else 'ready for ' + run.name('owner') + ' to review'}).",
            "warn" if d.held else "info", "negotiator")
    return _put(e)


def forget_draft(run: pipeline.Run, dispute_id: str) -> None:
    """The dispute changed before it was sent: the next look drafts its email again from the new lines."""
    with _lock:
        e = EMAILS.get(_email_id(run, dispute_id))
        if e and e.status not in ("sent", "outbox"):
            del EMAILS[e.id]


def edit(e: DisputeEmail, subject: str | None, body: str) -> DisputeEmail:
    """The admin's edit. Ready if it passes the outbound filter, held with the problems if not."""
    if e.status in ("sent", "outbox"):
        raise NotReady(f"{e.id} was already sent")
    found = find(e.dispute_id, e.run_id)
    if not found:
        raise NotReady(f"the run that filed {e.dispute_id} isn't here any more")
    run, dispute = found
    changed = e.model_copy(update={"subject": (subject or e.subject).strip()[:300], "body": body, "written_by": "admin"})
    problems = _check(changed, run, dispute)
    return _put(changed.model_copy(update={"problems": problems, "status": "held" if problems else "ready"}))


# ---------------------------------------------------------------- 2. sending

def _packet(run: pipeline.Run, dispute: Dispute) -> bytes:
    math = {cid: [p.text for p in f.math] for cid, f in run.findings.items() if f.math}
    return packet.packet_pdf(dispute, run.account, run.evidence, math, file_by=lookback.deadline(run.account)[0])


def _deliver(e: DisputeEmail, run: pipeline.Run, dispute: Dispute) -> DisputeEmail:
    refs = tuple(x.message_id for x in emails_of(run.id, dispute.id) if x.message_id)
    out = mailgun.Outgoing(
        to=e.to, from_addr=e.from_addr, subject=e.subject, text=e.body, reply_to=e.reply_to,
        in_reply_to=e.in_reply_to, references=refs if e.kind == "reply" else (),
        attachments=((f"{dispute.id}-packet.pdf", _packet(run, dispute), "application/pdf"),) if e.kind == "dispute" else (),
        tags={"X-Clawback-Dispute": dispute.id})
    try:
        sent = mailgun.send(out)
    except mailgun.SendFailed as err:
        run.log(f"The {dispute.id} email to {run.distributor} didn't go out ({err}). Sending again retries.", "error",
                "negotiator")
        return _put(e.model_copy(update={"status": "failed", "detail": str(err)}))
    with _lock:
        MESSAGE_IDS[sent.message_id] = (run.id, dispute.id)
    return _put(e.model_copy(update={"status": "outbox" if sent.simulated else "sent", "message_id": sent.message_id,
                                     "sent_at": sent.at, "detail": sent.detail}))


def send_dispute(run: pipeline.Run, dispute: Dispute, by: str = "owner", subject: str | None = None,
                 body: str | None = None, client=None) -> tuple[Dispute, DisputeEmail]:
    """The admin's "send" (or the policy's, with auto_send): email it, then file the dispute."""
    with _lock:
        e = email_for(run, dispute, client)
        if body is not None:
            e = edit(e, subject, body)
        if e.status in ("sent", "outbox"):
            raise NotReady(f"{dispute.id} was already sent")
        if e.status == "held":
            raise NotReady(f"{dispute.id}'s email is held: {'; '.join(e.problems)[:400]}. Edit it, then send.")
        e = _deliver(e, run, dispute)
        if e.status == "failed":
            return dispute, e
        filed = dispute.model_copy(update={"status": "filed", "approved_by": by, "filed_at": _now()})
        run.emit("dispute", filed)
    where = "the in-app outbox" if e.status == "outbox" else e.to
    who = run.name("owner") if by == "owner" else "policy (auto-send)"
    run.log(f"Filed {dispute.id}: emailed {where} with the packet, approved by {who}.", "good", "negotiator")
    return filed, e


# ---------------------------------------------------------------- 3. replies

def emails_of(run_id: str, dispute_id: str) -> list[DisputeEmail]:
    with _lock:
        return [e for e in EMAILS.values() if e.run_id == run_id and e.dispute_id == dispute_id]


def _reply_deliverer(replying_to: list[PortalMessage], in_reply_to: str | None):
    """disputes._post's `deliver` for the email channel: the answer becomes a reply email for the admin to send."""

    def deliver(run: pipeline.Run, dispute: Dispute, text: str, charge_ids: list[str], evidence_ids: list[str]):
        first = next((x for x in emails_of(run.id, dispute.id) if x.kind == "dispute"), None)
        n = sum(1 for x in emails_of(run.id, dispute.id) if x.kind == "reply") + 1
        subject = first.subject if first else email_writer.subject(dispute, run.account)
        body = "\n\n".join([email_writer.greeting(run.account), text.strip(),
                            email_writer.signature(run.account, portal_url(run, dispute.id))])
        e = DisputeEmail(id=f"{_email_id(run, dispute.id)}-R{n}", kind="reply", run_id=run.id,
                         account_id=run.account.id, dispute_id=dispute.id, to=run.account.distributor.desk_email,
                         from_addr=from_addr(run.account), reply_to=reply_to(run, dispute.id),
                         subject=subject if subject.lower().startswith("re:") else f"Re: {subject}", body=body,
                         in_reply_to=in_reply_to, status="ready", written_by="negotiator", charge_ids=charge_ids,
                         evidence_ids=evidence_ids, replying_to=replying_to[0].id if replying_to else None)
        problems = _check(e, run, dispute)
        e = _put(e.model_copy(update={"problems": problems, "status": "held" if problems else "ready"}))
        if auto_send() and not problems:
            send_reply(e.id)
        else:
            run.log(f"Drafted the answer to {run.distributor}'s email on {dispute.id}: waits for {run.name('owner')} "
                    "to send it.", "info", "negotiator")
        return None

    return deliver


def send_reply(email_id: str, subject: str | None = None, body: str | None = None) -> DisputeEmail:
    with _lock:
        e = EMAILS.get(email_id)
        if e is None or e.kind != "reply":
            raise KeyError(email_id)
        if body is not None:
            e = edit(e, subject, body)
        if e.status in ("sent", "outbox"):
            raise NotReady(f"{email_id} was already sent")
        if e.status == "held":
            raise NotReady(f"{email_id} is held: {'; '.join(e.problems)[:400]}. Edit it, then send.")
        found = find(e.dispute_id, e.run_id)
        if not found:
            raise NotReady(f"the run that filed {e.dispute_id} isn't here any more")
        run, dispute = found
        e = _deliver(e, run, dispute)
        if e.status == "failed":
            return e
        ours = disputes._message(dispute.id, "clawback", e.body, charge_ids=e.charge_ids, evidence_ids=e.evidence_ids,
                                 channel="email", email_message_id=e.message_id, thread_of=run)
        run.emit("portal_message", ours)
        _save_message(run, ours)
    run.log(f"Answered {run.distributor} on {dispute.id} by email.", "good", "negotiator")
    return e


def route(msg) -> tuple[pipeline.Run, Dispute] | None:
    """An inbound email (api/inbound_email.Message) that answers one of our dispute emails: by the d-<n>+<token>
    address, else by In-Reply-To / References naming a Message-Id we sent."""
    to = " ".join([msg.recipient, *msg.header("To"), *msg.header("Cc")])
    where = None
    for m in ADDRESS.finditer(to):
        with _lock:
            where = TOKENS.get(m.group(2).lower())
        if where is None:
            where = _load_token(m.group(2).lower())
        if where and where[1].lower() == f"d-{m.group(1)}":
            break
        where = None
    if where is None:
        ids = " ".join([*msg.header("In-Reply-To"), *msg.header("References")])
        with _lock:
            where = next((MESSAGE_IDS[i] for i in re.findall(r"<[^>]+>", ids) if i in MESSAGE_IDS), None)
    if where is None:
        return None
    found = find(where[1], where[0])
    return found


def _reply_text(body: str) -> str:
    """The new part of a reply: up to the quoted original ("On … wrote:" or "> " lines)."""
    keep = []
    for line in body.splitlines():
        if line.startswith(">") or re.match(r"^\s*On .+wrote:\s*$", line) or line.strip() == "-----Original Message-----":
            break
        keep.append(line)
    return "\n".join(keep).strip() or body.strip()


def _attachment_doc(run: pipeline.Run, msg) -> str | None:
    """An attached document the account already has (by file name, e.g. amendment-1.pdf, or the same text), else the
    attachment's own name, which the dispute logic holds for the owner as a document it doesn't have."""
    if not msg.attachments:
        return None
    docs = run.account.docs
    for a in msg.attachments:
        stem = Path(a.name).stem.lower()
        if stem in docs:
            return stem
        if a.name.lower().endswith((".md", ".txt", ".eml")):
            text = " ".join(a.data.decode("utf-8", "ignore").split())
            for doc_id, path in docs.items():
                try:
                    if " ".join(path.read_text().split()) == text:
                        return doc_id
                except OSError:
                    continue
    return Path(msg.attachments[0].name).stem


def on_reply(run: pipeline.Run, dispute: Dispute, msg, client=None) -> list[PortalMessage]:
    """The distributor's emailed reply, through the same logic as the portal's."""
    text = _reply_text(msg.body)
    doc = _attachment_doc(run, msg)
    sent = [x for x in emails_of(run.id, dispute.id) if x.message_id]
    with accounts.using(run.account):
        from api import trace

        with trace.run_context(run.id):
            got = disputes._post(run, dispute, text, doc, client,
                                 deliver=_reply_deliverer([], msg.message_id or (sent[-1].message_id if sent else None)),
                                 channel="email", email_message_id=msg.message_id)
    for m in got:
        _save_message(run, m)
    theirs = got[0] if got else None
    now = latest(run, dispute.id) or dispute
    if theirs and theirs.classification == "new_document" and now.total != dispute.total:
        what = f"sent a signed document; {dispute.id} now totals ${now.total:,.0f}"
    elif theirs and theirs.classification == "agrees":
        what = f"agree on {', '.join(theirs.charge_ids) or 'a line'}"
    elif theirs and theirs.classification == "claim_without_document":
        what = "pushed back without a document; an answer is drafted for you to send"
    else:
        what = "need a person to answer"
    notify(run, dispute.id, f"{run.distributor} replied to {dispute.id} by email: they {what}.")
    return got


# ---------------------------------------------------------------- 4. telling the supplier

def notify(run: pipeline.Run, dispute_id: str | None, text: str) -> SupplierNotification:
    n = SupplierNotification(id=f"N-{secrets.token_hex(4)}", account_id=run.account.id, run_id=run.id,
                             dispute_id=dispute_id, text=text, at=_now())
    with _lock:
        NOTIFICATIONS.append(n)
    _save("INSERT INTO supplier_notifications (id, account_id, at, data) VALUES (%s, %s, %s, %s) "
          "ON CONFLICT (id) DO NOTHING", (n.id, n.account_id, n.at, _json(n)))
    status = sms.send("owner", text)
    where = "Texted" if status == "sent" else f"In the app (text {status}) for"
    run.log(f"{where} {run.name('owner')}: \"{text}\"", "info", "negotiator")
    return n


def notifications(only=None) -> list[SupplierNotification]:
    with _lock:
        found = list(NOTIFICATIONS)
    keep = []
    for n in found:
        try:
            if only is None or only(accounts.get(n.account_id)):
                keep.append(n)
        except accounts.UnknownAccount:
            continue
    return sorted(keep, key=lambda n: n.at, reverse=True)


def thread(run: pipeline.Run, dispute_id: str) -> list[PortalMessage]:
    return list(disputes.THREADS.get((run.id, dispute_id), []))


def outbox(only=None) -> list[DisputeEmail]:
    with _lock:
        found = list(EMAILS.values())
    out = []
    for e in found:
        try:
            if only is None or only(accounts.get(e.account_id)):
                out.append(e)
        except accounts.UnknownAccount:
            continue
    return out


# ---------------------------------------------------------------- saving

def _json(model):
    try:
        from psycopg.types.json import Jsonb

        return Jsonb(model.model_dump(mode="json"))
    except ImportError:
        return None


def _save(sql: str, params: tuple) -> None:
    from api.db import events

    events.write_later(sql, params)


def _put(e: DisputeEmail) -> DisputeEmail:
    with _lock:
        EMAILS[e.id] = e
    _save("INSERT INTO dispute_emails (id, run_id, account_id, dispute_id, kind, status, message_id, data, updated_at) "
          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now()) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, "
          "message_id = EXCLUDED.message_id, data = EXCLUDED.data, updated_at = now()",
          (e.id, e.run_id, e.account_id, e.dispute_id, e.kind, e.status, e.message_id, _json(e)))
    return e


def _save_message(run: pipeline.Run, m: PortalMessage) -> None:
    _save("INSERT INTO dispute_messages (run_id, id, dispute_id, account_id, created_at, data) VALUES "
          "(%s, %s, %s, %s, %s, %s) ON CONFLICT (run_id, id) DO NOTHING",
          (run.id, m.id, m.dispute_id, run.account.id, m.created_at, _json(m)))


def _load_token(t: str) -> tuple[str, str] | None:
    from api.db import conn

    if not conn.enabled():
        return None
    try:
        row = conn.shared.run(lambda db: db.execute("SELECT run_id, dispute_id FROM dispute_tokens WHERE token = %s",
                                                    (t,)).fetchone())
    except Exception as e:  # noqa: BLE001 - a reply we can't place is kept as an ordinary email
        log.warning("dispute tokens: %s", conn.scrub(e))
        return None
    return (row[0], row[1]) if row else None


def reset() -> None:
    with _lock:
        EMAILS.clear(), TOKENS.clear(), MESSAGE_IDS.clear(), NOTIFICATIONS.clear()
    mailgun.reset()
