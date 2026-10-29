"""Google Drive as the document source (Phase D, narrow).

The supplier shares one folder with Clawback's service account (GOOGLE_SERVICE_ACCOUNT_JSON: the key's JSON, or a
path to it; DRIVE_ROOT_FOLDER_ID: the shared folder). The layout is the plan's:

    <root>/<Supplier>/<Distributor>/{Contracts, Promotions, Remittances, Correspondence, Sales data}

A supplier folder is named by the supplier's id or brand name ("Peak Bar Co."), a distributor folder by the account's
id or the distributor's name ("Northmart"); each distributor folder is one account.

Watching: a poller (every DRIVE_POLL_SECONDS, 30 by default; DRIVE_POLL=off stops it; never in DEMO_MODE) reads
Drive's Changes API from a saved page token; the first look walks the whole tree. POST /drive/sync is "Sync now".

A new or changed file is downloaded (a Google Doc exported as text) and hashed. Same sha256 as its newest version:
nothing happens. Otherwise a new version is kept (VERSIONS, the document_versions table; old ones never edited):
- Contracts, Promotions, Correspondence: the text is saved under accounts.drive_root() as one of the account's
  documents (accounts.clear() picks it up; the next run's readers read it). A file named like a document the
  account already has (amendment-1.pdf) is that document: data/'s copy stays the original. If the account's newest
  run has an open dispute, the document goes through the portal's logic (api/disputes._new_document): both Deal
  Readers read it; if it can change the deal (signed by both) the engine recomputes and the Negotiator concedes the
  difference, drafted as a reply email for the admin to send (api/dispute_email.py); the admin is told either way.
- Remittances: read by the Payment reader and checked like an upload; lines that add up start the account's run.
- Sales data: kept as a version only (rows aren't read from it yet).

Every Drive call has a 30 s timeout and one retry; with no keys or in DEMO_MODE nothing calls out, and upload stays
the fallback. Documents are data, never instructions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from api import accounts
from api.integrations import replay

log = logging.getLogger("clawback.drive")

TIMEOUT_S = 30
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
KINDS = {"contracts": "deals", "promotions": "deals", "correspondence": "notices", "remittances": "remittances",
         "sales data": "sales", "sales": "sales", "deductions & backup": "notices", "deductions and backup": "notices",
         "deductions": "notices", "orders & shipping": "orders", "orders and shipping": "orders", "orders": "orders"}


def kind_of(folder_name: str) -> str | None:
    """A kind folder's meaning, plain ("Contracts") or numbered the way people keep Drive tidy ("01 Contracts")."""
    return KINDS.get(re.sub(r"^\s*\d+[\s._-]+", "", folder_name).strip().lower())
FIELDS = "id, name, mimeType, modifiedTime, parents, trashed"


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str | None = None
    parents: tuple[str, ...] = ()
    trashed: bool = False

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME


class Client(Protocol):
    def children(self, folder_id: str) -> list[DriveFile]: ...
    def start_token(self) -> str: ...
    def changes(self, token: str) -> tuple[list[tuple[str, bool, DriveFile | None]], str]: ...
    def content(self, f: DriveFile) -> bytes: ...


class NotConfigured(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") and os.getenv("DRIVE_ROOT_FOLDER_ID"))


def root_id() -> str | None:
    return (os.getenv("DRIVE_ROOT_FOLDER_ID") or "").strip() or None


class GoogleClient:
    """google-api-python-client (Drive v3) with a service account; each request 30 s, retried once."""

    def __init__(self):
        import google_auth_httplib2
        import httplib2
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"].strip()
        info = json.loads(raw if raw.startswith("{") else Path(raw).read_text())
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=TIMEOUT_S))
        self.api = build("drive", "v3", http=http, cache_discovery=False)
        self.email = info.get("client_email")

    @staticmethod
    def _file(d: dict) -> DriveFile:
        return DriveFile(d["id"], d.get("name", ""), d.get("mimeType", ""), d.get("modifiedTime"),
                         tuple(d.get("parents") or ()), bool(d.get("trashed")))

    def children(self, folder_id: str) -> list[DriveFile]:
        out, page = [], None
        while True:
            r = self.api.files().list(q=f"'{folder_id}' in parents and trashed = false", fields=f"nextPageToken, files({FIELDS})",
                                      pageSize=1000, pageToken=page, supportsAllDrives=True,
                                      includeItemsFromAllDrives=True).execute(num_retries=1)
            out += [self._file(d) for d in r.get("files", [])]
            page = r.get("nextPageToken")
            if not page:
                return out

    def start_token(self) -> str:
        return self.api.changes().getStartPageToken(supportsAllDrives=True).execute(num_retries=1)["startPageToken"]

    def changes(self, token: str):
        out, page = [], token
        while True:
            r = self.api.changes().list(pageToken=page, includeRemoved=True, spaces="drive", supportsAllDrives=True,
                                        includeItemsFromAllDrives=True, pageSize=1000,
                                        fields=f"nextPageToken, newStartPageToken, changes(fileId, removed, file({FIELDS}))"
                                        ).execute(num_retries=1)
            out += [(c["fileId"], bool(c.get("removed")), self._file(c["file"]) if c.get("file") else None)
                    for c in r.get("changes", [])]
            if r.get("newStartPageToken"):
                return out, r["newStartPageToken"]
            page = r["nextPageToken"]

    def content(self, f: DriveFile) -> bytes:
        if f.mime_type == GOOGLE_DOC:
            return self.api.files().export_media(fileId=f.id, mimeType="text/plain").execute(num_retries=1)
        if f.mime_type == GOOGLE_SHEET:
            return self.api.files().export_media(fileId=f.id, mimeType="text/csv").execute(num_retries=1)
        return self.api.files().get_media(fileId=f.id, supportsAllDrives=True).execute(num_retries=1)


def google_client() -> Client:
    if not configured():
        raise NotConfigured("Google Drive isn't connected (GOOGLE_SERVICE_ACCOUNT_JSON, DRIVE_ROOT_FOLDER_ID)")
    try:
        return GoogleClient()
    except ImportError as e:
        raise NotConfigured(f"the Google client isn't installed ({e.name}); pip install -r api/requirements.txt") from e


# ---------------------------------------------------------------- state

@dataclass
class Version:
    account_id: str
    doc_id: str
    version: int
    sha256: str
    drive_file_id: str
    name: str
    kind: str  # deals | notices | remittances | sales
    modified_time: str | None
    seen_at: datetime


@dataclass
class Status:
    folder_id: str | None = None
    checked_at: datetime | None = None
    changed_at: datetime | None = None
    files: int = 0
    problem: str | None = None
    last: str | None = None  # the newest thing it did, in words
    token: str | None = None
    folders: dict[str, tuple[str, str]] = field(default_factory=dict)  # folder id -> (account id, kind)


VERSIONS: dict[tuple[str, str], list[Version]] = {}  # (account id, drive file id) -> versions, oldest first
STATUS = Status()
_lock = threading.RLock()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def slug(name: str) -> str:
    stem = Path(name).stem if Path(name).suffix.lower() in (".pdf", ".md", ".txt", ".docx", ".csv", ".eml") else name
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "document"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def versions_of(account_id: str, doc_id: str) -> list[Version]:
    with _lock:
        return [v for vs in VERSIONS.values() for v in vs if v.account_id == account_id and v.doc_id == doc_id]


def current_version(account_id: str, doc_id: str) -> Version | None:
    found = versions_of(account_id, doc_id)
    return max(found, key=lambda v: v.version) if found else None


# ---------------------------------------------------------------- the tree

def _account_for(supplier_name: str, distributor_name: str) -> accounts.Account | None:
    for a in accounts.every():
        sid = a.config.supplier or a.id
        home = next((x for x in accounts.every() if x.id == sid), a)
        if _norm(supplier_name) not in {_norm(sid), _norm(home.brand.name), _norm(a.brand.name)}:
            continue
        if _norm(distributor_name) in _names(a, sid):
            return a
    return None


def _names(a: accounts.Account, supplier_id: str) -> set[str]:
    """What a distributor's folder may be called: its name ("KeHE Distributors"), its first word ("KeHE"), the
    account id, or the account id without the supplier's prefix ("kehe" for peak-bar-kehe)."""
    name = a.distributor.name
    short = a.id.removeprefix(f"{supplier_id}-")
    return {_norm(x) for x in (a.id, name, name.split()[0] if name.split() else name, short) if _norm(x)}


def map_folders(client: Client, root: str) -> dict[str, tuple[str, str]]:
    """folder id -> (account id, kind) for every kind folder under <root>/<Supplier>/<Distributor>/."""
    found: dict[str, tuple[str, str]] = {}
    for sup in (f for f in client.children(root) if f.is_folder):
        for dist in (f for f in client.children(sup.id) if f.is_folder):
            a = _account_for(sup.name, dist.name)
            if a is None:
                continue
            for k in (f for f in client.children(dist.id) if f.is_folder):
                if (kind := kind_of(k.name)) is not None:
                    found[k.id] = (a.id, kind)
    return found


# ---------------------------------------------------------------- one file

@dataclass
class Outcome:
    account_id: str
    file: str
    doc_id: str
    version: int
    kind: str
    did: str  # what happened, in words
    run_id: str | None = None


def _is_remittance(f: DriveFile) -> bool:
    """A remittance advice (PDF, text, EDI 820, a payment CSV), not a history or balance export kept beside it."""
    name = f.name.lower()
    if re.search(r"history|prior|balances|lines\.csv", name):
        return False
    return _is_document(f) or name.endswith((".csv", ".edi", ".820"))


def _is_document(f: DriveFile) -> bool:
    """A file the readers can read as a document; spreadsheets and exports are kept as versions."""
    return f.mime_type in (GOOGLE_DOC,) or f.name.lower().endswith((".pdf", ".md", ".txt", ".eml", ".docx"))


def _text(data: bytes, f: DriveFile) -> str:
    if f.name.lower().endswith(".pdf") or data[:4] == b"%PDF":
        from api import remittance

        return remittance.extract_text(data, f.name)[0]
    return data.decode("utf-8", "ignore")


def _save_version(v: Version) -> None:
    from api.db import events

    events.write_later("INSERT INTO document_versions (account_id, doc_id, version, sha256, drive_file_id, name, kind, "
                       "modified_time, seen_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                       "ON CONFLICT (account_id, doc_id, version) DO NOTHING",
                       (v.account_id, v.doc_id, v.version, v.sha256, v.drive_file_id, v.name, v.kind,
                        v.modified_time, v.seen_at))


_PAGE = re.compile(r"^\s*(page\s+\d+(\s*(of|/)\s*\d+)?|\d+\s*(of|/)\s*\d+)\s*$", re.IGNORECASE | re.MULTILINE)


def canon(text: str) -> str:
    """Text as words only, for "is this the same document": page numbers, markdown and spacing don't count, so a
    PDF printed from a document matches the document."""
    text = _PAGE.sub(" ", unicodedata.normalize("NFKC", text or ""))  # NFKC: a printed "ﬁ" ligature is "fi"
    return " ".join(re.findall(r"[a-z0-9$%]+", text.lower()))


def same_document(account: accounts.Account, text: str) -> str | None:
    """The account's own document with this text, if it has one."""
    want = canon(text)
    if not want:
        return None
    for doc_id, path in account.docs.items():
        try:
            if canon(path.read_text(errors="ignore")) == want:
                return doc_id
        except OSError:
            continue
    return None


def process(client: Client, f: DriveFile, account_id: str, kind: str, run_client=None,
            background: bool = True, baseline: bool = False) -> Outcome | None:
    """One new or changed file: a new version if its bytes changed, then what its folder means.
    baseline (the first look at a folder): keep the version and its hash only. What was in Drive before Clawback
    looked is history: nothing is read again, no run starts, no AI is called."""
    data = client.content(f)
    sha = hashlib.sha256(data).hexdigest()
    key = (account_id, f.id)
    with _lock:
        before = VERSIONS.get(key, [])
        if before and before[-1].sha256 == sha:
            return None
    account = accounts.get(account_id)
    text = _text(data, f) if not baseline or kind in ("deals", "notices") else ""
    same = same_document(account, text) if kind in ("deals", "notices") else None
    doc_id = same or slug(f.name)
    known = doc_id in account.docs and doc_id not in account.drive  # data/'s copy stays the original
    if not known and kind in ("deals", "notices") and not doc_id.startswith(account.id):
        doc_id = f"drive-{account.id}-{doc_id}"
        known = doc_id in account.docs and doc_id not in account.drive
    v = Version(account_id, doc_id, len(versions_of(account_id, doc_id)) + 1, sha, f.id, f.name, kind,
                f.modified_time, _now())
    with _lock:
        VERSIONS.setdefault(key, []).append(v)
    _save_version(v)
    if baseline:
        why = f"the same as the account's {doc_id}" if same else "kept as it was when Clawback first looked"
        return Outcome(account_id, f.name, doc_id, v.version, kind, f"baseline · {why}")
    text = text or _text(data, f)
    root = accounts.drive_root()
    if root:
        keep = root / account_id / "versions" / f"{doc_id}.v{v.version}.txt"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text(text)
    if kind == "remittances" and not _is_remittance(f):
        return Outcome(account_id, f.name, doc_id, v.version, kind, "kept as a new version")
    if kind == "remittances":
        return _remittance(account, f, text, v, run_client, background)
    if kind == "sales":
        return Outcome(account_id, f.name, doc_id, v.version, kind, "kept as a new version (sales rows aren't read from Drive yet)")
    if kind == "orders" or not _is_document(f):
        return Outcome(account_id, f.name, doc_id, v.version, kind, "kept as a new version")
    if not known:
        if root is None:
            return Outcome(account_id, f.name, doc_id, v.version, kind, "kept as a version; DRIVE_DOCS_DIR isn't set")
        folder = "notices" if kind == "notices" else "deals"
        path = root / account_id / folder / f"{doc_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        accounts.clear()
    did = f"{'Updated' if v.version > 1 else 'Added'} · v{v.version}"
    out = Outcome(account_id, f.name, doc_id, v.version, kind, did)
    out.did += _open_disputes(accounts.get(account_id), doc_id, run_client)
    return out


@dataclass(frozen=True)
class DriveArrival:
    """A remittance found in Drive, as pipeline.start_for_deposit takes it."""

    id: str
    amount: object
    description: str
    sender: str = "google-drive"
    source: str = "drive"


def _remittance(account, f: DriveFile, text: str, v: Version, run_client, background) -> Outcome:
    from api import remittance

    try:
        r = remittance.read(account.id, text, "pdf" if f.name.lower().endswith(".pdf") else "text", client=run_client)
    except Exception as e:  # noqa: BLE001 - noted for a person; upload is the fallback
        return Outcome(account.id, f.name, v.doc_id, v.version, "remittances", f"couldn't be read ({type(e).__name__})")
    if not r.can_run:
        why = r.problems[0].text if r.problems else "its lines don't add up"
        return Outcome(account.id, f.name, v.doc_id, v.version, "remittances", f"read, no run: {why}")
    paid = r.totals.paid if r.totals and r.totals.paid is not None else account.invoice.received
    run = remittance.start_with_charges(account.id, r.charges, run_client, background,
                                        arrival=DriveArrival(f"drive-{f.id}-{v.sha256[:8]}", paid,
                                                             f"Google Drive: {f.name}"))
    return Outcome(account.id, f.name, v.doc_id, v.version, "remittances", f"started run {run.id}", run.id)


def _open_disputes(account, doc_id: str, run_client) -> str:
    """A document that may change a term an open dispute depends on: the portal's logic, the answer drafted for the
    admin, and the admin told."""
    from api import dispute_email, disputes, pipeline, trace

    run = pipeline.latest(account=account)
    if run is None:
        return ""
    open_ = [d for i in dict.fromkeys(e.data.id for e in run.events if e.type == "dispute")
             if (d := dispute_email.latest(run, i)) and d.status not in ("withdrawn", "resolved")]
    if not open_ or doc_id in {t.source_doc_id for t in run.terms}:  # nothing open, or a document it already read
        return ""
    from api import documents

    try:
        with accounts.using(account):
            kind = documents.load(doc_id)[0].kind
    except Exception:  # noqa: BLE001 - a document that can't be loaded can't change a dispute
        return ""
    if kind != "amendment":  # only a signed amendment changes the deal under an open dispute; the rest wait for a run
        return ""
    run.account = account  # the reloaded account, which has the new document
    dispute = open_[-1]
    before = dispute.total
    with accounts.using(account), trace.run_context(run.id):
        draft = dispute_email._reply_deliverer([], None)
        sent = dispute.status not in ("ready_to_send", "draft")
        # A sent dispute: only a concession goes to the distributor (as a draft for the admin); "it changes nothing"
        # stays in the app. An unsent one: nothing to answer; its email is redrafted with the new lines below.
        disputes._new_document(run, dispute, doc_id, run_client,
                               lambda r, d, text, cids, eids: draft(r, d, text, cids, eids) if cids and sent else None,
                               keep_status=not sent)
    if not sent:
        dispute_email.forget_draft(run, dispute.id)
    now = dispute_email.latest(run, dispute.id)
    if now and now.total != before:
        text = (f"A new document in Google Drive changes your dispute with {run.distributor}: it now totals "
                f"${now.total:,.0f}. The answer to them is drafted for you to send.")
    else:
        text = (f"A new document in Google Drive was checked against your dispute with {run.distributor}: it changes "
                "nothing.")
    dispute_email.notify(run, dispute.id, text)
    return f"; {dispute.id} {'recomputed' if now and now.total != before else 'unchanged'}"


# ---------------------------------------------------------------- syncing

@dataclass
class SyncResult:
    ok: bool
    detail: str
    outcomes: list[Outcome] = field(default_factory=list)


def sync(client: Client | None = None, full: bool = False, run_client=None, background: bool = True) -> SyncResult:
    """One look: the whole tree the first time (or with full), else Drive's changes since the saved token."""
    if replay.demo_mode() and client is None:
        return SyncResult(False, "DEMO_MODE: Drive isn't called; upload documents instead")
    try:
        client = client or google_client()
    except NotConfigured as e:
        return SyncResult(False, str(e))
    root = root_id()
    if root is None:
        return SyncResult(False, "DRIVE_ROOT_FOLDER_ID isn't set")
    outcomes: list[Outcome] = []
    with _lock:
        try:
            first = STATUS.token is None or STATUS.folder_id != root
            if full or first:
                token = client.start_token()  # first, so nothing that changes during the walk is missed
                STATUS.folders, STATUS.folder_id = map_folders(client, root), root
                todo = [(f, *STATUS.folders[fid]) for fid in STATUS.folders for f in client.children(fid)
                        if not f.is_folder]
            else:
                changes, token = client.changes(STATUS.token)
                todo = []
                for _, removed, f in changes:
                    if removed or f is None or f.trashed:
                        continue
                    if f.is_folder or not any(p in STATUS.folders for p in f.parents):
                        if f.is_folder or f.parents:
                            STATUS.folders = map_folders(client, root)  # a new or moved folder
                        if f.is_folder:
                            continue
                    parent = next((p for p in f.parents if p in STATUS.folders), None)
                    if parent:
                        todo.append((f, *STATUS.folders[parent]))
            for f, account_id, kind in todo:
                try:
                    if (o := process(client, f, account_id, kind, run_client, background, baseline=first)) is not None:
                        outcomes.append(o)
                except Exception as e:  # noqa: BLE001 - one file that fails doesn't stop the others
                    log.warning("drive: %s failed (%s)", f.name, type(e).__name__)
                    outcomes.append(Outcome(account_id, f.name, slug(f.name), 0, kind, f"failed ({type(e).__name__})"))
            STATUS.token = token
            STATUS.checked_at = _now()
            STATUS.files = sum(1 for vs in VERSIONS.values() if vs)
            STATUS.problem = None
            if outcomes:
                STATUS.changed_at = STATUS.checked_at
                STATUS.last = f"{outcomes[-1].file}: {outcomes[-1].did}"
        except Exception as e:  # noqa: BLE001 - the next look tries again
            STATUS.checked_at, STATUS.problem = _now(), f"{type(e).__name__}: {str(e)[:200]}"
            return SyncResult(False, STATUS.problem)
    return SyncResult(True, f"{len(outcomes)} change(s)", outcomes)


class Poller:
    def __init__(self, every: float):
        self.every, self._stop = every, threading.Event()
        self.thread = threading.Thread(target=self._loop, name="drive-poller", daemon=True)

    def _loop(self) -> None:
        first = True
        while not self._stop.wait(0 if first else self.every):
            first = False
            sync()

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return self.thread.is_alive()


poller: Poller | None = None


def start_poller() -> bool:
    global poller
    if not configured() or replay.demo_mode() or os.getenv("DRIVE_POLL", "on").lower() == "off":
        return False
    poller = Poller(float(os.getenv("DRIVE_POLL_SECONDS") or 30))
    poller.start()
    return True


def reset() -> None:
    global STATUS
    with _lock:
        VERSIONS.clear()
        STATUS = Status()
