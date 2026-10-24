"""Twilio inbound SMS. Stub: accepts the form post and replies with empty TwiML.

Before going live: validate X-Twilio-Signature and match From to OWNER_PHONE / CONTROLLER_PHONE.
"""

from urllib.parse import parse_qs

from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/twilio/sms")
async def twilio_sms(request: Request) -> Response:
    form = parse_qs((await request.body()).decode())
    _body, _sender = form.get("Body", [""])[0], form.get("From", [""])[0]
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")
