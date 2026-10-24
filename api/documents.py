"""Source documents: text plus who sent them and whether they can change the deal.

Each account's documents are the files in its deals/, emails/ and notices/ folders (api/accounts.py); a document's
id is its file stem, unique across every account, so an id alone finds the file and the account it belongs to.
The text is never edited; quotes are checked against it. A document is signed by both parties when it's the
account's deal (the first of its deal_docs) or an amendment (deals/*amendment*): Peak Bar's spring-promo and
amendment-1. Anything else changes the deal only if its sender is one of the account's approved_senders.
"""

from __future__ import annotations

import email
import email.utils
import hashlib
import re
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path

from api import accounts
from api.contracts import Document

DATA = accounts.DATA

_PASTED: dict[str, tuple[Document, str]] = {}  # the judge's clauses from the scenario box

_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_MD_DATE = re.compile(r"\*\*(?:[A-Za-z ]*?date):\*\*\s*([A-Z][a-z]+ \d{1,2}, \d{4})", re.I)
_MD_FROM = re.compile(r"^\*\*From:\*\*(.*)$", re.M)


class _Paths(Mapping[str, str]):
    """doc_id -> its path, as Document.path gives it ("accounts/peak-bar/deals/spring-promo.md"), for every account."""

    def _all(self) -> dict[str, str]:
        return {doc_id: _rel(a, p) for a in accounts.every() for doc_id, p in a.docs.items()}

    def __getitem__(self, doc_id: str) -> str:
        found = accounts.document(doc_id)
        if found is None:
            raise KeyError(doc_id)
        return _rel(*found)

    def __iter__(self) -> Iterator[str]:
        return iter(self._all())

    def __len__(self) -> int:
        return len(self._all())

    def __contains__(self, doc_id: object) -> bool:
        return isinstance(doc_id, str) and accounts.document(doc_id) is not None


PATHS = _Paths()


def _rel(account: accounts.Account, path: Path) -> str:
    """The path under the folder that holds accounts/: relative to data/ for every real account."""
    return path.relative_to(account.dir.parent.parent).as_posix()


def file(doc_id: str) -> Path:
    found = accounts.document(doc_id)
    if found is None:
        raise KeyError(doc_id)
    return found[1]


def account_of(doc_id: str) -> accounts.Account:
    """The account a document belongs to; a pasted one (scenario box, eval) belongs to the current account."""
    found = accounts.document(doc_id)
    return found[0] if found else accounts.current()


def _kind(doc_id: str, folder: str) -> str:
    if folder == "emails":
        return "email"
    if folder == "notices":
        return "notice"
    if "amendment" in doc_id:
        return "amendment"
    return "draft" if "draft" in doc_id else "deal"


def _approved(sender: str | None, account: accounts.Account) -> bool:
    return sender is not None and sender.lower() in account.config.approved_senders


def paste(text: str, kind: str = "deal", sender: str | None = None, received_at: datetime | None = None) -> Document:
    """A document that isn't a file under data/: a clause pasted into the scenario box (treated as part of the
    signed deal for that one case), or an eval case's deal or email. It belongs to the current account."""
    basis = text if kind == "deal" and sender is None else f"{kind}|{sender}|{text}"  # a pasted clause keeps its id
    sha = hashlib.sha256(basis.encode()).hexdigest()
    doc = Document(id=f"pasted-{sha[:10]}", kind=kind, path="(not a file in data/)", sender=sender,
                   approved_sender=_approved(sender, accounts.current()), signed_by_both=kind == "deal",
                   received_at=received_at, sha256=sha)
    _PASTED[doc.id] = (doc, text)
    return doc


def load(doc_id: str) -> tuple[Document, str]:
    if doc_id in _PASTED:
        return _PASTED[doc_id]
    found = accounts.document(doc_id)
    if found is None:
        raise KeyError(doc_id)
    account, path = found
    text = path.read_text()
    kind = _kind(doc_id, path.parent.name)
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
    signed = kind == "amendment" or (kind == "deal" and doc_id == account.config.deal_docs[0])
    doc = Document(id=doc_id, kind=kind, path=_rel(account, path), sender=sender,
                   approved_sender=_approved(sender, account), signed_by_both=signed, received_at=received_at,
                   sha256=hashlib.sha256(text.encode()).hexdigest())
    return doc, text


def can_change_deal(doc: Document) -> bool:
    """Only approved senders or documents signed by both parties change a deal; anything else is a claim."""
    return doc.signed_by_both or doc.approved_sender
