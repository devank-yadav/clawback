"""Phase E: the dispute email. Drafted (Claude, checked; the code template when the call fails), reviewed and sent by
the admin through a fake Mailgun, replies routed back by address or Message-Id, the emailed amendment concedes
$1,000, and the outbound filter holds a made-up figure."""

import re
from decimal import Decimal as D
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from api import dispute_email, disputes, inbound_email, pipeline
from api.agents import claude as claude_mod, email_writer
from api.agents.email_writer import LLMEmail
from api.integrations import mailgun, replay
from api.tests.test_disputes import PortalClaude, finished_march
from api.tests.test_pipeline import final, last_totals


class EmailClaude(PortalClaude):
    """PortalClaude plus the email writer: one paragraph per line, every figure the line's own."""

    def __init__(self, invent: int = 0, **kw):
        super().__init__(**kw)
        self.invent = invent

    def _parse(self, output_format, messages, **kw):
        if output_format is LLMEmail:
            self.calls.append("LLMEmail")
            import json

            payload = json.loads(messages[0]["content"].split("\n\nYour previous answer")[0])["dispute"]
            paras = [{"charge_id": ln["charge_id"],
                      "text": f"{ln['ref']}: ${D(ln['amount']):,.0f} disputed. {ln['reason']}"} for ln in payload["lines"]]
            if self.invent:
                self.invent -= 1
                paras[0]["text"] += " We also want $999 back."
            out = {"opening": f"Peak Bar Co. disputes {payload['id']}, ${D(payload['total']):,.0f} in total.",
                   "paragraphs": paras, "closing": "Please review the attached packet."}
            return SimpleNamespace(stop_reason="end_turn", stop_details=None, parsed_output=LLMEmail.model_validate(out))
        return super()._parse(output_format=output_format, messages=messages, **kw)


class FakeMailgun:
    def __init__(self, status=200):
        self.requests: list[httpx.Request] = []
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        n = len(self.requests)
        return httpx.Response(self.status, json={"id": f"<20261025.{n}@mg.clawback.test>", "message": "Queued. Thank you."})


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset(), disputes.reset(), inbound_email.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    monkeypatch.setenv("INBOUND_EMAIL_DOMAIN", "in.clawback.test")
    yield
    pipeline.reset(), disputes.reset(), inbound_email.reset()


@pytest.fixture
def mg(monkeypatch):
    fake = FakeMailgun()
    monkeypatch.setenv("MAILGUN_API_KEY", "key-test")
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.clawback.test")
    real = httpx.Client
    monkeypatch.setattr(mailgun.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
    return fake


def _dispute(run):
    return [e.data for e in run.events if e.type == "dispute"][-1]


def _form(request: httpx.Request) -> dict[str, list[str]]:
    """The multipart form Mailgun got: field name -> values (files as their filenames)."""
    body = request.read()
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    out: dict[str, list[str]] = {}
    for part in body.split(b"--" + boundary)[1:-1]:
        head, _, value = part.partition(b"\r\n\r\n")
        name = re.search(rb'name="([^"]+)"', head).group(1).decode()
        fname = re.search(rb'filename="([^"]+)"', head)
        out.setdefault(name, []).append(fname.group(1).decode() if fname else value[:-2].decode())
        if fname:
            out.setdefault(f"{name}:bytes", []).append(value[:4].decode("latin-1"))
    return out


def test_disputes_start_as_drafts_and_the_email_is_drafted_from_the_lines():
    fake = EmailClaude()
    run = finished_march(fake)
    d = _dispute(run)
    assert (d.id, d.status, d.total, d.filed_at) == ("D-0417", "ready_to_send", D(4120), None)
    e = dispute_email.email_for(run, d, fake)
    assert e.status == "ready" and e.written_by == "claude" and not e.problems
    refs = ", ".join(ln.ref for ln in d.lines)
    assert e.subject == f"Dispute: Peak Bar Co., Remittance {d.remittance_id}, Deductions {refs}, $4,120.00 [D-0417]"
    assert re.fullmatch(r"d-0417\+[0-9a-f]{12}@in\.clawback\.test", e.reply_to)
    assert e.to == "deductions@northmart.example" and e.from_addr.endswith("<disputes@clawback.local>")
    assert e.body.startswith("Hello Northmart deductions team,") and e.body.count("disputed.") == 4
    assert "Dana Okafor" in e.body and e.attachments == ["D-0417-packet.pdf"]


def test_without_gmail_keys_mailgun_still_sends_and_files_the_dispute(mg, monkeypatch):
    from api.main import app

    fake = EmailClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    run = finished_march(fake)
    client = TestClient(app)
    email = client.get(f"/disputes/D-0417/email?run_id={run.id}").json()
    assert email["status"] == "ready" and email["from_addr"] == "Peak Bar Co. <disputes@mg.clawback.test>"
    assert not mg.requests  # nothing goes out before the admin says so
    r = client.post(f"/disputes/D-0417/send?run_id={run.id}")
    assert r.status_code == 200
    body = r.json()
    assert (body["dispute"]["status"], body["dispute"]["approved_by"]) == ("filed", "owner")
    assert body["email"]["status"] == "sent" and body["email"]["message_id"] == "<20261025.1@mg.clawback.test>"
    (req,) = mg.requests
    assert str(req.url) == "https://api.mailgun.net/v3/mg.clawback.test/messages"
    assert req.headers["authorization"].startswith("Basic ")  # user "api", the key
    form = _form(req)
    assert form["to"] == ["deductions@northmart.example"] and form["subject"][0].startswith("Dispute: Peak Bar Co.")
    assert re.fullmatch(r"d-0417\+[0-9a-f]{12}@in\.clawback\.test", form["h:Reply-To"][0])
    assert form["attachment"] == ["D-0417-packet.pdf"] and form["attachment:bytes"] == ["%PDF"]
    assert _dispute(run).status == "filed"
    assert client.post(f"/disputes/D-0417/send?run_id={run.id}").status_code == 409  # once
    assert client.get(f"/disputes/D-0417/thread?run_id={run.id}").json()["emails"][0]["status"] == "sent"


def test_no_keys_or_demo_mode_goes_to_the_in_app_outbox():
    fake = EmailClaude()
    run = finished_march(fake)
    filed, e = dispute_email.send_dispute(run, _dispute(run), client=fake)
    assert filed.status == "filed" and e.status == "outbox" and e.message_id.startswith("<sim-")
    assert mailgun.OUTBOX and "no Gmail or Mailgun keys" in e.detail


def test_a_failed_call_falls_back_to_the_template_and_an_invented_figure_twice_is_held():
    run = finished_march(EmailClaude())
    d = _dispute(run)

    class Down(EmailClaude):
        def _parse(self, output_format, **kw):
            if output_format is LLMEmail:
                raise RuntimeError("no network")
            return super()._parse(output_format=output_format, **kw)

    t = email_writer.draft(d, run.terms, run.account, Down())
    assert t.written_by == "template" and not t.held, t.problems
    assert "$4,120.00" in t.body and all(ln.ref in t.body for ln in d.lines)

    once = email_writer.draft(d, run.terms, run.account, EmailClaude(invent=1))
    assert once.written_by == "claude" and "$999" not in once.body  # retried with the problem, fixed
    twice = email_writer.draft(d, run.terms, run.account, EmailClaude(invent=2))
    assert twice.held and "999" in twice.problems[0]


def test_the_outbound_filter_holds_an_admin_edit_with_a_made_up_figure():
    fake = EmailClaude()
    run = finished_march(fake)
    d = _dispute(run)
    e = dispute_email.email_for(run, d, fake)
    held = dispute_email.edit(e, None, e.body + "\n\nPay us $7,777 and we'll drop the rest.")
    assert held.status == "held" and any("7,777" in p for p in held.problems)
    with pytest.raises(dispute_email.NotReady):
        dispute_email.send_dispute(run, d)
    fixed = dispute_email.edit(held, "Dispute D-0417", e.body)
    assert fixed.status == "ready" and fixed.written_by == "admin" and fixed.subject == "Dispute D-0417"


def _reply(to: str, body: str, *, in_reply_to: str | None = None, attachments=(), mid="<reply-1@northmart.example>"):
    headers = [("Message-Id", mid)] + ([("In-Reply-To", in_reply_to)] if in_reply_to else [])
    return inbound_email.Message(from_header="Desk <deductions@northmart.example>", envelope="deductions@northmart.example",
                                 recipient=to, subject="Re: Dispute", body=body, headers=tuple(headers),
                                 attachments=tuple(attachments))


def test_a_reply_to_the_dispute_address_is_answered_as_a_draft_and_the_admin_is_told():
    fake = EmailClaude()
    run = finished_march(fake)
    _, sent = dispute_email.send_dispute(run, _dispute(run), client=fake)
    msg = _reply(sent.reply_to, "There was no unit cap on the Spring promo.\n\nOn Sat, Clawback wrote:\n> old text")
    result = inbound_email.handle(msg, client=fake, background=False)
    assert (result.status, result.dispute_id, result.run_id) == ("dispute_reply", "D-0417", run.id)
    theirs = [m for m in dispute_email.thread(run, "D-0417") if m.from_party == "northmart"][-1]
    assert theirs.channel == "email" and theirs.text == "There was no unit cap on the Spring promo."
    assert theirs.classification == "claim_without_document"
    (reply,) = [x for x in dispute_email.emails_of(run.id, "D-0417") if x.kind == "reply"]
    assert reply.status == "ready" and reply.in_reply_to == "<reply-1@northmart.example>"
    assert reply.subject.startswith("Re: Dispute: Peak Bar Co.") and "signed change" in reply.body
    assert not [m for m in dispute_email.thread(run, "D-0417") if m.from_party == "clawback"]  # waits for the admin
    (n,) = dispute_email.notifications()
    assert n.text == "Northmart pushed back on your $4,120 dispute: an answer is drafted for you to send."
    sent_reply = dispute_email.send_reply(reply.id)
    assert sent_reply.status == "outbox"
    assert [m.channel for m in dispute_email.thread(run, "D-0417") if m.from_party == "clawback"] == ["email"]
    again = inbound_email.handle(msg, client=fake, background=False)
    assert again.status == "duplicate"  # Mailgun's retry is handled once


def test_a_reply_threads_by_in_reply_to_alone():
    fake = EmailClaude()
    run = finished_march(fake)
    _, sent = dispute_email.send_dispute(run, _dispute(run), client=fake)
    msg = _reply("deductions-reply@in.clawback.test", "Agreed, Mint wasn't part of the Spring promo.",
                 in_reply_to=sent.message_id, mid="<reply-2@northmart.example>")
    assert dispute_email.route(msg) == (run, _dispute(run))
    assert dispute_email.route(_reply("d-0417+000000000000@in.clawback.test", "hi", mid="<x@y>")) is None


def test_the_emailed_signed_amendment_concedes_1000():
    fake = EmailClaude()
    run = finished_march(fake)
    _, sent = dispute_email.send_dispute(run, _dispute(run), client=fake)
    text = run.account.docs["amendment-1"].read_bytes()
    msg = _reply(sent.reply_to, "The cap was raised to 6,000 units. Signed amendment attached.",
                 attachments=[inbound_email.Attachment("amendment-1.md", "text/markdown", text)])
    inbound_email.handle(msg, client=fake, background=False)
    assert final(run)["C4"] == ("split", D(540), D(1000))
    t = last_totals(run)
    assert (t.disputed, t.accepted) == (D(3120), D(3730))
    assert _dispute(run).total == D(3120)
    (reply,) = [x for x in dispute_email.emails_of(run.id, "D-0417") if x.kind == "reply"]
    assert "withdraw $1,000" in reply.body and reply.status == "ready"
    assert "now totals $3,120" in dispute_email.notifications()[0].text


def test_an_unknown_attachment_is_held_for_the_owner():
    fake = EmailClaude()
    run = finished_march(fake)
    _, sent = dispute_email.send_dispute(run, _dispute(run), client=fake)
    msg = _reply(sent.reply_to, "See attached.", attachments=[inbound_email.Attachment("scan.pdf", "application/pdf", b"%PDF")])
    inbound_email.handle(msg, client=fake, background=False)
    assert final(run)["C4"] == ("dispute", D(1540), D(0))
    assert any("doesn't have (scan)" in e.data.text for e in run.events if e.type == "log")


def test_auto_send_files_and_emails_within_the_limit(monkeypatch):
    monkeypatch.setattr(dispute_email, "auto_send", lambda: True)
    fake = EmailClaude()
    run = finished_march(fake)
    d = _dispute(run)
    assert (d.status, d.approved_by) == ("filed", "policy")
    assert dispute_email.emails_of(run.id, "D-0417")[0].status == "outbox"


def test_another_supplier_cant_see_or_send_the_dispute(monkeypatch):
    from api import accounts, users
    from api.main import app

    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", "lantern-hill"})
    accounts.clear()
    monkeypatch.setenv("DEMO_USER_PASSWORD", "p1")
    monkeypatch.setenv("DEMO_USER2_PASSWORD", "p2")
    users.reset()
    fake = EmailClaude()
    run = finished_march(fake)
    teresa = TestClient(app)
    assert teresa.post("/auth/login", json={"email": "teresa@lanternhillsoda.example", "password": "p2"}).status_code == 200
    for method, path in [("GET", "/disputes/D-0417/email"), ("GET", f"/disputes/D-0417/thread?run_id={run.id}"),
                         ("POST", "/disputes/D-0417/send"), ("PUT", "/disputes/D-0417/email"),
                         ("POST", "/disputes/D-0417/replies/EM-x/send")]:
        r = teresa.request(method, path, json={"body": "x"} if method == "PUT" else None)
        assert r.status_code == 404, (method, path, r.status_code)
    assert teresa.get("/disputes").json() == [] and teresa.get("/outbox").json() == []
    assert _dispute(run).status == "ready_to_send"
    users.reset()
    accounts.clear()


# ---------------------------------------------------------------- the supplier's Gmail: SMTP out, IMAP in

class FakeSmtp:
    """Gmail's SMTP server: login with the app password, sendmail, quit."""

    def __init__(self, password="app-pw"):
        self.password, self.sent = password, []

    def login(self, user, password):
        import smtplib

        if password != self.password:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        return 235, b"Accepted"

    def sendmail(self, from_addr, to, raw):
        self.sent.append((from_addr, to, raw))
        return {}

    def quit(self):
        return 221, b"bye"


class FakeImap:
    """Gmail's IMAP server, enough for reading INBOX: login, SELECT, UID SEARCH, UID FETCH."""

    def __init__(self):
        self.inbox: list[bytes] = []

    def login(self, user, password):
        return "OK", [b"ok"]

    def logout(self):
        return "BYE", [b""]

    def select(self, box, readonly=False):
        assert box == "INBOX" and readonly
        return "OK", [str(len(self.inbox)).encode()]

    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [" ".join(str(i + 1) for i in range(len(self.inbox))).encode()]
        uid = int(args[0])
        return "OK", [(f"{uid} (UID {uid} BODY[] {{1}}".encode(), self.inbox[uid - 1]), b")"]


@pytest.fixture
def gm(monkeypatch):
    from api.integrations import gmail

    smtp, imap = FakeSmtp(), FakeImap()
    monkeypatch.setenv("GMAIL_ADDRESS", "dana.peakbar@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pw")
    monkeypatch.setattr(gmail, "smtp_fn", lambda: smtp)
    monkeypatch.setattr(gmail, "connect_fn", lambda: imap)
    return smtp, imap


def _parsed(raw: bytes):
    from email import policy
    from email.parser import BytesParser

    return BytesParser(policy=policy.default).parsebytes(raw)


def _distributor_reply(to_mid, subject, body, *, mid, attachment=None) -> bytes:
    from email.message import EmailMessage

    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = ("Desk <deductions@northmart.example>",
                                                        "dana.peakbar@gmail.com", subject, mid)
    if to_mid:
        m["In-Reply-To"], m["References"] = to_mid, to_mid
    m.set_content(body)
    if attachment:
        m.add_attachment(attachment[1], maintype="text", subtype="markdown", filename=attachment[0])
    return m.as_bytes()


def test_review_then_send_goes_out_from_the_suppliers_gmail(gm, mg, monkeypatch):
    from api.main import app

    smtp, _ = gm
    fake = EmailClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    run = finished_march(fake)
    client = TestClient(app)
    email = client.get(f"/disputes/D-0417/email?run_id={run.id}").json()
    assert email["from_addr"] == "Dana Okafor <dana.peakbar@gmail.com>" and email["reply_to"] is None
    assert not smtp.sent  # nothing goes out before the admin says so
    body = client.post(f"/disputes/D-0417/send?run_id={run.id}").json()
    assert (body["dispute"]["status"], body["email"]["status"]) == ("filed", "sent")
    ((frm, to, raw),) = smtp.sent
    assert (frm, to) == ("dana.peakbar@gmail.com", ["deductions@northmart.example"])
    m = _parsed(raw)
    assert m["Subject"].endswith("[D-0417]") and m["Message-ID"] == body["email"]["message_id"]
    assert m["Message-ID"].endswith("@gmail.com>") and "through Gmail" in body["email"]["detail"]
    (pdf,) = list(m.iter_attachments())
    assert pdf.get_filename() == "D-0417-packet.pdf" and pdf.get_content()[:4] == b"%PDF"
    assert not mg.requests  # Gmail wins over Mailgun when both are set
    assert client.post(f"/disputes/D-0417/send?run_id={run.id}").status_code == 409


def test_a_wrong_app_password_fails_and_sending_again_retries(gm, monkeypatch):
    smtp, _ = gm
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "wrong")
    fake = EmailClaude()
    run = finished_march(fake)
    d, e = dispute_email.send_dispute(run, _dispute(run), client=fake)
    assert e.status == "failed" and "app password" in e.detail and d.status == "ready_to_send" and not smtp.sent
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pw")
    d, e = dispute_email.send_dispute(run, _dispute(run), client=fake)
    assert (d.status, e.status) == ("filed", "sent") and len(smtp.sent) == 1


def test_demo_mode_keeps_the_outbox_even_with_gmail_keys(gm, monkeypatch):
    smtp, _ = gm
    fake = EmailClaude()
    run = finished_march(fake)
    monkeypatch.setenv("DEMO_MODE", "true")
    _, e = dispute_email.send_dispute(run, _dispute(run), client=fake)
    assert e.status == "outbox" and "DEMO_MODE" in e.detail and not smtp.sent


def test_gmail_replies_match_by_in_reply_to_and_the_answer_is_sent_after_approval(gm):
    smtp, imap = gm
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.send_dispute(run, _dispute(run), client=fake)
    assert dispute_email.poll_once(fake)["replies"] == 0  # the first look notes where INBOX stands
    imap.inbox.append(_distributor_reply(e.message_id, "RE: deductions", "There was no unit cap on the Spring promo."
                                         "\n\nOn Sat, Dana wrote:\n> old", mid="<r1@northmart.example>"))
    assert dispute_email.poll_once(fake)["replies"] == 1
    theirs = [m for m in dispute_email.thread(run, "D-0417") if m.from_party == "northmart"][-1]
    assert (theirs.channel, theirs.text, theirs.classification) == (
        "email", "There was no unit cap on the Spring promo.", "claim_without_document")
    (reply,) = [x for x in dispute_email.emails_of(run.id, "D-0417") if x.kind == "reply"]
    assert reply.status == "ready" and "signed change" in reply.body and len(smtp.sent) == 1  # waits for the admin
    assert "Northmart pushed back on your $4,120 dispute" in dispute_email.notifications()[0].text
    sent = dispute_email.send_reply(reply.id)
    assert sent.status == "sent" and len(smtp.sent) == 2
    m = _parsed(smtp.sent[-1][2])
    assert m["In-Reply-To"] == "<r1@northmart.example>" and e.message_id in m["References"]
    assert m["Subject"].startswith("Re: Dispute: Peak Bar Co.") and m["Subject"].endswith("[D-0417]")
    assert [x.channel for x in dispute_email.thread(run, "D-0417") if x.from_party == "clawback"] == ["email"]
    assert dispute_email.poll_once(fake)["replies"] == 0  # read once


def test_gmail_replies_match_by_subject_tag_and_our_own_mail_is_skipped(gm):
    _, imap = gm
    fake = EmailClaude()
    run = finished_march(fake)
    dispute_email.send_dispute(run, _dispute(run), client=fake)
    dispute_email.poll_once(fake)
    imap.inbox.append(_distributor_reply(None, "Re: Dispute: Peak Bar Co. [D-0417]",
                                         "Agreed, Mint wasn't part of the Spring promo.", mid="<r2@northmart.example>"))
    imap.inbox.append(_distributor_reply(None, "[D-0417] note", "x", mid="<own@gmail.com>").replace(
        b"Desk <deductions@northmart.example>", b"dana.peakbar@gmail.com"))
    imap.inbox.append(_distributor_reply(None, "Lunch?", "unrelated", mid="<r3@x>"))
    assert dispute_email.poll_once(fake)["replies"] == 1
    assert [m.classification for m in dispute_email.thread(run, "D-0417") if m.from_party == "northmart"] == ["agrees"]


def test_the_signed_amendment_by_gmail_concedes_1000(gm):
    _, imap = gm
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.send_dispute(run, _dispute(run), client=fake)
    dispute_email.poll_once(fake)
    text = run.account.docs["amendment-1"].read_bytes()
    imap.inbox.append(_distributor_reply(e.message_id, "Re", "The cap was raised to 6,000 units. Signed amendment "
                                         "attached.", mid="<r4@northmart.example>", attachment=("amendment-1.md", text)))
    dispute_email.poll_once(fake)
    assert final(run)["C4"] == ("split", D(540), D(1000))
    t = last_totals(run)
    assert (t.disputed, t.accepted) == (D(3120), D(3730))
    (reply,) = [x for x in dispute_email.emails_of(run.id, "D-0417") if x.kind == "reply"]
    assert "withdraw $1,000" in reply.body and reply.status == "ready"


def test_without_gmail_keys_nothing_polls():
    assert dispute_email.poll_once()["ok"] is False and dispute_email.start_poller() is False


def test_the_admin_answers_pushback_in_their_own_words_through_the_same_filter():
    fake = EmailClaude()
    run = finished_march(fake)
    dispute_email.send_dispute(run, _dispute(run), client=fake)
    disputes._message("D-0417", "northmart", "There was no cap on that promo. The deduction stands.", thread_of=run)
    # a figure nobody computed is held, not sent
    held = dispute_email.owner_reply(run, _dispute(run), "We'll settle for $999.99 if you pay this week.")
    assert held.status == "held" and held.written_by == "admin" and held.problems
    assert not [m for m in dispute_email.thread(run, "D-0417") if m.from_party == "clawback"]
    with pytest.raises(dispute_email.NotReady, match="already drafted"):  # fix the held one rather than start another
        dispute_email.owner_reply(run, _dispute(run), "Another try.")
    # fixed in plain words that stick to the dispute, it goes out on the same thread, answering their last message
    fixed = dispute_email.edit(held, None, held.body.replace(
        "We'll settle for $999.99 if you pay this week.",
        "Section 3.2 caps the promo at 5,000 units. Please send the signed change if the cap moved."))
    assert fixed.status == "ready"
    ok = dispute_email.send_reply(fixed.id, by="owner")
    assert ok.status == "outbox" and ok.replying_to and ok.subject.startswith("Re: ")
    assert [m.from_party for m in dispute_email.thread(run, "D-0417")][-1] == "clawback"
    assert any(e.type == "log" and e.data.actor == "owner" and "in their own words" in e.data.text for e in run.events)
    # once answered it's their turn again: a second answer is refused until they reply
    with pytest.raises(dispute_email.NotReady, match="hasn't replied"):
        dispute_email.owner_reply(run, _dispute(run), "One more thing.")
    # a clean answer to their next message is sent at once
    disputes._message("D-0417", "northmart", "We still think the cap was lifted.", thread_of=run)
    again = dispute_email.owner_reply(run, _dispute(run), "Please send the signed change that lifted it.")
    assert again.status == "outbox" and again.id.endswith("-R2")
