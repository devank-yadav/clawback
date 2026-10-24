"""The two accounts on KeHE Distributors' real 2015 Vendor Policies & Procedures, end to end through the pipeline:
Lantern Hill Soda Co. and Peak Bar Co. (peak-bar-kehe, Peak Bar's KeHE account, on its own copy of the policy).
Each has our side's promotion submission, broker email and KeHE's notices, one month of charges and one older
deduction. Faked AI answers (api/tests/lantern_hill_answers.py) go through the real Claude call path, the readers'
JSON validation, the quote check, the merge, the engine, the gate, the owner's one answer and the rule writer; the
decisions reproduce each account's expected.csv, and every total comes from the engine."""

import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import accounts, documents, fee_accounts, pipeline
from api.agents import prompts, reader, reader_b
from api.agents.investigator import LLMFinding
from api.agents.negotiator import LLMRehearsal
from api.agents.reader import LLMFeeOutput, LLMOutput
from api.agents.rule_writer import LLMRule
from api.engine import gate
from api.integrations import replay
from api.tests import lantern_hill_answers as fake

CONTRACTS = Path(__file__).resolve().parents[2] / "data" / "contracts"
# Per account: what its month adds up to, worked out by hand from its files (the engine must agree).
EXPECT = {
    "lantern-hill": {"sender": "teresa@lanternhillsoda.example", "other_brand": "Peak Bar", "taken": "9943.36",
                     "disputed": "1436.76", "accepted": "8506.60", "k8_fee": "185.76", "k8_firm": "1032.00",
                     "k10_taken": "286.20", "k10_allowed": "250.20"},
    "peak-bar-kehe": {"sender": "dana@peakbar.example", "other_brand": "Lantern Hill", "taken": "10409.92",
                      "disputed": "1471.32", "accepted": "8938.60", "k8_fee": "220.32", "k8_firm": "1224.00",
                      "k10_taken": "466.20", "k10_allowed": "430.20"},
}


class FakeClaude:
    """Answers both readers, the Investigator, the rehearsal and the rule writer from lantern_hill_answers, citing
    only evidence IDs the request holds: a clause and the charge's backup or purchase orders."""

    def __init__(self, readers):
        self.calls: list[tuple[str, str]] = []
        self.systems: dict[str, str] = {}  # agent -> the system prompt it was sent
        self.readers = readers
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, output_format, messages, system, **_):
        user = messages[0]["content"]
        if output_format is LLMFeeOutput:
            doc = re.search(r"Document ID: (\S+)", user).group(1)
            b = "A second reader reads the same document separately" in system
            self.calls.append(("B" if b else "A", doc))
            out = self.readers[doc][1 if b else 0]
        elif output_format is LLMFinding:
            payload = json.loads(user)
            self.calls.append(("investigator", payload["charge"]["id"]))
            self.systems["investigator"] = system
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
        clause = [i for i in ids if i.startswith(("ev-kehe-vendor-policies-2015-", "ev-lantern-hill-promotion",
                                                  "ev-peak-bar-kehe-promotion"))][:1]
        data = [i for i in ids if i == f"ev-backup-{ref}"] or [i for i in ids if i.startswith("ev-po-")][:1]
        return clause + data + [f"ev-charge-{payload['charge']['id']}"]


@pytest.fixture(autouse=True, params=list(fake.KEHE_ACCOUNTS))
def kehe(request, monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", request.param})
    accounts.clear()
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    yield accounts.get(request.param)
    pipeline.reset()
    accounts.clear()


def decide_month(acct, readers=None):
    """The month decided by the pipeline, then the owner's one answer."""
    client = FakeClaude(readers or fake.readers(acct.id))
    r = pipeline.start(account=acct.id, client=client, background=False)
    first = dict(r.shown)
    asked = [q.charge_id for q in r.questions.values()]
    for qid in list(r.questions):
        pipeline.answer(qid, fake.OWNER_ANSWER, client=client)
    return SimpleNamespace(run=r, first=first, asked=asked, calls=client.calls, systems=client.systems)


@pytest.fixture
def run(kehe):
    return decide_month(kehe)


def want(acct, key) -> Decimal:
    return Decimal(EXPECT[acct.id][key])


def money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


def expected(acct):
    import csv
    with (acct.dir / "expected.csv").open(newline="") as f:
        return {r["charge_id"]: r for r in csv.DictReader(f)}


# --- The data -------------------------------------------------------------------------------------------------

def test_the_policy_is_kehes_text_unedited(kehe):
    policy = fake.KEHE_ACCOUNTS[kehe.id]["policy"]
    doc, text = documents.load(policy)
    assert text == (CONTRACTS / "kehe-vendor-policies-2015.txt").read_text()  # Peak Bar's copy too
    assert doc.kind == "deal" and doc.signed_by_both
    assert len(text.split()) == 5775  # data/contracts/README.md: identical word for word to the SEC filing
    assert documents.account_of(doc.id).id == kehe.id and kehe.config.deal_docs[0] == doc.id


def test_the_remittance_adds_up(kehe):
    inv = kehe.invoice
    month = fee_accounts.charges(kehe)
    assert inv.expected - inv.received == sum((c.amount for c in month), Decimal(0)) == want(kehe, "taken")
    as_of = fee_accounts.fee_data(kehe).as_of
    assert {c.deducted_on for c in month} == {as_of}
    assert all(c.deducted_on < as_of for c in fee_accounts.older_charges(kehe))


def test_documents_and_senders(kehe):
    names = fake.KEHE_ACCOUNTS[kehe.id]
    promo = documents.load(f"{names['docs']}-promotion-2026-03")[0]
    assert promo.sender == EXPECT[kehe.id]["sender"] and documents.can_change_deal(promo)
    broker = documents.load(f"{names['docs']}-broker-2026-03-24")[0]
    assert broker.approved_sender
    notice = documents.load(names["notice"])[0]
    assert notice.sender == "vendorportal@kehe.example" and notice.approved_sender
    assert fee_accounts.noticed_on(notice.id, kehe).isoformat() == "2026-03-02"
    assert fee_accounts.noticed_on(broker.id, kehe) is None
    refs = {c.ref for c in fee_accounts.charges(kehe) + fee_accounts.older_charges(kehe)}
    for r in fee_accounts.backup(kehe):  # every backup line belongs to a charge; every proof it names exists
        assert r.deduction_ref in refs and (r.proof_doc is None or r.proof_doc in kehe.docs)


# --- The readers ----------------------------------------------------------------------------------------------

def test_fee_documents_get_the_fee_prompt_and_peak_bar_keeps_its_own(kehe):
    system, schema = reader.with_fees(reader.prompt(kehe), kehe)
    assert schema is LLMFeeOutput and system.startswith(reader.prompt(kehe))
    assert kehe.brand.name in system and "KeHE Distributors" in system
    assert EXPECT[kehe.id]["other_brand"] not in system and "Northmart" not in system
    assert "fee_schedule" in system and "fee_schedule" not in reader.prompt(kehe)
    for p in (reader.prompt("peak-bar"), reader_b.prompt("peak-bar")):  # Peak Bar: as recorded
        assert reader.with_fees(p, "peak-bar") == (p, LLMOutput)


def test_both_readers_read_every_document(run, kehe):
    reads = [c for c in run.calls if c[0] in "AB"]
    assert sorted(reads) == sorted((r, d) for d in kehe.config.deal_docs for r in "AB")
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


def test_a_made_up_fee_quote_is_rejected(kehe):
    doc, text = documents.load(fake.KEHE_ACCOUNTS[kehe.id]["policy"])
    made_up = fake.term("fee_schedule", "KeHE will charge a processing fee of 10% of the MCB amount.",
                        fee_code="MCB", basis="percent", rate="10", per="incident", requires_proof=True)
    out = reader._to_reader_output({"terms": [made_up], "unclear": []}, doc, text, LLMFeeOutput)
    [t] = reader._check(out, doc, text, [])
    assert t.status == "rejected" and t.reasons == ["quote not found in source"]


# --- The decisions --------------------------------------------------------------------------------------------

def test_expected_decisions_are_reproduced(run, kehe):
    rows = expected(kehe)
    assert set(rows) == set(run.run.charges)
    for cid, r in rows.items():
        d = run.run.shown[cid]
        assert (d.decision, d.disputed, d.accepted, d.gate_row) == (
            r["decision"], money(r["disputed"]), money(r["accepted"]), int(r["gate_row"])), cid
        assert (cid in run.asked) == (r["asked"] == "yes"), cid


def test_one_question_then_the_rule(run, kehe):
    assert run.asked == ["K8"] and run.first["K8"].gate_row == 4 and run.first["K8"].decision == "ask"
    rule = pipeline.rules_of(kehe.id)[0]
    assert (rule.term_type, rule.condition, rule.counterparty, rule.label) == (
        "fee_schedule", "fee_amount <= 150", "KeHE Distributors", "Rule #1")
    assert run.run.shown["K8"].rule_id == rule.id
    assert ("rule", "") in run.calls


def test_totals_come_from_the_engine(run, kehe):
    month = {c.id for c in fee_accounts.charges(kehe)}
    decided = [run.run.decisions[c] for c in month]
    t = gate.summarize(decided)
    assert (t.disputed, t.accepted, t.questions) == (want(kehe, "disputed"), want(kehe, "accepted"), 0)
    assert t.disputed + t.accepted == kehe.invoice.expected - kehe.invoice.received
    rows = expected(kehe)
    assert t.disputed == sum(money(rows[c]["disputed"]) for c in month)
    assert t.accepted == sum(money(rows[c]["accepted"]) for c in month)
    assert run.run.decisions["K10"].accepted == want(kehe, "k10_taken")


def test_the_reasons_name_each_check(run, kehe):
    a = run.run.allowances
    assert a["K4"].steps[0] == "Fee MCB 03/01-03/14: 5% of $940.00 = $47.00; minimum $65.00 -> $65.00."
    assert a["K6"].steps[0] == "Fee R-55120: 5% of $5,400.00 = $270.00; maximum $175.00 -> $175.00."
    assert a["K7"].facts["change_before_notice"] == (f"{fake.KEHE_ACCOUNTS[kehe.id]['notice']}/fee_schedule",)
    assert a["K8"].facts["fee_amount"] == want(kehe, "k8_fee") and a["K8"].firm == want(kehe, "k8_firm")
    assert a["K9"].steps[0] == "Fee CR-88120: 240 units x $0.29 = $69.60 -> $69.60."
    assert a["K3"].steps[2] == "410 units outside the deal dates are covered by an approved amendment."
    assert (a["K10"].allowed, a["K10"].facts["past_dispute_window"]) == (want(kehe, "k10_allowed"), True)
    assert run.run.shown["K10"].reason == ("Past the dispute window (it closed on Apr 4, 2026): accepted and noted; "
                                           f"the deal allows ${want(kehe, 'k10_allowed')}, $36.00 less.")


def test_every_fee_charge_cites_its_backup(run, kehe):
    for cid in ("K4", "K5", "K6", "K7", "K8", "K9", "K10"):
        f = run.run.findings[cid]
        assert f"ev-backup-{run.run.charges[cid].ref}" in f.evidence_ids
        assert all(i in run.run.evidence for i in f.evidence_ids)
    assert run.run.evidence[f"ev-{fake.KEHE_ACCOUNTS[kehe.id]['policy']}-6.4"].kind == "clause"


def test_the_run_files_the_disputes_and_asks_the_admin(run):
    events = [e.type for e in run.run.events]
    assert "dispute" in events and "approval" in events


def test_readers_that_differ_only_in_form_change_no_decision(kehe):
    """Reader B writes every fee differently (names, signs, a fraction for a percent, defaults left out, the MCB
    quote without its backup sentence, §6.6 unflagged): every fee term still verifies, and expected.csv still holds."""
    month = decide_month(kehe, fake.readers_b_variant(kehe.id))
    fees = {t.params["fee_code"]: t for t in month.run.terms if t.type == "fee_schedule"}
    for code in ("MCB", "Extra Performance", "Free Placements", "Spoils"):
        assert fees[code].status == "verified", (code, fees[code].reasons)
    assert fees["MCB"].params["requires_proof"] is True  # Reader A found the backup sentence
    assert fees["Free Placements"].discretion is True  # Reader A flagged it: still a judgment call
    notice = next(t for t in month.run.terms if t.source_doc_id == fake.KEHE_ACCOUNTS[kehe.id]["notice"])
    assert notice.status == "verified" and notice.params["fee_code"] == "Extra Performance"
    for cid, r in expected(kehe).items():
        d = month.run.shown[cid]
        assert (d.decision, d.disputed, d.accepted, d.gate_row) == (
            r["decision"], money(r["disputed"]), money(r["accepted"]), int(r["gate_row"])), cid


def test_a_real_difference_in_pricing_is_still_disputed(kehe):
    """Same fee, but Reader B applies the $65 minimum per invoice: that changes the price, so K4 and K5 go to a person."""
    variant = [t if not t["exact_quote"].startswith("KeHE will charge a bi weekly") else
               {**t, "params": {**t["params"], "per": "invoice"}} for t in fake.POLICY]
    base, policy = fake.readers(kehe.id), fake.KEHE_ACCOUNTS[kehe.id]["policy"]
    month = decide_month(kehe, {**base, policy: (base[policy][0], {"terms": variant, "unclear": []})})
    mcb = next(t for t in month.run.terms if t.params.get("fee_code") == "MCB")
    assert mcb.status == "disputed"
    assert (month.first["K4"].decision, month.first["K4"].gate_row) == ("ask", 2)
    assert (month.first["K5"].decision, month.first["K5"].gate_row) == ("ask", 2)


def test_the_investigator_is_told_to_cite_the_backup(run, kehe):
    assert run.systems["investigator"].endswith(prompts.render("investigator_fees", kehe))
    system, _ = reader.with_fees(reader.prompt(kehe), kehe)
    assert "fee names, for fee_code: MCB; Extra Performance; Free Placements; Spoils." in system
