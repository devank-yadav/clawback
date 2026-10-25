"""Accounts (api/accounts.py): every account.yaml loads and checks, each account's files, people and numbers stay its
own, a second account (api/tests/data/accounts/test-oat) runs end to end with a fake Claude, and the account routes.
Peak Bar's numbers are pinned in test_pipeline.py and test_acceptance_p0.py; here they must not move either."""

import json
import re
import shutil
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from api import account_rows, accounts, documents, overview, pipeline, rows
from api.agents.investigator import LLMFinding
from api.agents.negotiator import LLMRehearsal
from api.agents.reader import LLMOutput
from api.agents.rule_writer import LLMRule
from api.db import seed
from api.integrations import moss, nessie, qbo, replay, sms
from api.main import app
from api.tests.test_books import FakeQBO, live_books
from api.tests.test_pipeline import ScenarioClaude
from api.tests.test_reader import answer, term

D = Decimal
client = TestClient(app)
OWNER_ANSWER = "accept if notice is at least 14 days"

S31 = "Supplier will fund a promotional allowance of $0.50 per unit on Hill Oat Classic sold between June 1 and June 30, 2026."
S32 = "The promotional allowance applies to a maximum of 1,000 units in total."
S54 = "Eastway may charge a display fee of up to $400 per month at its discretion, with written notice to Supplier."
OAT_DEAL = [
    term("promo_rate", S31, effective_from="2026-06-01", effective_to="2026-06-30", rate="0.50"),
    term("product_scope", S31, products=["Hill Oat Classic"]),
    term("date_range", S31, start="2026-06-01", end="2026-06-30"),
    term("unit_cap", S32, max_units=1000),
    term("fee_discretion", S54, discretion=True, max_fee="400"),
]


class OatClaude(ScenarioClaude):
    """ScenarioClaude for Hill Oat Co.: reads its deal, cites its clauses, and keeps every system prompt it was sent."""

    def __init__(self):
        super().__init__()
        self.systems: list[str] = []

    def _parse(self, output_format, messages, **kw):
        self.systems.append(kw["system"])
        return super()._parse(output_format, messages, **kw)

    def _reader(self, user):
        doc = re.search(r"Document ID: (\S+)", user).group(1)
        return answer(OAT_DEAL) if doc == "test-oat-deal" else super()._reader(user)

    def _finding(self, user):
        out = super()._finding(user)
        ids = [e["id"] for e in json.loads(user)["evidence"]]
        if not any(i.startswith("ev-spring-promo") for i in out["evidence_ids"]):
            out["evidence_ids"] = [next(i for i in ids if i.startswith("ev-test-oat-deal"))] + out["evidence_ids"]
        return out

    def _rehearsal(self, user):
        ids = [e["id"] for e in json.loads(user)["evidence"]]
        clause = next(i for i in ids if i.startswith(("ev-spring-promo", "ev-test-oat-deal")))
        return {"predicted_rebuttal": "The deduction stands.",
                "answer": "The signed deal and the store sales show the charge is too high.",
                "answer_evidence_ids": [clause]}


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    for k in ("DEMO_MODE", "RECORD_FIXTURES"):
        monkeypatch.delenv(k, raising=False)
    yield
    pipeline.reset()


def final(run):
    return {cid: (d.decision, d.disputed, d.accepted) for cid, d in run.shown.items()}


def last_totals(run):
    return [e.data for e in run.events if e.type == "totals"][-1]


def oat_run(fake=None, answer_owner=True):
    fake = fake or OatClaude()
    run = pipeline.start(None, fake, background=False, account="test-oat")
    if answer_owner:
        pipeline.answer(next(iter(run.questions)), OWNER_ANSWER, client=fake)
    return run, fake


# ---------------------------------------------------------------- loading and checking account.yaml

def test_every_account_in_data_loads_and_checks_clean():
    assert accounts.problems() == []
    assert accounts.every()[0].id == "peak-bar"


def test_peak_bars_account_is_todays_demo():
    a = accounts.get("peak-bar")
    c = a.config
    assert (c.invoice.id, c.invoice.expected, c.invoice.received, c.invoice.month) == \
           ("INV-3102", D("48200.00"), D("41350.00"), "march")
    assert (a.brand.owner.name, a.brand.controller.name, a.distributor.name) == ("Dana Okafor", "Sam Reyes", "Northmart")
    assert c.deal_docs == ["spring-promo", "broker-2026-03-28", "northmart-2026-03-30"]
    assert c.approved_senders == ["dana@peakbar.example", "jordan@peakbar-broker.example"]
    assert (a.months, a.dispute_start("march"), a.dispute_start("april")) == (("march", "april"), 417, 427)
    assert (c.qbo.customer, c.qbo.invoice_no, c.nessie_description) == \
           ("Northmart", "INV-3102", "Northmart remittance INV-3102")
    assert sum(ln.qty * ln.unit_price for ln in c.qbo.lines) == c.invoice.expected  # the sandbox invoice's lines


def _copy(tmp_path, name="peak-bar", **changes):
    """A copy of an account under tmp_path/<new id>, its account.yaml changed."""
    new = changes.get("id", name)
    shutil.copytree(accounts.DATA / "accounts" / name, tmp_path / new)
    path = tmp_path / new / "account.yaml"
    config = yaml.safe_load(path.read_text())
    config.update(changes)
    path.write_text(yaml.safe_dump(config))
    return tmp_path / new


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Accounts from tmp_path only (start with none)."""
    monkeypatch.setattr(accounts, "ROOTS", [tmp_path])
    monkeypatch.setattr(accounts, "ONLY", None)
    accounts.clear()
    yield tmp_path
    accounts.clear()


def test_a_clash_with_another_account_leaves_the_second_out(roots):
    _copy(roots)
    _copy(roots, id="copy-cat")  # same documents, invoice, QuickBooks invoice, Nessie text and disputes
    assert [a.id for a in accounts.every()] == ["peak-bar"]
    said = " ".join(accounts.problems())
    for clash in ("document 'spring-promo' is already peak-bar's", "invoice 'INV-3102' is already peak-bar's",
                  "QuickBooks invoice 'INV-3102'", "Nessie description", "overlap peak-bar's D-0417 to D-0436"):
        assert clash in said


def test_a_bad_account_is_left_out_and_says_why(roots):
    _copy(roots)
    bad = _copy(roots, "peak-bar", id="broken")
    shutil.rmtree(bad / "deals")
    shutil.rmtree(bad / "emails")
    shutil.rmtree(bad / "notices")
    (roots / "wrong-name").mkdir()
    (roots / "wrong-name" / "account.yaml").write_text((bad / "account.yaml").read_text().replace("broken", "other"))
    (roots / "typo").mkdir()
    (roots / "typo" / "account.yaml").write_text("id: typo\nbrand: {name: X}\n")
    assert [a.id for a in accounts.every()] == ["peak-bar"]
    said = "\n".join(accounts.problems())
    assert "broken/account.yaml: deal_docs not in deals/, emails/ or notices/" in said
    assert "wrong-name/account.yaml: id 'other' isn't the folder's name 'wrong-name'" in said
    assert "typo/account.yaml:" in said and "Field required" in said


def test_unknown_account_and_the_current_one():
    with pytest.raises(accounts.UnknownAccount):
        accounts.get("nobody")
    assert accounts.current().id == "peak-bar"


def test_using_sets_the_current_account(two_accounts):
    with accounts.using("test-oat"):
        assert accounts.current() is two_accounts
        assert [c.id for c in rows.charges("june")] == ["T1", "T2", "T3"]  # loaders read it without being told
    assert accounts.current().id == "peak-bar"


# ---------------------------------------------------------------- each account's documents and rows

def test_documents_belong_to_their_account(two_accounts):
    doc, _ = documents.load("test-oat-deal")
    assert (doc.kind, doc.path, doc.signed_by_both) == ("deal", "accounts/test-oat/deals/test-oat-deal.md", True)
    assert documents.account_of("test-oat-deal") is two_accounts
    assert documents.load("test-oat-fall-draft")[0].kind == "draft"
    notice, _ = documents.load("test-oat-notice-2026-06-05")
    assert (notice.kind, notice.sender, notice.approved_sender) == ("notice", "deductions@eastway.example", False)
    assert documents.account_of("spring-promo").id == "peak-bar"
    assert "test-oat-deal" in documents.PATHS and "nope" not in documents.PATHS


def test_approved_senders_are_the_accounts_own(two_accounts):
    """Jordan may change Peak Bar's deal; on Hill Oat's list he isn't, and Hill Oat's owner is."""
    with accounts.using("test-oat"):
        assert not documents.paste("x", kind="email", sender="jordan@peakbar-broker.example").approved_sender
        assert documents.paste("x", kind="email", sender="ari@hilloat.example").approved_sender
    assert documents.paste("x", kind="email", sender="jordan@peakbar-broker.example").approved_sender


def test_a_pasted_clause_belongs_to_the_account_it_was_pasted_for(two_accounts):
    """The readers run on worker threads, where the current account isn't set: the pasted document remembers it."""
    from concurrent.futures import ThreadPoolExecutor

    with accounts.using("test-oat"):
        doc = documents.paste("Eastway may charge a display fee of up to $250 per month at its discretion.")
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(documents.account_of, doc.id).result() is two_accounts


def test_each_account_reads_its_own_rows(two_accounts):
    june = rows.charges("june", account="test-oat")
    assert [(c.id, c.code, c.amount, c.notice_date) for c in june] == [
        ("T1", "PA", D("300.00"), None), ("T2", "PA", D("300.00"), None), ("T3", "DF", D("300.00"), date(2026, 6, 5))]
    assert [s.promo_units for s in rows.sales(account="test-oat")] == [600, 600]
    assert rows.prior_payments(account="test-oat") == []  # no payments/ folder: no rows
    assert [p.promo_id for p in rows.promo_plan(account="test-oat")] == ["SUMMER-26"]
    assert [c.id for c in rows.charges("march")] == ["C1", "C2", "C3", "C4", "C5", "C6"]  # Peak Bar's by default
    assert rows.charges("june") == []  # Peak Bar has no June


def test_line_ref_loads_but_stays_out_of_the_json_when_unset(tmp_path):
    shutil.copytree(accounts.get("peak-bar").dir, tmp_path / "pb")
    path = tmp_path / "pb" / "charges" / "march.csv"
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0] + ",line_ref", lines[1] + ",L-7", *(ln + "," for ln in lines[2:])]) + "\n")
    c1, c2, *_ = rows.charges("march", tmp_path / "pb")
    assert (c1.line_ref, c2.line_ref) == ("L-7", None)
    assert c1.model_dump(mode="json")["line_ref"] == "L-7" and "line_ref" not in c2.model_dump(mode="json")


def test_ops_and_history_rows(two_accounts):
    ops = account_rows.ops("test-oat")
    assert [(d.line_ref, d.shipped_units, d.received_units, d.unit_price) for d in ops.deliveries] == [
        ("L-1", 480, 480, D("2.10"))]
    assert [(p.product, p.agreed_price, p.effective_to) for p in ops.prices] == [("Hill Oat Classic", D("2.10"), None)]
    assert [(t.key, t.value, t.quote) for t in ops.terms] == [("shortage_claim_days", "30", None)]
    assert [r.recovered for r in account_rows.deductions("test-oat")] == [D("250.00"), D("0.00"), D("0.00")]
    assert account_rows.ops("peak-bar") == account_rows.Ops()  # no such files: no rows
    assert account_rows.invoices("peak-bar") == [] or all(r.invoice for r in account_rows.invoices("peak-bar"))


# ---------------------------------------------------------------- the second account, end to end

def test_a_second_account_runs_end_to_end(two_accounts):
    run, fake = oat_run()
    assert final(run) == {"T1": ("accept", D(0), D(300)), "T2": ("split", D(100), D(200)), "T3": ("accept", D(0), D(300))}
    t = last_totals(run)
    assert (t.taken, t.disputed, t.accepted, t.waiting, t.questions) == (D(900), D(100), D(800), D(0), 1)
    rem = run.events[0].data.remittance
    assert (rem.id, rem.counterparty, rem.invoice_id, rem.expected, rem.received) == \
           ("REM-INV-9001", "Eastway", "INV-9001", D("10000.00"), D("9100.00"))
    (dispute,) = {e.data.id: e.data for e in run.events if e.type == "dispute"}.values()
    assert (dispute.id, dispute.counterparty, dispute.total) == ("D-0901", "Eastway", D(100))
    (q,) = run.questions.values()
    assert q.text.startswith("Eastway took $300: Display fee (notice Jun 5).")
    logs = [e.data.text for e in run.events if e.type == "log"]
    assert "Eastway paid $9,100 on invoice INV-9001 for $10,000. $900 was taken out in 3 charges." in logs
    assert any(x.startswith("Asked Ari one question about T3") for x in logs)
    assert any("Within the $5,000 limit Ari set" in x for x in logs)
    assert not any("Northmart" in x or "Dana" in x or "Sam" in x for x in logs)
    rule = next(e.data for e in run.events if e.type == "rule")
    assert (rule.label, rule.counterparty, rule.approver) == ("Rule #1", "Eastway", "Ari Lane")
    assert run.evidence[f"ev-{rule.id}"].person == "Ari Lane (owner)"
    # $800 is within the approval limit, so the memo posts on policy, to Eastway in QuickBooks
    approval = [e.data for e in run.events if e.type == "approval"][-1]
    assert (approval.status, approval.amount) == ("approved", D(800))
    (memo,) = [c for c in qbo.books().calls if c[0] == "CreditMemo"]
    assert memo[2]["customer"] == "Eastway"
    assert any(c[0] == "Payment" and c[2]["invoice"] == "INV-9001" for c in qbo.books().calls)
    # every agent was told it works for Hill Oat Co. against Eastway
    assert fake.systems and all("Peak Bar" not in s and "Northmart" not in s for s in fake.systems)
    assert any("Hill Oat Co." in s and "Eastway" in s for s in fake.systems)
    assert run.ops.deliveries[0].line_ref == "L-1"  # loaded for the engine


def test_rules_belong_to_their_account(two_accounts):
    """Hill Oat's owner answers first; Peak Bar's C6 still asks Dana, her rule is Peak Bar's Rule #1, April uses it."""
    oat, _ = oat_run()
    oat_rule = pipeline.rules_of("test-oat")[0]
    assert (oat_rule.id, oat_rule.label) == ("rule-1", "Rule #1")
    march = pipeline.start("march", ScenarioClaude(), background=False)
    assert final(march)["C6"][0] == "ask" and len(march.questions) == 1  # Ari's rule doesn't answer for Dana
    pipeline.answer(next(iter(march.questions)), OWNER_ANSWER, client=ScenarioClaude())
    pb_rule = pipeline.rules_of("peak-bar")[0]
    assert (pb_rule.id, pb_rule.label, pb_rule.approver) == ("rule-2", "Rule #1", "Dana Okafor")
    assert (last_totals(march).disputed, last_totals(march).accepted) == (D(4120), D(2730))
    april = pipeline.start("april", ScenarioClaude(), background=False)
    assert final(april) == {"A1": ("accept", D(0), D(1200)), "A2": ("dispute", D(800), D(0))}
    assert {d.rule_id for d in april.shown.values()} == {"rule-2"} and not april.questions
    # UNDO undoes the account's own newest rule
    _, undone = pipeline.answer(next(iter(oat.questions)), "UNDO")
    assert undone.id == "rule-1" and pipeline.rules_of("peak-bar")[0].status == "active"


def test_a_new_run_replaces_only_its_own_accounts_runs(two_accounts):
    oat, _ = oat_run(answer_owner=False)
    march = pipeline.start("march", ScenarioClaude(), background=False)
    assert oat.replaced_by is None and pipeline.is_open(next(iter(oat.questions.values())))
    again, _ = oat_run(answer_owner=False)
    assert oat.replaced_by == again.id and march.replaced_by is None


def test_a_month_the_account_doesnt_have_is_refused(two_accounts):
    with pytest.raises(pipeline.UnknownMonth, match="test-oat has no march charges"):
        pipeline.start("march", ScenarioClaude(), background=False, account="test-oat")


def test_the_portal_answers_on_the_second_accounts_dispute(two_accounts):
    from api import disputes

    run, _ = oat_run()
    msgs = disputes.post("D-0901", "Agreed on the week 3 to 4 line.", attachment_doc_id="amendment-1")
    assert [m.from_party for m in msgs] == ["northmart"]  # amendment-1 is Peak Bar's: held, not read
    held = [e.data.text for e in run.events if e.type == "log"][-1]
    assert held == "Eastway attached a document Clawback doesn't have (amendment-1): held for Ari."


# ---------------------------------------------------------------- routes

@pytest.fixture
def api(two_accounts):
    yield client


def test_get_accounts_lists_peak_bar_first(api):
    got = api.get("/accounts").json()
    assert [a["id"] for a in got] == ["peak-bar", "test-oat"]
    assert got[0]["brand"]["name"] == "Peak Bar Co." and got[0]["distributor"]["name"] == "Northmart"
    assert got[0]["invoice"] == {"id": "INV-3102", "expected": 48200.0, "received": 41350.0, "month": "march",
                                 "period_start": "2026-03-01", "period_end": "2026-03-31"}
    assert set(got[0]) == {"id", "brand", "distributor", "invoice", "latest_run_id", "supplier"} and got[1]["latest_run_id"] is None
    run, _ = oat_run(answer_owner=False)
    assert api.get("/accounts").json()[1]["latest_run_id"] == run.id


def test_overview_before_the_payment_arrives(api):
    o = api.get("/accounts/test-oat/overview").json()
    assert [m["month"] for m in o["months"]] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    assert o["months"][3:] == [
        {"month": "2026-04", "invoiced": 8000.0, "paid": 7600.0, "deducted": 400.0, "recovered": 250.0},
        {"month": "2026-05", "invoiced": 9000.0, "paid": 8500.0, "deducted": 500.0, "recovered": 0.0},
        {"month": "2026-06", "invoiced": 10000.0, "paid": 0.0, "deducted": 0.0, "recovered": 0.0}]
    assert o["kpis"] == {"invoiced_6m": 27000.0, "collected_6m": 16100.0, "deducted_6m": 900.0, "recovered_6m": 250.0,
                         "recovery_rate": 0.2778, "open_disputes": 1, "open_balance": 10300.0,
                         "wrongly_taken_6m": 0.0, "lost_past_window": 0.0, "claimable_now": 0.0}
    assert o["deductions_by_type"] == [
        {"code": "PA", "label": "Promotional allowance", "count": 1, "amount": 400.0},
        {"code": "SH", "label": "Shortage", "count": 1, "amount": 300.0},
        {"code": "DF", "label": "Display fee", "count": 1, "amount": 200.0}]
    assert [r["invoice"] for r in o["recent_remittances"]] == ["INV-8901", "INV-8801", "INV-8001"]
    assert o["current"] == {"invoice": "INV-9001", "expected": 10000.0, "received": 9100.0, "deducted": 900.0,
                            "run_id": None, "status": "waiting_for_payment", "value": None}
    assert o["account"]["id"] == "test-oat"


def test_overview_after_the_run(api):
    run, _ = oat_run()
    o = api.get("/accounts/test-oat/overview").json()
    assert o["months"][-1] == {"month": "2026-06", "invoiced": 10000.0, "paid": 9100.0, "deducted": 900.0,
                               "recovered": 0.0}
    k = o["kpis"]
    assert (k["collected_6m"], k["deducted_6m"], k["recovery_rate"]) == (25200.0, 1800.0, 0.1389)
    assert (k["open_disputes"], k["open_balance"]) == (2, 400.0)  # SH still open + T2's line; $300 + $10,000-9,100-800
    assert {t["code"]: (t["count"], t["amount"]) for t in o["deductions_by_type"]} == {
        "PA": (3, 1000.0), "DF": (2, 500.0), "SH": (1, 300.0)}
    assert o["recent_remittances"][0]["invoice"] == "INV-9001" and o["recent_remittances"][0]["paid"] == 9100.0
    assert (o["current"]["run_id"], o["current"]["status"]) == (run.id, "finished")
    assert o["account"]["latest_run_id"] == run.id


def test_overview_counts_a_charge_in_history_and_in_the_run_once(api, monkeypatch, two_accounts):
    run, _ = oat_run()
    rows_ = account_rows.deductions("test-oat")
    again = rows_ + [account_rows.DeductionHistory(month="2026-06", ref="EW-1", code="PA", amount=D("300.00"))]
    monkeypatch.setattr(account_rows, "deductions", lambda account=None: again)
    o = api.get("/accounts/test-oat/overview").json()
    assert {t["code"]: t["count"] for t in o["deductions_by_type"]}["PA"] == 3


def test_overview_of_peak_bar_without_history(api):
    o = api.get("/accounts/peak-bar/overview").json()
    assert o["months"][-1]["month"] == "2026-03" and o["current"]["deducted"] == 6850.0
    assert api.get("/accounts/nobody/overview").status_code == 404


def test_parse_month_reads_the_ways_a_month_is_written():
    for text in ("2026-02", "2026-02-28", "February 2026", "feb 2026", "february"):
        assert overview.parse_month(text, "2026-06") == "2026-02", text
    assert overview.parse_month("december", "2026-06") == "2025-12"  # the latest December up to June 2026
    assert overview.parse_month("not a month", "2026-06") is None


def test_post_runs_takes_an_account_and_a_month(api, monkeypatch):
    started = []
    monkeypatch.setattr(pipeline, "start", lambda kind, account=None, **_: started.append((kind, account.id))
                        or SimpleNamespace(id="run-x"))
    assert api.post("/runs", json={"account": "test-oat"}).json() == {"run_id": "run-x", "events_url": "/runs/run-x/events"}
    assert api.post("/runs", json={}).status_code == 200 and api.post("/runs").status_code == 200
    assert started == [("june", "test-oat"), ("march", "peak-bar"), ("march", "peak-bar")]
    assert api.post("/runs", json={"account": "nobody"}).status_code == 404


def test_post_runs_refuses_a_month_the_account_doesnt_have(api):
    r = api.post("/runs", json={"account": "test-oat", "kind": "march"})
    assert r.status_code == 422 and "test-oat has no march charges" in r.text


def test_runs_latest_and_summary_per_account(api, monkeypatch):
    assert api.get("/runs/latest", params={"account": "test-oat"}).status_code == 404
    run, _ = oat_run(answer_owner=False)
    assert api.get("/runs/latest", params={"account": "test-oat"}).json()["run_id"] == run.id
    assert api.get("/runs/latest").status_code == 404  # Peak Bar has none yet
    assert api.get("/runs/latest", params={"account": "nobody"}).status_code == 404
    monkeypatch.setenv("CLAWBACK_READONLY_TOKEN", "t0ken-for-tests")
    auth = {"Authorization": "Bearer t0ken-for-tests"}
    s = api.get("/summary", params={"account": "test-oat"}, headers=auth).json()
    assert (s["run_id"], s["pending_question"]["charge_id"]) == (run.id, "T3")
    assert api.get("/summary", headers=auth).json()["run_id"] is None  # Peak Bar: the recorded run until a live one


def test_payments_per_account_and_the_northmart_alias(api):
    paid = api.post("/payments/test-oat").json()
    assert paid["via"] == "direct" and pipeline.RUNS[paid["run_id"]].account.id == "test-oat"
    alias = api.post("/payments/northmart").json()
    assert pipeline.RUNS[alias["run_id"]].account.id == "peak-bar"
    assert pipeline.RUNS[api.post("/payments/peak-bar").json()["run_id"]].account.id == "peak-bar"
    assert api.post("/payments/nobody").status_code == 404


def test_payments_post_the_accounts_own_deposit(api, monkeypatch):
    posted = []

    class Fake:
        def post_deposit(self, amount, description):
            posted.append((amount, description))
            return nessie.Deposit("dep-1", amount, description, None)

    monkeypatch.setattr(nessie, "client", lambda: Fake())
    monkeypatch.setattr(pipeline, "start_for_deposit", lambda d, account=None, **_: SimpleNamespace(id="run-x"))
    assert api.post("/payments/test-oat").json()["deposit_id"] == "dep-1"
    assert api.post("/payments/northmart").json()["deposit_id"] == "dep-1"
    assert posted == [(D("9100.00"), "Eastway remittance INV-9001"), (D("41350.00"), "Northmart remittance INV-3102")]


def test_the_cap_route_takes_an_account(api):
    assert api.get("/db/cap", params={"account": "test-oat", "promo_id": "SUMMER-26"}).status_code == 503  # no db


# ---------------------------------------------------------------- Nessie, QuickBooks, the seed

def test_a_deposit_starts_the_account_it_names(two_accounts):
    found = accounts.for_deposit
    assert found("Eastway remittance INV-9001").id == "test-oat"
    assert found("EASTWAY  remittance inv-9001 (wire)").id == "test-oat"
    assert found("Northmart remittance INV-3102").id == "peak-bar"
    assert found("Northmart payment").id == "peak-bar"  # names only one account's distributor
    assert found("Payroll") is None
    run = pipeline.start_for_deposit(nessie.Deposit("dep-7", D("9100.00"), "Eastway remittance INV-9001", None),
                                     client=OatClaude(), background=False)
    assert (run.account.id, run.kind, run.events[0].data.remittance.nessie_tx_id) == ("test-oat", "june", "dep-7")


def test_the_poller_hands_on_only_deposits_that_pay_an_account(two_accounts):
    seen = []

    class Bank:
        def __init__(self):
            self.rows = []

        def deposits(self):
            return self.rows

    bank = Bank()
    poller = nessie.Poller(bank, seen.append)
    poller.tick()  # history
    bank.rows = [nessie.Deposit("a", D(1), "Payroll", None), nessie.Deposit("b", D(9100), "Eastway remittance INV-9001", None)]
    assert [d.id for d in poller.tick()] == ["b"] and [d.id for d in seen] == ["b"]


def test_a_reset_undoes_every_accounts_customer(two_accounts, monkeypatch):
    fake = FakeQBO()
    monkeypatch.setattr(qbo, "_books", live_books(fake))
    qbo.books().undo_demo_writes()
    asked = [r.url.params["query"] for r in fake.requests if r.url.path.endswith("/query")]
    assert "select * from Customer where DisplayName = 'Northmart'" in asked
    assert "select * from Customer where DisplayName = 'Eastway'" in asked
    assert qbo.account_customers() == ["Northmart", "Eastway"]


def test_the_seed_loads_every_account(two_accounts):
    got = seed.seed_rows()
    assert {r["account_id"] for t in got.values() for r in t} == {"peak-bar", "test-oat"}
    oat = [r for r in got["charges"] if r["account_id"] == "test-oat"]
    assert [(r["id"], r["remittance_id"], r["source_file"]) for r in oat] == [
        ("T1", "REM-INV-9001", "charges/june.csv"), ("T2", "REM-INV-9001", "charges/june.csv"),
        ("T3", "REM-INV-9001", "charges/june.csv")]
    assert [r["id"] for r in got["remittances"]] == ["REM-INV-3102", "REM-INV-9001"]
    assert len({(r["account_id"], r["id"]) for r in got["charges"]}) == len(got["charges"])  # the key holds


def test_the_seed_puts_every_account_in_the_database(two_accounts, monkeypatch):
    import os

    from api.db import conn, reads

    psycopg = pytest.importorskip("psycopg")
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("set TEST_DATABASE_URL to a throwaway Postgres to run the database tests")
    name = f"accounts_test_{__import__('uuid').uuid4().hex[:8]}"
    options = f"-c search_path={name},public"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {name}")
        try:
            with psycopg.connect(url, autocommit=True, options=options) as db:
                seeded = seed.seed(db)
                assert seed.seed(db).inserted == {t: 0 for t in seed.KEYS}
                monkeypatch.setenv("DATABASE_URL", url)
                monkeypatch.setenv("PGOPTIONS", options)
                conn.reset()
                assert repr(rows.charges("june", account="test-oat")) == repr(
                    rows.charges_from_files("june", account="test-oat"))
                assert repr(rows.charges("march")) == repr(rows.charges_from_files("march"))
                weeks = reads.cap_query(db, "test-oat", "SUMMER-26", seeded.weekly)
                assert [(w[2], w[3], w[4]) for w in weeks] == [(600, 600, 1000), (600, 1200, 1000)]
        finally:
            conn.reset()
            admin.execute(f"DROP SCHEMA {name} CASCADE")


def test_texts_name_the_accounts_people(two_accounts):
    run, _ = oat_run(answer_owner=False)
    (question, summary) = sms.outbox[-2:]  # the question went out mid-gate, the run's summary after the gate
    assert question[0] == "owner" and question[1].startswith("Eastway took $300")
    assert summary == ("owner", "Clawback checked Eastway's 3 deductions: $100 being recovered, $500 fair, 1 question "
                                "for you. 6-month check: $0 still claimable.")
    assert moss.Outcome().matches == ()


def test_every_data_account_loads(every_account):
    assert every_account[0].id == "peak-bar" and len({a.id for a in every_account}) == len(every_account)
    for a in every_account:
        assert a.config.deal_docs and all(d in a.docs for d in a.config.deal_docs), a.id
