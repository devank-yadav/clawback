"""Phase D: Google Drive as the document source, with a fake Drive client. The first look walks the shared folder;
later looks read the changes since the saved token; a file's versions are kept by sha256; the signed amendment
dropped into Contracts concedes $1,000 on the open dispute; a remittance in Remittances starts a run."""

from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import accounts, dispute_email, disputes, drive, library, pipeline, remittance
from api.integrations import replay
from api.tests.test_dispute_email import EmailClaude
from api.tests.test_disputes import finished_march
from api.tests.test_pipeline import final, last_totals

FOLDER = drive.FOLDER_MIME


class FakeDrive:
    """root/Peak Bar Co./Northmart/{Contracts, Correspondence, Remittances, Sales data}."""

    def __init__(self):
        self.files: dict[str, drive.DriveFile] = {}
        self.data: dict[str, bytes] = {}
        self.pending: list[tuple[str, bool, drive.DriveFile | None]] = []
        self.tokens = 0
        self.folder("sup", "Peak Bar Co.", "root")
        self.folder("dist", "Northmart", "sup")
        self.folder("other", "Somebody Else", "root")
        for fid, name in (("con", "Contracts"), ("cor", "Correspondence"), ("rem", "Remittances"), ("sal", "Sales data")):
            self.folder(fid, name, "dist")

    def folder(self, fid, name, parent):
        self.files[fid] = drive.DriveFile(fid, name, FOLDER, None, (parent,))

    def put(self, fid, name, parent, data: bytes, mime="text/markdown"):
        f = drive.DriveFile(fid, name, mime, f"2026-10-25T0{len(self.pending)}:00:00Z", (parent,))
        self.files[fid], self.data[fid] = f, data
        self.pending.append((fid, False, f))
        return f

    def children(self, folder_id):
        return [f for f in self.files.values() if folder_id in f.parents]

    def start_token(self):
        self.tokens += 1
        self.pending.clear()  # changes before the start token are covered by the walk
        return f"t{self.tokens}"

    def changes(self, token):
        out, self.pending = self.pending, []
        self.tokens += 1
        return out, f"t{self.tokens}"

    def content(self, f):
        return self.data[f.id]


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setenv("DRIVE_ROOT_FOLDER_ID", "root")
    monkeypatch.setenv("DRIVE_DOCS_DIR", str(tmp_path / "drive"))
    monkeypatch.setattr(replay, "FIXTURES", tmp_path / "fixtures")
    pipeline.reset(), disputes.reset(), drive.reset()
    accounts.clear()
    yield
    pipeline.reset(), disputes.reset(), drive.reset()
    accounts.clear()


def test_the_folder_tree_maps_to_accounts():
    fake = FakeDrive()
    assert drive.map_folders(fake, "root") == {"con": ("peak-bar", "deals"), "cor": ("peak-bar", "notices"),
                                               "rem": ("peak-bar", "remittances"), "sal": ("peak-bar", "sales")}


def test_versions_by_sha256_and_changes_since_the_token(tmp_path):
    fake = FakeDrive()
    fake.put("f1", "Store visit notes.md", "cor", b"Week 3 endcap confirmed.")
    first = drive.sync(fake)
    assert first.ok and [(o.doc_id, o.version, o.did) for o in first.outcomes] == [
        ("drive-peak-bar-store-visit-notes", 1, "Added · v1")]
    assert "drive-peak-bar-store-visit-notes" in accounts.get("peak-bar").docs  # one of the account's documents now
    assert (tmp_path / "drive" / "peak-bar" / "notices" / "drive-peak-bar-store-visit-notes.md").read_text() == \
        "Week 3 endcap confirmed."
    assert drive.sync(fake).outcomes == []  # nothing changed
    fake.put("f1", "Store visit notes.md", "cor", b"Week 3 endcap confirmed.")  # touched, same bytes
    assert drive.sync(fake).outcomes == []
    fake.put("f1", "Store visit notes.md", "cor", b"Week 3 endcap confirmed. Week 4 too.")
    (o,) = drive.sync(fake).outcomes
    assert (o.version, o.did) == (2, "Updated · v2")
    assert [v.version for v in drive.versions_of("peak-bar", "drive-peak-bar-store-visit-notes")] == [1, 2]
    assert (tmp_path / "drive" / "peak-bar" / "versions" / "drive-peak-bar-store-visit-notes.v1.txt").is_file()
    lib = {d.id: d for d in library.library(accounts.get("peak-bar")).documents}
    assert (lib["drive-peak-bar-store-visit-notes"].version, lib["drive-peak-bar-store-visit-notes"].source) == (2, "drive")
    assert "Week 4 too." in lib["drive-peak-bar-store-visit-notes"].text


def test_a_file_outside_any_account_folder_is_ignored():
    fake = FakeDrive()
    fake.put("x", "random.md", "other", b"hello")
    assert drive.sync(fake).outcomes == []


def test_the_signed_amendment_dropped_into_contracts_concedes_1000():
    claude = EmailClaude()
    run = finished_march(claude)
    fake = FakeDrive()
    _, e = dispute_email.draft_dispute(run, [e.data for e in run.events if e.type == "dispute"][-1], client=claude)
    dispute_email.mark_sent(e.id)  # the person sent it from Gmail
    drive.sync(fake, run_client=claude)  # the first look: nothing in the folder yet
    text = accounts.get("peak-bar").docs["amendment-1"].read_bytes()
    fake.put("amd", "amendment-1.md", "con", text)
    (o,) = drive.sync(fake, run_client=claude).outcomes
    assert (o.doc_id, o.version) == ("amendment-1", 1) and "D-0417 recomputed" in o.did
    assert final(run)["C4"] == ("split", D(540), D(1000))
    t = last_totals(run)
    assert (t.disputed, t.accepted) == (D(3120), D(3730))
    (reply,) = [e for e in dispute_email.emails_of(run.id, "D-0417") if e.kind == "reply"]
    assert reply.status == "ready" and "withdraw $1,000" in reply.body  # waits for the admin
    assert "now totals $3,120" in dispute_email.notifications()[0].text
    lib = {d.id: d for d in library.library(accounts.get("peak-bar")).documents}
    assert lib["amendment-1"].version == 1 and lib["amendment-1"].locked  # data/'s signed copy stays the original


def test_an_unsent_dispute_is_recomputed_and_its_email_redrafted():
    claude = EmailClaude()
    run = finished_march(claude)
    d = [e.data for e in run.events if e.type == "dispute"][-1]
    assert "$4,120.00" in dispute_email.email_for(run, d, claude).subject
    fake = FakeDrive()
    fake.put("amd", "amendment-1.md", "con", accounts.get("peak-bar").docs["amendment-1"].read_bytes())
    drive.sync(fake, run_client=claude)
    now = dispute_email.latest(run, "D-0417")
    assert (now.total, now.status) == (D(3120), "ready_to_send")  # still the admin's to send
    assert not [e for e in dispute_email.emails_of(run.id, "D-0417") if e.kind == "reply"]
    assert "$3,120.00" in dispute_email.email_for(run, now, claude).subject


def test_a_document_the_run_already_read_changes_nothing():
    claude = EmailClaude()
    run = finished_march(claude)
    fake = FakeDrive()
    fake.put("sp", "spring-promo.md", "con", accounts.get("peak-bar").docs["spring-promo"].read_bytes())
    (o,) = drive.sync(fake, run_client=claude).outcomes
    assert o.did == "Added · v1" and not dispute_email.emails_of(run.id, "D-0417")


def test_a_remittance_in_remittances_starts_a_run(monkeypatch):
    seen = []
    monkeypatch.setattr(remittance, "read", lambda slug, text, kind, client=None: SimpleNamespace(
        can_run=True, charges=["C1"], problems=[], totals=SimpleNamespace(paid=D(41350))))
    monkeypatch.setattr(remittance, "start_with_charges", lambda slug, charges, client, background, arrival:
                        seen.append((slug, charges, arrival)) or SimpleNamespace(id="run-x"))
    fake = FakeDrive()
    fake.put("r1", "Northmart remittance INV-3102.csv", "rem", b"ref,amount\nNM-2229,1800", mime="text/csv")
    (o,) = drive.sync(fake).outcomes
    assert (o.kind, o.run_id, o.did) == ("remittances", "run-x", "started run run-x")
    ((slug, charges, arrival),) = seen
    assert slug == "peak-bar" and arrival.source == "drive" and arrival.amount == D(41350)


def test_without_keys_sync_says_so_and_the_card_says_not_connected(monkeypatch):
    monkeypatch.delenv("DRIVE_ROOT_FOLDER_ID")
    r = drive.sync()
    assert not r.ok and "isn't connected" in r.detail
    card = next(c for c in library.connections() if c.id == "drive")
    assert card.status == "not_connected"


def test_the_card_and_sync_now_route(monkeypatch):
    from api.main import app

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    fake = FakeDrive()
    fake.put("f1", "notes.md", "cor", b"hi")
    monkeypatch.setattr(drive, "google_client", lambda: fake)
    client = TestClient(app)
    r = client.post("/drive/sync").json()
    assert r["ok"] and [c["doc_id"] for c in r["changes"]] == ["drive-peak-bar-notes"]
    card = next(c for c in client.get("/connections").json() if c["id"] == "drive")
    assert card["status"] == "connected" and "last change just now · 1 files" in card["detail"]
    assert client.get("/drive/status").json()["files"] == 1
