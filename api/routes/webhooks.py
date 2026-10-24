"""Twilio inbound SMS (F8, F10): the owner's answer and the controller's yes / no, the same way as answering in the app.

From is matched to OWNER_PHONE or CONTROLLER_PHONE; anyone else gets an empty reply and changes nothing. The
reply text goes through the same parser as the app (api/replies.py via api/pipeline.answer). What Clawback texts
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
    for role, env in (("owner", "OWNER_PHONE"), ("controller", "CONTROLLER_PHONE")):
        if _digits(os.getenv(env, "")) == _digits(sender):
            return role
    return None


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
    open_ = [qid for qid, q in qs if q.answer is None]
    return (open_ or [qid for qid, _ in qs] or [None])[-1]


def _owner(text: str) -> list[str]:
    qid = _open_question()
    if qid is None:
        return [NO_QUESTION_TEXT]
    run = pipeline.RUNS[pipeline.QUESTIONS[qid][0]]
    before = len(run.texts)
    pipeline.answer(qid, text, "owner")
    return [t for role, t in run.texts[before:] if role == "owner"]


def _controller(text: str) -> list[str]:
    approval_id = pipeline.pending_approval("controller")
    if approval_id is None:
        return [NO_QUESTION_TEXT]
    reply = replies.parse_controller_reply(text)
    if reply.kind == "unclear":
        return [replies.CONTROLLER_REASK_TEXT]
    try:
        approval, _ = pipeline.decide_approval(approval_id, reply.kind == "approve", reply.note or None)
    except ValueError:  # decided in the app a moment ago
        return [NO_QUESTION_TEXT]
    if approval.status == "approved":
        return [f"Approved: ${approval.amount:,.0f} credit memo ({len(approval.lines)} lines)."]
    return [f"Held: the ${approval.amount:,.0f} credit memo won't post. Your note is on the card."]


@router.post(PATH)
async def twilio_sms(request: Request) -> Response:
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
    _check_signature(request, form)
    role = _role(form.get("From", ""))
    if role is None:
        return _twiml()  # not the owner or the controller: say nothing, change nothing
    text = form.get("Body", "")
    return _twiml(*(_owner(text) if role == "owner" else _controller(text)))
