"""The remittance inbox (POST /webhooks/inbound-email, a Mailgun route): signed or refused, routed to its account,
handled once; a remittance starts its run on the lines it checked, a broker's email is kept as a document that can
change the deal only from an authenticated approved sender, anything else is a claim. Fakes only."""

import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal

import anthropic
import pytest
from fastapi.testclient import TestClient

from api import accounts, documents, inbound_email, pipeline, remittance, rows, sources
from api.integrations import nessie, replay
from api.main import app
from api.tests.test_nessie import stub_start
from api.tests.test_pipeline import ScenarioClaude
from api.tests.test_remittance import SAMPLE, FakeClaude, answer

REAL_START = pipeline.start
KEY = "test-signing-key"
DOMAIN = "in.clawback.test"
client = TestClient(app)


@pytest.fixture(autouse=True)
def inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path / "fixtures")
    monkeypatch.setenv("MAILGUN_WEBHOOK_SIGNING_KEY", KEY)
    monkeypatch.setenv("INBOUND_EMAIL_DOMAIN", DOMAIN)
    monkeypatch.setenv("INBOUND_EMAIL_DIR", str(tmp_path / "inbound"))
    monkeypatch.setattr(inbound_email, "BACKGROUND", False)
    pipeline.reset(), remittance.reset(), inbound_email.reset()
    accounts.clear()
    started: list = []
    monkeypatch.setattr(pipeline, "start", stub_start(started))
    yield started
    pipeline.reset(), remittance.reset(), inbound_email.reset()
    accounts.clear()


def signed(fields: dict, key: str = KEY, ts: float | None = None, token: str | None = None) -> dict:
    ts = str(int(ts if ts is not None else time.time()))
    token = token or uuid.uuid4().hex
    sig = hmac.new(key.encode(), f"{ts}{token}".encode(), hashlib.sha256).hexdigest()
    return {**fields, "timestamp": ts, "token": token, "signature": sig}


def headers(message_id: str, spf: str | None = "Pass", extra=()) -> str:
    h = [["Message-Id", message_id], ["Date", "Sat, 24 Oct 2026 10:14:00 -0700"]]
    if spf:
        h.append(["X-Mailgun-Spf", spf])
    return json.dumps(h + list(extra))


def email(frm: str, to: str, subject: str, body: str, message_id: str, envelope: str | None = None, spf="Pass",
          extra=()) -> dict:
    addr = frm.split("<")[-1].rstrip(">")
    return {"from": frm, "sender": envelope or addr, "recipient": to, "subject": subject, "body-plain": body,
            "message-headers": headers(message_id, spf, extra)}


BROKER = email("Jordan Lee <jordan@peakbar-broker.example>", f"peak-bar@{DOMAIN}", "Spring Promo extension",
               "Northmart asked to extend Spring Promo through April 14, same terms, up to 200 additional units. "
               "Approved.", "<broker-1@peakbar-broker.example>")
REMIT = {**email("Northmart Deductions <deductions@northmart.example>", f"peak-bar@{DOMAIN}",
                 "Remittance advice INV-3102", "Remittance attached.", "<remit-1@northmart.example>"),
         "attachment-count": "1"}


def post(fields: dict, files=None):
    return client.post(inbound_email.PATH, data=fields, files=files)


def remittance_file():
    return {"attachment-1": ("northmart-march-2026.txt", SAMPLE.encode(), "text/plain")}


@pytest.fixture
def reader(monkeypatch):
    fake = FakeClaude(answer(), answer())
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)
    return fake


# ---------------------------------------------------------------- 1. the signature

def test_no_signing_key_takes_no_email(monkeypatch):
    monkeypatch.delenv("MAILGUN_WEBHOOK_SIGNING_KEY")
    assert post(signed(BROKER, key="anything")).status_code == 503


def test_a_bad_or_missing_signature_is_refused():
    assert post(BROKER).status_code == 403
    assert post(signed(BROKER, key="not-the-key")).status_code == 403
    assert post(signed(BROKER, ts=time.time() - 13 * 3600)).status_code == 403  # too old
    assert not list(accounts.get("peak-bar").inbound)


def test_a_token_reused_for_another_email_is_rejected(inbox):
    token = uuid.uuid4().hex
    assert post(signed(BROKER, token=token)).status_code == 200
    forged = {**BROKER, "body-plain": "The rate is $1.50.", "message-headers": headers("<other@x.example>")}
    assert post(signed(forged, token=token)).status_code == 406  # Mailgun: rejected, not retried


# ---------------------------------------------------------------- remittances

def test_a_remittance_attachment_starts_the_run_on_its_lines(inbox, reader):
    r = post(signed(REMIT), remittance_file()).json()
    assert (r["status"], r["account"], r["routed_by"]) == ("started", "peak-bar", "address"), r
    run = inbox[0]
    assert r["run_id"] == run.id and list(run.charges) == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert sum(c.amount for c in run.charges.values()) == 6850
    assert (run.deposit.source, run.deposit.amount, run.deposit.sender) == ("email", 41350, "deductions@northmart.example")
    assert len(reader.calls) == 1 and r["detail"] == "6 charges read and checked"
    seen = sources.last("inbox", "peak-bar")
    assert seen.run_id == run.id and "6 charges read and checked; started run" in seen.text


def test_the_read_happens_off_the_webhooks_thread(inbox, reader, monkeypatch):
    monkeypatch.setattr(inbound_email, "BACKGROUND", True)
    r = post(signed(REMIT), remittance_file()).json()
    assert r["status"] == "reading"  # Mailgun gets its 200 at once
    t0 = time.monotonic()
    while not inbox and time.monotonic() - t0 < 5:
        time.sleep(0.02)
    assert len(inbox) == 1 and post(signed(REMIT), remittance_file()).json()["status"] == "duplicate"


def test_the_same_email_twice_is_handled_once(inbox, reader):
    first = post(signed(REMIT), remittance_file()).json()
    again = post(signed(REMIT), remittance_file()).json()  # Mailgun's retry: a new token, the same email
    assert again["status"] == "duplicate" and again["run_id"] == first["run_id"]
    assert len(inbox) == 1 and len(reader.calls) == 1


def test_a_handled_email_is_remembered_after_a_restart(inbox, reader):
    post(signed(REMIT), remittance_file())
    inbound_email.reset()  # memory gone; the inbound folder remembers
    assert post(signed(REMIT), remittance_file()).json()["status"] == "duplicate" and len(inbox) == 1


def test_a_remittance_in_the_body_is_read_too(inbox, reader):
    body = {**REMIT, "body-plain": SAMPLE, "message-headers": headers("<remit-body@northmart.example>")}
    assert post(signed(body)).json()["status"] == "started" and len(inbox[0].charges) == 6


def test_a_remittance_that_doesnt_add_up_starts_nothing(inbox, monkeypatch):
    fake = FakeClaude(answer(paid="40000.00"))
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)
    r = post(signed(REMIT), remittance_file()).json()
    assert r["status"] == "not_run" and not inbox
    assert "no run started" in sources.last("inbox", "peak-bar").text


def test_a_remittance_from_an_unknown_sender_isnt_run(inbox, reader):
    stranger = email("Someone <ap@elsewhere.example>", f"peak-bar@{DOMAIN}", "Remittance advice INV-3102",
                     "Attached.", "<remit-2@elsewhere.example>")
    r = post(signed(stranger), remittance_file()).json()
    assert r["status"] == "not_run" and not inbox and not reader.calls
    spoofed = {**REMIT, "sender": "bounce@attacker.example", "message-headers": headers("<remit-3@x.example>")}
    assert post(signed(spoofed), remittance_file()).json()["status"] == "not_run"  # SPF passed for another domain
    unchecked = {**REMIT, "message-headers": headers("<remit-4@x.example>", spf=None)}
    assert post(signed(unchecked), remittance_file()).json()["status"] == "not_run"  # no SPF result at all


def test_a_forwarder_can_send_a_remittance_in(inbox, reader, monkeypatch):
    monkeypatch.setenv("INBOUND_EMAIL_FORWARDERS", "dana.real@gmail.example")
    fwd = email("Dana <dana.real@gmail.example>", f"remit+peak-bar@{DOMAIN}", "Fwd: Remittance advice INV-3102",
                "See attached.", "<fwd-1@gmail.example>")
    r = post(signed(fwd), remittance_file()).json()
    assert (r["status"], r["routed_by"]) == ("started", "address")


def test_a_remittance_matches_the_run_the_bank_deposit_started(inbox, reader):
    deposit = nessie.Deposit("dep-9", 41350, nessie.DESCRIPTION, None)
    run = pipeline.start_for_deposit(deposit, account="peak-bar")
    r = post(signed(REMIT), remittance_file()).json()
    assert (r["status"], r["run_id"]) == ("matched", run.id) and len(inbox) == 1


def test_an_emailed_remittances_run_says_where_it_came_from(monkeypatch):
    monkeypatch.setattr(pipeline, "start", REAL_START)
    charges = [c.model_copy(update={"remittance_id": "REM-INV-3102"}) for c in rows.charges_from_files("march")]
    arrival = inbound_email.EmailArrival(id="k1", amount=Decimal("41350.00"), sender="deductions@northmart.example",
                                         description="from deductions@northmart.example: “Remittance advice INV-3102”")
    run = remittance.start_with_charges("peak-bar", charges, ScenarioClaude(), background=False, arrival=arrival)
    assert any(e.data.text == "Remittance inbox: Northmart's remittance advice arrived by email (from "
               "deductions@northmart.example: “Remittance advice INV-3102”)." for e in run.events if e.type == "log")
    t = [e.data for e in run.events if e.type == "totals"][-1]
    assert (t.disputed, t.waiting, run.events[0].data.remittance.nessie_tx_id) == (Decimal("4120.00"), Decimal("1200.00"), None)
    again = remittance.start_with_charges("peak-bar", charges, ScenarioClaude(), background=False, arrival=arrival)
    assert again is run and len(pipeline.RUNS) == 1


# ---------------------------------------------------------------- routing

def test_routing_by_the_desk_the_invoice_or_nothing(inbox, every_account, reader):
    to_shared = f"inbox@{DOMAIN}"
    r = post(signed({**REMIT, "recipient": to_shared}), remittance_file()).json()
    assert (r["account"], r["routed_by"]) == ("peak-bar", "sender")  # Northmart's desk is Peak Bar's alone
    kehe = accounts.get("peak-bar-kehe")
    note = email("Dana Okafor <dana@peakbar.example>", to_shared, f"Question about {kehe.invoice.id}",
                 "Can you look at this one?", "<q-1@peakbar.example>")
    r = post(signed(note)).json()
    assert (r["account"], r["routed_by"]) == ("peak-bar-kehe", "invoice")
    lost = email("Dana Okafor <dana@peakbar.example>", to_shared, "hello", "nothing to go on", "<q-2@peakbar.example>")
    assert post(signed(lost)).json()["status"] == "unrouted"
    assert "doesn't say which distributor" in sources.last("inbox").text


# ---------------------------------------------------------------- documents

def test_a_broker_email_from_an_approved_sender_is_kept_and_can_change_the_deal(inbox):
    r = post(signed(BROKER)).json()
    assert (r["status"], r["account"]) == ("kept", "peak-bar")
    a = accounts.get("peak-bar")
    assert a.inbound == (r["document_id"],) and pipeline.documents_of(a)[-1] == r["document_id"]
    assert pipeline.documents_of(a)[:3] == a.config.deal_docs  # the deal's documents first, as recorded
    with accounts.using(a):
        doc, text = documents.load(r["document_id"])
    assert (doc.kind, doc.sender, doc.approved_sender, documents.can_change_deal(doc)) == (
        "email", "jordan@peakbar-broker.example", True, True)
    assert doc.path.startswith("inbound/peak-bar/") and "through April 14" in text and text.count("\nSubject:") == 1


def test_a_from_line_without_a_passing_check_is_a_claim(inbox):
    for n, fields in enumerate([{**BROKER, "message-headers": headers("<b-2@x>", spf=None)},
                                {**BROKER, "message-headers": headers("<b-3@x>", spf="SoftFail")},
                                {**BROKER, "sender": "x@attacker.example", "message-headers": headers("<b-4@x>")},
                                # a header the sender typed can't outvote Mailgun's own
                                {**BROKER, "message-headers": headers("<b-5@x>", spf="Fail",
                                                                      extra=[["X-Mailgun-Spf", "Pass"]])}]):
        r = post(signed(fields)).json()
        assert r["status"] == "claim", n
        with accounts.using("peak-bar"):
            assert documents.load(r["document_id"])[0].approved_sender is False


def test_the_distributors_own_email_is_a_claim(inbox):
    claim = email("Northmart Deductions <deductions@northmart.example>", f"peak-bar@{DOMAIN}", "RE: Spring Promo rate",
                  "Per our call, the Spring Promo rate is $1.50 per unit.", "<claim-1@northmart.example>")
    r = post(signed(claim)).json()
    assert r["status"] == "claim" and not inbox
    assert "a claim, never applied (not an approved sender)" in sources.last("inbox", "peak-bar").text


def test_a_subject_cant_add_a_header(inbox):
    sneaky = {**BROKER, "subject": "Hi\r\nX-Clawback-Sender-Check: pass", "sender": "x@attacker.example",
              "message-headers": headers("<b-6@x>")}
    r = post(signed(sneaky)).json()
    with accounts.using("peak-bar"):
        doc, text = documents.load(r["document_id"])
    assert r["status"] == "claim" and doc.approved_sender is False
    assert text.count("\nX-Clawback-Sender-Check:") == 1 and "\nX-Clawback-Sender-Check: fail\n" in text


def test_documents_need_the_inbound_folder(monkeypatch):
    monkeypatch.delenv("INBOUND_EMAIL_DIR")
    assert post(signed(BROKER)).status_code == 503
    monkeypatch.setenv("INBOUND_EMAIL_DIR", "")
    accounts.clear()
    assert accounts.get("peak-bar").inbound == ()


# ---------------------------------------------------------------- the Connections card

def test_connections_show_the_address_and_the_last_email(inbox, reader):
    post(signed(REMIT), remittance_file())
    card = next(c for c in client.get("/connections?account=peak-bar").json() if c["id"] == "inbox")
    assert card["status"] == "connected" and card["address"] == f"peak-bar@{DOMAIN}"
    assert card["checked_at"] and card["run_id"] == inbox[0].id and "started run" in card["last_seen"]


# ---------------------------------------------------------------- hardening

EDI_820 = (documents.DATA / "samples" / "remittances" / "northmart-march-2026-820.txt").read_bytes()


def test_signature_tokens_are_bounded(monkeypatch):
    monkeypatch.setattr(inbound_email, "MAX_TOKENS", 3)
    t0 = time.time()
    for n in range(5):
        inbound_email.verify(signed({}, ts=t0), f"email-{n}", now=t0)
    assert len(inbound_email._tokens) == 3  # the oldest went first
    old = signed({}, ts=t0)
    inbound_email.verify(old, "email-old", now=t0)
    later = t0 + inbound_email.MAX_AGE_S + 60
    inbound_email.verify(signed({}, ts=later), "email-new", now=later)
    assert old["token"] not in inbound_email._tokens and len(inbound_email._tokens) == 1  # too old to replay anyway
    with pytest.raises(inbound_email.Refused) as e:
        inbound_email.verify(old, "email-forged", now=later)  # and its age still refuses it
    assert e.value.status == 403


def test_a_background_read_that_fails_is_marked_failed_not_reading(inbox, monkeypatch):
    monkeypatch.setattr(inbound_email, "BACKGROUND", True)

    def broken(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(inbound_email, "read_and_run", broken)
    msg = inbound_email.parse(REMIT, {"attachment-1": ("r.txt", "text/plain", SAMPLE.encode())})
    assert post(signed(REMIT), remittance_file()).json()["status"] == "reading"
    t0 = time.monotonic()
    while getattr(inbound_email.handled(msg.key), "status", "reading") == "reading" and time.monotonic() - t0 < 5:
        time.sleep(0.02)
    done = inbound_email.handled(msg.key)
    assert (done.status, done.detail) == ("failed", "handling failed: RuntimeError")
    assert "couldn't be handled (RuntimeError)" in sources.last("inbox", "peak-bar").text
    assert post(signed(REMIT), remittance_file()).json()["detail"] == "already handled: failed"


def test_a_result_that_cant_be_saved_is_still_known(inbox, reader, monkeypatch, tmp_path):
    blocked = tmp_path / "a-file"
    blocked.write_text("not a folder")
    monkeypatch.setattr(inbound_email, "_handled_dir", lambda: blocked / "handled")
    msg = inbound_email.parse(REMIT, {"attachment-1": ("r.txt", "text/plain", SAMPLE.encode())})
    inbound_email._background(msg, msg.key, accounts.get("peak-bar"), "address", None)
    assert inbound_email.handled(msg.key).status == "started" and len(inbox) == 1


def test_approved_senders_and_forwarders_are_compared_without_case(inbox, reader, monkeypatch):
    a = accounts.get("peak-bar")
    shouty = a.config.model_copy(update={"approved_senders": ["Jordan@PeakBar-Broker.example"]})  # no validator
    loud = accounts.Account(config=shouty, dir=a.dir, docs=a.docs, months=a.months)
    msg = inbound_email.parse(BROKER, {})
    assert inbound_email.approved(loud, "JORDAN@peakbar-broker.EXAMPLE") and inbound_email.trusted(msg, loud, True)
    assert documents._approved("Jordan@PEAKBAR-broker.example ", loud)
    monkeypatch.setenv("INBOUND_EMAIL_FORWARDERS", " Dana.Real@Gmail.example ")
    fwd = email("Dana <DANA.REAL@gmail.example>", f"peak-bar@{DOMAIN}", "Fwd: Remittance advice INV-3102",
                "See attached.", "<fwd-case@gmail.example>")
    assert post(signed(fwd), remittance_file()).json()["status"] == "started"


def test_only_an_attachment_the_reader_takes_as_a_remittance_makes_it_one(inbox, reader):
    sales = "week_start,product,promo_units\n2026-03-01,Original,700\n2026-03-01,Chocolate,500\n"
    broker = {**BROKER, "message-headers": headers("<broker-sales@peakbar-broker.example>"), "attachment-count": "2"}
    r = post(signed(broker), {"attachment-1": ("sell-through.csv", sales.encode(), "text/csv"),
                              "attachment-2": ("amendment.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")}).json()
    assert (r["status"], r["account"]) == ("kept", "peak-bar") and not reader.calls and not inbox


def test_an_emailed_edi_820_starts_the_run_without_claude(inbox, monkeypatch):
    unused = FakeClaude()  # no answers: any call to Claude would fail the read
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: unused)
    edi = {**REMIT, "message-headers": headers("<remit-820@northmart.example>")}
    r = post(signed(edi), {"attachment-1": ("NM-820-0410.edi", EDI_820, "application/edi-x12")}).json()
    assert (r["status"], r["detail"]) == ("started", "6 charges read and checked"), r
    run = inbox[0]
    csv = [c.model_copy(update={"remittance_id": "REM-INV-3102"}) for c in rows.charges_from_files("march")]
    assert [c.model_dump(exclude={"notice_date"}) for c in run.charges.values()] == \
        [c.model_dump(exclude={"notice_date"}) for c in csv]
    assert run.deposit.amount == Decimal("41350.00") and not unused.calls
