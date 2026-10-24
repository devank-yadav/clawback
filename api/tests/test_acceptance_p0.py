"""P0 acceptance tests (docs/design.md, Feature spec) that weren't covered elsewhere, run the way the demo runs:
DEMO_MODE on, recorded answers from data/fixtures, no API key and no network.

The rest of each P0 row's acceptance test lives where the code does; `make acceptance` runs them all together.
If a recorded-answer test fails after a prompt or payload change, re-record with `make record`.
"""

import socket
import time
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api import documents, pipeline
from api.contracts import EventAdapter
from api.engine import gate, quote_check
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy
from api.engine.tests import scenario as s
from api.engine.types import DecisionKind, TermStatus
from api.integrations import replay
from api.main import app
from api.tests.test_reader import RECORDED

D = Decimal
_sleep = time.sleep  # the fixture below turns time.sleep off for the demo pacing


@pytest.fixture(autouse=True)
def _offline_demo_mode(monkeypatch):
    """Wi-Fi off: any socket connect fails, there is no key, and every agent answer comes from data/fixtures."""
    def no_network(*_a, **_k):
        raise AssertionError("DEMO_MODE must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    monkeypatch.setattr(replay.time, "sleep", lambda _s: None)  # skip the demo pacing delay
    pipeline.reset()
    yield
    pipeline.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _wait(run_id: str, status: str) -> pipeline.Run:
    run = pipeline.RUNS[run_id]
    for _ in range(2000):
        if any(e.type == "run" and e.data.status in (status, "failed") for e in run.events):
            break
        _sleep(0.01)
    statuses = [e.data.status for e in run.events if e.type == "run"]
    assert statuses[-1] == status, f"run ended as {statuses[-1]}: {[e.data.text for e in run.events if e.type == 'log'][-1]}"
    return run


def _sse(text: str) -> list:
    return [EventAdapter.validate_json(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def _march(client) -> pipeline.Run:
    run_id = client.post("/runs", json={"kind": "march"}).json()["run_id"]
    return _wait(run_id, "waiting")


# ---------------------------------------------------------------- F2 Deal Reader

def test_f2_every_recorded_quote_is_found_word_for_word_at_its_offsets(client):
    run = _march(client)
    spring = [t for t in run.terms if t.source_doc_id == "spring-promo" and t.status == "verified"]
    assert sorted(t.type for t in spring) == sorted(
        ["promo_rate", "product_scope", "date_range", "unit_cap", "fee_discretion"])  # + the broker amendment = 6
    assert any(t.type == "amendment" and t.status == "verified" for t in run.terms)
    for t in run.terms:
        if t.status != "verified":
            continue
        text = documents.load(t.source_doc_id)[1]
        span = quote_check.normalize(text[t.char_start:t.char_end])
        assert span == quote_check.normalize(t.exact_quote), t.id


# ---------------------------------------------------------------- F4 Investigator

# docs/design.md scenario table, "Evidence" column: what each finding must cite.
F4_EXPECTED = {
    "C1": ("rate_over", {"ev-spring-promo-3.1", "ev-sales-2026-03-01"}),
    "C2": ("duplicate", {"ev-payment-NM-2178", "ev-sales-2026-03-08"}),
    "C3": ("amended_by_email", {"ev-broker-2026-03-28"}),
    "C4": ("over_cap", {"ev-spring-promo-3.2", "ev-sales-2026-03-01", "ev-sales-2026-03-08", "ev-sales-2026-03-15"}),
    "C5": ("product_not_covered", {"ev-spring-promo-3.1", "ev-sales-mint"}),
    "C6": ("discretionary_fee", {"ev-spring-promo-5.4", "ev-display-fee-2026-03-11"}),
}


@pytest.mark.parametrize("cid", sorted(F4_EXPECTED))
def test_f4_findings_cite_the_right_clause_and_rows(client, cid):
    run = _march(client)
    f = run.findings[cid]
    kind, must_cite = F4_EXPECTED[cid]
    assert f.type == kind
    assert must_cite <= set(f.evidence_ids), f"{cid} is missing {must_cite - set(f.evidence_ids)}"
    assert all(i in run.evidence for i in f.evidence_ids)
    assert len(f.finding.split()) <= 25


# ---------------------------------------------------------------- F5 Decision gate

def test_f5_readers_disagreeing_on_a_term_forces_ask():
    """Quote check -> engine -> gate: from the same §3.1 sentence Claude reads both flavours, Gemini only Original."""
    source = documents.load("spring-promo")[1]
    claude = {"type": "product_scope", "params": {"products": [s.ORIG, s.CHOC]}, "exact_quote": s.Q_RATE}
    gemini = {"type": "product_scope", "params": {"products": [s.ORIG]}, "exact_quote": s.Q_RATE}
    assert quote_check.verify_term(source, claude, claude).status == quote_check.VERIFIED
    verdict = quote_check.verify_term(source, claude, gemini)
    assert verdict.status == quote_check.DISPUTED

    terms = [t if t.id != "T-scope" else replace(t, status=TermStatus(verdict.status))
             for t in s.spring_terms()]
    c1 = s.march_charges()["C1"]
    a = compute_allowed(c1, terms, s.store_sales(), s.prior_payments())
    assert a.allowed == D(1200)  # the engine still computes; the gate decides not to act
    d = gate.decide(c1, a, s.strong_finding("C1"), load_policy())
    assert (d.kind, d.gate_row, d.disputed, d.accepted) == (DecisionKind.ASK, 2, 0, 0)


# ---------------------------------------------------------------- F6 Board (API side)

def test_f6_refresh_mid_run_recovers_the_same_state(client):
    run = _march(client)
    url = f"/runs/{run.id}/events"
    full = _sse(client.get(url, params={"keepalive": False}).text)
    cut = len(full) // 2
    first = _sse(client.get(url, params={"keepalive": False, "after": 0}).text)[:cut]
    rest = _sse(client.get(url, headers={"Last-Event-ID": str(first[-1].id)}, params={"keepalive": False}).text)
    assert [e.id for e in first + rest] == [e.id for e in full]
    totals = [e.data for e in first + rest if e.type == "totals"][-1]
    assert (totals.taken, totals.disputed, totals.accepted, totals.waiting, totals.questions) == (
        D(6850), D(4120), D(1530), D(1200), 1)


# ---------------------------------------------------------------- F7 Evidence card (API side)

def test_f7_every_source_on_every_card_opens(client):
    run = _march(client)
    for cid in run.charges:
        card = client.get(f"/charges/{cid}", params={"run_id": run.id}).json()
        cited = set(card["finding"]["evidence_ids"]) | set((card.get("rehearsal") or {}).get("answer_evidence_ids", []))
        assert cited <= {e["id"] for e in card["evidence"]}, cid
        for ev in card["evidence"]:
            opened = client.get(f"/evidence/{ev['id']}", params={"run_id": run.id})
            assert opened.status_code == 200, ev["id"]
            body = opened.json()
            assert body["quote"] or body["rows"] or body["sender"] or body["rule_id"] or body["person"], ev["id"]
            if body["kind"] == "clause":
                q = body["quote"]
                text = documents.load(q["doc_id"])[1]
                assert quote_check.normalize(text[q["char_start"]:q["char_end"]]) == quote_check.normalize(q["text"])


# ---------------------------------------------------------------- F8 Ask once + F11 DEMO_MODE, through the routes

def test_f8_f11_full_demo_over_the_api_with_wifi_off(client):
    march = _march(client)
    assert [q.charge_id for q in march.questions.values()] == ["C6"]
    r = client.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 14 days"}).json()
    assert r["rule"]["label"] == "Rule #1" and r["rule"]["condition"] == "notice_days >= 14"
    _wait(march.id, "finished")
    totals = [e.data for e in march.events if e.type == "totals"][-1]
    assert (totals.taken, totals.disputed, totals.accepted, totals.waiting, totals.questions) == (
        D(6850), D(4120), D(2730), D(0), 1)
    dispute = next(e.data for e in march.events if e.type == "dispute")
    assert (dispute.id, dispute.total, dispute.status) == ("D-0417", D(4120), "filed")
    approval = next(e.data for e in march.events if e.type == "approval")
    assert (approval.amount, approval.approver_role, approval.status, len(approval.lines)) == (
        D(2730), "controller", "pending", 3)

    april = _wait(client.post("/replay/april").json()["run_id"], "finished")
    assert not april.questions
    assert set(april.findings) == {"A1", "A2"}  # recorded Investigator answers still match the requests
    assert {cid: (d.decision, d.rule_id) for cid, d in april.shown.items()} == {
        "A1": ("accept", "rule-1"), "A2": ("dispute", "rule-1")}
    for cid in april.charges:
        card = client.get(f"/charges/{cid}", params={"run_id": april.id}).json()
        assert card["rule"]["label"] == "Rule #1"
        assert "ev-rule-1" in {e["id"] for e in card["evidence"]}


# ---------------------------------------------------------------- F8 Ask once, by SMS (Twilio webhook, offline)

OWNER_PHONE, CONTROLLER_PHONE = "+15550100001", "+15550100002"  # fake numbers; nothing is sent


def _sms(client, sender: str, body: str, **headers) -> str:
    r = client.post("/webhooks/twilio/sms", data={"From": sender, "Body": body, "To": "+15550100000"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.text


@pytest.fixture
def phones(monkeypatch):
    monkeypatch.setenv("OWNER_PHONE", OWNER_PHONE)
    monkeypatch.setenv("CONTROLLER_PHONE", CONTROLLER_PHONE)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)


def test_f8_owner_sms_reply_saves_rule_1_and_april_asks_nothing(client, phones):
    march = _march(client)
    reply = _sms(client, "(555) 010-0001", "accept if notice is at least 14 days")  # same number, other format
    assert "Saved: accept display fees with 14+ days' notice. Reply UNDO to cancel." in reply
    rule = next(e.data for e in march.events if e.type == "rule")
    assert (rule.label, rule.condition, rule.status) == ("Rule #1", "notice_days >= 14", "active")
    assert next(e.data for e in march.events if e.type == "answer").text == "accept if notice is at least 14 days"
    _wait(march.id, "finished")
    totals = [e.data for e in march.events if e.type == "totals"][-1]
    assert (totals.disputed, totals.accepted, totals.questions) == (D(4120), D(2730), 1)

    april = _wait(client.post("/replay/april").json()["run_id"], "finished")
    assert not april.questions
    assert {d.rule_id for d in april.shown.values()} == {"rule-1"}


def test_f8_owner_sms_undo_and_unclear(client, phones):
    march = _march(client)
    assert "Sorry, I couldn't turn that into a rule." in _sms(client, OWNER_PHONE, "hmm let me think")
    assert not any(e.type == "rule" for e in march.events)
    _sms(client, OWNER_PHONE, "accept if notice is at least 14 days")
    assert "Undone: Rule #1 is cancelled." in _sms(client, OWNER_PHONE, "UNDO")
    assert [e.data.status for e in march.events if e.type == "rule"] == ["active", "undone"]


def test_f8_sms_from_a_stranger_changes_nothing(client, phones):
    march = _march(client)
    n = len(march.events)
    assert "<Message>" not in _sms(client, "+15559999999", "accept")
    assert len(march.events) == n and march.questions["Q-1"].answer is None


def test_f8_twilio_signature_is_checked_when_the_token_is_set(client, phones, monkeypatch):
    from api.routes import webhooks
    _march(client)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token-not-real")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clawback.example")
    form = {"From": OWNER_PHONE, "Body": "accept if notice is at least 14 days", "To": "+15550100000"}
    bad = client.post("/webhooks/twilio/sms", data=form, headers={"X-Twilio-Signature": "nope"})
    assert bad.status_code == 403
    sig = webhooks.signature("https://clawback.example/webhooks/twilio/sms", form, "test-token-not-real")
    assert "Saved:" in _sms(client, OWNER_PHONE, form["Body"], **{"X-Twilio-Signature": sig})


# ---------------------------------------------------------------- F10 controller approval on a live run

def _finished_march(client) -> tuple[pipeline.Run, str]:
    march = _march(client)
    client.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 14 days"})
    _wait(march.id, "finished")
    approval = next(e.data for e in march.events if e.type == "approval")
    return march, approval.id


def test_f10_controller_yes_in_app_posts_the_memo(client):
    march, ap = _finished_march(client)
    r = client.post(f"/approvals/{ap}", json={"approve": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approval"]["status"] == "approved"
    post = body["ledger_post"]
    assert (post["qbo_entity"], post["amount"], post["approval_id"], post["status"]) == (
        "credit_memo", 2730.0, ap, "posted")
    assert {ln["charge_id"]: ln["amount"] for ln in post["lines"]} == {"C1": 1200.0, "C3": 330.0, "C6": 1200.0}
    assert [e.data.status for e in march.events if e.type == "approval"] == ["pending", "approved"]
    # the memo, then the invoice's open-balance note (api/pipeline._post_books)
    assert [e.data.qbo_entity for e in march.events if e.type == "ledger_post"] == ["credit_memo", "invoice_note"]
    assert client.post(f"/approvals/{ap}", json={"approve": False}).status_code == 409


def test_f10_controller_no_posts_nothing_and_keeps_the_note(client):
    march, ap = _finished_march(client)
    body = client.post(f"/approvals/{ap}", json={"approve": False, "note": "Wait for Northmart's reply."}).json()
    assert body["ledger_post"] is None
    assert (body["approval"]["status"], body["approval"]["note"]) == ("refused", "Wait for Northmart's reply.")
    assert not any(e.type == "ledger_post" for e in march.events)
    assert client.post("/approvals/AP-nope", json={"approve": True}).status_code == 404


def test_f10_controller_sms_yes_and_no(client, phones):
    march, ap = _finished_march(client)
    assert "Reply YES to approve" in _sms(client, CONTROLLER_PHONE, "yes but only two lines")
    assert "Held: the $2,730 credit memo won't post." in _sms(client, CONTROLLER_PHONE, "No, wait for D-0417")
    refused = [e.data for e in march.events if e.type == "approval"][-1]
    assert (refused.id, refused.status, refused.note) == (ap, "refused", "wait for D-0417")
    assert not any(e.type == "ledger_post" for e in march.events)
    assert "nothing waiting" in _sms(client, CONTROLLER_PHONE, "yes")

    pipeline.reset()
    march, ap = _finished_march(client)
    assert "Approved: $2,730 credit memo (3 lines)." in _sms(client, CONTROLLER_PHONE, "YES")
    assert [e.data.status for e in march.events if e.type == "approval"] == ["pending", "approved"]
    assert next(e.data for e in march.events if e.type == "ledger_post").amount == D(2730)


# ---------------------------------------------------------------- F12 scoreboard numbers = make eval

def test_f12_eval_latest_serves_what_make_eval_printed(client, tmp_path, monkeypatch):
    from api.routes import eval as eval_route
    latest = tmp_path / "latest.json"
    monkeypatch.setattr(eval_route, "latest_path", lambda: latest)
    ev = eval_route._harness()
    assert client.get("/eval/latest").json()["status"] == "not_run"

    assert ev.main(["--out", str(latest)]) == 0  # what `make eval` runs
    printed = ev.summary(ev.run(ev.DEFAULT_DATA))
    shown = client.get("/eval/latest").json()
    assert shown["status"] == "done" and shown["run_at"]
    assert (shown["cases"], shown["correct"], shown["asked"], shown["wrong_automatic"],
            shown["amounts_correct"], shown["unnecessary_questions"]) == (
        printed["cases"], printed["correct"], printed["asked"], printed["wrong_actions"],
        printed["correct_amounts"], printed["unnecessary_questions"])

    latest.unlink()
    ran = client.post("/eval/run").json()
    assert ran["status"] == "done" and ran["correct"] == printed["correct"]
    assert client.get("/eval/latest").json()["correct"] == printed["correct"]
