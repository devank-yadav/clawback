"""Inbound webhooks: Twilio's texts (below) and the remittance inbox's emails (POST /webhooks/inbound-email, a Mailgun
route; api/inbound_email.py). Both live under /webhooks/, which Caddy passes to the API unchanged.

Twilio inbound SMS (F8, F10): the admin's answer and yes / no, the same way as answering in the app.

Also the WhatsApp Sandbox's "When a message comes in" URL (SMS_CHANNEL=whatsapp): the fields are the same and From
is "whatsapp:+1555…", which matches on its digits like any other format.

From is matched to a user's phone (config/users.yaml phone_env; Peak Bar's admin is OWNER_PHONE), and the reply
reaches only that user's supplier's questions and memos; anyone else gets an empty reply and changes nothing. An open question takes the reply first; with none, a YES or NO (or anything while a memo waits) goes to the
credit memo approval; anything else (UNDO, a late reply) goes to the newest question. The reply text goes through the same parser as the app
(api/replies.py via api/pipeline.answer). What Clawback texts
back (the rule echo, UNDO, the re-ask) is returned as TwiML, so Twilio sends it without an outbound API call.

When TWILIO_AUTH_TOKEN is set, X-Twilio-Signature must match (HMAC-SHA1 over the public URL plus the sorted form
fields, per Twilio's webhook security docs); without the token (local dev, tests) it is not checked.
"""

import asyncio
import base64
import hashlib
import hmac
import os
import re
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response

from api import inbound_email, pipeline, remittance, replies, sources, tenancy, users

router = APIRouter(tags=["webhooks"])

PATH = "/webhooks/twilio/sms"
NO_QUESTION_TEXT = "There's nothing waiting on you right now."


def _twiml(*messages: str) -> Response:
    body = "".join(f"<Message>{escape(m)}</Message>" for m in messages)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone)
    return d[1:] if len(d) == 11 and d.startswith("1") else d  # +1 555… and 555… are the same US number


def _sender(sender: str):
    """The user this phone belongs to (config/users.yaml phone_env; Peak Bar's admin is OWNER_PHONE), or None.
    Returns (role, `only`): the reply reaches only that user's supplier's runs."""
    if not _digits(sender):
        return None, None
    user = users.by_phone(sender)
    if user is None:
        return None, None
    return "owner", (lambda a: tenancy.supplier_of(a) == user.supplier_id)


def _role(sender: str) -> str | None:
    return _sender(sender)[0]


def signature(url: str, form: dict[str, str], token: str) -> str:
    """Twilio's X-Twilio-Signature: base64 HMAC-SHA1 of the URL followed by each field name and value, sorted."""
    payload = url + "".join(k + form[k] for k in sorted(form))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def _check_signature(request: Request, form: dict[str, str]) -> None:
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        return
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    url = f"{base}{PATH}" if base else str(request.url)  # behind Caddy, Twilio signed the public URL
    if not hmac.compare_digest(signature(url, form, token), request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "bad Twilio signature")


def _open_question(only=None) -> str | None:
    """The newest unanswered owner question; else the newest one at all (so UNDO and late replies still land)."""
    qs = [(qid, pipeline.RUNS[rid].questions[qid]) for qid, (rid, _) in pipeline.QUESTIONS.items()
          if rid in pipeline.RUNS and pipeline.RUNS[rid].questions[qid].to_role == "owner"
          and (only is None or only(pipeline.RUNS[rid].account))]
    open_ = [qid for qid, q in qs if pipeline.is_open(q)]
    return (open_ or [qid for qid, _ in qs] or [None])[-1]


def _has_open_question(only=None) -> bool:
    qid = _open_question(only)
    return qid is not None and pipeline.is_open(pipeline.RUNS[pipeline.QUESTIONS[qid][0]].questions[qid])


def _owner(text: str, only=None) -> list[str]:
    qid = _open_question(only)
    if qid is None:
        return [NO_QUESTION_TEXT]
    run = pipeline.RUNS[pipeline.QUESTIONS[qid][0]]
    before = len(run.texts)
    try:
        pipeline.answer(qid, text, "owner")
    except pipeline.QuestionClosed:  # the newest question belongs to a replaced run, and the new one hasn't asked
        return [NO_QUESTION_TEXT]
    return [t for role, t in run.texts[before:] if role == "owner"]


def _waiting_approval(reply: replies.ApprovalReply, only=None) -> str | None:
    approval_id = pipeline.pending_approval(only=only)
    if approval_id is None and reply.kind == "approve":
        approval_id = pipeline.failed_approval(only)  # YES again after QuickBooks failed: retry the write
    return approval_id


def _approval(text: str, only=None) -> list[str]:
    reply = replies.parse_approval_reply(text)
    approval_id = _waiting_approval(reply, only)
    if approval_id is None:
        return [NO_QUESTION_TEXT]
    if reply.kind == "unclear":
        return [replies.APPROVAL_REASK_TEXT]
    try:
        approval, made = pipeline.decide_approval(approval_id, reply.kind == "approve", reply.note or None)
    except ValueError:  # decided in the app a moment ago
        return [NO_QUESTION_TEXT]
    if approval.status == "approved" and any(p.status == "failed" for p in made):
        return [f"Approved, but QuickBooks didn't take the ${approval.amount:,.0f} credit memo yet. "
                "Reply YES to try again."]
    if approval.status == "approved":
        return [f"Approved: ${approval.amount:,.0f} credit memo ({len(approval.lines)} lines)."]
    return [f"Held: the ${approval.amount:,.0f} credit memo won't post. Your note is on the card."]


@router.post(inbound_email.PATH, response_model=inbound_email.InboundResult)
async def inbound_email_webhook(request: Request) -> inbound_email.InboundResult:
    """The remittance inbox (api/inbound_email.py): a Mailgun route forwards every email sent to the receiving domain
    here. Signed (403 / 406 / 503 otherwise); a remittance starts its account's run, anything else is kept."""
    try:
        form = await request.form(max_files=inbound_email.MAX_ATTACHMENTS + 5, max_fields=300,
                                  max_part_size=4 * 1024 * 1024)
    except Exception:  # noqa: BLE001 - not a form Mailgun would send
        raise HTTPException(400, "Send Mailgun's form fields (a route forwarding to this URL).") from None
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, str, bytes]] = {}
    for name, value in form.multi_items():
        if isinstance(value, str):
            fields.setdefault(name, value)
            if name.startswith("attachment-"):  # sent as a field rather than a file part
                files.setdefault(name, (name, "text/plain", value.encode()))
            continue
        data = await value.read(remittance.MAX_BYTES + 1)
        if len(data) <= remittance.MAX_BYTES:  # anything bigger isn't a remittance advice; it's left out
            files[name] = (value.filename or name, value.content_type or "", data)
    await form.close()
    msg = inbound_email.parse(fields, files)
    try:
        inbound_email.verify(fields, msg.key)
        sources.checked("inbox")
        return await asyncio.to_thread(inbound_email.handle, msg)
    except inbound_email.Refused as e:
        raise HTTPException(e.status, e.detail) from None


@router.post(PATH)
async def twilio_sms(request: Request) -> Response:
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
    _check_signature(request, form)
    role, only = _sender(form.get("From", ""))
    if role is None:
        return _twiml()  # not a user's phone: say nothing, change nothing
    text = form.get("Body", "")
    if _has_open_question(only):
        return _twiml(*_owner(text, only))
    reply = replies.parse_approval_reply(text)
    undo = reply.kind == "unclear" and replies.parse_owner_reply(text).kind == "undo"  # UNDO is about the rule
    to_approval = not undo and (reply.kind != "unclear" or pipeline.pending_approval(only=only) is not None)
    return _twiml(*(_approval(text, only) if to_approval else _owner(text, only)))
