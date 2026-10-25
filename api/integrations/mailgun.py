"""Outbound email through Mailgun's send API (Phase E: the dispute email and its follow-ups).

POST https://api.mailgun.net/v3/<MAILGUN_DOMAIN>/messages (MAILGUN_API_BASE for the EU region,
https://api.eu.mailgun.net), HTTP Basic auth with user "api" and MAILGUN_API_KEY, multipart form fields from, to,
subject, text, attachment (repeatable) and h:<Header> for custom headers (Reply-To, In-Reply-To, References), per
Mailgun's "Send an email" API reference. The response's `id` is the Message-Id, saved so replies thread back.

With no keys, or in DEMO_MODE, nothing leaves the server: the email goes to the in-app outbox (OUTBOX, GET /outbox)
with a made-up "<sim-…@clawback.local>" id, and the result says so. 30 s timeout; one retry, only when the request
never reached Mailgun or Mailgun answered 429 / 5xx, so a sent email isn't sent twice.
"""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from api.integrations import replay

API_BASE = "https://api.mailgun.net"
TIMEOUT_S = 30


@dataclass(frozen=True)
class Outgoing:
    to: str
    from_addr: str
    subject: str
    text: str
    reply_to: str | None = None
    in_reply_to: str | None = None
    references: tuple[str, ...] = ()
    attachments: tuple[tuple[str, bytes, str], ...] = ()  # (filename, bytes, content type)
    tags: dict[str, str] = field(default_factory=dict)  # extra X- headers, e.g. X-Clawback-Dispute


@dataclass(frozen=True)
class Sent:
    message_id: str
    simulated: bool
    detail: str
    at: datetime


OUTBOX: list[tuple[Outgoing, Sent]] = []
_lock = threading.Lock()


class SendFailed(Exception):
    pass


def domain() -> str | None:
    return (os.getenv("MAILGUN_DOMAIN") or "").strip() or None


def configured() -> bool:
    return bool(os.getenv("MAILGUN_API_KEY") and domain())


def why_simulated() -> str | None:
    if replay.demo_mode():
        return "DEMO_MODE"
    if not configured():
        return "no MAILGUN_API_KEY / MAILGUN_DOMAIN"
    return None


def _record(msg: Outgoing, sent: Sent) -> Sent:
    with _lock:
        OUTBOX.append((msg, sent))
    return sent


def form(msg: Outgoing) -> list[tuple[str, str]]:
    data = [("from", msg.from_addr), ("to", msg.to), ("subject", msg.subject), ("text", msg.text)]
    if msg.reply_to:
        data.append(("h:Reply-To", msg.reply_to))
    if msg.in_reply_to:
        data.append(("h:In-Reply-To", msg.in_reply_to))
    if msg.references:
        data.append(("h:References", " ".join(msg.references)))
    data += [(f"h:{k}", v) for k, v in msg.tags.items()]
    return data


def send(msg: Outgoing, client: httpx.Client | None = None) -> Sent:
    """Send it (or put it in the outbox). Raises SendFailed when Mailgun refuses or can't be reached twice."""
    now = datetime.now(timezone.utc)
    why = why_simulated()
    if why:
        return _record(msg, Sent(f"<sim-{secrets.token_hex(8)}@clawback.local>", True, f"in the outbox ({why})", now))
    base = (os.getenv("MAILGUN_API_BASE") or API_BASE).rstrip("/")
    url = f"{base}/v3/{domain()}/messages"
    files = [("attachment", (name, data, ctype)) for name, data, ctype in msg.attachments]
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S)
    last = ""
    try:
        for _ in range(2):
            try:
                fields: dict[str, str | list[str]] = {}
                for k, v in form(msg):
                    fields[k] = [*fields[k], v] if isinstance(fields.get(k), list) else [fields[k], v] if k in fields else v
                r = client.post(url, auth=("api", os.environ["MAILGUN_API_KEY"]), data=fields, files=files or None)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:  # never reached Mailgun: safe to try again
                last = f"{type(e).__name__}"
                continue
            except httpx.HTTPError as e:  # may have been sent: don't send it twice
                raise SendFailed(f"{type(e).__name__} talking to Mailgun") from None
            if r.status_code == 429 or r.status_code >= 500:
                last = f"Mailgun answered {r.status_code}"
                continue
            if r.status_code >= 400:
                raise SendFailed(f"Mailgun refused it ({r.status_code}: {r.text[:200]})")
            mid = (r.json() or {}).get("id") or ""
            mid = mid if mid.startswith("<") else f"<{mid}>"
            return _record(msg, Sent(mid, False, (r.json() or {}).get("message", "queued"), now))
        raise SendFailed(f"couldn't send after two tries ({last})")
    finally:
        if own:
            client.close()


def reset() -> None:
    with _lock:
        OUTBOX.clear()
