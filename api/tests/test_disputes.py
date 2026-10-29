"""F9 on the live portal: the judge's replies get the right answers; the signed amendment concedes $1,000."""

import json
import re
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import disputes, pipeline
from api.agents.negotiator import LLMReply
from api.integrations import replay
from api.tests.test_pipeline import ScenarioClaude, final, last_totals
from api.tests.test_reader import NULLS, answer

AMENDMENT_TERMS = [{"type": "unit_cap", "params": {**NULLS, "max_units": 6000}, "effective_from": "2026-03-20",
                    "effective_to": None, "discretion": False,
                    "exact_quote": "3.2 The promotional allowance applies to a maximum of 6,000 units in total."}]


class PortalClaude(ScenarioClaude):
    """ScenarioClaude plus the Negotiator's portal answers and a reader for amendment-1."""

    def __init__(self, bad_answers: int = 0):
        super().__init__()
        self.bad_answers = bad_answers

    def _parse(self, output_format, messages, **kw):
        if output_format is LLMReply:
            self.calls.append("LLMReply")
            out = self._reply(messages[0]["content"])
            return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=LLMReply.model_validate(out))
        return super()._parse(output_format=output_format, messages=messages, **kw)

    def _reader(self, user):
        if "Document ID: amendment-1" in user:
            return answer(AMENDMENT_TERMS)
        return super()._reader(user)

    def _reply(self, user):
        payload = json.loads(user.split("\n\nYour previous answer")[0])
        text = payload["northmart_reply"]
        if self.bad_answers:
            self.bad_answers -= 1
            return {"classification": "claim_without_document", "charge_ids": ["C4"], "claim": "no cap",
                    "answer": "We'll settle for $2,000 if you pay by Friday.", "answer_evidence_ids": ["ev-spring-promo-3.2"]}
        if "cap" in text:
            return {"classification": "claim_without_document", "charge_ids": ["C4"], "claim": "there was no cap",
                    "answer": 'The signed deal says: "The promotional allowance applies to a maximum of 5,000 units in total." '
                              "Please attach the signed change if the cap was raised.",
                    "answer_evidence_ids": ["ev-spring-promo-3.2", "ev-sales-2026-03-15"]}
        if "Agreed" in text:
            return {"classification": "agrees", "charge_ids": ["C5"], "claim": None,
                    "answer": "Thank you for agreeing on the Mint line.", "answer_evidence_ids": []}
        return {"classification": "other", "charge_ids": [], "claim": None, "answer": "", "answer_evidence_ids": []}


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset(), disputes.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("RECORD_FIXTURES", raising=False)
    yield
    pipeline.reset(), disputes.reset()


def finished_march(fake):
    run = pipeline.start("march", fake, background=False)
    pipeline.answer(next(iter(run.questions)), "accept if notice is at least 14 days", client=fake)
    return run


def test_presets_cover_every_reply_kind():
    assert {p.expect for p in disputes.PRESETS} == {"claim_without_document", "agrees", "new_document"}
    assert sum(p.attachment_doc_id == "amendment-1" for p in disputes.PRESETS) == 1


def test_claim_without_document_gets_evidence_and_a_request():
    fake = PortalClaude()
    run = finished_march(fake)
    theirs, ours = disputes.post("D-0417", "There was no unit cap on the Spring promo. The week 4 deduction stands.", client=fake)
    assert (theirs.classification, theirs.charge_ids) == ("claim_without_document", ["C4"])
    assert ours.from_party == "clawback" and "signed change" in ours.text and "ev-spring-promo-3.2" in ours.evidence_ids
    assert [e.data.id for e in run.events if e.type == "portal_message"][-2:] == [theirs.id, ours.id]
    assert final(run)["C4"] == ("dispute", D(1540), D(0))  # a claim alone changes nothing


def test_answer_that_breaks_the_outbound_filter_twice_is_held():
    fake = PortalClaude(bad_answers=2)
    run = finished_march(fake)
    out = disputes.post("D-0417", "There was no cap.", client=fake)
    assert [m.from_party for m in out] == ["northmart"]
    assert any("held for Dana" in e.data.text for e in run.events if e.type == "log")


def test_bad_answer_once_is_retried():
    fake = PortalClaude(bad_answers=1)
    finished_march(fake)
    out = disputes.post("D-0417", "There was no cap.", client=fake)
    assert [m.from_party for m in out] == ["northmart", "clawback"] and fake.calls.count("LLMReply") == 2


def test_agreement_is_acknowledged_and_nonsense_is_held():
    fake = PortalClaude()
    run = finished_march(fake)
    _, ours = disputes.post("D-0417", "Agreed, Mint wasn't part of the Spring promo.", client=fake)
    assert "Mint" in ours.text
    assert [m.from_party for m in disputes.post("D-0417", "asdf lol call me", client=fake)] == ["northmart"]


def test_signed_amendment_concedes_1000_and_keeps_540():
    fake = PortalClaude()
    run = finished_march(fake)
    theirs, ours = disputes.post("D-0417", "The cap was raised to 6,000 units. Signed amendment attached.",
                                 attachment_doc_id="amendment-1", client=fake)
    assert theirs.classification == "new_document"
    assert final(run)["C4"] == ("split", D(540), D(1000))
    t = last_totals(run)
    assert (t.disputed, t.accepted, t.questions) == (D(3120), D(3730), 1)
    dispute = [e.data for e in run.events if e.type == "dispute"][-1]
    assert (dispute.total, dispute.status) == (D(3120), "answered")
    assert {ln.charge_id: ln.amount for ln in dispute.lines}["C4"] == D(540)
    assert "withdraw $1,000 of NM-2236 and keep" in ours.text and "$540 disputed" in ours.text and "$3,120" in ours.text
    memo = [e.data for e in run.events if e.type == "approval"][-1]
    assert (memo.amount, memo.status, [ln.charge_id for ln in memo.lines]) == (D(1000), "approved", ["C4"])  # within policy
    assert run.findings["C4"].expected == D(1000)


def test_document_that_cannot_change_the_deal_changes_nothing():
    fake = PortalClaude()
    run = finished_march(fake)
    _, ours = disputes.post("D-0417", "See our email.", attachment_doc_id="northmart-2026-03-30", client=fake)
    assert "doesn't change the deal" in ours.text and final(run)["C4"] == ("dispute", D(1540), D(0))


def test_portal_routes_use_the_live_dispute(monkeypatch):
    from api.agents import claude as claude_mod
    from api.main import app

    fake = PortalClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    finished_march(fake)
    client = TestClient(app)
    assert len(client.get("/portal/presets").json()) == 5
    assert client.get("/portal/disputes/D-0417").json()["total"] == 4120.0
    out = client.post("/portal/disputes/D-0417/messages",
                      json={"text": "Signed amendment attached.", "attachment_doc_id": "amendment-1"}).json()
    assert [m["from_party"] for m in out] == ["northmart", "clawback"]
    assert client.get("/portal/disputes/D-0417").json()["total"] == 3120.0
    assert len(client.get("/portal/disputes/D-0417/messages").json()) == 2


def test_committed_recordings_replay_the_portal_offline(monkeypatch):
    """F9 with Wi-Fi off: every preset replays from data/fixtures. Portal replies try live first, so the client
    here fails and the saved answer is used. Re-record with `make record` if this breaks."""
    from api.tests.test_reader import RECORDED

    class Offline:
        def with_options(self, **_):
            raise ConnectionError("offline")

    monkeypatch.setattr(replay, "FIXTURES", RECORDED)
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)
    monkeypatch.setenv("DEMO_MODE", "true")
    run = finished_march(Offline())
    for p in disputes.PRESETS:
        out = disputes.post("D-0417", p.text, p.attachment_doc_id, client=Offline())
        assert out[0].classification == p.expect and out[-1].from_party == "clawback", p.id
    assert final(run)["C4"] == ("split", D(540), D(1000))
    assert (last_totals(run).disputed, last_totals(run).accepted) == (D(3120), D(3730))


def test_every_run_numbers_its_own_disputes():
    """A second run of the same payment files D-0417 again; the portal answers on the newest one and each run keeps
    its own thread. April numbers from D-0427, so it never takes D-0417."""
    fake = PortalClaude()
    first = finished_march(fake)
    second = pipeline.start("march", fake, background=False)  # Rule #1 is saved: no question this time
    assert [[e.data.id for e in r.events if e.type == "dispute"] for r in (first, second)] == [["D-0417"], ["D-0417"]]
    assert disputes.find("D-0417")[0] is second
    disputes.post("D-0417", "There was no unit cap on the Spring promo.", client=fake)
    assert [e.type for e in first.events].count("portal_message") == 0
    assert [e.type for e in second.events].count("portal_message") == 2 and len(disputes.thread("D-0417")) == 2
    april = pipeline.start("april", fake, background=False)
    assert [e.data.id for e in april.events if e.type == "dispute"] == ["D-0427"]
    assert disputes.find("D-0417")[0] is second
