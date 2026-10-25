"""Dispute email over Gmail: written (Claude, checked; the code template when the call fails), put in the supplier's
Gmail Drafts by IMAP APPEND when the admin says so (never sent by Clawback), filed when it shows in Sent or the admin
says "I sent it"; replies read from the same inbox, matched by In-Reply-To or the [D-n] tag, answered as Gmail drafts;
the emailed amendment concedes $1,000; the outbound filter holds a made-up figure. A fake IMAP server stands in."""

from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import dispute_email, disputes, inbound_email, pipeline
from api.agents import claude as claude_mod, email_writer
from api.agents.email_writer import LLMEmail
from api.integrations import gmail, replay
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



class FakeImap:
    """A Gmail-like IMAP server: special-use flags in LIST (a localized Drafts name), APPEND, SELECT, SEARCH, UID."""

    DRAFTS, SENT = "[Gmail]/Brouillons", "[Gmail]/Sent Mail"

    def __init__(self, password="app-pw"):
        self.password = password
        self.boxes: dict[str, list[tuple[str, bytes]]] = {"INBOX": [], self.DRAFTS: [], self.SENT: []}
        self.selected = None
        self.uids = 0
        self.logins = 0

    def login(self, user, password):
        import imaplib

        self.logins += 1
        if password != self.password:
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        return "OK", [b"ok"]

    def logout(self):
        return "BYE", [b""]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasChildren \\Noselect) "/" "[Gmail]"',
                      f'(\\HasNoChildren \\Drafts) "/" "{self.DRAFTS}"'.encode(),
                      f'(\\HasNoChildren \\Sent) "/" "{self.SENT}"'.encode()]

    @staticmethod
    def _name(box):
        return box[1:-1] if box.startswith('"') else box

    def append(self, box, flags, date, raw):
        assert "\\Draft" in flags
        self.boxes[self._name(box)].append((flags, raw))
        return "OK", [b"APPEND completed"]

    def select(self, box, readonly=False):
        self.selected = self._name(box)
        return "OK", [str(len(self.boxes[self.selected])).encode()]

    def _msgs(self):
        from email import message_from_bytes

        return [message_from_bytes(raw) for _, raw in self.boxes[self.selected]]

    def search(self, charset, *criteria):
        key, *rest = criteria
        if key == "HEADER":
            want = rest[1].strip('"')
            hits = [i + 1 for i, m in enumerate(self._msgs()) if m.get(rest[0]) == want]
        else:  # SUBJECT
            want = rest[0].strip('"')
            hits = [i + 1 for i, m in enumerate(self._msgs()) if want in (m.get("Subject") or "")]
        return "OK", [" ".join(map(str, hits)).encode()]

    def uid(self, command, *args):
        box = self.boxes[self.selected]
        if command == "SEARCH":
            return "OK", [" ".join(str(i + 1) for i in range(len(box))).encode()]
        uid = int(args[0])
        return "OK", [(f"{uid} (UID {uid} BODY[] {{1}}".encode(), box[uid - 1][1]), b")"]

    # what the test does as the person and as the distributor
    def deliver(self, raw: bytes):
        self.boxes["INBOX"].append(("", raw))

    def person_sends_draft(self, i=-1):
        self.boxes[self.SENT].append(self.boxes[self.DRAFTS][i])


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    pipeline.reset(), disputes.reset(), inbound_email.reset()
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    yield
    pipeline.reset(), disputes.reset(), inbound_email.reset()


@pytest.fixture
def imap(monkeypatch):
    server = FakeImap()
    monkeypatch.setenv("GMAIL_ADDRESS", "dana.peakbar@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pw")
    monkeypatch.setattr(gmail, "connect_fn", lambda: server)
    return server


def _dispute(run):
    return [e.data for e in run.events if e.type == "dispute"][-1]


def _parsed(raw: bytes):
    from email import policy
    from email.parser import BytesParser

    return BytesParser(policy=policy.default).parsebytes(raw)


def _distributor_reply(to_mid: str | None, subject: str, body: str, *, mid: str, attachment=None) -> bytes:
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


def test_disputes_start_as_drafts_and_the_email_is_written_from_the_lines():
    fake = EmailClaude()
    run = finished_march(fake)
    d = _dispute(run)
    assert (d.id, d.status, d.total, d.filed_at) == ("D-0417", "ready_to_send", D(4120), None)
    e = dispute_email.email_for(run, d, fake)
    assert e.status == "ready" and e.written_by == "claude" and not e.problems
    refs = ", ".join(ln.ref for ln in d.lines)
    assert e.subject == f"Dispute: Peak Bar Co., Remittance {d.remittance_id}, Deductions {refs}, $4,120.00 [D-0417]"
    assert e.to == "deductions@northmart.example" and e.reply_to is None
    assert e.body.startswith("Hello Northmart deductions team,") and e.body.count("disputed.") == 4
    assert "Dana Okafor" in e.body and e.attachments == ["D-0417-packet.pdf"]


def test_create_gmail_draft_appends_to_drafts_and_i_sent_it_files_the_dispute(imap, monkeypatch):
    from api.main import app

    fake = EmailClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    run = finished_march(fake)
    client = TestClient(app)
    email = client.get(f"/disputes/D-0417/email?run_id={run.id}").json()
    assert email["status"] == "ready" and email["from_addr"] == "Dana Okafor <dana.peakbar@gmail.com>"
    assert not imap.boxes[imap.DRAFTS]  # nothing goes to Gmail before the admin says so
    r = client.post(f"/disputes/D-0417/draft?run_id={run.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dispute"]["status"] == "ready_to_send"  # drafted is not sent
    assert body["email"]["status"] == "drafted" and body["email"]["drafted_at"]
    assert "[Gmail]/Brouillons" in body["email"]["detail"]  # found by the \Drafts flag, not by name
    ((flags, raw),) = imap.boxes[imap.DRAFTS]
    m = _parsed(raw)
    assert flags == "(\\Draft \\Seen)" and m["To"] == "deductions@northmart.example"
    assert m["From"] == "Dana Okafor <dana.peakbar@gmail.com>" and m["Subject"].endswith("[D-0417]")
    assert m["Message-ID"] == body["email"]["message_id"] and m["Message-ID"].endswith("@gmail.com>")
    (pdf,) = list(m.iter_attachments())
    assert pdf.get_filename() == "D-0417-packet.pdf" and pdf.get_content()[:4] == b"%PDF"
    assert not imap.boxes[imap.SENT]  # Clawback never sends
    assert client.post(f"/disputes/D-0417/draft?run_id={run.id}").status_code == 409  # one draft
    sent = client.post(f"/disputes/D-0417/sent?run_id={run.id}").json()  # "I sent it"
    assert (sent["dispute"]["status"], sent["email"]["status"]) == ("filed", "sent")
    assert _dispute(run).status == "filed"
    assert client.post(f"/disputes/D-0417/sent?run_id={run.id}").status_code == 409


def test_the_poller_files_the_dispute_once_gmail_shows_it_in_sent(imap):
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)
    assert dispute_email.poll_once(fake)["sent"] == 0 and _dispute(run).status == "ready_to_send"
    imap.person_sends_draft()
    assert dispute_email.poll_once(fake)["sent"] == 1
    assert _dispute(run).status == "filed" and dispute_email.EMAILS[e.id].status == "sent"


def test_no_gmail_keys_keeps_the_in_app_outbox_and_i_sent_it_still_files():
    fake = EmailClaude()
    run = finished_march(fake)
    d, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)
    assert d.status == "ready_to_send" and e.status == "outbox" and "no GMAIL_ADDRESS" in e.detail
    assert dispute_email.OUTBOX and dispute_email.OUTBOX[0][0] == e.id
    filed, done = dispute_email.mark_sent(e.id)
    assert filed.status == "filed" and done.status == "sent"
    assert dispute_email.poll_once(fake)["ok"] is False  # no keys: nothing polls


def test_a_wrong_app_password_fails_the_draft_and_nothing_is_drafted(imap, monkeypatch):
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "wrong")
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)
    assert e.status == "failed" and "app password" in e.detail and not imap.boxes[imap.DRAFTS]
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-pw")
    _, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)  # try again
    assert e.status == "drafted"


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


def test_the_outbound_filter_holds_an_admin_edit_with_a_made_up_figure(imap):
    fake = EmailClaude()
    run = finished_march(fake)
    d = _dispute(run)
    e = dispute_email.email_for(run, d, fake)
    held = dispute_email.edit(e, None, e.body + "\n\nPay us $7,777 and we'll drop the rest.")
    assert held.status == "held" and any("7,777" in p for p in held.problems)
    with pytest.raises(dispute_email.NotReady):
        dispute_email.draft_dispute(run, d)
    assert not imap.boxes[imap.DRAFTS]
    fixed = dispute_email.edit(held, "Dispute D-0417", e.body)
    assert fixed.status == "ready" and fixed.written_by == "admin"
    _, drafted = dispute_email.draft_dispute(run, d)
    assert _parsed(imap.boxes[imap.DRAFTS][0][1])["Subject"] == "Dispute D-0417 [D-0417]"  # the tag is kept


def test_a_reply_in_gmail_matches_by_in_reply_to_and_its_answer_becomes_a_gmail_draft(imap):
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)
    imap.person_sends_draft()
    assert dispute_email.poll_once(fake)["replies"] == 0  # the first look notes where INBOX stands
    imap.deliver(_distributor_reply(e.message_id, "RE: our deductions", "There was no unit cap on the Spring promo.\n\n"
                                    "On Sat, Dana wrote:\n> old text", mid="<r1@northmart.example>"))
    assert dispute_email.poll_once(fake)["replies"] == 1
    theirs = [m for m in dispute_email.thread(run, "D-0417") if m.from_party == "northmart"][-1]
    assert (theirs.channel, theirs.text, theirs.classification) == (
        "email", "There was no unit cap on the Spring promo.", "claim_without_document")
    (reply,) = [x for x in dispute_email.emails_of(run.id, "D-0417") if x.kind == "reply"]
    assert reply.status == "ready" and reply.in_reply_to == "<r1@northmart.example>" and "signed change" in reply.body
    (n,) = dispute_email.notifications()
    assert "Northmart replied to D-0417" in n.text
    drafted = dispute_email.draft_reply(reply.id)
    assert drafted.status == "drafted"
    m = _parsed(imap.boxes[imap.DRAFTS][-1][1])
    assert m["In-Reply-To"] == "<r1@northmart.example>" and m["Subject"].startswith("Re: Dispute: Peak Bar Co.")
    assert e.message_id in m["References"]
    assert not [x for x in dispute_email.thread(run, "D-0417") if x.from_party == "clawback"]  # not sent yet
    _, done = dispute_email.mark_sent(reply.id)
    assert done.status == "sent"
    assert [x.channel for x in dispute_email.thread(run, "D-0417") if x.from_party == "clawback"] == ["email"]
    assert dispute_email.poll_once(fake)["replies"] == 0  # read once


def test_a_reply_matches_by_the_subject_tag_alone_and_our_own_mail_is_skipped(imap):
    fake = EmailClaude()
    run = finished_march(fake)
    dispute_email.draft_dispute(run, _dispute(run), client=fake)
    dispute_email.poll_once(fake)
    imap.deliver(_distributor_reply(None, "Re: Dispute: Peak Bar Co. [D-0417]",
                                    "Agreed, Mint wasn't part of the Spring promo.", mid="<r2@northmart.example>"))
    own = _distributor_reply(None, "[D-0417] note to self", "x", mid="<own@gmail.com>").replace(
        b"Desk <deductions@northmart.example>", b"dana.peakbar@gmail.com")
    imap.deliver(own)
    imap.deliver(_distributor_reply(None, "Lunch?", "unrelated", mid="<r3@x>"))
    assert dispute_email.poll_once(fake)["replies"] == 1
    theirs = [m for m in dispute_email.thread(run, "D-0417") if m.from_party == "northmart"]
    assert [m.classification for m in theirs] == ["agrees"]


def test_the_signed_amendment_by_gmail_concedes_1000(imap):
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)
    dispute_email.mark_sent(e.id)
    dispute_email.poll_once(fake)
    text = run.account.docs["amendment-1"].read_bytes()
    imap.deliver(_distributor_reply(e.message_id, "Re: dispute", "The cap was raised to 6,000 units. Signed amendment "
                                    "attached.", mid="<r4@northmart.example>", attachment=("amendment-1.md", text)))
    dispute_email.poll_once(fake)
    assert final(run)["C4"] == ("split", D(540), D(1000))
    t = last_totals(run)
    assert (t.disputed, t.accepted) == (D(3120), D(3730))
    (reply,) = [x for x in dispute_email.emails_of(run.id, "D-0417") if x.kind == "reply"]
    assert "withdraw $1,000" in reply.body and reply.status == "ready"
    assert "now totals $3,120" in dispute_email.notifications()[0].text


def test_an_unknown_attachment_is_held_for_the_owner():
    fake = EmailClaude()
    run = finished_march(fake)
    _, e = dispute_email.draft_dispute(run, _dispute(run), client=fake)
    msg = dispute_email.as_message(_distributor_reply(e.message_id, "Re", "See attached.", mid="<r5@x>",
                                                      attachment=("scan.md", b"something else")))
    dispute_email.on_reply(*dispute_email.route(msg), msg, fake)
    assert final(run)["C4"] == ("dispute", D(1540), D(0))
    assert any("doesn't have (scan)" in ev.data.text for ev in run.events if ev.type == "log")


def test_auto_draft_puts_it_in_drafts_within_the_limit_but_never_files(imap, monkeypatch):
    monkeypatch.setattr(dispute_email, "auto_draft", lambda: True)
    fake = EmailClaude()
    run = finished_march(fake)
    d = _dispute(run)
    assert (d.status, d.approved_by) == ("ready_to_send", "policy")
    assert dispute_email.emails_of(run.id, "D-0417")[0].status == "drafted" and len(imap.boxes[imap.DRAFTS]) == 1
    assert not imap.boxes[imap.SENT]


def test_another_supplier_cant_see_or_draft_the_dispute(monkeypatch):
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
                         ("POST", "/disputes/D-0417/draft"), ("POST", "/disputes/D-0417/sent"),
                         ("POST", "/disputes/D-0417/send"), ("PUT", "/disputes/D-0417/email"),
                         ("POST", "/disputes/D-0417/replies/EM-x/draft"), ("POST", "/disputes/D-0417/replies/EM-x/sent")]:
        r = teresa.request(method, path, json={"body": "x"} if method == "PUT" else None)
        assert r.status_code == 404, (method, path, r.status_code)
    assert teresa.get("/disputes").json() == [] and teresa.get("/outbox").json() == []
    assert _dispute(run).status == "ready_to_send"
    users.reset()
    accounts.clear()
