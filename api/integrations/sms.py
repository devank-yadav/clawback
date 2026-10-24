"""Texts to the admin (the brand's owner) through Twilio (the same calls as scripts/send_sms.py): the questions and the
credit memo approvals both go to OWNER_PHONE.

Not sent in DEMO_MODE or without the Twilio keys: the question or approval still waits in /inbox and the board,
so nothing depends on the text arriving. A failed send is logged by the caller, never raised.

SMS_CHANNEL=whatsapp sends the same texts over Twilio's WhatsApp Sandbox instead, because US SMS needs A2P 10DLC or
toll-free verification first. Twilio only adds a "whatsapp:" prefix to both numbers; TWILIO_FROM is then the
Sandbox number, and each phone must have sent the join code (and a message within 24 hours) to receive anything.
Replies arrive at the same webhook with the same fields, From prefixed the same way.
"""

from __future__ import annotations

import os

from api.integrations import replay

PHONES = {"owner": "OWNER_PHONE"}
KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")
TIMEOUT_S = 30
CHANNELS = ("sms", "whatsapp")

outbox: list[tuple[str, str]] = []  # (role, text) of every text the app meant to send, sent or not


def configured(role: str) -> bool:
    return all(os.getenv(k) for k in (*KEYS, PHONES[role]))


def channel() -> str:
    """SMS_CHANNEL, "sms" by default; anything unknown counts as "sms"."""
    value = os.getenv("SMS_CHANNEL", "sms").strip().lower()
    return value if value in CHANNELS else "sms"


def address(phone: str) -> str:
    """The number as Twilio wants it on this channel: "+1555…" for SMS, "whatsapp:+1555…" for WhatsApp."""
    bare = phone.strip().removeprefix("whatsapp:")
    return f"whatsapp:{bare}" if channel() == "whatsapp" else bare


def send(role: str, text: str) -> str:
    """Returns how it went, for the log: "sent", "not sent (...)" or "failed (...)"."""
    outbox.append((role, text))
    if replay.demo_mode():
        return "not sent (DEMO_MODE)"
    if not configured(role):
        return "not sent (no Twilio keys)"
    from twilio.base.exceptions import TwilioRestException
    from twilio.http.http_client import TwilioHttpClient
    from twilio.rest import Client

    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"],
                    http_client=TwilioHttpClient(timeout=TIMEOUT_S, max_retries=1))
    try:
        client.messages.create(to=address(os.environ[PHONES[role]]), from_=address(os.environ["TWILIO_FROM"]), body=text)
    except (TwilioRestException, OSError) as e:
        return f"failed ({type(e).__name__})"
    return "sent"
