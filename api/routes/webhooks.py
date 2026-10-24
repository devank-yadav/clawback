"""Twilio inbound SMS (F8, F10): the admin's answer and yes / no, the same way as answering in the app.

Also the WhatsApp Sandbox's "When a message comes in" URL (SMS_CHANNEL=whatsapp): the fields are the same and From
is "whatsapp:+1555…", which matches on its digits like any other format.

From is matched to OWNER_PHONE (the admin, the one person who decides); anyone else gets an empty reply and changes
nothing. An open question takes the reply first; with none, a YES or NO (or anything while a memo waits) goes to the
credit memo approval; anything else (UNDO, a late reply) goes to the newest question. The reply text goes through the same parser as the app
(api/replies.py via api/pipeline.answer). What Clawback texts
back (the rule echo, UNDO, the re-ask) is returned as TwiML, so Twilio sends it without an outbound API call.

When TWILIO_AUTH_TOKEN is set, X-Twilio-Signature must match (HMAC-SHA1 over the public URL plus the sorted form
fields, per Twilio's webhook security docs); without the token (local dev, tests) it is not checked.
"""

import base64
import hashlib
import hmac
import os
import re
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response

from api import pipeline, replies

router = APIRouter(tags=["webhooks"])

PATH = "/webhooks/twilio/sms"
NO_QUESTION_TEXT = "There's nothing waiting on you right now."


def _twiml(*messages: str) -> Response:
    body = "".join(f"<Message>{escape(m)}</Message>" for m in messages)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone)
    return d[1:] if len(d) == 11 and d.startswith("1") else d  # +1 555… and 555… are the same US number


def _role(sender: str) -> str | None:
    if not _digits(sender):
        return None
    return "owner" if _digits(os.getenv("OWNER_PHONE", "")) == _digits(sender) else None


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


def _open_question() -> str | None:
    """The newest unanswered owner question; else the newest one at all (so UNDO and late replies still land)."""
    qs = [(qid, pipeline.RUNS[rid].questions[qid]) for qid, (rid, _) in pipeline.QUESTIONS.items()
          if rid in pipeline.RUNS and pipeline.RUNS[rid].questions[qid].to_role == "owner"]
    open_ = [qid for qid, q in qs if pipeline.is_open(q)]
    return (open_ or [qid for qid, _ in qs] or [None])[-1]


def _has_open_question() -> bool:
    qid = _open_question()
    return qid is not None and pipeline.is_open(pipeline.RUNS[pipeline.QUESTIONS[qid][0]].questions[qid])


def _owner(text: str) -> list[str]:
    qid = _open_question()
    if qid is None:
        return [NO_QUESTION_TEXT]
    run = pipeline.RUNS[pipeline.QUESTIONS[qid][0]]
    before = len(run.texts)
    try:
        pipeline.answer(qid, text, "owner")
    except pipeline.QuestionClosed:  # the newest question belongs to a replaced run, and the new one hasn't asked
        return [NO_QUESTION_TEXT]
    return [t for role, t in run.texts[before:] if role == "owner"]


def _waiting_approval(reply: replies.ApprovalReply) -> str | None:
    approval_id = pipeline.pending_approval()
    if approval_id is None and reply.kind == "approve":
        approval_id = pipeline.failed_approval()  # YES again after QuickBooks failed: retry the write
    return approval_id


def _approval(text: str) -> list[str]:
    reply = replies.parse_approval_reply(text)
    approval_id = _waiting_approval(reply)
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


@router.post(PATH)
async def twilio_sms(request: Request) -> Response:
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
    _check_signature(request, form)
    role = _role(form.get("From", ""))
    if role is None:
        return _twiml()  # not the admin: say nothing, change nothing
    text = form.get("Body", "")
    if _has_open_question():
        return _twiml(*_owner(text))
    reply = replies.parse_approval_reply(text)
    undo = reply.kind == "unclear" and replies.parse_owner_reply(text).kind == "undo"  # UNDO is about the rule
    to_approval = not undo and (reply.kind != "unclear" or pipeline.pending_approval() is not None)
    return _twiml(*(_approval(text) if to_approval else _owner(text)))
