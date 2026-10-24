"""D9 / F10: the controller's yes posts the credit memo and the open-balance note; a no posts nothing."""

import itertools
import json
from decimal import Decimal as D

import httpx
import pytest
from fastapi.testclient import TestClient

from api import disputes, pipeline
from api.integrations import qbo, replay, sms
from api.tests.test_disputes import PortalClaude, finished_march
from api.tests.test_pipeline import ScenarioClaude, last_totals

OWNER, SAM = "+15550000001", "+15550000002"


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    for k in (*qbo.KEYS, *sms.KEYS, "DEMO_MODE", "RECORD_FIXTURES", "PUBLIC_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OWNER_PHONE", OWNER)
    monkeypatch.setenv("CONTROLLER_PHONE", SAM)
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset(), disputes.reset()
    yield
    pipeline.reset(), disputes.reset()


def pending(run):
    (a,) = [e.data for e in run.events if e.type == "approval" and e.data.status == "pending"]
    return a


def posts(run):
    return [e.data for e in run.events if e.type == "ledger_post"]


def test_yes_posts_memo_applies_it_and_notes_the_open_balance():
    run = finished_march(ScenarioClaude())
    assert not posts(run)  # nothing posts before Sam says yes
    approval, made = pipeline.decide_approval(pending(run).id, True)
    assert approval.status == "approved" and approval.decided_at
    memo, note = made
    assert (memo.qbo_entity, memo.amount, memo.status, [ln.charge_id for ln in memo.lines]) == (
        "credit_memo", D(2730), "posted", ["C1", "C3", "C6"])
    assert memo.qbo_id.startswith("sim-") and "Applied to INV-3102" in memo.note and "Simulated" in memo.note
    assert (note.qbo_entity, note.amount, [ln.charge_id for ln in note.lines]) == (
        "invoice_note", D(4120), ["C1", "C2", "C4", "C5"])
    calls = qbo.books().calls
    assert [(e, rid.rsplit("-", 1)[-1]) for e, rid, _ in calls] == [("CreditMemo", "memo"), ("Payment", "apply"),
                                                                    ("Invoice", "note")]
    assert last_totals(run).accepted == D(2730)  # posting doesn't change the meters


def test_no_posts_nothing_keeps_the_note_and_tells_dana():
    run = finished_march(ScenarioClaude())
    approval, made = pipeline.decide_approval(pending(run).id, False, "Hold until Dana checks the display fee")
    assert (approval.status, approval.note, made, posts(run)) == ("refused", "Hold until Dana checks the display fee", [], [])
    assert not qbo.books().calls
    assert any(role == "owner" and "held the $2,730 credit memo" in text for role, text in sms.outbox)


def test_one_answer_per_approval():
    run = finished_march(ScenarioClaude())
    a = pending(run)
    pipeline.decide_approval(a.id, True)
    with pytest.raises(pipeline.AlreadyDecided):
        pipeline.decide_approval(a.id, False)
    assert len(posts(run)) == 2 and len(qbo.books().calls) == 3


def test_stand_in_answers_a_repeated_request_id_like_intuit():
    b = qbo.StandInBooks()
    first = b.post_credit_memo("AP-x-memo", [qbo.Line("C1", "x", D(5))], "m")
    assert b.post_credit_memo("AP-x-memo", [qbo.Line("C1", "x", D(5))], "m") == first and len(b.calls) == 1


def test_amendment_concession_posts_on_policy_and_updates_the_note():
    fake = PortalClaude()
    run = finished_march(fake)
    pipeline.decide_approval(pending(run).id, True)
    disputes.post("D-0417", "Signed amendment attached.", attachment_doc_id="amendment-1", client=fake)
    memo2, note2 = posts(run)[2:]
    assert (memo2.amount, [ln.charge_id for ln in memo2.lines], memo2.status) == (D(1000), ["C4"], "posted")
    assert note2.amount == D(3120) and "C4 NM-2236 $540.00" in note2.note


def test_inbox_lists_what_waits_on_people():
    fake = ScenarioClaude()
    run = pipeline.start("march", fake, background=False)
    questions, approvals = pipeline.inbox()
    assert [q.charge_id for q in questions] == ["C6"] and approvals == []
    pipeline.answer(questions[0].id, "accept if notice is at least 14 days", client=fake)
    questions, approvals = pipeline.inbox()
    assert questions == [] and [a.amount for a in approvals] == [D(2730)]


# ---------------------------------------------------------------- texts in, through the webhook

def text(client, frm, body, **headers):
    return client.post("/webhooks/twilio/sms", content=f"From={frm.replace('+', '%2B')}&Body={body}",
                       headers={"content-type": "application/x-www-form-urlencoded", **headers})


@pytest.fixture
def api(monkeypatch):
    from api.agents import claude as claude_mod
    from api.main import app

    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    return TestClient(app)


def test_dana_and_sam_reply_by_text(api):
    run = pipeline.start("march", ScenarioClaude(), background=False)
    r = text(api, OWNER, "accept if notice is at least 14 days")
    assert r.status_code == 200 and "<Message>Saved: accept display fees" in r.text  # the reply goes back as TwiML
    assert run.shown["C6"].rule_id == "rule-1"
    assert "Approved: $2,730 credit memo" in text(api, SAM, "YES").text
    assert [p.qbo_entity for p in posts(run)] == ["credit_memo", "invoice_note"]


def test_sam_refuses_by_text_with_a_note(api):
    run = finished_march(ScenarioClaude())
    text(api, SAM, "No - wait for Dana")
    assert (run.events and [e.data for e in run.events if e.type == "approval"][-1].note) == "wait for Dana"
    assert posts(run) == []


def test_unclear_reply_from_sam_is_asked_again(api):
    run = finished_march(ScenarioClaude())
    r = text(api, SAM, "yes but only 2 lines")
    assert pending(run) and pipeline.replies.CONTROLLER_REASK_TEXT in r.text


def test_unknown_number_and_bad_signature(api, monkeypatch):
    run = finished_march(ScenarioClaude())
    text(api, "+15559999999", "YES")
    assert pending(run)  # a stranger can't approve
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://clawback.example")
    assert text(api, SAM, "YES").status_code == 403
    from twilio.request_validator import RequestValidator
    sig = RequestValidator("test-auth-token").compute_signature(
        "https://clawback.example/webhooks/twilio/sms", {"From": SAM, "Body": "YES"})
    assert text(api, SAM, "YES", **{"X-Twilio-Signature": sig}).status_code == 200
    assert [e.data for e in run.events if e.type == "approval"][-1].status == "approved"


def test_approval_route_returns_what_posted(api):
    run = finished_march(ScenarioClaude())
    r = api.post(f"/approvals/{pending(run).id}", json={"approve": True}).json()
    assert r["approval"]["status"] == "approved" and r["ledger_post"]["amount"] == 2730.0
    assert [p["qbo_entity"] for p in r["ledger_posts"]] == ["credit_memo", "invoice_note"]
    assert api.post(f"/approvals/{pending_id(run)}", json={"approve": False}).status_code == 409
    assert api.get("/inbox").json()["approvals"] == []


def pending_id(run):
    return [e.data for e in run.events if e.type == "approval"][0].id


# ---------------------------------------------------------------- the live QuickBooks client, offline

class FakeQBO:
    """The seeded sandbox, offline: Northmart (58), the allowance item (21), INV-3102 (130) and the seed's $41,350
    payment (150), plus whatever is written to it. A delete needs the latest SyncToken, and a credit memo that a
    payment still applies can't be deleted."""

    def __init__(self, fail=False):
        self.requests: list[httpx.Request] = []
        self.fail = fail
        self.ids = itertools.count(201)
        self.invoice = {"Id": "130", "SyncToken": "2", "CustomerRef": {"value": "58"}}
        self.rows = {"CreditMemo": {}, "Payment": {"150": {
            "Id": "150", "SyncToken": "0", "TotalAmt": 41350.0, "CustomerRef": {"value": "58"},
            "Line": [{"Amount": 41350.0, "LinkedTxn": [{"TxnId": "130", "TxnType": "Invoice"}]}]}}}

    def applied(self, memo_id):
        return any(lt == {"TxnId": memo_id, "TxnType": "CreditMemo"}
                   for p in self.rows["Payment"].values() for ln in p["Line"] for lt in ln["LinkedTxn"])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            return httpx.Response(500, text="boom")
        path, q = request.url.path, request.url.params
        if path.endswith("/query"):
            entity = q["query"].split()[3]
            rows = {"Customer": [{"Id": "58"}], "Item": [{"Id": "21"}], "Invoice": [self.invoice],
                    **{e: list(found.values()) for e, found in self.rows.items()}}[entity]
            return httpx.Response(200, json={"QueryResponse": {entity: rows} if rows else {}})
        body = json.loads(request.content)
        entity = {"creditmemo": "CreditMemo", "payment": "Payment", "invoice": "Invoice"}[path.rsplit("/", 1)[-1]]
        if q.get("operation") == "delete":
            row = self.rows[entity].get(body["Id"])
            stale = row is None or row["SyncToken"] != body["SyncToken"]
            if stale or (entity == "CreditMemo" and self.applied(body["Id"])):
                return httpx.Response(400, text=f"can't delete {entity} {body['Id']}")
            del self.rows[entity][body["Id"]]
            return httpx.Response(200, json={entity: {"status": "Deleted", "domain": "QBO", "Id": body["Id"]}})
        if entity == "Invoice":  # the sparse note update
            self.invoice = {**self.invoice, "PrivateNote": body["PrivateNote"],
                            "SyncToken": str(int(self.invoice["SyncToken"]) + 1)}
            return httpx.Response(200, json={"Invoice": self.invoice})
        made = {**body, "Id": str(next(self.ids)), "SyncToken": "0",
                "TotalAmt": body.get("TotalAmt", sum(ln["Amount"] for ln in body["Line"]))}
        self.rows[entity][made["Id"]] = made
        return httpx.Response(200, json={entity: made})


def live_books(fake):
    http = httpx.Client(base_url=f"{qbo.BASE}/9341", transport=httpx.MockTransport(fake))
    return qbo.LiveBooks("9341", token=lambda: "test-access-token", http=http)


def test_live_client_sends_intuit_shaped_writes_with_request_ids():
    fake = FakeQBO()
    b = live_books(fake)
    memo = b.post_credit_memo("AP-1-memo", [qbo.Line("C1", "NM-2229: Spring promo week 1", D("1200"))], "Clawback AP-1")
    b.apply_to_invoice("AP-1-apply", "INV-3102", memo.id, D("1200"))
    b.note_open_balance("AP-1-note", "INV-3102", "Open $4,120.00 disputed", D("4120"))
    writes = [r for r in fake.requests if r.method == "POST"]
    assert [(r.url.path.rsplit("/", 1)[-1], r.url.params["requestid"], r.url.params["minorversion"]) for r in writes] == [
        ("creditmemo", "AP-1-memo", "75"), ("payment", "AP-1-apply", "75"), ("invoice", "AP-1-note", "75")]
    cm, pay, inv = (json.loads(r.content) for r in writes)
    assert cm["CustomerRef"] == {"value": "58"} and cm["Line"][0]["SalesItemLineDetail"]["ItemRef"] == {"value": "21"}
    assert pay["TotalAmt"] == 0 and [l["LinkedTxn"][0]["TxnType"] for l in pay["Line"]] == ["Invoice", "CreditMemo"]
    assert (cm["PrivateNote"], pay["PrivateNote"]) == ("Clawback AP-1", "Clawback AP-1-apply")  # how a reset finds them
    assert inv == {"Id": "130", "SyncToken": "2", "sparse": True, "PrivateNote": "Open $4,120.00 disputed"}
    assert all(r.headers["Authorization"] == "Bearer test-access-token" for r in fake.requests)


def test_live_client_failure_shows_as_failed_not_posted(monkeypatch):
    run = finished_march(ScenarioClaude())
    monkeypatch.setattr(qbo, "_books", live_books(FakeQBO(fail=True)))
    monkeypatch.setattr(replay.time, "sleep", lambda s: None)
    _, made = pipeline.decide_approval(pending(run).id, True)
    assert [(p.status, p.qbo_id) for p in made] == [("failed", None)]


def test_demo_mode_posts_to_the_stand_in_even_with_keys(monkeypatch):
    """A recorded QuickBooks write never matches a new run (its request id and date change), so DEMO_MODE uses the
    stand-in instead of failing at Sam's yes with Wi-Fi off."""
    run = finished_march(ScenarioClaude())
    for k in qbo.KEYS:
        monkeypatch.setenv(k, "set")
    monkeypatch.setenv("DEMO_MODE", "true")
    qbo.reset()
    books = qbo.books()
    assert isinstance(books, qbo.StandInBooks) and "DEMO_MODE" in books.why
    _, made = pipeline.decide_approval(pending(run).id, True)
    assert [p.status for p in made] == ["posted", "posted"] and all(p.qbo_id.startswith("sim-") for p in made)
    assert "Simulated: DEMO_MODE is on" in made[0].note
    monkeypatch.delenv("DEMO_MODE")
    qbo.reset()
    assert isinstance(qbo.books(), qbo.LiveBooks)  # keys and no DEMO_MODE: the sandbox


# ---------------------------------------------------------------- POST /demo/reset undoes the books

def sandbox_yes(monkeypatch, fake):
    """March decided, then Sam's yes written to the fake sandbox."""
    run = finished_march(ScenarioClaude())
    monkeypatch.setattr(qbo, "_books", live_books(fake))
    pipeline.decide_approval(pending(run).id, True)
    return run


def test_reset_deletes_the_payment_then_the_memo_and_clears_the_note(monkeypatch):
    fake = FakeQBO()
    sandbox_yes(monkeypatch, fake)
    assert (set(fake.rows["CreditMemo"]), set(fake.rows["Payment"])) == ({"201"}, {"150", "202"})
    assert fake.invoice["PrivateNote"].startswith("Open $4,120.00 disputed with Northmart:")
    sent = len(fake.requests)
    undone = qbo.books().undo_demo_writes()
    assert [(u.entity, u.id, u.action, u.simulated) for u in undone] == [
        ("Payment", "202", "deleted", False), ("CreditMemo", "201", "deleted", False),
        ("Invoice", "130", "note cleared", False)]
    writes = [r for r in fake.requests[sent:] if r.method == "POST"]
    assert [(r.url.path.rsplit("/", 1)[-1], r.url.params.get("operation"), json.loads(r.content)) for r in writes] == [
        ("payment", "delete", {"Id": "202", "SyncToken": "0"}),
        ("creditmemo", "delete", {"Id": "201", "SyncToken": "0"}),
        ("invoice", None, {"Id": "130", "SyncToken": "3", "sparse": True, "PrivateNote": ""})]
    assert [r.url.params["requestid"] for r in writes] == ["undo-payment-202", "undo-creditmemo-201", "undo-note-130-3"]
    assert all(r.url.params["minorversion"] == "75" for r in writes)
    assert (set(fake.rows["Payment"]), fake.rows["CreditMemo"], fake.invoice["PrivateNote"]) == ({"150"}, {}, "")
    sent = len(fake.requests)
    assert qbo.books().undo_demo_writes() == []  # a second reset finds nothing and writes nothing
    assert all(r.method == "GET" for r in fake.requests[sent:])


def test_reset_finds_a_payment_written_before_payments_had_a_note(monkeypatch):
    fake = FakeQBO()
    sandbox_yes(monkeypatch, fake)
    del fake.rows["Payment"]["202"]["PrivateNote"]  # how apply_to_invoice wrote it until now
    assert [(u.entity, u.id) for u in qbo.books().undo_demo_writes()] == [
        ("Payment", "202"), ("CreditMemo", "201"), ("Invoice", "130")]
    assert set(fake.rows["Payment"]) == {"150"}  # the seed's $41,350 payment stays


def test_stand_in_reset_clears_its_own_records():
    fake = PortalClaude()
    run = finished_march(fake)
    pipeline.decide_approval(pending(run).id, True)
    disputes.post("D-0417", "Signed amendment attached.", attachment_doc_id="amendment-1", client=fake)
    books = qbo.books()
    assert isinstance(books, qbo.StandInBooks) and len(books.calls) == 6  # two memos, two payments, two notes
    undone = books.undo_demo_writes()
    assert [(u.entity, u.action, u.simulated) for u in undone] == [
        ("Payment", "deleted", True), ("Payment", "deleted", True), ("CreditMemo", "deleted", True),
        ("CreditMemo", "deleted", True), ("Invoice", "note cleared", True)]
    assert all(u.id.startswith("sim-") for u in undone)
    assert all(u.note.startswith("Clawback ") for u in undone[:4]) and undone[4].note.startswith("Open $3,120.00")
    assert books.calls == [] and books.undo_demo_writes() == []


def test_reset_route_says_what_it_removed_and_resets_even_if_quickbooks_fails(api, monkeypatch):
    sandbox_yes(monkeypatch, FakeQBO())
    r = api.post("/demo/reset").json()
    assert (r["ok"], r["stub"], "error" in r) == (True, False, False)
    assert [(u["entity"], u["id"], u["action"]) for u in r["quickbooks"]] == [
        ("Payment", "202", "deleted"), ("CreditMemo", "201", "deleted"), ("Invoice", "130", "note cleared")]
    assert r["quickbooks"][1]["note"].startswith("Clawback AP-") and pipeline.RUNS == {} and qbo._books is None

    finished_march(ScenarioClaude())
    monkeypatch.setattr(qbo, "_books", live_books(FakeQBO(fail=True)))
    r = api.post("/demo/reset").json()
    assert (r["ok"], r["stub"], r["quickbooks"]) == (False, False, []) and "returned 500" in r["error"]
    assert pipeline.RUNS == {} and qbo._books is None  # the in-memory demo still resets


def test_reset_route_with_the_stand_in(api):
    run = finished_march(ScenarioClaude())
    pipeline.decide_approval(pending(run).id, True)
    r = api.post("/demo/reset").json()
    assert r["ok"] and [(u["entity"], u["simulated"]) for u in r["quickbooks"]] == [
        ("Payment", True), ("CreditMemo", True), ("Invoice", True)]
    assert api.post("/demo/reset").json() == {"ok": True, "stub": False, "quickbooks": []}
