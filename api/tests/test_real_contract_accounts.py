"""Copperline Home Co. <- Walmart and Fizzwick Toys Co. <- Five Below, end to end through the pipeline: Walmart's real
2013 Supplier Agreement and verbatim excerpts of Five Below's 2023 and 2025 Vendor Agreements, our side's purchase
orders, delivery logs and acceptance, and the other side's notices and backup. Faked AI answers
(api/tests/real_contract_answers.py) go through the real Claude call path, the readers' JSON validation, the quote
check, the merge, the engine and the gate; the decisions reproduce each account's expected.csv to the cent, and every
total comes from the engine."""

import csv
import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import accounts, documents, fee_accounts, pipeline
from api.agents.investigator import LLMFinding
from api.agents.negotiator import LLMRehearsal
from api.agents.reader import LLMFeeOutput
from api.engine import gate
from api.integrations import replay
from api.tests import real_contract_answers as fake

CONTRACTS = Path(__file__).resolve().parents[2] / "data" / "contracts"
CLAUSES = ("ev-walmart-supplier-agreement-2013", "ev-five-below-vendor-agreement-")


class FakeClaude:
    """Both readers from real_contract_answers; the Investigator and the rehearsal confident and citing only evidence
    the request holds: a clause and the charge's backup."""

    def __init__(self, account: str):
        self.readers = fake.READERS[account]
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
            out = self.readers[doc][1 if b else 0]
        elif output_format is LLMFinding:
            payload = json.loads(user)
            self.calls.append(("investigator", payload["charge"]["id"]))
            out = {"finding": "The agreement and the backup explain this charge.", "type": "matches_deal",
                   "evidence_ids": self._cite(payload), "confidence": 0.95, "open_questions": []}
        elif output_format is LLMRehearsal:
            payload = json.loads(user)
            self.calls.append(("rehearsal", payload["charge"]["id"]))
            out = {"predicted_rebuttal": "The agreement allows the deduction.",
                   "answer": "The agreement's sentence and the backup show what is owed.",
                   "answer_evidence_ids": self._cite(payload)[:1]}
        else:
            raise AssertionError(f"unexpected agent {output_format.__name__}")
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=output_format.model_validate(out))

    @staticmethod
    def _cite(payload):
        ids = [e["id"] for e in payload["evidence"]]
        clause = [i for i in ids if i.startswith(CLAUSES)][:1]
        backup = [i for i in ids if i == f"ev-backup-{payload['charge']['ref']}"]
        return clause + backup + [f"ev-charge-{payload['charge']['id']}"]


@pytest.fixture(params=["copperline", "fizzwick"])
def account(request, monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", request.param})
    accounts.clear()
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    yield accounts.get(request.param)
    pipeline.reset()
    accounts.clear()


@pytest.fixture
def run(account):
    client = FakeClaude(account.id)
    r = pipeline.start(account=account.id, client=client, background=False)
    return SimpleNamespace(run=r, asked=sorted(q.charge_id for q in r.questions.values()), calls=client.calls)


def money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


def expected(acct):
    with (acct.dir / "expected.csv").open(newline="") as f:
        return {r["charge_id"]: r for r in csv.DictReader(f)}


# --- The data -------------------------------------------------------------------------------------------------

def test_the_contracts_are_the_filings_text(account):
    for name in account.config.contracts:
        doc, text = documents.load(Path(name).stem)
        assert text == (CONTRACTS / name).read_text() and doc.kind == "deal" and doc.signed_by_both
        assert documents.account_of(doc.id).id == account.id
    assert account.config.deal_docs[:len(account.config.contracts)] == [Path(n).stem for n in account.config.contracts]


def test_the_remittance_adds_up(account):
    inv = account.invoice
    month = fee_accounts.charges(account)
    assert inv.expected - inv.received == sum((c.amount for c in month), Decimal(0))
    as_of = fee_accounts.fee_data(account).as_of
    assert all(c.deducted_on <= as_of for c in month + fee_accounts.older_charges(account))


def test_our_records_reach_the_engine(account):
    lines = {ln.deduction_ref: ln for ln in fee_accounts.fee_data(account).lines}
    if account.id == "copperline":
        assert (lines["8840151-SA"].po_type, lines["8840135-SA"].po_type) == ("Regular", "New Store")
        assert lines["FN-26-032611"].caused_by == "carrier" and lines["FN-26-032714"].caused_by == "supplier"
    else:
        assert lines["CB0418830"].variance_pct == Decimal("3.50") and lines["CB0418822"].variance_pct == Decimal("10.91")
        assert lines["CB0418847"].variance_pct is None  # not a quantity fee
        assert lines["CB0418866"].caused_by == "retailer"
        assert str(fee_accounts.governs_from("five-below-vendor-agreement-2025-excerpt", account)) == "2026-03-01"


# --- The decisions --------------------------------------------------------------------------------------------

def test_both_readers_read_every_document(run, account):
    reads = sorted(c for c in run.calls if c[0] in "AB")
    assert reads == sorted((r, d) for d in account.config.deal_docs for r in "AB")
    assert all(t.status == "verified" for t in run.run.terms)  # every quote found in the filing, both readers agree


def test_expected_decisions_are_reproduced(run, account):
    rows = expected(account)
    assert set(rows) == set(run.run.charges)
    for cid, r in rows.items():
        d = run.run.shown[cid]
        assert (d.decision, d.disputed, d.accepted, d.gate_row) == (
            r["decision"], money(r["disputed"]), money(r["accepted"]), int(r["gate_row"])), (cid, d.reason)
    assert run.asked == sorted(c for c, r in rows.items() if r["asked"] == "yes")


def test_totals_come_from_the_engine(run, account):
    rows = expected(account)
    month = {c.id for c in fee_accounts.charges(account)}
    t = gate.summarize(run.run.decisions[c] for c in month)
    assert t.disputed == sum(money(rows[c]["disputed"]) for c in month)
    assert t.accepted == sum(money(rows[c]["accepted"]) for c in month)
    asked = sum((run.run.charges[c].amount for c in month if rows[c]["decision"] == "ask"), Decimal(0))
    assert t.disputed + t.accepted + asked == account.invoice.expected - account.invoice.received


def test_the_reasons_name_each_check(run, account):
    a = run.run.allowances
    if account.id == "copperline":
        assert a["W2"].steps[0] == ("No New Store/Club Discount fee: 8840151 is a regular order; the fee applies only "
                                    "to new store.")
        assert a["W6"].facts["not_owed"] and run.run.shown["W6"].gate_row == 7
        assert a["W9"].steps[0] == "Fee DB-2512-0097: 12% a year on $8,450.00 for 52 days = $144.46 -> $144.46."
    else:
        assert a["F1"].steps[:2] == ("Fee 4500912: 3% of $25,200.00 = $756.00; maximum $750.00 -> $750.00.",
                                     "Plus the administrative fee for 4500912: $100.00.")
        assert "within the 5% the buyer may permit at its discretion" in a["F2"].steps[0]
        assert a["F6"].missing == ("one rule for Documents not uploaded (the deal states 2)",)
        assert a["F9"].facts["past_dispute_window"] and a["F9"].allowed == Decimal("850.00")


def test_every_decided_charge_cites_its_backup(run):
    for cid, f in run.run.findings.items():
        assert f"ev-backup-{run.run.charges[cid].ref}" in f.evidence_ids
        assert all(i in run.run.evidence for i in f.evidence_ids)
