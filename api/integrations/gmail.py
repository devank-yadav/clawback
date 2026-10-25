"""The supplier's own Gmail (dispute email): Clawback sends the email the admin approved, and reads the replies.

Sending is SMTP to smtp.gmail.com:465 over SSL; reading is IMAP to imap.gmail.com:993 over SSL (Google's "IMAP, POP,
and SMTP" page and its "send email from a printer, scanner or app" page). Both sign in with the full address and an
app password (GMAIL_ADDRESS, GMAIL_APP_PASSWORD; no OAuth). Standard library only: smtplib and imaplib.

- send(): the RFC 822 email, from GMAIL_ADDRESS to the distributor's desk. It carries our own Message-ID, which is
  saved so a reply threads back. Gmail files the sent copy in Sent itself.
- new_inbox_messages(): messages that arrived in INBOX since the last look (by UID; the first look only notes where
  INBOX stands, so old mail is never replayed).

Every connection has a 30 s timeout. Sending is retried once only when the connection couldn't be made, so an email
is never sent twice; IMAP connections are retried once. With no keys, or in DEMO_MODE, nothing connects: callers keep
the in-app outbox instead (why_simulated()).
"""

from __future__ import annotations

import imaplib
import os
import smtplib
import ssl
from collections.abc import Callable
from contextlib import contextmanager

from api.integrations import replay

HOST = "imap.gmail.com"
PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL (587 is STARTTLS)
TIMEOUT_S = 30


class GmailError(Exception):
    pass


def address() -> str | None:
    return (os.getenv("GMAIL_ADDRESS") or "").strip() or None


def configured() -> bool:
    return bool(address() and os.getenv("GMAIL_APP_PASSWORD"))


def why_simulated() -> str | None:
    if replay.demo_mode():
        return "DEMO_MODE"
    if not configured():
        return "no GMAIL_ADDRESS / GMAIL_APP_PASSWORD"
    return None


def _real() -> imaplib.IMAP4:
    return imaplib.IMAP4_SSL(HOST, PORT, timeout=TIMEOUT_S)


def _real_smtp() -> smtplib.SMTP:
    return smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_S, context=ssl.create_default_context())


connect_fn: Callable[[], imaplib.IMAP4] = _real  # the tests put a fake IMAP server here
smtp_fn: Callable[[], smtplib.SMTP] = _real_smtp  # and a fake SMTP server here


def send(raw: bytes, to: str) -> None:
    """Send it from GMAIL_ADDRESS. Raises GmailError when Gmail refuses it or can't be reached twice."""
    last = None
    for _ in range(2):
        try:
            conn = smtp_fn()
            break
        except OSError as e:  # never connected: safe to try again
            last = e
    else:
        raise GmailError(f"can't reach Gmail's SMTP server ({type(last).__name__})")
    try:
        try:
            conn.login(address(), os.environ["GMAIL_APP_PASSWORD"])
        except smtplib.SMTPAuthenticationError:
            raise GmailError("Gmail refused the sign-in (check GMAIL_ADDRESS and the app password)") from None
        try:
            refused = conn.sendmail(address(), [to], raw)
        except smtplib.SMTPException as e:  # may or may not have gone: not retried
            raise GmailError(f"Gmail didn't take it ({type(e).__name__}: {str(e)[:200]})") from None
        if refused:
            raise GmailError(f"Gmail refused the recipient {to}")
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001 - closing a connection that already broke
            pass


@contextmanager
def session():
    """A signed-in IMAP connection; one retry when it can't connect."""
    last = None
    for _ in range(2):
        try:
            conn = connect_fn()
            break
        except (OSError, imaplib.IMAP4.abort) as e:
            last = e
    else:
        raise GmailError(f"can't reach Gmail ({type(last).__name__})")
    try:
        try:
            conn.login(address(), os.environ["GMAIL_APP_PASSWORD"])
        except imaplib.IMAP4.error:
            raise GmailError("Gmail refused the sign-in (check GMAIL_ADDRESS and the app password)") from None
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 - closing a connection that already broke
            pass


def new_inbox_messages(after_uid: int | None) -> tuple[list[tuple[int, bytes]], int]:
    """(new messages as (uid, RFC 822 bytes), the highest UID seen). after_uid None: the first look, nothing read."""
    with session() as conn:
        typ, data = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise GmailError("can't open INBOX")
        typ, data = conn.uid("SEARCH", None, "ALL")
        uids = [int(x) for x in (data[0] or b"").split()] if typ == "OK" and data else []
        top = max(uids, default=after_uid or 0)
        if after_uid is None:
            return [], top
        out = []
        for uid in (u for u in uids if u > after_uid):
            typ, parts = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in parts or [] if isinstance(p, tuple) and len(p) > 1), None)
            if typ == "OK" and raw:
                out.append((uid, raw))
        return out, top
