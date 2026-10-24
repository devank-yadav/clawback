"""P0 audit (docs/design.md, Feature spec): checks where the existing acceptance tests were weaker than the spec.

- F2: a term whose quote isn't in the deal is rejected, and the charges that depend on it are skipped
  ("can't verify the deal", gate row 1), never disputed.
- F4: the Investigator's code check (evidence IDs exist, no invented numbers, confidence floor) routes to Ask.
- F9: each of the four preset replies gets the right answer, from the recordings, citing the right evidence, and
  none of them moves money; only the signed amendment concedes the $1,000.
- F10: the owner's text can't approve the controller's credit memo.
"""

import json
import time
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from api import disputes, pipeline
from api.integrations import replay
from api.tests.test_disputes import finished_march
from api.tests.test_pipeline import MARCH_FIRST, ScenarioClaude, final, last_totals, logs
from api.tests.test_reader import RECORDED, SPRING, answer, term

_sleep = time.sleep


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY", "TWILIO_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setattr(replay.time, "sleep", lambda _s: None)
    pipeline.reset(), disputes.reset()
    yield
    pipeline.reset(), disputes.reset()


# ---------------------------------------------------------------- F2: a quote that isn't in the deal

class PlantedCapQuote(ScenarioClaude):
    """Both readers quote a cap sentence the deal doesn't contain (close to §3.2, not word for word)."""

    def _reader(self, user):
        if "Document ID: spring-promo" in user:
            fake = term("unit_cap", "The allowance applies to a maximum of 5,000 units.", max_units=5000)
            return answer([t if t["type"] != "unit_cap" else fake for t in SPRING])
        return super()._reader(user)


def test_f2_planted_quote_is_rejected_and_its_charges_are_skipped_not_disputed():
    run = pipeline.start("march", PlantedCapQuote(), background=False)
    assert {t.type: t.status for t in run.terms if t.source_doc_id == "spring-promo"}["unit_cap"] == "rejected"
    shown = {cid: (d.decision, d.gate_row, d.disputed, d.accepted) for cid, d in run.shown.items()}
    # every promo charge runs the cap check, so none of them is decided on an unverified term
    assert {cid: shown[cid] for cid in ("C1", "C2", "C3", "C4")} == {
        cid: ("skip", 1, D(0), D(0)) for cid in ("C1", "C2", "C3", "C4")}
    assert shown["C5"] == ("dispute", 7, D(1000), D(0))  # Mint isn't a deal product: no cap needed
    t = last_totals(run)
    assert (t.disputed, t.accepted, t.skipped, t.undecided) == (D(1000), D(0), 4, D(4650))
    assert any("rejected: quote not found" in x for x in logs(run))


# ---------------------------------------------------------------- F4: the Investigator's code check

class BadInvestigator(ScenarioClaude):
    """Gives a bad answer for one charge, `times` times, then the good one."""

    def __init__(self, charge_id, bad, times):
        super().__init__()
        self.charge_id, self.bad, self.times, self.asked = charge_id, bad, times, 0

    def _finding(self, user):
        user = user.split("\n\nYour previous answer")[0]  # the retry carries the error after the payload
        out = super()._finding(user)
        if json.loads(user)["charge"]["id"] != self.charge_id:
            return out
        self.asked += 1
        return {**out, **self.bad} if self.asked <= self.times else out


BAD = {
    "unknown evidence ID": {"evidence_ids": ["ev-spring-promo-3.2", "ev-made-up"]},
    "invented number": {"finding": "Northmart took $1,540 but the deal allows $777 for these units."},
}


@pytest.mark.parametrize("why", sorted(BAD))
def test_f4_a_bad_finding_is_retried_once(why):
    fake = BadInvestigator("C4", BAD[why], times=1)
    run = pipeline.start("march", fake, background=False)
    assert fake.asked == 2 and final(run) == MARCH_FIRST


@pytest.mark.parametrize("why", sorted(BAD))
def test_f4_a_finding_that_fails_its_check_twice_goes_to_ask(why):
    fake = BadInvestigator("C4", BAD[why], times=2)
    run = pipeline.start("march", fake, background=False)
    assert fake.asked == 2 and "C4" not in run.findings
    d = run.shown["C4"]
    assert (d.decision, d.gate_row, d.disputed, d.waiting) == ("ask", 9, D(0), D(1540))
    filed = next(e.data for e in run.events if e.type == "dispute")
    assert "C4" not in {ln.charge_id for ln in filed.lines} and filed.total == D(2580)
    assert any("Couldn't explain C4" in x for x in logs(run))


def test_f4_confidence_below_the_floor_goes_to_ask():
    fake = BadInvestigator("C1", {"confidence": 0.6}, times=2)
    run = pipeline.start("march", fake, background=False)
    assert run.findings["C1"].confidence == 0.6
    d = run.shown["C1"]
    assert (d.decision, d.gate_row, d.disputed, d.accepted) == ("ask", 9, D(0), D(0))
    assert [q.charge_id for q in run.questions.values()] == ["C1", "C6"]


# ---------------------------------------------------------------- F9: the four preset replies, from the recordings

PRESET_CITES = {  # docs/design.md scenario table: the evidence that answers each claim
    "no-cap": ("claim_without_document", {"ev-spring-promo-3.2", "ev-sales-2026-03-15"}),
    "rate": ("claim_without_document", {"ev-spring-promo-3.1", "ev-sales-2026-03-01"}),
    "not-a-repeat": ("claim_without_document", {"ev-payment-NM-2178", "ev-sales-2026-03-08"}),
    "agree-mint": ("agrees", {"ev-charge-C5"}),
}


def test_f9_each_preset_gets_the_right_answer_and_only_the_amendment_moves_money(monkeypatch):
    from api.main import app

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    api = TestClient(app)
    run = pipeline.RUNS[api.post("/runs", json={"kind": "march"}).json()["run_id"]]
    for _ in range(2000):
        if run.questions:
            break
        _sleep(0.01)
    api.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 14 days"})
    for _ in range(2000):
        if run.done:
            break
        _sleep(0.01)
    before = final(run)

    for p in disputes.PRESETS:
        if p.attachment_doc_id:
            continue
        kind, must_cite = PRESET_CITES[p.id]
        theirs, ours = api.post("/portal/disputes/D-0417/messages", json={"text": p.text}).json()
        assert (theirs["classification"], theirs["charge_ids"]) == (kind, p.charge_ids), p.id
        assert ours["from_party"] == "clawback" and must_cite <= set(ours["evidence_ids"]), p.id
        assert final(run) == before, p.id  # a reply without a document changes no number
    no_cap, rate = [m.text for m in disputes.thread("D-0417") if m.from_party == "clawback"][:2]
    assert "§3.2" in no_cap and "maximum of 5,000 units" in no_cap  # the cap itself, not the rate clause
    assert "$1.00 per unit" in rate and "signed written amendment" in rate  # a call or an email isn't a change

    amendment = next(p for p in disputes.PRESETS if p.attachment_doc_id == "amendment-1")
    _, ours = api.post("/portal/disputes/D-0417/messages",
                       json={"text": amendment.text, "attachment_doc_id": "amendment-1"}).json()
    assert "withdraw $1,000 of NM-2236 (C4)" in ours["text"] and "$540 disputed" in ours["text"]
    assert final(run)["C4"] == ("split", D(540), D(1000))
    assert {cid: v for cid, v in final(run).items() if cid != "C4"} == {cid: v for cid, v in before.items() if cid != "C4"}


# ---------------------------------------------------------------- F10: controller only

def test_f10_the_owners_text_never_approves_the_credit_memo(monkeypatch):
    from api.main import app

    monkeypatch.setenv("OWNER_PHONE", "+15550100001")
    monkeypatch.setenv("CONTROLLER_PHONE", "+15550100002")
    run = finished_march(ScenarioClaude())
    api = TestClient(app)
    for body in ("YES", "approve", "yes approve the memo"):
        r = api.post("/webhooks/twilio/sms", data={"From": "+15550100001", "Body": body})
        assert r.status_code == 200
    assert [e.data.status for e in run.events if e.type == "approval"] == ["pending"]
    assert not any(e.type == "ledger_post" for e in run.events)
    assert final(run)["C6"] == ("accept", D(0), D(1200))  # Dana's texts didn't reopen her answered question either
