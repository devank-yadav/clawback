"""Source documents under data/: text plus who sent them and whether they can change the deal.

The text is never edited; quotes are checked against it. Whether a deal or amendment is signed by both
parties is listed in SIGNED_BY_BOTH (the seed copies this into the documents table).
"""

from __future__ import annotations

import email
import email.utils
import hashlib
import re
from datetime import datetime
from pathlib import Path

from api.contracts import Document
from api.engine.policy import load_policy

DATA = Path(__file__).resolve().parents[1] / "data"

# doc_id -> path under data/
PATHS = {
    "spring-promo": "deals/spring-promo.md",
    "amendment-1": "deals/amendment-1.md",
    "summer-draft": "deals/summer-draft.md",
    "broker-2026-03-28": "emails/broker-2026-03-28.eml",
    "northmart-2026-03-30": "emails/northmart-2026-03-30.eml",
    "display-fee-2026-03-11": "notices/display-fee-2026-03-11.md",
    "display-fee-2026-04-12": "notices/display-fee-2026-04-12.md",
    "display-fee-2026-04-25": "notices/display-fee-2026-04-25.md",
}
SIGNED_BY_BOTH = {"spring-promo", "amendment-1"}  # both signature blocks are filled in
_PASTED: dict[str, tuple[Document, str]] = {}  # the judge's clauses from the scenario box

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_MD_DATE = re.compile(r"\*\*(?:[A-Za-z ]*?date):\*\*\s*([A-Z][a-z]+ \d{1,2}, \d{4})", re.I)
_MD_FROM = re.compile(r"^\*\*From:\*\*(.*)$", re.M)


def _kind(doc_id: str, path: str) -> str:
    if path.startswith("emails/"):
        return "email"
    if path.startswith("notices/"):
        return "notice"
    if doc_id.startswith("amendment"):
        return "amendment"
    return "draft" if "draft" in doc_id else "deal"


def paste(text: str, kind: str = "deal", sender: str | None = None, received_at: datetime | None = None) -> Document:
    """A document that isn't a file under data/: a clause pasted into the scenario box (treated as part of the
    signed deal for that one case), or an eval case's deal or email."""
    basis = text if kind == "deal" and sender is None else f"{kind}|{sender}|{text}"  # a pasted clause keeps its id
    sha = hashlib.sha256(basis.encode()).hexdigest()
    approved = sender is not None and sender.lower() in load_policy().approved_amendment_senders
    doc = Document(id=f"pasted-{sha[:10]}", kind=kind, path="(not a file in data/)", sender=sender,
                   approved_sender=approved, signed_by_both=kind == "deal", received_at=received_at, sha256=sha)
    _PASTED[doc.id] = (doc, text)
    return doc


def load(doc_id: str) -> tuple[Document, str]:
    if doc_id in _PASTED:
        return _PASTED[doc_id]
    path = PATHS[doc_id]
    text = (DATA / path).read_text()
    kind = _kind(doc_id, path)
    sender, received_at = None, None
    if kind == "email":
        msg = email.message_from_string(text)
        sender = email.utils.parseaddr(msg.get("From", ""))[1] or None
        if msg.get("Date"):
            received_at = email.utils.parsedate_to_datetime(msg["Date"])
    else:
        if m := _MD_FROM.search(text):
            if e := _EMAIL.search(m.group(1)):
                sender = e.group()
        if m := _MD_DATE.search(text):
            received_at = datetime.strptime(m.group(1), "%B %d, %Y")
    approved = sender is not None and sender.lower() in load_policy().approved_amendment_senders
    doc = Document(id=doc_id, kind=kind, path=path, sender=sender, approved_sender=approved,
                   signed_by_both=doc_id in SIGNED_BY_BOTH, received_at=received_at,
                   sha256=hashlib.sha256(text.encode()).hexdigest())
    return doc, text


def can_change_deal(doc: Document) -> bool:
    """Only approved senders or documents signed by both parties change a deal; anything else is a claim."""
    return doc.signed_by_both or doc.approved_sender
