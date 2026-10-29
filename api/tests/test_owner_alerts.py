"""The owner hears about the work the agents do in the background: an email when a payment's check finishes
(api/alerts.py), Home's "Done for you" with what can be taken back (supplier_overview.done_for_you, POST
/autopilot/undo), and the setup checklist for a new company (api/onboarding.py, GET /setup)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api import accounts, alerts, autopilot, digest, disputes, pipeline, suppliers
from api.routes import payments

PEAK = suppliers.supplier_of(accounts.get(accounts.DEFAULT))


@pytest.fixture(autouse=True)
def _demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clawback.test")
    pipeline.reset(), disputes.reset(), payments.reset()
    yield
    pipeline.reset(), disputes.reset(), payments.reset()


@pytest.fixture
def api():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def mailbox(monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "deliver", lambda to, subject, text, html: sent.append((to, subject, text)) or ("sent", "ok"))
    return sent


def test_a_checked_payment_emails_the_owner_once_with_one_tap_answers(mailbox):
    autopilot.update(PEAK, "Dana Okafor", digest_email="owner@example.com")
    run = pipeline.start("march", background=False)
    mine = [m for m in mailbox if "Northmart" in m[1]]
    assert len(mine) == 1
    to, subject, text = mine[0]
    assert to == "owner@example.com"
    assert subject.startswith("Northmart’s payment is checked: $4,120.00 to get back")
    assert "Accept this one: https://clawback.test/api/tap/" in text  # the display-fee question, answerable from the mail
    assert f"run={run.id}" in text
    assert alerts.SENT[run.id].status == "sent"
    assert any("Emailed Dana that the check is done" in e.data.text for e in run.events if e.type == "log")
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")  # the run finishes now
    assert len([m for m in mailbox if "Northmart" in m[1]]) == 1  # no second email for the same payment


def test_no_address_or_turned_off_sends_nothing(mailbox):
    run = pipeline.start("march", background=False)
    assert mailbox == [] and alerts.SENT[run.id].status == "off"
    pipeline.reset()
    autopilot.update(PEAK, None, digest_email="owner@example.com", alert_on_check=False)
    pipeline.start("march", background=False)
    assert mailbox == []


def test_without_gmail_the_run_says_why():
    autopilot.update(PEAK, None, digest_email="owner@example.com")
    run = pipeline.start("march", background=False)  # DEMO_MODE: nothing is emailed
    assert alerts.SENT[run.id].status == "not_sent"
    assert any("Didn't email Dana that the check is done" in e.data.text for e in run.events if e.type == "log")


def test_done_for_you_shows_what_went_without_asking_and_undo_stops_the_next(api):
    autopilot.update(PEAK, "Dana Okafor", send_disputes_under=Decimal("5000"), post_fair_under=Decimal("5000"))
    run = pipeline.start("march", background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    done = api.get("/overview").json()["done_for_you"]
    kinds = {d["kind"]: d for d in done if d["distributor"] == "Northmart"}
    assert "rule_applied" not in kinds  # the display fee: the owner answered it, so it wasn't done without asking
    assert kinds["dispute_sent"]["text"] == "Sent your $4,120 dispute to Northmart"
    assert kinds["dispute_sent"]["why"] == "Under the $5,000 limit you set in Settings"
    assert kinds["dispute_sent"]["undo"]["kind"] == "disputes"
    assert kinds["memo_posted"]["text"] == "Sent $2,730 of Northmart’s fair charges to QuickBooks"
    assert kinds["memo_posted"]["undo"]["kind"] == "memos_settings"

    assert api.post("/autopilot/undo", json={"kind": "disputes"}).status_code == 200
    assert autopilot.get(PEAK).send_disputes_under is None
    after = {d["kind"]: d for d in api.get("/overview").json()["done_for_you"] if d["distributor"] == "Northmart"}
    assert after["dispute_sent"]["undo"] is None  # it stays in the list: it was sent; nothing left to take back
    assert api.post("/autopilot/undo", json={"kind": "memos_settings"}).status_code == 200
    assert autopilot.get(PEAK).post_fair_under is None


def test_a_rule_applied_on_its_own_can_be_undone_from_home(api):
    run = pipeline.start("march", background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    pipeline.start("april", background=False)  # both April fees decided by Rule #1, no question
    done = [d for d in api.get("/overview").json()["done_for_you"] if d["kind"] == "rule_applied"]
    assert len(done) == 2 and all(d["why"].startswith("By Rule #1") for d in done)
    undo = done[0]["undo"]
    assert undo["kind"] == "rule" and undo["label"] == "Undo Rule #1"
    r = api.post("/autopilot/undo", json={k: undo[k] for k in ("kind", "account_id", "rule_id")})
    assert r.status_code == 200 and "Rule #1 is undone" in r.json()["done"]
    assert all(d["undo"] is None for d in api.get("/overview").json()["done_for_you"] if d["kind"] == "rule_applied")
    assert api.post("/autopilot/undo", json={k: undo[k] for k in ("kind", "account_id", "rule_id")}).status_code == 409


def test_an_account_limit_set_on_approval_can_be_turned_off(api):
    run = pipeline.start("march", background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    approval = next(e.data for e in run.events if e.type == "approval")
    pipeline.decide_approval(approval.id, True, None, auto_post=True)
    assert "peak-bar" in pipeline.AUTO_POST
    r = api.post("/autopilot/undo", json={"kind": "memos_account", "account_id": "peak-bar"})
    assert r.status_code == 200 and "peak-bar" not in pipeline.AUTO_POST
    assert api.post("/autopilot/undo", json={"kind": "memos_account", "account_id": "peak-bar"}).status_code == 409


def test_setup_checklist_counts_only_what_can_be_done_here(api):
    s = api.get("/setup").json()
    by = {x["id"]: x for x in s["steps"]}
    assert by["distributor"]["state"] == "done" and by["contract"]["state"] == "done"
    assert by["books"]["state"] == "demo" and by["payments"]["state"] == "demo"  # DEMO_MODE: simulated, not nagged
    assert by["alerts"]["state"] == "todo" and s["left"] == 1
    api.put("/settings/autopilot", json={"digest_email": "owner@example.com"})
    s = api.get("/setup").json()
    assert s["left"] == 0 and "owner@example.com" in next(x for x in s["steps"] if x["id"] == "alerts")["detail"]
