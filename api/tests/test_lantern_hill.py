"""Lantern Hill Soda Co. <- KeHE Distributors: KeHE's real 2015 Vendor Policies & Procedures, our side's promotion
submission, broker email and KeHE's fee notices, one month of charges. Both readers (faked answers, through the
real Claude call path, quote check and merge), the engine and the gate reproduce data/accounts/lantern-hill/
expected.csv, and every total comes from the engine."""

import csv
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import adapters, documents, fee_accounts
from api.agents import reader, reader_b, readers, rule_writer
from api.agents.reader import LLMFeeOutput, LLMOutput
from api.agents.rule_writer import LLMRule
from api.contracts import Question
from api.engine import gate
from api.engine import types as eng
from api.engine.allowed import compute_allowed
from api.engine.policy import load_policy
from api.integrations import replay
from api.tests import lantern_hill_answers as fake

ACCOUNT = "lantern-hill"
POLICY_TEXT = Path(__file__).resolve().parents[2] / "data" / "contracts" / "kehe-vendor-policies-2015.txt"


class FakeClaude:
    """Answers Reader A, Reader B (the second Claude prompt) and the rule writer from lantern_hill_answers."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def with_options(self, **_):
        return self

    def _parse(self, output_format, messages, system, **_):
        user = messages[0]["content"]
        if output_format is LLMRule:
            self.calls.append(("rule", ""))
            out = fake.RULE
        else:
            doc = re.search(r"Document ID: (\S+)", user).group(1)
            b = "A second reader reads the same document separately" in system
            self.calls.append(("B" if b else "A", doc))
            out = fake.READERS[doc][1 if b else 0]
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=output_format.model_validate(out))


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)


@pytest.fixture(scope="module")
def acct():
    a = fee_accounts.load(ACCOUNT)
    fee_accounts.register(a)
    return a


def read_all(acct, client):
    """Both readers on every document, in order; an extension is dated from the deal documents read before it."""
    terms, base = [], []
    for doc_id in acct.read_order:
        m = readers.read_both(doc_id, base_terms=base, client=client)
        if m.doc.kind == "deal":
            base += [t for t in m.terms if t.status == "verified"]
        terms += m.terms
    return terms


@pytest.fixture(scope="module")
def run(acct):
    """The month decided: the readers, the engine, the gate, the owner's one answer and the gate again."""
    mp = pytest.MonkeyPatch()
    mp.setattr(replay, "FIXTURES", Path("/nonexistent-fixtures"))
    for k in ("DEMO_MODE", "RECORD_FIXTURES", "GEMINI_API_KEY"):
        mp.delenv(k, raising=False)
    client = FakeClaude()
    policy = load_policy()
    terms = read_all(acct, client)
    eng_terms = fee_accounts.engine_terms(acct, terms)
    fees, sales = fee_accounts.fee_data(acct), fee_accounts.engine_sales(acct)
    allowances, first, final = {}, {}, {}
    for c in acct.all_charges():
        ec = fee_accounts.engine_charge(acct, c)
        a = allowances[c.id] = compute_allowed(ec, eng_terms, sales, (), fees=fees)
        finding = eng.Finding(c.id, Decimal(fake.FINDING["confidence"]), ("ev-1", "ev-2"),
                              fake.FINDING["independent_sources"], fake.FINDING["comeback_answered"])
        first[c.id] = final[c.id] = gate.decide(ec, a, finding, policy)
    asked = [cid for cid, d in first.items() if d.kind == eng.DecisionKind.ASK]
    rules = []
    for n, cid in enumerate(asked, 2):  # one question per asked charge; the owner's answer becomes a rule
        a = allowances[cid]
        term = next(t for t in terms if t.id == next(x.id for x in a.terms if gate.uses_discretion(x, policy)))
        q = Question(id=f"Q-{cid}", to_role="owner", charge_id=cid, text="Accept KeHE's 18% placement fee?",
                     sent_at=datetime(2026, 4, 10, tzinfo=timezone.utc))
        rule = rule_writer.write_rule(q, fake.OWNER_ANSWER, term, acct.distributor, dict(a.facts), n,
                                      acct.config["brand"]["owner"]["name"], datetime(2026, 4, 10, tzinfo=timezone.utc),
                                      client)
        rules.append(adapters.to_engine_rule(rule))
    for cid in asked:
        c = next(x for x in acct.all_charges() if x.id == cid)
        final[cid] = gate.decide(fee_accounts.engine_charge(acct, c), allowances[cid],
                                 eng.Finding(cid, Decimal("0.95"), ("ev-1", "ev-2"), 2, True), policy, rules)
    mp.undo()
    return SimpleNamespace(terms=terms, allowances=allowances, first=first, final=final, asked=asked, rules=rules,
                           calls=client.calls)


def money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


# --- The data -------------------------------------------------------------------------------------------------

def test_the_policy_is_kehes_text_unedited(acct):
    doc, text = acct.docs["kehe-vendor-policies-2015"]
    assert text == POLICY_TEXT.read_text() and doc.kind == "deal" and doc.signed_by_both
    assert len(text.split()) == 5775  # data/contracts/README.md: identical word for word to the SEC filing


def test_the_remittance_adds_up(acct):
    inv = acct.config["invoice"]
    taken = sum((c.amount for c in acct.charges), Decimal(0))
    assert (money(inv["expected"]) - money(inv["received"])) == taken == Decimal("9943.36")
    assert sum((ln["qty"] * Decimal(str(ln["unit_price"])) for ln in acct.config["qbo"]["lines"]), Decimal(0)) == \
        money(inv["expected"])
    assert {c.deducted_on.isoformat() for c in acct.charges} == {acct.fees["as_of"].isoformat()}
    assert all(c.deducted_on < acct.fees["as_of"] for c in acct.older_charges)


def test_documents_and_senders(acct):
    docs = {k: d for k, (d, _) in acct.docs.items()}
    assert documents.can_change_deal(docs["lantern-hill-promotion-2026-03"])  # carries KeHE's acceptance
    broker = docs["lantern-hill-broker-2026-03-24"]
    assert broker.sender == "avery@harborline-brokers.example" and broker.approved_sender
    notice = docs["kehe-ep-admin-2026-03-02"]
    assert notice.sender == "vendorportal@kehe.example" and notice.approved_sender
    assert fee_accounts.noticed_on(acct, notice.id).isoformat() == "2026-03-02"
    assert fee_accounts.noticed_on(acct, broker.id) is None
    for r in acct.backup:  # every backup line belongs to a charge; every proof it names exists
        assert r.deduction_ref in {c.ref for c in acct.all_charges()}
        assert r.proof_doc is None or r.proof_doc in acct.docs
    assert set(acct.fees["codes"]) <= {c.code for c in acct.all_charges()}


def test_account_yaml_keeps_the_account_config_shape(acct):
    """PR #64's AccountConfig forbids extra keys, so the fee wiring stays in fees/fees.yaml."""
    assert set(acct.config) == {"id", "brand", "distributor", "invoice", "deal_docs", "approved_senders",
                                "dispute_start", "qbo", "nessie_description"}
    assert acct.config["id"] == ACCOUNT and all(d in acct.docs for d in acct.config["deal_docs"])


# --- The readers ----------------------------------------------------------------------------------------------

def test_fee_documents_get_the_fee_prompt_and_peak_bar_keeps_its_own(acct):
    doc = acct.docs["kehe-vendor-policies-2015"][0]
    system, schema = reader.prompt_for(doc, reader.PROMPT)
    assert schema is LLMFeeOutput and system.endswith(reader.FEES_PROMPT)
    assert "Lantern Hill Soda Co. (the supplier) and KeHE Distributors (the distributor)" in system
    assert "Peak Bar" not in system and "Northmart" not in system
    system_b, _ = reader.prompt_for(doc, reader_b.PROMPT)
    assert "Lantern Hill Soda Co. (the brand, called Supplier) and KeHE Distributors" in system_b
    for doc_id in documents.PATHS:  # every Peak Bar document: the prompts and schema as recorded
        d, _ = documents.load(doc_id)
        assert reader.prompt_for(d, reader.PROMPT) == (reader.PROMPT, LLMOutput)
        assert reader.prompt_for(d, reader_b.PROMPT) == (reader_b.PROMPT, LLMOutput)


def test_both_readers_read_every_document(run, acct):
    assert sorted(run.calls[:8]) == sorted((r, d) for d in acct.read_order for r in "AB")
    by_id = {t.id: t for t in run.terms}
    verified = {(t.type, t.params.get("fee_code")) for t in run.terms if t.status == "verified"}
    assert verified >= {("fee_schedule", "MCB"), ("fee_schedule", "Extra Performance"),
                        ("fee_schedule", "Free Placements"), ("fee_schedule", "Spoils"), ("dispute_window", None),
                        ("notice_period", None), ("promo_rate", None), ("product_scope", None), ("date_range", None),
                        ("unit_cap", None), ("amendment", None)}
    # Only Reader B read §6.10 as a fee: disputed, and it doesn't knock any other fee out of its pair.
    mkt = [t for t in run.terms if t.params.get("fee_code") == "Marketing Allowance"]
    assert [t.status for t in mkt] == ["disputed"]
    assert by_id["lantern-hill-broker-2026-03-24/amendment"].effective_from.isoformat() == "2026-03-29"
    mcb = next(t for t in run.terms if t.params.get("fee_code") == "MCB")
    assert mcb.params["requires_proof"] is True and mcb.status == "verified"
    window = next(t for t in run.terms if t.type == "dispute_window")
    assert window.params == {"days": 180, "from": "deduction"}


def test_a_made_up_fee_quote_is_rejected(acct):
    doc, text = acct.docs["kehe-vendor-policies-2015"]
    made_up = fake.term("fee_schedule", "KeHE will charge a processing fee of 10% of the MCB amount.",
                        fee_code="MCB", basis="percent", rate="10", per="incident", requires_proof=True)
    out = reader._to_reader_output({"terms": [made_up], "unclear": []}, doc, text, LLMFeeOutput)
    [t] = reader._check(out, doc, text, [])
    assert t.status == "rejected" and t.reasons == ["quote not found in source"]


# --- The decisions --------------------------------------------------------------------------------------------

def expected(acct):
    return {r["charge_id"]: r for r in acct.expected()}


def test_expected_decisions_are_reproduced(run, acct):
    rows = expected(acct)
    assert set(rows) == {c.id for c in acct.all_charges()}
    for cid, r in rows.items():
        d = run.final[cid]
        assert (d.kind.value, d.disputed, d.accepted, d.gate_row) == (
            r["decision"], money(r["disputed"]), money(r["accepted"]), int(r["gate_row"])), cid
        assert (cid in run.asked) == (r["asked"] == "yes"), cid


def test_one_question_then_the_rule(run):
    assert run.asked == ["K8"] and run.first["K8"].gate_row == 4
    [rule] = run.rules
    assert (rule.term_type, rule.condition, rule.counterparty) == (
        eng.TermType.FEE_SCHEDULE, "fee_amount <= 150", "KeHE Distributors")
    assert run.final["K8"].rule_id == rule.id


def test_totals_come_from_the_engine(run, acct):
    month = gate.summarize(run.final[c.id] for c in acct.charges)
    assert (month.disputed, month.accepted, month.questions) == (Decimal("1436.76"), Decimal("8506.60"), 0)
    assert month.disputed + month.accepted == sum((c.amount for c in acct.charges), Decimal(0))
    rows = expected(acct)
    assert month.disputed == sum(money(rows[c.id]["disputed"]) for c in acct.charges)
    assert month.accepted == sum(money(rows[c.id]["accepted"]) for c in acct.charges)
    older = gate.summarize(run.final[c.id] for c in acct.older_charges)
    assert (older.disputed, older.accepted) == (Decimal("0.00"), Decimal("286.20"))


def test_the_reasons_name_each_check(run):
    a = run.allowances
    assert a["K4"].steps[0] == "Fee MCB 03/01-03/14: 5% of $940.00 = $47.00; minimum $65.00 -> $65.00."
    assert a["K6"].steps[0] == "Fee R-55120: 5% of $5,400.00 = $270.00; maximum $175.00 -> $175.00."
    assert a["K7"].facts["change_before_notice"] == ("kehe-ep-admin-2026-03-02/fee_schedule",)
    assert a["K7"].allowed == Decimal("130.00")
    assert a["K8"].facts["fee_amount"] == Decimal("185.76") and a["K8"].firm == Decimal("1032.00")
    assert a["K9"].steps[0] == "Fee CR-88120: 240 units x $0.29 = $69.60 -> $69.60."
    assert a["K3"].steps[2] == "410 units outside the deal dates are covered by an approved amendment."
    assert (a["K10"].allowed, a["K10"].facts["past_dispute_window"]) == (Decimal("250.20"), True)
    assert run.final["K10"].reason == ("Past the dispute window (it closed on Mar 30, 2026): accepted and noted; the "
                                       "deal allows $250.20, $36.00 less.")


def test_expected_csv_is_well_formed(acct):
    with (acct.dir / "expected.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        assert money(r["disputed"]) + money(r["accepted"]) == next(
            c.amount for c in acct.all_charges() if c.id == r["charge_id"]) or r["decision"] == "ask"
