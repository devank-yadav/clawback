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
    from api import autopilot, suppliers  # these tests follow a payment that waits for "Run the agents"

    autopilot.save(suppliers.supplier_of(accounts.get(accounts.DEFAULT)), autopilot.Autopilot(run_on_arrival=False))
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
    assert runs == {"peak-bar-five-below", "peak-bar-unfi", "peak-bar-sams"}  # the fully recorded ones
    assert "peak-bar" not in runs  # Northmart's March payment is the live moment
    n = len(pipeline.RUNS)
    assert story.build()["state"] == "built" and len(pipeline.RUNS) == n  # idempotent


def test_home_shows_a_month_of_work(built):
    o = supplier_overview.overview(PEAK)
    t = o.totals
    assert t.taken > 0 and t.disputed > 0 and t.fair > 0
    # UNFI's desk accepted U5 with the portal's Accept action (Peanut Butter isn't in the MCB deal).
    assert t.recovered == D("420.00")
    (ev,) = t.evidence
    assert (ev.dispute_id, ev.charge_id, ev.amount) == ("D-1030", "U5", D("420.00")) and ev.message_id
    notes = [n.text for n in dispute_email.notifications()]
    assert "UNFI agreed to pay back $420 of your $2,320 dispute." in notes
    assert any(n.startswith("Sam's Club replied on your $2,283.20 dispute") for n in notes)
    kinds = {(n.kind, n.distributor) for n in o.needs_you}
    assert ("question", "Sam's Club") in kinds and ("reply_email", "Sam's Club") in kinds
    q = next(n for n in o.needs_you if n.kind == "question")
    assert q.risk_level in ("high", "medium") and o.needs_you[0].risk_level == "high"
    sent = {d.dispute_id: d.status for d in o.open_disputes}
    assert sent["D-1030"] == "filed" and sent["D-1040"] == "filed" and sent["D-1020"] == "filed"
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
    assert f["run_id"] is None and r["message"] == "Northmart paid $41,350.00 on INV-3102. New payment received."
    assert "demo" not in r["message"].lower() and "test" not in r["message"].lower()
    (p,) = client.get("/payments/pending").json()  # received, waiting for "Run the agents"
    assert (p["account_id"], p["source"], p["received"]) == ("peak-bar", "bank", 41350.0)
    started = client.post(f"/payments/pending/{p['id']}/run").json()
    assert client.get("/payments/pending").json() == []
    run = pipeline.RUNS[started["run_id"]]
    for _ in range(200):
        if any(e.type == "question" for e in run.events):
            break
        time.sleep(0.05)
    assert all(e.at for e in run.events)  # every event carries its time, so a finished run replays at its pace
    again = client.post("/payments/sync").json()  # the next distributor waiting for its payment, never Northmart twice
    assert [f["account_id"] for f in again["found"]] != ["peak-bar"] and len(again["found"]) == 1


@pytest.mark.parametrize("preset", ["no-cap", "rate", "not-a-repeat", "agree-mint", "amendment"])
def test_every_northmart_preset_replays_and_notifies_on_a_ready_to_send_dispute(preset, monkeypatch):
    """The presenter's "Northmart replies": each preset is answered from the recordings, and the admin is told."""
    from api.main import app

    monkeypatch.setenv("DEMO_MODE", "true")
    pipeline.reset(), disputes.reset()
    run = pipeline.start("march", background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    assert dispute_email.latest(run, "D-0417").status == "ready_to_send"  # replies work before it's emailed
    p = next(x for x in disputes.PRESETS if x.id == preset)
    out = TestClient(app).post("/portal/disputes/D-0417/messages",
                               json={"text": p.text, "attachment_doc_id": p.attachment_doc_id}).json()
    assert [m["from_party"] for m in out] == ["northmart", "clawback"] and out[0]["classification"] == p.expect
    (n,) = dispute_email.notifications()
    assert n.text.startswith("Northmart ") and ("your $4,120 dispute" in n.text or "now totals" in n.text)
    if preset == "amendment":
        assert dispute_email.latest(run, "D-0417").total == D(3120)
    pipeline.reset(), disputes.reset()


def test_the_portal_accept_action_is_read_by_code(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    pipeline.reset(), disputes.reset()
    pipeline.start("march", background=False)
    theirs, ours = disputes.post("D-0417", "Accepted.", agree_charge_ids=["C5", "C9"])
    assert (theirs.classification, theirs.charge_ids) == ("agrees", ["C5"])  # C9 isn't on the dispute
    assert ours.text == "Thank you for accepting NM-2237, $1,000.00 of D-0417."
    assert supplier_overview.overview(tenancy.EVERYONE).totals.recovered == D(1000)
    pipeline.reset(), disputes.reset()


def test_the_story_has_one_closing_window_and_honest_statuses(built):
    from api import suppliers

    o = supplier_overview.overview(PEAK)
    windows = {d.dispute_id: d.days_left for d in o.open_disputes}
    assert windows["D-1020"] == 10 and windows["D-1030"] == 90  # filed 80 days ago; the 90-day window is the deal's
    (peak,) = [s for s in suppliers.items() if s.id == "peak-bar"]
    unfi = next(r for r in peak.distributors if r.account_id == "peak-bar-unfi")
    assert (unfi.status, unfi.status_label) == ("dispute_open", "$2,320 dispute open, waiting for their reply")
    q = next(n for n in o.needs_you if n.kind == "question")
    assert "March" in q.title and "march" not in q.title
    assert all("march" not in r.text for r in o.recent)


def test_no_cap_replays_its_answer_even_before_danas_answer(monkeypatch):
    """The recordings were made after Dana answered C6; the same reply before her answer finds the same recording."""
    monkeypatch.setenv("DEMO_MODE", "true")
    pipeline.reset(), disputes.reset()
    run = pipeline.start("march", background=False)
    assert any(pipeline.is_open(q) for q in run.questions.values())
    p = next(x for x in disputes.PRESETS if x.id == "no-cap")
    theirs, ours = disputes.post("D-0417", p.text)
    assert theirs.classification == "claim_without_document" and "5,000 units" in ours.text
    pipeline.reset(), disputes.reset()


def test_a_payment_summary_keeps_its_own_kept_apart_from_older_charges(built):
    from api import accounts, history

    (fb,) = [r for r in history.runs(accounts.get("peak-bar-five-below")) if not r.replaced]
    # the list showed $6,184.25 "kept" while the payment slip took $5,139.25: an older charge was checked with it
    assert fb.kept == D("5139.25") and fb.older_charges == 1 and fb.taken == D("6184.25")
