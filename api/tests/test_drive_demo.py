"""Google Drive for the live demo, against the real prepared folder (data/drive/Peak Bar Co/) through a fake Drive:
numbered folders and distributor names map to accounts; the first look is a baseline that reads nothing and starts
nothing (every read and run is a paid AI call on the live server); then the signed amendment, dropped into
Northmart's Contracts as a PDF, is matched to amendment-1 and concedes $1,000 on D-0417."""

import hashlib
from decimal import Decimal as D
from pathlib import Path

import pytest
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from api import accounts, dispute_email, disputes, drive, pipeline
from api.agents import claude as claude_mod
from api.tests.test_pipeline import final, last_totals

FOLDER = Path(__file__).resolve().parents[2] / "data" / "drive"


class DiskDrive:
    """data/drive/ as a Drive: folders and files with stable ids; put() adds a file later, as a Changes entry."""

    def __init__(self, base: Path = FOLDER):
        self.files: dict[str, drive.DriveFile] = {}
        self.data: dict[str, bytes] = {}
        self.pending: list = []
        self.tokens = 0
        self._walk(base, "root")

    def _id(self, path: Path) -> str:
        return hashlib.sha1(str(path).encode()).hexdigest()[:12]

    def _walk(self, folder: Path, parent: str):
        for p in sorted(folder.iterdir()):
            fid = self._id(p)
            if p.is_dir():
                self.files[fid] = drive.DriveFile(fid, p.name, drive.FOLDER_MIME, None, (parent,))
                self._walk(p, fid)
            else:
                self.files[fid] = drive.DriveFile(fid, p.name, "application/octet-stream", "2026-10-24T00:00:00Z",
                                                  (parent,))
                self.data[fid] = p.read_bytes()

    def folder_id(self, *names: str) -> str:
        parent = "root"
        for n in names:
            parent = next(f.id for f in self.files.values() if f.name == n and parent in f.parents)
        return parent

    def put(self, name: str, parent: str, data: bytes) -> drive.DriveFile:
        f = drive.DriveFile(f"new-{len(self.pending)}", name, "application/pdf", "2026-10-25T09:00:00Z", (parent,))
        self.files[f.id], self.data[f.id] = f, data
        self.pending.append((f.id, False, f))
        return f

    def children(self, folder_id):
        return [f for f in self.files.values() if folder_id in f.parents]

    def start_token(self):
        self.tokens += 1
        return f"t{self.tokens}"

    def changes(self, token):
        out, self.pending = self.pending, []
        self.tokens += 1
        return out, f"t{self.tokens}"

    def content(self, f):
        return self.data[f.id]


@pytest.fixture
def every(monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "ONLY", None)
    monkeypatch.setenv("DRIVE_ROOT_FOLDER_ID", "root")
    monkeypatch.setenv("DRIVE_DOCS_DIR", str(tmp_path / "drive"))
    accounts.clear(), drive.reset(), pipeline.reset(), disputes.reset()
    yield
    accounts.clear(), drive.reset(), pipeline.reset(), disputes.reset()


def test_numbered_folders_and_distributor_names_map_to_accounts(every):
    fake = DiskDrive()
    mapped = drive.map_folders(fake, "root")
    by_account = {}
    for fid, (aid, kind) in mapped.items():
        by_account.setdefault(aid, {})[fake.files[fid].name] = kind
    assert set(by_account) == {"peak-bar", "peak-bar-kehe", "peak-bar-walmart", "peak-bar-five-below",
                               "peak-bar-unfi", "peak-bar-sams"}
    assert by_account["peak-bar"] == {"01 Contracts": "deals", "02 Promotions": "deals", "03 Remittances": "remittances",
                                      "04 Deductions & backup": "notices", "05 Correspondence": "notices",
                                      "06 Sales data": "sales", "07 Orders & shipping": "orders"}
    assert drive.kind_of("Contracts") == "deals" and drive.kind_of("_Company") is None


def test_the_first_look_at_the_whole_folder_calls_no_ai_and_starts_no_run(every, monkeypatch):
    calls, runs = [], []
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: calls.append(a[0]))
    monkeypatch.setattr(pipeline, "start", lambda *a, **k: runs.append(a))
    from api import remittance

    monkeypatch.setattr(remittance, "read", lambda *a, **k: calls.append("remittance"))
    fake = DiskDrive()
    files = sum(1 for f in fake.files.values() if not f.is_folder)
    result = drive.sync(fake)
    assert result.ok and calls == [] and runs == []
    mapped = [o for o in result.outcomes]
    assert len(mapped) == files - 3  # every file but _Company's two and the folder's README
    assert all(o.did.startswith("baseline") for o in mapped)
    same = {o.doc_id for o in mapped if "the same as the account's" in o.did}
    assert {"spring-promo", "amendment-1", "broker-2026-03-28", "northmart-2026-03-30"} <= same
    assert drive.sync(fake).outcomes == []  # nothing changed since
    assert accounts.get("peak-bar").drive == ()  # nothing was added as a new document


def _pdf(text: str) -> bytes:
    """A printed version of a document: wrapped lines, a heading face, page numbers."""
    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.splitlines():
        line = line.replace("—", "-").replace("–", "-").replace("’", "'").replace("“", '"').replace("”", '"')
        line = line.replace("§", "Sec. ").encode("latin-1", "replace").decode("latin-1") if False else \
            line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 5, line or " ", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(-15)
    pdf.cell(0, 5, f"Page {pdf.page_no()} of 1", align="C")
    return bytes(pdf.output())


def test_the_demo_drop_amendment_pdf_concedes_1000_on_d0417(every, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")  # the run and the readers replay their recordings in the test
    from api.tests.test_dispute_email import EmailClaude  # noqa: F401 - the recordings answer; no fake needed

    run = pipeline.start("march", account=accounts.get("peak-bar"), background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    fake = DiskDrive()
    drive.sync(fake)  # the baseline
    text = accounts.get("peak-bar").docs["amendment-1"].read_text()
    pdf = _pdf(text)
    assert drive.same_document(accounts.get("peak-bar"), drive._text(pdf, drive.DriveFile("x", "a.pdf", "application/pdf")))
    fake.put("Northmart amendment 1 - signed.pdf", fake.folder_id("Peak Bar Co", "Northmart", "01 Contracts"), pdf)
    (o,) = drive.sync(fake).outcomes
    # the folder already had amendment-1's text (v1, the baseline); the signed PDF is its second version
    assert (o.account_id, o.doc_id, o.version, o.did.split(";")[0]) == ("peak-bar", "amendment-1", 2, "Updated · v2")
    assert "D-0417 recomputed" in o.did
    assert final(run)["C4"] == ("split", D(540), D(1000))
    t = last_totals(run)
    assert (t.disputed, t.accepted) == (D(3120), D(3730))
    d = dispute_email.latest(run, "D-0417")
    assert d.total == D(3120) and d.status == "ready_to_send"  # not sent yet: its email is redrafted
    assert any("changes your dispute with Northmart: it now totals $3,120" in n.text for n in dispute_email.notifications())
    lib = {x.id: x for x in __import__("api.library", fromlist=["library"]).library(accounts.get("peak-bar")).documents}
    assert lib["amendment-1"].version == 2 and lib["amendment-1"].source == "drive" and lib["amendment-1"].locked
