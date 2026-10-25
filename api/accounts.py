"""Accounts: a brand and the distributor that pays it, one folder each under data/accounts/<id>/.

    account.yaml                  AccountConfig (api/contracts.py, "# ---- accounts"); the only file that must exist
    deals/ emails/ notices/       documents; their ids are the file stems, unique across every account
    charges/<month>.csv           a month's charges: the invoice month's, and any later one's (Peak Bar's April)
    sales/store-sales.csv  payments/prior.csv  plan/promo-plan.csv
    history/  deliveries/  pricing/  terms/      rows api/account_rows.py reads
A missing file means no rows. Emails the remittance inbox kept for an account (api/inbound_email.py) are documents too:
<INBOUND_EMAIL_DIR>/<id>/emails/*.eml, listed in Account.inbound; accounts.clear() picks up a new one.

Every account.yaml is loaded once and checked: it validates against AccountConfig, its id is its folder's name, its
deal_docs are its own documents, and nothing clashes with another account: document ids, invoice ids and QuickBooks
DocNumbers (all accounts share one sandbox company), Nessie descriptions, and dispute numbers (each month of an account
gets ten from dispute_start: Peak Bar's March files D-0417, its April D-0427). An account that fails is left out and its
problems are kept (problems()); the others still work, and the tests assert there are none.

The current account is a context variable, Peak Bar by default. Loaders that aren't handed an account use it, so the
pipeline sets it on a run's thread and code that takes no account (the evidence builders) reads that run's files.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from api.contracts import MONTHS, AccountConfig, Brand, Distributor, AccountInvoice

DEFAULT = "peak-bar"
DATA = Path(__file__).resolve().parents[1] / "data"
ROOTS: list[Path] = [DATA / "accounts"]  # the tests add api/tests/data/accounts
DOC_DIRS = ("deals", "emails", "notices")
DOC_SUFFIXES = (".md", ".eml")
CONTRACTS = "contracts"  # data/contracts/: real contracts an account.yaml names in `contracts`
DISPUTES_PER_MONTH = 10
INBOUND_DOCS = "emails"  # <inbound_root()>/<account id>/emails/<doc id>.eml, so documents.load reads them as emails


class UnknownAccount(KeyError):
    pass


@dataclass(frozen=True)
class Account:
    config: AccountConfig
    dir: Path
    docs: dict[str, Path] = field(repr=False)  # this account's documents: id -> file
    months: tuple[str, ...]  # the invoice month first, then each other charges/<month>.csv in calendar order
    inbound: tuple[str, ...] = ()  # emails the remittance inbox kept for it (inbound_root()), oldest first; in docs too
    drive: tuple[str, ...] = ()  # documents Google Drive brought in (drive_root(), api/drive.py); in docs too

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def brand(self) -> Brand:
        return self.config.brand

    @property
    def distributor(self) -> Distributor:
        return self.config.distributor

    @property
    def invoice(self) -> AccountInvoice:
        return self.config.invoice

    def first_name(self, role: str = "owner") -> str:
        """Dana: how texts and the log name the admin (the owner), the one person who decides."""
        return self.brand.owner.name.split()[0]

    def dispute_start(self, month: str) -> int:
        """The first dispute number a run of this month files."""
        return self.config.dispute_start + DISPUTES_PER_MONTH * self.months.index(month)

    def path(self, rel: str) -> Path:
        return self.dir / rel


_lock = threading.Lock()
_registry: tuple[dict[str, Account], list[str]] | None = None
_current: ContextVar[str | None] = ContextVar("clawback_account", default=None)


ONLY: set[str] | None = None  # the tests load just the accounts they name (api/tests/conftest.py)


def inbound_root() -> Path | None:
    """Where the remittance inbox keeps the emails it was sent (api/inbound_email.py): INBOUND_EMAIL_DIR, the VM's
    mounted state/inbound (docker-compose.yml). Unset: nowhere, so no account has inbound documents (the tests)."""
    value = os.getenv("INBOUND_EMAIL_DIR")
    return Path(value) if value else None


def drive_root() -> Path | None:
    """Where api/drive.py keeps the documents it brought in from Google Drive: DRIVE_DOCS_DIR, else
    <CLAWBACK_STATE_DIR>/drive once DRIVE_ROOT_FOLDER_ID is set. Unset: nowhere (the tests, laptops without Drive)."""
    if value := os.getenv("DRIVE_DOCS_DIR"):
        return Path(value)
    if os.getenv("DRIVE_ROOT_FOLDER_ID"):
        return Path(os.getenv("CLAWBACK_STATE_DIR", "state")) / "drive"
    return None


def _folders() -> list[Path]:
    found = [d for root in ROOTS if root.is_dir() for d in sorted(root.iterdir()) if (d / "account.yaml").is_file()
             and (ONLY is None or d.name in ONLY)]
    return sorted(found, key=lambda d: d.name != DEFAULT)  # Peak Bar first: it wins any clash


def _months(config: AccountConfig, folder: Path) -> tuple[str, ...]:
    files = {p.stem for p in (folder / "charges").glob("*.csv") if p.stem in MONTHS}
    first = MONTHS.index(config.invoice.month)
    later = [m for m in MONTHS[first + 1:] + MONTHS[:first] if m in files]
    return (config.invoice.month, *later)


def _desk_override(config: AccountConfig) -> AccountConfig:
    """DESK_EMAIL_<ACCOUNT_ID> (e.g. DESK_EMAIL_PEAK_BAR) on a server points the distributor's deductions desk at a real
    inbox, so dispute emails reach someone, without putting that address in the repo."""
    desk = (os.getenv(f"DESK_EMAIL_{config.id.upper().replace('-', '_')}") or "").strip()
    if not desk:
        return config
    return config.model_copy(update={"distributor": config.distributor.model_copy(update={"desk_email": desk})})


def _load() -> tuple[dict[str, Account], list[str]]:
    accounts: dict[str, Account] = {}
    problems: list[str] = []
    taken: dict[tuple[str, str], str] = {}  # (what, value) -> the account that has it
    disputes: list[tuple[int, int, str]] = []
    for folder in _folders():
        where = f"{folder.name}/account.yaml"
        try:
            config = AccountConfig.model_validate(yaml.safe_load((folder / "account.yaml").read_text()) or {})
        except (ValidationError, yaml.YAMLError) as e:
            problems.append(f"{where}: {e}")
            continue
        config = _desk_override(config)
        mine: list[str] = []
        if config.id != folder.name:
            mine.append(f"id {config.id!r} isn't the folder's name {folder.name!r}")
        if config.id in accounts:
            mine.append(f"a second account {config.id!r}")
        docs: dict[str, Path] = {}
        for sub in DOC_DIRS:
            for p in sorted((folder / sub).glob("*")) if (folder / sub).is_dir() else []:
                if p.suffix not in DOC_SUFFIXES:
                    continue
                if p.stem in docs:
                    mine.append(f"two documents named {p.stem!r}")
                docs[p.stem] = p
        for name in config.contracts:  # a real contract under data/contracts/, shared text, never edited
            p = folder.parent.parent / CONTRACTS / name
            if not p.is_file():
                mine.append(f"contract {name!r} isn't in {CONTRACTS}/")
            elif p.stem in docs:
                mine.append(f"two documents named {p.stem!r}")
            else:
                docs[p.stem] = p
        inbound: list[str] = []
        kept = inbound_root()
        kept = kept / folder.name / INBOUND_DOCS if kept else None
        for p in sorted(kept.glob("*.eml")) if kept and kept.is_dir() else []:  # api/inbound_email.py wrote these
            if p.stem in docs:
                mine.append(f"two documents named {p.stem!r}")
            else:
                docs[p.stem] = p
                inbound.append(p.stem)
        drive: list[str] = []
        synced = drive_root()
        for sub in DOC_DIRS if synced else ():
            for p in sorted((synced / folder.name / sub).glob("*.md")):  # api/drive.py wrote these
                if p.stem in docs:
                    mine.append(f"two documents named {p.stem!r}")
                else:
                    docs[p.stem] = p
                    drive.append(p.stem)
        if missing := [d for d in config.deal_docs if d not in docs]:
            mine.append(f"deal_docs not in deals/, emails/ or notices/: {missing}")
        months = _months(config, folder)
        claims = [("document", d) for d in docs] + [
            ("invoice", config.invoice.id), ("QuickBooks invoice", config.qbo.invoice_no),
            ("Nessie description", " ".join(config.nessie_description.lower().split()))]
        for what, value in claims:
            if (what, value) in taken:
                mine.append(f"{what} {value!r} is already {taken[what, value]}'s")
        low, high = config.dispute_start, config.dispute_start + DISPUTES_PER_MONTH * len(months)
        for a, b, other in disputes:
            if low < b and a < high:
                mine.append(f"disputes D-{low:04d} to D-{high - 1:04d} overlap {other}'s D-{a:04d} to D-{b - 1:04d}")
        if mine:
            problems += [f"{where}: {m}" for m in mine]
            continue
        for claim in claims:
            taken[claim] = config.id
        disputes.append((low, high, config.id))
        accounts[config.id] = Account(config, folder, docs, months, tuple(inbound), tuple(drive))
    return accounts, problems


def _loaded() -> tuple[dict[str, Account], list[str]]:
    global _registry
    with _lock:
        if _registry is None:
            _registry = _load()
        return _registry


def clear() -> None:
    """Read every account.yaml again on next use (tests; a data change)."""
    global _registry
    with _lock:
        _registry = None


def every() -> list[Account]:
    """Every account that loaded, Peak Bar first, then by id."""
    return sorted(_loaded()[0].values(), key=lambda a: (a.id != DEFAULT, a.id))


def problems() -> list[str]:
    """Why each account that didn't load was left out."""
    return list(_loaded()[1])


def get(account_id: str) -> Account:
    try:
        return _loaded()[0][account_id]
    except KeyError:
        raise UnknownAccount(account_id) from None


def resolve(account: Account | str | None) -> Account:
    """An Account from itself, its id, or None (the current account)."""
    if isinstance(account, Account):
        return account
    return get(account) if account else current()


def current() -> Account:
    return get(_current.get() or DEFAULT)


@contextmanager
def using(account: Account | str) -> Iterator[Account]:
    """Make this the current account for the code inside (this thread, or this request)."""
    found = resolve(account)
    token = _current.set(found.id)
    try:
        yield found
    finally:
        _current.reset(token)


def document(doc_id: str) -> tuple[Account, Path] | None:
    """The account a document belongs to, and its file."""
    for a in every():
        if doc_id in a.docs:
            return a, a.docs[doc_id]
    return None


def for_deposit(description: str) -> Account | None:
    """The account a Nessie deposit pays: its nessie_description exactly, else one it contains, else the one account
    whose distributor it names (so "Northmart remittance" still starts Peak Bar's run)."""
    text, listed = " ".join(description.lower().split()), every()
    for match in (str.__eq__, str.__contains__):
        found = [a for a in listed if match(text, " ".join(a.config.nessie_description.lower().split()))]
        if found:
            return found[0]
    named = [a for a in listed if a.distributor.name.lower() in text]
    return named[0] if len(named) == 1 else None
