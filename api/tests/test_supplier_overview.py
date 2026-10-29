"""GET /overview: the signed-in supplier across its tracked distributors. Every amount is the API's from engine
values; "recovered" counts only amounts with evidence; what needs the admin comes high, medium, low, then oldest."""

from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from api import accounts, auth, disputes, pipeline, supplier_overview, tenancy, users
from api.agents import claude as claude_mod
from api.contracts import NeedsYou, OverviewLink
from api.integrations import replay
from api.tests.test_disputes import PortalClaude, finished_march


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setenv("CLAWBACK_STATE_DIR", str(tmp_path / "state"))  # nothing untracked from another test
    pipeline.reset(), disputes.reset(), auth.reset(), users.reset()
    yield
    pipeline.reset(), disputes.reset(), auth.reset(), users.reset()


def test_recovered_is_zero_with_no_agreement_and_disputed_awaits_reply():
    fake = PortalClaude()
    finished_march(fake)
    o = supplier_overview.overview(tenancy.EVERYONE)
    t = o.totals
    assert (t.taken, t.disputed, t.fair, t.waiting) == (D(6850), D(4120), D(2730), D(0))
    assert (t.recovered, t.disputed_awaiting_reply, t.evidence) == (D(0), D(4120), [])
    (d,) = o.open_disputes
    assert (d.dispute_id, d.amount, d.status, d.days_left) == ("D-0417", D(4120), "ready_to_send", 90)
    assert str(d.file_by) == "2026-07-19"  # the deal's dispute window: the question's "Dispute window" detail


def test_the_signed_amendment_is_a_concession_not_a_recovery():
    """Clawback withdrew $1,000 of C4 because Northmart proved it: that money moved to fair, nothing came back."""
    fake = PortalClaude()
    finished_march(fake)
    disputes.post("D-0417", "The cap was raised to 6,000 units. Signed amendment attached.",
                  attachment_doc_id="amendment-1", client=fake)
    t = supplier_overview.overview(tenancy.EVERYONE).totals
    assert (t.disputed, t.fair, t.recovered, t.disputed_awaiting_reply) == (D(3120), D(3730), D(0), D(3120))


def test_northmarts_agreement_on_mint_is_1000_recovered_with_its_evidence():
    fake = PortalClaude()
    run = finished_march(fake)
    theirs, _ = disputes.post("D-0417", "Agreed, Mint wasn't part of the Spring promo. We'll credit the Mint "
                                        "deduction back.", client=fake)
    t = supplier_overview.overview(tenancy.EVERYONE).totals
    assert (t.recovered, t.disputed_awaiting_reply) == (D(1000), D(3120))
    (ev,) = t.evidence
    assert (ev.dispute_id, ev.message_id, ev.charge_id, ev.amount) == ("D-0417", theirs.id, "C5", D(1000))
    disputes.post("D-0417", "Agreed, Mint wasn't part of the Spring promo.", client=fake)  # said twice: counted once
    assert supplier_overview.overview(tenancy.EVERYONE).totals.recovered == D(1000)
    from api.routes.accounts import account_overview

    assert account_overview(run.account.id, tenancy.EVERYONE).kpis.disputed_awaiting_reply == D(3120)


def test_needs_you_is_high_medium_low_then_oldest():
    fake = PortalClaude()
    run = finished_march(fake)
    items = supplier_overview.overview(tenancy.EVERYONE).needs_you
    kinds = [(n.kind, n.risk_level) for n in items]
    # the $4,120 dispute email (high, filed first), the $2,730 memo approval (high, later); no open question left
    assert kinds == [("dispute_email", "high"), ("approval", "high")]
    assert items[0].link == OverviewLink(page="dispute", run_id=run.id, dispute_id="D-0417")
    assert items[0].amount == D(4120) and items[0].title == "Your $4,120 dispute to Northmart is ready to send"

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    mk = lambda lvl, mins: NeedsYou(kind="question", account_id="peak-bar", distributor="Northmart", title=lvl,  # noqa: E731
                                    risk_level=lvl, since=now - timedelta(minutes=mins), link=OverviewLink(page="run"))
    jumbled = [mk("low", 50), mk("high", 1), mk("medium", 9), mk("high", 30)]
    order = sorted(jumbled, key=lambda n: (supplier_overview.RANK[n.risk_level], n.since.replace(tzinfo=None)))
    assert [(n.risk_level, n.since) for n in order] == [("high", now - timedelta(minutes=30)),
                                                        ("high", now - timedelta(minutes=1)),
                                                        ("medium", now - timedelta(minutes=9)),
                                                        ("low", now - timedelta(minutes=50))]


def test_an_open_question_is_listed_with_its_risk():
    from api.tests.test_pipeline import ScenarioClaude

    run = pipeline.start("march", ScenarioClaude(), background=False)
    (q,) = [n for n in supplier_overview.overview(tenancy.EVERYONE).needs_you if n.kind == "question"]
    assert (q.risk_level, q.amount, q.link.page, q.link.run_id) == ("high", D(1200), "question", run.id)
    assert q.title == "Northmart kept $1,200 for “Display fee (notice Mar 11)”. Is that fair?"
    assert q.detail.startswith("$1,200 display fee rests on §5.4")  # the why, on its own line
    # answerable where it's shown: its question id and the same one-tap choices as the app and the weekly summary
    assert q.target_id in run.questions
    assert [(c.label, c.rule) for c in q.choices] == [("Accept when notice is at least 14 days", True),
                                                      ("Accept this one", False), ("Dispute this one", False)]


def test_recent_lists_the_run_and_the_reply():
    fake = PortalClaude()
    finished_march(fake)
    disputes.post("D-0417", "There was no unit cap on the Spring promo.", client=fake)
    recent = supplier_overview.overview(tenancy.EVERYONE).recent
    assert recent[0].kind == "reply" and recent[0].link.dispute_id == "D-0417"
    assert any(r.kind == "run_decided" for r in recent) and len(recent) <= 8


def test_overview_is_scoped_to_the_supplier_and_401_signed_out(monkeypatch):
    from api.main import app

    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", "lantern-hill"})
    accounts.clear()
    monkeypatch.setenv("DEMO_USER_PASSWORD", "p1")
    monkeypatch.setenv("DEMO_USER2_PASSWORD", "p2")
    users.reset()
    fake = PortalClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    finished_march(fake)
    assert TestClient(app).get("/overview").status_code == 401
    teresa = TestClient(app)
    teresa.post("/auth/login", json={"email": "teresa@lanternhillsoda.example", "password": "p2"})
    o = teresa.get("/overview").json()
    assert o["supplier"] == "lantern-hill" and o["needs_you"] == [] and o["open_disputes"] == []
    assert o["totals"]["disputed"] == 0.0 and o["recent"] == []
    dana = TestClient(app)
    dana.post("/auth/login", json={"email": "dana@peakbar.example", "password": "p1"})
    o = dana.get("/overview").json()
    assert o["supplier"] == "peak-bar" and o["totals"]["disputed"] == 4120.0 and o["open_disputes"][0]["dispute_id"] == "D-0417"
    assert teresa.get(f"/audit?run_id={pipeline.latest('march').id}").status_code == 404
    assert dana.get(f"/audit?run_id={pipeline.latest('march').id}").json()
    accounts.clear()
