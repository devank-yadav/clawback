"""Texts to the owner and the controller through Twilio (the same calls as scripts/send_sms.py).

Not sent in DEMO_MODE or without the Twilio keys: the question or approval still waits in /inbox and the board,
so nothing depends on the text arriving. A failed send is logged by the caller, never raised.
"""

from __future__ import annotations

import os

from api.integrations import replay

PHONES = {"owner": "OWNER_PHONE", "controller": "CONTROLLER_PHONE"}
KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")
TIMEOUT_S = 30

outbox: list[tuple[str, str]] = []  # (role, text) of every text the app meant to send, sent or not


def configured(role: str) -> bool:
    return all(os.getenv(k) for k in (*KEYS, PHONES[role]))


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
        client.messages.create(to=os.environ[PHONES[role]], from_=os.environ["TWILIO_FROM"], body=text)
    except (TwilioRestException, OSError) as e:
        return f"failed ({type(e).__name__})"
    return "sent"
