"""Accounts whose charges include fee-schedule fees: data/accounts/<id>/ with a fees/fees.yaml (Lantern Hill Soda Co.
<- KeHE Distributors is the first). Everything such an account needs beyond PR #64's account layout, behind a few
functions the pipeline can call once it runs per account (see the PR for the wiring):

    account.yaml                       AccountConfig's shape, nothing else (PR #64 validates it strictly)
    fees/fees.yaml                     contract (the governing policy, under data/contracts/), codes, policy_changes,
                                       as_of, invoice_date, older_charges
    deals/ emails/ notices/            our side's documents and the other side's notices (ids are file stems)
    fees/backup/                       the other side's backup documents (proof for requires_proof fees)
    fees/backup.csv                    FeeBackupRow lines, keyed by the charge's ref
    purchases/purchase-orders.csv      po, written_on, product, cases: what off-invoice (OI) charges are checked against
    charges/<month>.csv  expected.csv  the month's charges and their expected decisions

load() reads it all; register() makes its documents readable by both readers with the fee-term prompt section;
engine_terms(), fee_data() and engine_sales() give compute_allowed() what it needs. No AI here and no money math.
"""

from __future__ import annotations

import csv
import email
import email.utils
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

from api import adapters, documents
from api.contracts import Charge, Document, FeeBackupRow, Term
from api.engine import types as eng

ACCOUNTS = Path(__file__).resolve().parents[1] / "data" / "accounts"
DOC_DIRS = {"deals": "deal", "emails": "email", "notices": "notice", "fees/backup": "notice"}
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_MD_DATE = re.compile(r"\*\*(?:[A-Za-z ]*?date):\*\*\s*([A-Z][a-z]+ \d{1,2}, \d{4})", re.I)
_MD_FROM = re.compile(r"^\*\*From:\*\*(.*)$", re.M)


@dataclass
class FeeAccount:
    id: str
    dir: Path
    config: dict  # account.yaml
    fees: dict  # fees/fees.yaml
    docs: dict[str, tuple[Document, str]] = field(repr=False)
    read_order: list[str]  # the governing policy, then account.yaml's deal_docs
    charges: list[Charge]  # the invoice month's, in the remittance's total
    older_charges: list[Charge]  # reviewed with it, taken from earlier payments
    purchases: list[dict]
    backup: list[FeeBackupRow]

    @property
    def brand(self) -> str:
        return self.config["brand"]["name"]

    @property
    def distributor(self) -> str:
        return self.config["distributor"]["name"]

    def all_charges(self) -> list[Charge]:
        return self.charges + self.older_charges

    def expected(self) -> list[dict]:
        return _csv(self.dir / "expected.csv")


def has_fees(account_id: str) -> bool:
    return (ACCOUNTS / account_id / "fees" / "fees.yaml").exists()


def _csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _charges(path: Path) -> list[Charge]:
    return [Charge.model_validate({k: v for k, v in row.items() if k != "charge_id"} | {"id": row["charge_id"]})
            for row in _csv(path)]


def _doc(doc_id: str, kind: str, rel: str, text: str, approved: set[str], signed: bool,
         received_at: datetime | None = None) -> Document:
    sender = None
    if kind == "email":
        msg = email.message_from_string(text)
        sender = email.utils.parseaddr(msg.get("From", ""))[1] or None
        received_at = email.utils.parsedate_to_datetime(msg["Date"]).replace(tzinfo=None) if msg.get("Date") else None
    else:
        if (m := _MD_FROM.search(text)) and (e := _EMAIL.search(m.group(1))):
            sender = e.group()
        if m := _MD_DATE.search(text):
            received_at = datetime.strptime(m.group(1), "%B %d, %Y")
    return Document(id=doc_id, kind=kind, path=rel, sender=sender,
                    approved_sender=sender is not None and sender.lower() in approved, signed_by_both=signed,
                    received_at=received_at, sha256=hashlib.sha256(text.encode()).hexdigest())


def load(account_id: str) -> FeeAccount:
    root = ACCOUNTS / account_id
    config = yaml.safe_load((root / "account.yaml").read_text())
    fees = yaml.safe_load((root / "fees" / "fees.yaml").read_text())
    approved = {s.strip().lower() for s in config["approved_senders"]}
    docs: dict[str, tuple[Document, str]] = {}
    c = fees["contract"]
    path = ACCOUNTS.parent / c["path"]  # under data/
    text = path.read_text()
    when = datetime.combine(_date(c["date"]), datetime.min.time())
    # The policy binds both sides (accepting a PO accepts it), so it counts as signed by both, like a deal.
    docs[c["id"]] = (_doc(c["id"], "deal", str(path.relative_to(ACCOUNTS.parent)), text, approved, True, when), text)
    for folder, kind in DOC_DIRS.items():
        for p in sorted((root / folder).glob("*.md")) + sorted((root / folder).glob("*.eml")):
            text = p.read_text()
            # Our promotion submission carries KeHE's acceptance, so it's signed by both; the rest change the deal
            # only through an approved sender.
            docs[p.stem] = (_doc(p.stem, kind, str(p.relative_to(ACCOUNTS.parent)), text, approved, kind == "deal"),
                            text)
    month = config["invoice"]["month"]
    return FeeAccount(
        id=account_id, dir=root, config=config, fees=fees, docs=docs,
        read_order=[c["id"], *config["deal_docs"]],
        charges=_charges(root / "charges" / f"{month}.csv"),
        older_charges=_charges(root / fees["older_charges"]) if fees.get("older_charges") else [],
        purchases=_csv(root / "purchases" / "purchase-orders.csv"),
        backup=[FeeBackupRow.model_validate(r) for r in _csv(root / "fees" / "backup.csv")],
    )


def _date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def register(acct: FeeAccount) -> None:
    """Make the account's documents loadable (documents.load) and read with the fee-term prompt section."""
    for doc, text in acct.docs.values():
        documents.register(doc, text, parties=(acct.brand, acct.distributor))


def noticed_on(acct: FeeAccount, doc_id: str) -> date | None:
    """A policy-change document's notice date (fees.yaml policy_changes); None for every other document."""
    if doc_id not in acct.fees.get("policy_changes", []):
        return None
    received = acct.docs[doc_id][0].received_at
    return received.date() if received else None


def engine_terms(acct: FeeAccount, terms: list[Term]) -> list[eng.Term]:
    return [adapters.to_engine_term(t, noticed_on(acct, t.source_doc_id)) for t in terms]


def engine_charge(acct: FeeAccount, c: Charge) -> eng.Charge:
    return adapters.to_engine_charge(c, counterparty=acct.distributor)


def fee_data(acct: FeeAccount) -> eng.FeeData:
    return eng.FeeData(
        lines=tuple(adapters.to_engine_fee_line(r) for r in acct.backup),
        codes=dict(acct.fees.get("codes", {})),
        proof_docs=frozenset(acct.docs),
        as_of=_date(acct.fees["as_of"]) if acct.fees.get("as_of") else None,
        invoice_date=_date(acct.fees["invoice_date"]) if acct.fees.get("invoice_date") else None,
    )


def engine_sales(acct: FeeAccount) -> list[eng.SalesWeek]:
    """Each purchase order as a one-day row (written_on to written_on, cases as the promoted units), so the promo
    engine counts an off-invoice allowance by the date its PO was written (policy §6.2) and caps it in that order."""
    out = []
    for r in acct.purchases:
        day, cases = date.fromisoformat(r["written_on"]), int(r["cases"])
        out.append(eng.SalesWeek(day, day, r["product"], cases, cases))
    return out
