"""The supplier's Gmail over IMAP (dispute email): Clawback only ever writes drafts; a person sends them from Gmail.

Gmail's IMAP server is imap.gmail.com:993 over SSL (Google's "IMAP, POP, and SMTP" page). Sign-in is the account's
address and an app password (GMAIL_ADDRESS, GMAIL_APP_PASSWORD; no OAuth). Standard library only: imaplib.

- append_draft(): APPEND the email to the Drafts mailbox, flagged \\Draft. The mailbox is found by its RFC 6154
  special-use flag in LIST (Gmail's is "[Gmail]/Drafts" in English, but the name can vary), never by name.
- in_sent(): is the email in the \\Sent mailbox yet (by Message-ID, else by the [D-n] tag in its subject)?
- new_inbox_messages(): messages that arrived in INBOX since the last look (by UID; the first look only notes where
  INBOX stands, so old mail is never replayed).

Every connection has a 30 s timeout and one retry when it can't connect. With no keys, or in DEMO_MODE, nothing
connects: callers keep the in-app outbox instead (why_simulated()).
"""

from __future__ import annotations

import imaplib
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager

from api.integrations import replay

HOST = "imap.gmail.com"
PORT = 993
TIMEOUT_S = 30
_LIST = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>"(?:[^"\\]|\\.)*"|\S+)')


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


connect_fn: Callable[[], imaplib.IMAP4] = _real  # the tests put a fake IMAP server here


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


def _unquote(name: bytes) -> str:
    s = name.decode("utf-8", "replace")
    return s[1:-1].replace('\\"', '"').replace("\\\\", "\\") if s.startswith('"') else s


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def mailbox(conn, flag: str) -> str:
    """The mailbox carrying this RFC 6154 special-use flag (\\Drafts, \\Sent)."""
    typ, rows = conn.list()
    if typ != "OK":
        raise GmailError("Gmail's LIST failed")
    for row in rows or []:
        raw = row if isinstance(row, bytes) else (row[0] if isinstance(row, tuple) else b"")
        m = _LIST.search(raw)
        if m and flag.lower().encode() in m.group("flags").lower().split():
            return _unquote(m.group("name"))
    raise GmailError(f"no {flag} mailbox in this Gmail account (is IMAP on?)")


def append_draft(raw: bytes) -> str:
    """Put the email in Drafts. Returns the Drafts mailbox it went to."""
    with session() as conn:
        drafts = mailbox(conn, "\\Drafts")
        typ, data = conn.append(_quote(drafts), "(\\Draft \\Seen)", imaplib.Time2Internaldate(time.time()), raw)
        if typ != "OK":
            raise GmailError(f"Gmail didn't take the draft ({data!r:.200})")
        return drafts


def _search(conn, *criteria: str) -> list[bytes]:
    typ, data = conn.search(None, *criteria)
    return (data[0] or b"").split() if typ == "OK" and data else []


def in_sent(message_id: str | None, tag: str | None) -> bool:
    """Is it in Sent: by Message-ID, else by the subject's [D-n] tag."""
    with session() as conn:
        typ, _ = conn.select(_quote(mailbox(conn, "\\Sent")), readonly=True)
        if typ != "OK":
            raise GmailError("can't open Sent")
        if message_id and _search(conn, "HEADER", "Message-ID", _quote(message_id)):
            return True
        return bool(tag and _search(conn, "SUBJECT", _quote(tag)))


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
