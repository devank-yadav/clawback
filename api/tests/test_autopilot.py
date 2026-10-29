"""The owner's autopilot (api/autopilot.py), Settings (api/routes/settings.py) and the weekly summary with one-tap
answers (api/digest.py): a received payment starts the agents at once; the limits set once post fair memos and send
disputes without asking; the summary's links answer exactly one thing, once, after a confirm."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api import accounts, autopilot, digest, dispute_email, disputes, pipeline, suppliers, tenancy
from api.engine import policy as eng_policy
from api.routes import payments

PEAK = suppliers.supplier_of(accounts.get(accounts.DEFAULT))


@pytest.fixture(autouse=True)
def _demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")  # runs replay their recordings
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clawback.test")
    pipeline.reset(), disputes.reset(), payments.reset()
    yield
    pipeline.reset(), disputes.reset(), payments.reset()


@pytest.fixture
def api():
    from api.main import app

    return TestClient(app)


def test_settings_start_safe_and_persist(api):
    s = api.get("/settings/autopilot").json()
    assert s["run_on_arrival"] is True and s["send_disputes_under"] is None and s["post_fair_under"] is None
    out = api.put("/settings/autopilot", json={"post_fair_under": 1000, "digest_email": "owner@example.com"}).json()
    assert Decimal(str(out["post_fair_under"])) == 1000 and out["digest_email"] == "owner@example.com"
    assert autopilot.get(PEAK).post_fair_under == 1000  # saved to the state folder
    cleared = api.put("/settings/autopilot", json={"clear": ["post_fair_under"]}).json()
    assert cleared["post_fair_under"] is None and cleared["digest_email"] == "owner@example.com"


@pytest.mark.parametrize("body", [{"post_fair_under": 0}, {"send_disputes_under": -5}, {"digest_email": "not an email"},
                                  {"clear": ["run_on_arrival"]}])
def test_settings_refuse_bad_values(api, body):
    assert api.put("/settings/autopilot", json=body).status_code == 422


def test_a_received_payment_starts_the_agents_at_once(api):
    import time

    sent = api.post("/portal/payments/peak-bar").json()
    assert sent["run_id"] and sent["run_id"] in pipeline.RUNS
    assert api.get("/payments/pending").json() == []  # nothing waits for "Run the agents"
    assert api.post("/payments/sync").json()["found"] == []  # the check never makes a payment up
    end = time.monotonic() + 60  # let the runs it started finish before the next test
    while time.monotonic() < end and not all(r.done or any(e.type == "run" and e.data.status in ("waiting", "finished", "failed")
                                                           for e in r.events) for r in pipeline.RUNS.values()):
        time.sleep(0.1)


def test_the_owners_limit_posts_fair_memos_without_asking():
    assert pipeline.auto_post_of("peak-bar", eng_policy.load_policy()) is None
    autopilot.update(PEAK, "Dana Okafor", post_fair_under=Decimal("5000"))
    standing = pipeline.auto_post_of("peak-bar", eng_policy.load_policy())
    assert standing.limit == 5000 and standing.set_by == "Dana Okafor" and standing.approval_id == "settings"


def test_the_owners_limit_sends_disputes_within_it(monkeypatch):
    autopilot.update(PEAK, "Dana Okafor", send_disputes_under=Decimal("5000"))
    sent = []
    monkeypatch.setattr(dispute_email, "send_dispute", lambda r, d, by: sent.append((r.id, d.id, by)))
    run = pipeline.start("march", background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    # $4,120 is under the owner's $5,000: sent once, with no review step (other tests' runs may still be finishing)
    assert [(d, by) for r, d, by in sent if r == run.id] == [("D-0417", "policy")]
    assert autopilot.sends_dispute(accounts.get("peak-bar"), Decimal("4120"))
    assert not autopilot.sends_dispute(accounts.get("peak-bar"), Decimal("5000.01"))


def test_the_summary_answers_a_question_in_one_tap_once(api):
    run = pipeline.start("march", background=False)
    d = digest.build(tenancy.Caller(supplier_id=PEAK))
    item = next(i for i in d.items if i.actions)
    labels = [a.label for a in item.actions]
    assert labels == ["Accept when notice is at least 14 days", "Accept this one", "Dispute this one"]
    assert d.subject.startswith("Clawback: $") and "being disputed" in d.subject
    url = item.actions[0].url
    assert url.startswith("https://clawback.test/api/tap/")
    token = url.rsplit("/", 1)[1]
    page = api.get(f"/tap/{token}")
    assert page.status_code == 200 and "Accept when notice is at least 14 days?" in page.text
    q = next(iter(run.questions.values()))
    assert pipeline.is_open(q)  # opening the link changes nothing
    done = api.post(f"/tap/{token}").text
    assert "Done" in done and "Saved as a rule" in done
    assert not pipeline.is_open(run.questions[q.id])
    again = api.post(f"/tap/{token}").text
    assert "Already answered" in again


def test_a_tampered_or_expired_link_does_nothing(api, monkeypatch):
    token = digest.sign({"k": "q", "id": "nope", "t": "dispute it", "r": False})
    body, sig = token.rsplit(".", 1)
    assert "expired" in api.get(f"/tap/{body}.{'0' * len(sig)}").text
    monkeypatch.setattr(digest, "TOKEN_DAYS", -1)
    old = digest.sign({"k": "q", "id": "nope", "t": "x", "r": False})
    assert "expired" in api.post(f"/tap/{old}").text


def test_the_memo_link_approves_once(api):
    run = pipeline.start("march", background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days")
    d = digest.build(tenancy.Caller(supplier_id=PEAK))
    memo = next(i for i in d.items if i.actions and i.actions[0].label == "Send $2,730 to QuickBooks")
    token = memo.actions[0].url.rsplit("/", 1)[1]
    assert "Sent to QuickBooks" in api.post(f"/tap/{token}").text
    assert "Already decided" in api.post(f"/tap/{token}").text


def test_send_needs_an_address_and_gmail(api):
    assert digest.send(tenancy.Caller(supplier_id=PEAK)).status == "not_sent"
    autopilot.update(PEAK, None, digest_email="owner@example.com")
    out = digest.send(tenancy.Caller(supplier_id=PEAK))
    assert out.status == "not_sent" and out.to == "owner@example.com"  # DEMO_MODE: nothing leaves


def test_the_weekly_loop_sends_on_monday_once(monkeypatch):
    autopilot.update(PEAK, None, digest_email="owner@example.com")
    calls = []
    monkeypatch.setattr(digest, "send", lambda who: calls.append(who.supplier_id) or digest.DigestSent(status="sent", to="owner@example.com", detail="", subject=""))
    monday = datetime(2026, 11, 2, 16, tzinfo=timezone.utc)
    assert digest.tick(monday) == [PEAK]
    autopilot.update(PEAK, None, digest_last_sent=monday)
    assert digest.tick(monday) == []  # not twice in one week
    assert digest.tick(datetime(2026, 11, 3, 16, tzinfo=timezone.utc)) == []  # Tuesday: no


def test_a_fee_with_no_notice_gets_no_notice_rule_and_an_honest_tap(monkeypatch):
    monkeypatch.setattr(accounts, "ONLY", None)  # Peak Bar Co.'s six distributors, Sam's Club among them
    accounts.clear()
    run = pipeline.start(account="peak-bar-sams", background=False)
    q = next(q for q in run.questions.values() if pipeline.is_open(q))
    assert "fee_discretion" in run.allowances[q.charge_id].missing  # the club sampling deal has no verified fee clause
    # so the question doesn't promise a rule it can't make (pipeline leaves the rule label off without a clause)
    assert "becomes a rule" not in q.risk.reason
    assert {d.label: d.value for d in q.details}["What your answer does"] == "Settles this charge only"
    d = digest.build(tenancy.Caller(supplier_id=PEAK))
    item = next(i for i in d.items if i.distributor == "Sam's Club" and i.actions)
    assert [a.label for a in item.actions] == ["Accept this one", "Dispute this one"]
    # an answer that can't become a rule leaves the question open, and the tap page says so
    out = digest.act({"k": "q", "id": q.id, "t": "accept if notice is at least 14 days", "r": True})
    assert not out.ok and "didn’t fit" in out.title and pipeline.is_open(run.questions[q.id])
    assert digest.act({"k": "q", "id": q.id, "t": "dispute it", "r": False}).title == "Done"
    accounts.clear()
