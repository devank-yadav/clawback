"""The remittance inbox: real inbound email through a Mailgun route (POST /webhooks/inbound-email).

Mailgun because it needs the fewest human steps of the providers that sign what they post: one receiving subdomain
(INBOUND_EMAIL_DOMAIN, e.g. in.clawback.biz, with the MX records Mailgun's dashboard shows, added at Porkbun), one route
that forwards every address on it to https://clawback.biz/webhooks/inbound-email (the free plan has one route), and
the account's HTTP webhook signing key in MAILGUN_WEBHOOK_SIGNING_KEY. The route's URL must not end in "json", "mime"
or "raw-mime": this reads Mailgun's form fields (Mailgun docs, "Receiving messages via HTTP through a forward()
action"). Each distributor gets its own address on the subdomain: <account id>@in.clawback.biz.

Each POST, in order:
1. Signature (Mailgun docs, "Securing webhooks"): `signature` must be the hex HMAC-SHA256 of `timestamp` + `token`
   keyed with MAILGUN_WEBHOOK_SIGNING_KEY. Wrong or missing: 403. No key on this server: 503, so an unsigned email
   never reaches the agents. A timestamp more than 12 hours off: 403. A token already used for a different email: 406
   (Mailgun's "rejected, don't retry"); the signature covers only timestamp + token, so this stops a replay.
2. Duplicates: one email (its Message-Id, else a hash of what it says) is handled once. Mailgun retries anything but
   200 and 406, so a repeat gets 200 and the first outcome, and never starts a second run.
3. The account: the address it was sent to (<account id>@…, or anything+<account id>@…); else the sender is exactly one
   account's distributor desk (account.yaml distributor.desk_email); else, among the accounts the sender could be
   for, the one whose invoice number, then distributor name, the email mentions. None or several: kept for a person.
4. Who sent it: the From address counts only when Mailgun's SPF check passed (X-Mailgun-Spf, every copy of it) for an
   envelope sender in the From address's domain. Anyone can type a From line.
5. A remittance (a PDF, CSV, text or EDI 820 attachment the Payment reader accepts, api/remittance.extract_text, that
   is an 820 or says remittance or payment advice or names the account's invoice; or a body that is an 820, or says
   remittance or payment advice and names the account's invoice; any other attachment, a sales report or a signed
   amendment, leaves the email a document), from a trusted sender (the distributor's desk or its domain, one of the account's
   approved_senders, or INBOUND_EMAIL_FORWARDERS, the people who forward remittances), is read and checked exactly as
   an upload (api/remittance.read: Claude lists the lines, code checks every one and that they add up), and if it can
   run, starts the run on its lines (remittance.start_with_charges, once per email; a run the bank's deposit or
   QuickBooks already started for the same payment is matched instead). The read runs off the request's thread.
   Anything that can't run is noted on the Connections page for a person; nothing is decided from the email. A read
   that fails in the background is marked failed (never left "reading"). An EDI 820 is read by plain code
   (api/edi820.py), not by Claude. Addresses (desk, approved senders, forwarders) are compared without case.
6. Anything else is kept as a document of the account under accounts.inbound_root() (INBOUND_EMAIL_DIR), with what
   the sender check found, and the account's next run reads it with both readers: an email from an approved sender
   (authenticated) can change the deal, as the broker's extension does; anyone else's is shown as a claim and never
   applied (documents.can_change_deal). Emails are data, never instructions: nothing in one changes a rule or a tool.
"""

from __future__ import annotations

import email.utils
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

import anthropic

from api import accounts, documents, edi820, remittance, sources
from api.contracts import Contract

log = logging.getLogger("clawback.inbound_email")

PATH = "/webhooks/inbound-email"
SIGNING_KEY = "MAILGUN_WEBHOOK_SIGNING_KEY"
DOMAIN = "INBOUND_EMAIL_DOMAIN"
FORWARDERS = "INBOUND_EMAIL_FORWARDERS"
MAX_AGE_S = 12 * 3600  # Mailgun retries for 8 hours and says not to be strict about the timestamp
MAX_ATTACHMENTS = 10
REMITTANCE_FILES = (".pdf", ".csv", ".txt", ".edi", ".x12", ".820")
REMITTANCE_TYPES = ("application/pdf", "text/csv", "text/plain", "application/edi-x12")  # EDI-X12: RFC 1767
TEXT_FILES = (".csv", ".txt", ".edi", ".x12", ".820")
MAX_TOKENS = 20_000  # signature tokens remembered; one older than MAX_AGE_S is refused by its age anyway
REMITTANCE_WORDS = re.compile(r"\bremittance\b|\bremit advice\b|\bpayment advice\b", re.I)
HANDLED = "_handled"  # under the inbound root: one file per email handled, so a restart still knows it
BACKGROUND = True  # the remittance read and its run happen off the request's thread (tests turn it off)

Status = Literal["reading", "started", "matched", "kept", "claim", "not_run", "unrouted", "duplicate", "dispute_reply",
                 "failed"]


class Refused(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class InboundResult(Contract):
    """What POST /webhooks/inbound-email did with one email."""

    status: Status
    detail: str
    account: str | None = None
    routed_by: str | None = None  # address · sender · invoice · payer
    run_id: str | None = None
    document_id: str | None = None
    dispute_id: str | None = None  # a reply to one of our dispute emails (api/dispute_email.py)


@dataclass(frozen=True)
class Attachment:
    name: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class Message:
    from_header: str  # "Jordan Lee <jordan@…>"
    envelope: str  # MAIL FROM, Mailgun's `sender`
    recipient: str
    subject: str
    body: str
    headers: tuple[tuple[str, str], ...]
    attachments: tuple[Attachment, ...] = ()

    @property
    def sender(self) -> str:
        return email.utils.parseaddr(self.from_header)[1].lower() or self.envelope.lower()

    def header(self, name: str) -> list[str]:
        return [v for k, v in self.headers if k.lower() == name.lower()]

    @property
    def message_id(self) -> str | None:
        found = self.header("Message-Id")
        return found[0].strip() if found and found[0].strip() else None

    @property
    def key(self) -> str:
        """One email, however many times it's posted: its Message-Id, else what it says."""
        basis = self.message_id or "|".join([self.sender, self.subject, self.body,
                                             *(hashlib.sha256(a.data).hexdigest() for a in self.attachments)])
        return hashlib.sha256(basis.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class EmailArrival:
    """A remittance email, as pipeline.start_for_deposit takes it (Nessie's deposits have the same fields)."""

    id: str  # Message.key
    amount: Decimal | None  # what the remittance says was paid
    description: str  # "from deductions@northmart.example: “Remittance INV-3102”"
    sender: str
    source: str = "email"


# ---------------------------------------------------------------- 1. the signature

def configured() -> bool:
    return bool(os.getenv(SIGNING_KEY))


def address(account: accounts.Account) -> str | None:
    """The account's own inbox address, once the receiving domain is set."""
    domain = os.getenv(DOMAIN, "").strip().lower()
    return f"{account.id}@{domain}" if domain else None


def signature(timestamp: str, token: str, key: str) -> str:
    return hmac.new(key.encode(), f"{timestamp}{token}".encode(), hashlib.sha256).hexdigest()


# token -> (the email it signed, its timestamp), oldest first. Bounded: a token whose timestamp is more than MAX_AGE_S
# from now can't pass the age check again, so it's forgotten; past MAX_TOKENS the oldest go first.
_tokens: OrderedDict[str, tuple[str, float]] = OrderedDict()
_lock = threading.Lock()


def _forget_old_tokens(now: float) -> None:
    """Under _lock."""
    for tok in [t for t, (_, ts) in _tokens.items() if abs(now - ts) > MAX_AGE_S]:
        del _tokens[tok]
    while len(_tokens) > MAX_TOKENS:
        _tokens.popitem(last=False)


def verify(form: dict[str, str], key_of_email: str, now: float | None = None) -> None:
    key = os.getenv(SIGNING_KEY)
    if not key:
        raise Refused(503, "The remittance inbox isn't set up on this server (no signing key), so it takes no email.")
    timestamp, token, sig = (form.get(k, "") for k in ("timestamp", "token", "signature"))
    if not (timestamp and token and sig) or not hmac.compare_digest(signature(timestamp, token, key), sig):
        raise Refused(403, "bad signature")
    now = now if now is not None else time.time()
    try:
        ts = float(timestamp)
        age = abs(now - ts)
    except ValueError:
        raise Refused(403, "bad timestamp") from None
    if not age <= MAX_AGE_S:  # too old (or not a number at all)
        raise Refused(403, "the signature is too old")
    with _lock:
        seen = _tokens.setdefault(token, (key_of_email, ts))[0]
        _forget_old_tokens(now)  # after: the newest token is never the one dropped
    if seen != key_of_email:
        raise Refused(406, "this signature was already used for another email")


# ---------------------------------------------------------------- 2. what was posted

def parse(form: dict[str, str], files: dict[str, tuple[str, str, bytes]]) -> Message:
    """Mailgun's fields: from, sender, recipient, subject, body-plain, message-headers (a JSON list of [name, value])
    and attachment-1 … attachment-<attachment-count>, given here as name -> (filename, content type, bytes)."""
    try:
        raw = json.loads(form.get("message-headers") or "[]")
        headers = tuple((str(k), str(v)) for k, v in raw if isinstance(k, str))
    except (ValueError, TypeError):
        headers = ()
    try:
        count = int(form.get("attachment-count") or 0)
    except ValueError:
        count = 0
    count = min(count or sum(k.startswith("attachment-") for k in files), MAX_ATTACHMENTS)
    atts = tuple(Attachment(*files[f"attachment-{i}"]) for i in range(1, count + 1) if f"attachment-{i}" in files)
    return Message(from_header=form.get("from") or form.get("sender") or "", envelope=form.get("sender") or "",
                   recipient=form.get("recipient") or "", subject=form.get("subject") or "",
                   body=form.get("body-plain") or "", headers=headers, attachments=atts)


# ---------------------------------------------------------------- 3. the account

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _addr(s: str) -> str:
    return s.strip().lower()


def approved(account: accounts.Account, sender: str) -> bool:
    """One of the account's approved_senders, whatever the case of either address."""
    return bool(sender) and _addr(sender) in {_addr(a) for a in account.config.approved_senders}


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


def _text_of(msg: Message) -> str:
    """Subject, body and any text attachments: where an invoice number or a payer's name would be."""
    texts = [msg.subject, msg.body]
    for a in msg.attachments:
        if a.name.lower().endswith(TEXT_FILES):
            texts.append(a.data[:200_000].decode("utf-8", "ignore"))
    return "\n".join(texts)


def route(msg: Message) -> tuple[accounts.Account | None, str]:
    listed = accounts.every()
    by_id = {a.id: a for a in listed}
    to = email.utils.parseaddr(msg.recipient)[1].lower()
    local = to.split("@", 1)[0]
    for name in (local.split("+", 1)[1] if "+" in local else "", local):
        if name in by_id:
            return by_id[name], "address"
    desk = [a for a in listed if _addr(a.distributor.desk_email) == _addr(msg.sender)]
    if len(desk) == 1:
        return desk[0], "sender"
    pool = desk or [a for a in listed if _domain(a.distributor.desk_email) == _domain(msg.sender)] or \
        [a for a in listed if approved(a, msg.sender)] or listed
    text = _text_of(msg)
    for how, says in (("invoice", lambda a: _norm(a.invoice.id) in _norm(text)),
                      ("payer", lambda a: a.distributor.name.lower() in text.lower())):
        found = [a for a in pool if says(a)]
        if len(found) == 1:
            return found[0], how
    return None, "none"


# ---------------------------------------------------------------- 4. who sent it

def sender_check(msg: Message) -> tuple[bool, str]:
    """Whether the From address is really the sender: Mailgun's SPF result passed (every copy of the header, so one
    the sender wrote in can't vote) for an envelope sender in the From address's domain or under it."""
    spf = [v.strip().lower() for v in msg.header("X-Mailgun-Spf")]
    if not spf:
        return False, "no SPF result from Mailgun"
    if any(v != "pass" for v in spf):
        return False, f"SPF {spf[0]}"
    env, frm = _domain(msg.envelope), _domain(msg.sender)
    if not env or not frm or not (env == frm or env.endswith("." + frm)):
        return False, f"SPF passed for {env or 'an unknown domain'}, not the From address's {frm or 'domain'}"
    return True, "SPF pass"


def trusted(msg: Message, account: accounts.Account, authenticated: bool) -> bool:
    """May this sender's remittance start a run: the distributor's desk (or its domain), an approved sender, or one of
    the people who forward remittances (INBOUND_EMAIL_FORWARDERS). Addresses are compared without case."""
    forwarders = {_addr(f) for f in os.getenv(FORWARDERS, "").split(",") if f.strip()}
    s = _addr(msg.sender)
    desk = _addr(account.distributor.desk_email)
    return authenticated and (s == desk or _domain(s) == _domain(desk) or approved(account, s) or s in forwarders)


# ---------------------------------------------------------------- 5. remittance or document

def _candidate(a: Attachment) -> bool:
    return a.name.lower().endswith(REMITTANCE_FILES) or a.content_type.split(";")[0].strip().lower() in REMITTANCE_TYPES


def _reads_as_remittance(text: str, account: accounts.Account) -> bool:
    """What the Payment reader would take as this account's remittance: an EDI 820, or text that says remittance or
    payment advice, or names the account's invoice."""
    head = text[:200_000]
    return edi820.looks_like(text) or bool(REMITTANCE_WORDS.search(head)) or _norm(account.invoice.id) in _norm(head)


def remittance_file(msg: Message, account: accounts.Account) -> tuple[Attachment, str, str] | None:
    """The first attachment that is a remittance: one the Payment reader accepts (api/remittance.extract_text: not too
    big, a PDF with text in it, or UTF-8 text) whose text reads as a remittance. A sales report, a price list or a
    signed amendment attached to a broker's email isn't one, so that email stays a document. Returns the attachment,
    its text and what it came as."""
    for a in msg.attachments:
        if not _candidate(a):
            continue
        try:
            text, kind = remittance.extract_text(a.data, a.name)
        except remittance.InputError:
            continue
        if _reads_as_remittance(text, account):
            return a, text, kind
    return None


def is_remittance(msg: Message, account: accounts.Account) -> bool:
    if remittance_file(msg, account) is not None:
        return True
    text = f"{msg.subject}\n{msg.body}"
    return edi820.looks_like(msg.body) or (bool(REMITTANCE_WORDS.search(text))
                                           and _norm(account.invoice.id) in _norm(text))


# ---------------------------------------------------------------- the store

def _handled_dir() -> Path | None:
    root = accounts.inbound_root()
    return root / HANDLED if root else None


_handled: dict[str, InboundResult] = {}


def handled(key: str) -> InboundResult | None:
    with _lock:
        if key in _handled:
            return _handled[key]
    d = _handled_dir()
    p = d / f"{key}.json" if d else None
    if p and p.is_file():
        try:
            return InboundResult.model_validate_json(p.read_text())
        except ValueError:
            return None
    return None


def _remember(key: str, result: InboundResult) -> InboundResult:
    with _lock:
        _handled[key] = result
    d = _handled_dir()
    if d:
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{key}.json.tmp"
        tmp.write_text(result.model_dump_json())
        tmp.replace(d / f"{key}.json")
    return result


def _claim(key: str) -> bool:
    """Take this email for handling; False if it's already being (or been) handled."""
    with _lock:
        if key in _handled:
            return False
        _handled[key] = InboundResult(status="reading", detail="being handled")
        return True


def _header_value(s: str) -> str:
    return " ".join(s.split())  # one line: nothing in a subject can add a header


def _date(msg: Message) -> datetime:
    for v in msg.header("Date"):
        try:
            return email.utils.parsedate_to_datetime(v)
        except (TypeError, ValueError):
            continue
    return datetime.now(timezone.utc)


def keep(msg: Message, account: accounts.Account, authenticated: bool, why: str) -> str:
    """Write the email as a document of the account (accounts.inbound_root()/<id>/emails/<doc id>.eml) and reload the
    accounts, so documents.load and the next run see it. Returns its document id."""
    root = accounts.inbound_root()
    if root is None:
        raise Refused(503, "INBOUND_EMAIL_DIR isn't set on this server, so the inbox can't keep documents yet")
    when = _date(msg)
    doc_id = f"inbound-{account.id}-{when:%Y%m%d}-{msg.key[:8]}"
    folder = root / account.id / accounts.INBOUND_DOCS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{doc_id}.eml"
    if not path.exists():
        head = [("From", msg.from_header or msg.sender), ("To", msg.recipient), ("Date", email.utils.format_datetime(when)),
                ("Subject", msg.subject), ("Message-ID", msg.message_id or f"<{msg.key}@inbound.clawback>"),
                ("X-Clawback-Inbound", "mailgun"), (documents.SENDER_CHECK, "pass" if authenticated else "fail"),
                ("X-Clawback-Sender-Check-Detail", why), ("MIME-Version", "1.0"),
                ("Content-Type", 'text/plain; charset="utf-8"')]
        text = "".join(f"{k}: {_header_value(v)}\n" for k, v in head) + "\n" + msg.body.replace("\r\n", "\n")
        tmp = path.with_suffix(".eml.tmp")
        tmp.write_text(text)
        tmp.replace(path)
    accounts.clear()
    return doc_id


# ---------------------------------------------------------------- handling one email

def _who(msg: Message) -> str:
    return f"Email from {msg.sender or 'an unknown sender'}" + (f" (“{msg.subject}”)" if msg.subject else "")


def _remittance_text(msg: Message, account: accounts.Account) -> tuple[str, Literal["text", "pdf"]]:
    found = remittance_file(msg, account)
    if found is not None:
        return found[1], found[2]  # type: ignore[return-value]
    return msg.body, "text"


def read_and_run(msg: Message, account: accounts.Account, client: anthropic.Anthropic | None = None,
                 background: bool = True) -> InboundResult:
    """Read the remittance and check it as an upload is; start the run on its lines if they add up."""
    who = _who(msg)
    try:
        text, kind = _remittance_text(msg, account)
        r = remittance.read(account.id, text, kind, client=client)
    except remittance.InputError as e:
        sources.saw("inbox", f"{who}: its remittance can't be read ({e})", account.id)
        return InboundResult(status="not_run", detail=str(e), account=account.id)
    except Exception as e:  # noqa: BLE001 - a failed read is noted for a person, never a crash of the inbox
        log.exception("inbound remittance read failed")
        sources.saw("inbox", f"{who}: the Payment reader failed ({type(e).__name__}); upload it instead", account.id)
        return InboundResult(status="not_run", detail=f"read failed: {type(e).__name__}", account=account.id)
    if not r.can_run:
        why = r.problems[0].text if r.problems else "its lines don't add up to what the payment is short"
        sources.saw("inbox", f"{who}: read {len(r.charges)} lines but no run started: {why}", account.id)
        return InboundResult(status="not_run", detail=why, account=account.id)
    paid = r.totals.paid if r.totals and r.totals.paid is not None else account.invoice.received
    arrival = EmailArrival(id=msg.key, amount=paid, sender=msg.sender,
                           description=f"from {msg.sender}" + (f": “{msg.subject}”" if msg.subject else ""))
    try:
        run = remittance.start_with_charges(account.id, r.charges, client, background, arrival=arrival)
    except Exception as e:  # noqa: BLE001 - noted for a person
        log.exception("inbound remittance couldn't start a run")
        sources.saw("inbox", f"{who}: read and checked, but the run couldn't start ({type(e).__name__})", account.id)
        return InboundResult(status="not_run", detail=f"run failed to start: {type(e).__name__}", account=account.id)
    dep = getattr(run, "deposit", None)
    matched = dep is not None and not (getattr(dep, "source", "nessie") == "email" and dep.id == msg.key)
    sources.saw("inbox", f"{who}: {len(r.charges)} charges read and checked; "
                + (f"the same payment as run {run.id}" if matched else f"started run {run.id}"), account.id, run.id)
    return InboundResult(status="matched" if matched else "started", account=account.id, run_id=run.id,
                         detail=f"{len(r.charges)} charges read and checked")


def handle(msg: Message, client: anthropic.Anthropic | None = None, background: bool | None = None) -> InboundResult:
    """Steps 2 to 6 for a verified email (the signature is step 1, in the route)."""
    background = BACKGROUND if background is None else background
    key = msg.key
    if (before := handled(key)) is not None or not _claim(key):
        first = before or handled(key)
        return InboundResult(status="duplicate", detail=f"already handled: {first.status if first else 'in progress'}",
                             account=first.account if first else None, run_id=first.run_id if first else None,
                             document_id=first.document_id if first else None)
    try:
        return _handle(msg, key, client, background)
    except BaseException:
        with _lock:  # not handled after all: Mailgun's retry gets another go
            _handled.pop(key, None)
        raise


def _background(msg: Message, key: str, account: accounts.Account, how: str,
                client: anthropic.Anthropic | None) -> None:
    """The remittance's read and run, off the webhook's thread. Whatever goes wrong, the email ends up with an outcome:
    failed (with why, on the Connections page) instead of "reading" forever. Mailgun already has its 200, so a person
    uploads it instead."""
    try:
        result = read_and_run(msg, account, client, True).model_copy(update={"routed_by": how})
    except Exception as e:  # noqa: BLE001 - noted for a person
        log.exception("inbound remittance failed in the background")
        result = InboundResult(status="failed", account=account.id, routed_by=how,
                               detail=f"handling failed: {type(e).__name__}")
        try:
            sources.saw("inbox", f"{_who(msg)}: couldn't be handled ({type(e).__name__}); upload the remittance "
                        "instead", account.id)
        except Exception:  # noqa: BLE001
            log.exception("couldn't note the failed email")
    try:
        _remember(key, result)
    except Exception:  # noqa: BLE001 - the outcome is in memory (set first); only the file that outlives a restart failed
        log.exception("couldn't save the inbound email's outcome")
        with _lock:
            _handled[key] = result


def _handle(msg: Message, key: str, client: anthropic.Anthropic | None, background: bool) -> InboundResult:
    who = _who(msg)
    from api import dispute_email  # a reply to a dispute email (d-<n>+<token>@, or In-Reply-To one we sent)

    if (found := dispute_email.route(msg)) is not None:
        run, dispute = found
        dispute_email.on_reply(run, dispute, msg, client)
        sources.saw("inbox", f"{who}: a reply to dispute {dispute.id}")
        return _remember(key, InboundResult(status="dispute_reply", detail=f"added to {dispute.id}'s thread",
                                            account=run.account.id, routed_by="dispute", run_id=run.id,
                                            dispute_id=dispute.id))
    account, how = route(msg)
    if account is None:
        domain = os.getenv(DOMAIN, "").strip()
        hint = f"; send it to <distributor>@{domain}" if domain else ""
        sources.saw("inbox", f"{who}: it doesn't say which distributor it's for{hint}")
        return _remember(key, InboundResult(status="unrouted", detail="no account matched the address, sender or text"))
    authenticated, why = sender_check(msg)
    if is_remittance(msg, account):
        if not trusted(msg, account, authenticated):
            sources.saw("inbox", f"{who}: a remittance from a sender who isn't {account.distributor.name}'s desk, an "
                        f"approved sender or a forwarder ({why}): not run. Upload it if it's real.", account.id)
            return _remember(key, InboundResult(status="not_run", account=account.id, routed_by=how,
                                                detail=f"untrusted sender ({why})"))
        if background:
            def work() -> None:
                _background(msg, key, account, how, client)

            threading.Thread(target=work, daemon=True, name="inbound-remittance").start()
            sources.saw("inbox", f"{who}: a remittance for {account.distributor.name}; the Payment reader is on it",
                        account.id)
            return InboundResult(status="reading", account=account.id, routed_by=how,
                                 detail="reading the remittance; the run starts if its lines add up")
        return _remember(key, read_and_run(msg, account, client, False).model_copy(update={"routed_by": how}))
    doc_id = keep(msg, account, authenticated, why)
    doc, _ = documents.load(doc_id)
    changes = documents.can_change_deal(doc)
    sources.saw("inbox", f"{who}: kept for {account.distributor.name}'s next run as "
                + ("an email from an approved sender, which can change the deal" if changes else
                   f"a claim, never applied ({'not an approved sender' if authenticated else why})"), account.id)
    return _remember(key, InboundResult(status="kept" if changes else "claim", account=account.id, routed_by=how,
                                        document_id=doc_id,
                                        detail="can change the deal" if changes else "shown as a claim"))


def reset() -> None:
    with _lock:
        _handled.clear()
        _tokens.clear()
