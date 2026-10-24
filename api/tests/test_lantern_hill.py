"""Lantern Hill Soda Co. <- KeHE Distributors, end to end through the pipeline: KeHE's real 2015 Vendor Policies &
Procedures, our side's promotion submission, broker email and KeHE's notices, one month of charges and one older
deduction. Faked AI answers (api/tests/lantern_hill_answers.py) go through the real Claude call path, the readers'
JSON validation, the quote check, the merge, the engine, the gate, the owner's one answer and the rule writer; the
decisions reproduce data/accounts/lantern-hill/expected.csv, and every total comes from the engine."""

import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import accounts, documents, fee_accounts, pipeline
from api.agents import reader, reader_b
from api.agents.investigator import LLMFinding
from api.agents.negotiator import LLMRehearsal
from api.agents.reader import LLMFeeOutput, LLMOutput
from api.agents.rule_writer import LLMRule
from api.engine import gate
from api.integrations import replay
from api.tests import lantern_hill_answers as fake

ACCOUNT = "lantern-hill"
POLICY_TEXT = Path(__file__).resolve().parents[2] / "data" / "contracts" / "kehe-vendor-policies-2015.txt"


class FakeClaude:
    """Answers both readers, the Investigator, the rehearsal and the rule writer from lantern_hill_answers, citing
    only evidence IDs the request holds: a clause and the charge's backup or purchase orders."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, output_format, messages, system, **_):
        user = messages[0]["content"]
        if output_format is LLMFeeOutput:
            doc = re.search(r"Document ID: (\S+)", user).group(1)
            b = "A second reader reads the same document separately" in system
            self.calls.append(("B" if b else "A", doc))
            out = fake.READERS[doc][1 if b else 0]
        elif output_format is LLMFinding:
            payload = json.loads(user)
            self.calls.append(("investigator", payload["charge"]["id"]))
            out = {"finding": "The policy and the backup explain this charge.", "type": "matches_deal",
                   "evidence_ids": self._cite(payload), "confidence": 0.95, "open_questions": []}
        elif output_format is LLMRehearsal:
            payload = json.loads(user)
            self.calls.append(("rehearsal", payload["charge"]["id"]))
            out = {"predicted_rebuttal": "KeHE's policy allows the deduction.",
                   "answer": "The policy sentence and the backup show what is owed.",
                   "answer_evidence_ids": self._cite(payload)[:1]}
        elif output_format is LLMRule:
            self.calls.append(("rule", ""))
            out = fake.RULE
        else:
            raise AssertionError(f"unexpected agent {output_format.__name__}")
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=output_format.model_validate(out))

    @staticmethod
    def _cite(payload):
        ids = [e["id"] for e in payload["evidence"]]
        ref = payload["charge"]["ref"]
        clause = [i for i in ids if i.startswith(("ev-kehe-vendor-policies-2015-", "ev-lantern-hill-promotion"))][:1]
        data = [i for i in ids if i == f"ev-backup-{ref}"] or [i for i in ids if i.startswith("ev-po-")][:1]
        return clause + data + [f"ev-charge-{payload['charge']['id']}"]


@pytest.fixture(autouse=True)
def lantern_hill(monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", ACCOUNT})
    accounts.clear()
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    yield accounts.get(ACCOUNT)
    pipeline.reset()
    accounts.clear()


@pytest.fixture
def run():
    """The month decided by the pipeline, then the owner's one answer."""
    client = FakeClaude()
    r = pipeline.start(account=ACCOUNT, client=client, background=False)
    first = dict(r.shown)
    asked = [q.charge_id for q in r.questions.values()]
    for qid in list(r.questions):
        pipeline.answer(qid, fake.OWNER_ANSWER, client=client)
    return SimpleNamespace(run=r, first=first, asked=asked, calls=client.calls)


def money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


def expected(acct):
    import csv
    with (acct.dir / "expected.csv").open(newline="") as f:
        return {r["charge_id"]: r for r in csv.DictReader(f)}


# --- The data -------------------------------------------------------------------------------------------------

def test_the_policy_is_kehes_text_unedited(lantern_hill):
    doc, text = documents.load("kehe-vendor-policies-2015")
    assert text == POLICY_TEXT.read_text() and doc.kind == "deal" and doc.signed_by_both
    assert len(text.split()) == 5775  # data/contracts/README.md: identical word for word to the SEC filing
    assert documents.account_of(doc.id).id == ACCOUNT and lantern_hill.config.deal_docs[0] == doc.id


def test_the_remittance_adds_up(lantern_hill):
    inv = lantern_hill.invoice
    month = fee_accounts.charges(lantern_hill)
    assert inv.expected - inv.received == sum((c.amount for c in month), Decimal(0)) == Decimal("9943.36")
    as_of = fee_accounts.fee_data(lantern_hill).as_of
    assert {c.deducted_on for c in month} == {as_of}
    assert all(c.deducted_on < as_of for c in fee_accounts.older_charges(lantern_hill))


def test_documents_and_senders(lantern_hill):
    promo = documents.load("lantern-hill-promotion-2026-03")[0]
    assert promo.sender == "teresa@lanternhillsoda.example" and documents.can_change_deal(promo)
    broker = documents.load("lantern-hill-broker-2026-03-24")[0]
    assert broker.approved_sender
    notice = documents.load("lantern-hill-kehe-ep-admin-2026-03-02")[0]
    assert notice.sender == "vendorportal@kehe.example" and notice.approved_sender
    assert fee_accounts.noticed_on(notice.id, lantern_hill).isoformat() == "2026-03-02"
    assert fee_accounts.noticed_on(broker.id, lantern_hill) is None
    refs = {c.ref for c in fee_accounts.charges(lantern_hill) + fee_accounts.older_charges(lantern_hill)}
    for r in fee_accounts.backup(lantern_hill):  # every backup line belongs to a charge; every proof it names exists
        assert r.deduction_ref in refs and (r.proof_doc is None or r.proof_doc in lantern_hill.docs)


# --- The readers ----------------------------------------------------------------------------------------------

def test_fee_documents_get_the_fee_prompt_and_peak_bar_keeps_its_own(lantern_hill):
    system, schema = reader.with_fees(reader.prompt(lantern_hill), lantern_hill)
    assert schema is LLMFeeOutput and system.startswith(reader.prompt(lantern_hill))
    assert "Lantern Hill Soda Co." in system and "KeHE Distributors" in system and "Peak Bar" not in system
    assert "fee_schedule" in system and "fee_schedule" not in reader.prompt(lantern_hill)
    for p in (reader.prompt("peak-bar"), reader_b.prompt("peak-bar")):  # Peak Bar: as recorded
        assert reader.with_fees(p, "peak-bar") == (p, LLMOutput)


def test_both_readers_read_every_document(run, lantern_hill):
    reads = [c for c in run.calls if c[0] in "AB"]
    assert sorted(reads) == sorted((r, d) for d in lantern_hill.config.deal_docs for r in "AB")
    terms = run.run.terms
    verified = {(t.type, t.params.get("fee_code")) for t in terms if t.status == "verified"}
    assert verified >= {("fee_schedule", "MCB"), ("fee_schedule", "Extra Performance"),
                        ("fee_schedule", "Free Placements"), ("fee_schedule", "Spoils"), ("dispute_window", None),
                        ("notice_period", None), ("promo_rate", None), ("product_scope", None), ("date_range", None),
                        ("unit_cap", None), ("amendment", None)}
    # Only Reader B read §6.10 as a fee: disputed, and it doesn't knock any other fee out of its pair.
    assert [t.status for t in terms if t.params.get("fee_code") == "Marketing Allowance"] == ["disputed"]
    ext = next(t for t in terms if t.type == "amendment")
    assert ext.effective_from.isoformat() == "2026-03-29"  # dated from the submission's buy dates, not the policy
    window = next(t for t in terms if t.type == "dispute_window")
    assert window.params == {"days": 180, "from": "deduction"}


def test_a_made_up_fee_quote_is_rejected(lantern_hill):
    doc, text = documents.load("kehe-vendor-policies-2015")
    made_up = fake.term("fee_schedule", "KeHE will charge a processing fee of 10% of the MCB amount.",
                        fee_code="MCB", basis="percent", rate="10", per="incident", requires_proof=True)
    out = reader._to_reader_output({"terms": [made_up], "unclear": []}, doc, text, LLMFeeOutput)
    [t] = reader._check(out, doc, text, [])
    assert t.status == "rejected" and t.reasons == ["quote not found in source"]


# --- The decisions --------------------------------------------------------------------------------------------

def test_expected_decisions_are_reproduced(run, lantern_hill):
    rows = expected(lantern_hill)
    assert set(rows) == set(run.run.charges)
    for cid, r in rows.items():
        d = run.run.shown[cid]
        assert (d.decision, d.disputed, d.accepted, d.gate_row) == (
            r["decision"], money(r["disputed"]), money(r["accepted"]), int(r["gate_row"])), cid
        assert (cid in run.asked) == (r["asked"] == "yes"), cid


def test_one_question_then_the_rule(run):
    assert run.asked == ["K8"] and run.first["K8"].gate_row == 4 and run.first["K8"].decision == "ask"
    rule = pipeline.rules_of(ACCOUNT)[0]
    assert (rule.term_type, rule.condition, rule.counterparty, rule.label) == (
        "fee_schedule", "fee_amount <= 150", "KeHE Distributors", "Rule #1")
    assert run.run.shown["K8"].rule_id == rule.id
    assert ("rule", "") in run.calls


def test_totals_come_from_the_engine(run, lantern_hill):
    month = {c.id for c in fee_accounts.charges(lantern_hill)}
    decided = [run.run.decisions[c] for c in month]
    t = gate.summarize(decided)
    assert (t.disputed, t.accepted, t.questions) == (Decimal("1436.76"), Decimal("8506.60"), 0)
    assert t.disputed + t.accepted == lantern_hill.invoice.expected - lantern_hill.invoice.received
    rows = expected(lantern_hill)
    assert t.disputed == sum(money(rows[c]["disputed"]) for c in month)
    assert t.accepted == sum(money(rows[c]["accepted"]) for c in month)
    assert run.run.decisions["K10"].accepted == Decimal("286.20")


def test_the_reasons_name_each_check(run):
    a = run.run.allowances
    assert a["K4"].steps[0] == "Fee MCB 03/01-03/14: 5% of $940.00 = $47.00; minimum $65.00 -> $65.00."
    assert a["K6"].steps[0] == "Fee R-55120: 5% of $5,400.00 = $270.00; maximum $175.00 -> $175.00."
    assert a["K7"].facts["change_before_notice"] == ("lantern-hill-kehe-ep-admin-2026-03-02/fee_schedule",)
    assert a["K8"].facts["fee_amount"] == Decimal("185.76") and a["K8"].firm == Decimal("1032.00")
    assert a["K9"].steps[0] == "Fee CR-88120: 240 units x $0.29 = $69.60 -> $69.60."
    assert a["K3"].steps[2] == "410 units outside the deal dates are covered by an approved amendment."
    assert (a["K10"].allowed, a["K10"].facts["past_dispute_window"]) == (Decimal("250.20"), True)
    assert run.run.shown["K10"].reason == ("Past the dispute window (it closed on Apr 4, 2026): accepted and noted; "
                                           "the deal allows $250.20, $36.00 less.")


def test_every_fee_charge_cites_its_backup(run):
    for cid in ("K4", "K5", "K6", "K7", "K8", "K9", "K10"):
        f = run.run.findings[cid]
        assert f"ev-backup-{run.run.charges[cid].ref}" in f.evidence_ids
        assert all(i in run.run.evidence for i in f.evidence_ids)
    assert run.run.evidence["ev-kehe-vendor-policies-2015-6.4"].kind == "clause"


def test_the_run_files_the_disputes_and_asks_the_controller(run):
    events = [e.type for e in run.run.events]
    assert "dispute" in events and "approval" in events
