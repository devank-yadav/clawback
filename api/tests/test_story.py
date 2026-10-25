"""The history Home opens on (api/story.py), replayed from recordings: fast, free, idempotent, never calling out;
Northmart's March payment is left for "Check for new payments" (POST /payments/sync) to deliver."""

import time
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from api import disputes, dispute_email, pipeline, story, supplier_overview, tenancy
from api.integrations import qbo

PEAK = tenancy.Caller(supplier_id="peak-bar", via="session")


@pytest.fixture
def built(monkeypatch, tmp_path):
    from api import accounts

    monkeypatch.setattr(accounts, "ONLY", None)  # Peak Bar Co.'s six distributors
    accounts.clear()
    monkeypatch.setenv("DEMO_STORY", "on")
    monkeypatch.setenv("CLAWBACK_STATE_DIR", str(tmp_path))
    pipeline.reset(), disputes.reset()
    started = time.monotonic()
    result = story.build()
    yield result, time.monotonic() - started
    pipeline.reset(), disputes.reset()
    accounts.clear()


def test_the_history_is_replayed_quickly_and_once(built):
    result, seconds = built
    assert result["state"] == "built" and seconds < 10
    runs = {r.account.id for r in pipeline.RUNS.values()}
    assert runs == {"peak-bar-kehe", "peak-bar-walmart", "peak-bar-five-below", "peak-bar-unfi", "peak-bar-sams"}
    assert "peak-bar" not in runs  # Northmart's March payment is the live moment
    n = len(pipeline.RUNS)
    assert story.build()["state"] == "built" and len(pipeline.RUNS) == n  # idempotent


def test_home_shows_a_month_of_work(built):
    o = supplier_overview.overview(PEAK)
    t = o.totals
    assert t.taken > 0 and t.disputed > 0 and t.fair > 0
    assert t.recovered == D("420.00")  # UNFI's desk agreed on U5 (Peanut Butter isn't in the MCB deal)
    (ev,) = t.evidence
    assert (ev.dispute_id, ev.charge_id, ev.amount) == ("D-1030", "U5", D("420.00")) and ev.message_id
    kinds = {(n.kind, n.distributor) for n in o.needs_you}
    assert ("question", "Sam's Club") in kinds and ("dispute_email", "Sam's Club") in kinds
    q = next(n for n in o.needs_you if n.kind == "question")
    assert q.risk_level in ("high", "medium") and o.needs_you[0].risk_level == "high"
    sent = {d.dispute_id: d.status for d in o.open_disputes}
    assert sent["D-1030"] == "filed" and sent["D-1040"] == "ready_to_send"
    assert any(r.kind == "reply" for r in o.recent)


def test_the_history_never_touches_the_live_books(built):
    assert isinstance(qbo.books(), qbo.StandInBooks)  # tests have no keys; the point is it isn't the history's
    assert qbo.books() is not qbo._history_books
    posts = [e.data for r in pipeline.RUNS.values() for e in r.events if e.type == "ledger_post"]
    assert posts and all("history" in (p.note or "") for p in posts)
    mails = [e for e in dispute_email.EMAILS.values() if e.kind == "dispute" and e.status == "outbox"]
    assert mails and all("history" in (m.detail or "") for m in mails)


def test_check_for_new_payments_delivers_northmarts_march_payment(built, monkeypatch):
    from api.main import app

    monkeypatch.setenv("DEMO_MODE", "true")  # the run itself replays its recordings in the test
    client = TestClient(app)
    r = client.post("/payments/sync").json()
    (f,) = r["found"]
    assert (f["account_id"], f["distributor"], f["amount"], f["invoice_id"]) == ("peak-bar", "Northmart", 41350.0,
                                                                                 "INV-3102")
    assert f["run_id"] and r["message"] == "Northmart paid $41,350.00 on INV-3102. The agents are checking it."
    assert "demo" not in r["message"].lower() and "test" not in r["message"].lower()
    run = pipeline.RUNS[f["run_id"]]
    for _ in range(200):
        if any(e.type == "question" for e in run.events):
            break
        time.sleep(0.05)
    assert all(e.at for e in run.events)  # every event carries its time, so a finished run replays at its pace
    again = client.post("/payments/sync").json()
    assert again["found"] == [] and again["message"] == "No new payments."
