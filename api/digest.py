"""The weekly summary email, with one-tap answers (Settings: api/autopilot.py digest_email, digest_weekly).

What it says comes from the same company overview as Home (api/supplier_overview.py): the money being clawed back, what
came back, the fair total, and what needs the owner. Each open question gets one link per choice, and each credit memo
waiting for a yes gets an "approve" link, so the owner can answer from their inbox. A dispute email to review and a
distributor's reply link into the app: those deserve a read first.

One-tap links: /tap/<token>. The token names exactly one action (this question, this choice; or this memo), expires in
14 days, and is signed with HMAC-SHA256 (DIGEST_SECRET, else a random secret kept in the state folder). Opening the
link shows a confirm page; only its button (a POST) acts, so an email scanner that follows links can't answer for you.
An answer to a question that's already answered, or a memo already decided, changes nothing.

Sending uses the supplier's Gmail (api/integrations/gmail.py); without it, or in DEMO_MODE, nothing is sent and the
reason comes back. A weekly loop sends Monday mornings (15:00 UTC, 8 AM Pacific) to each supplier that turned it on.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path

from api import accounts, autopilot, pipeline, suppliers, tenancy
from api.contracts import Contract

log = logging.getLogger("clawback.digest")

TOKEN_DAYS = 14


class TapAction(Contract):
    label: str
    url: str


class DigestItem(Contract):
    title: str
    distributor: str
    amount: float | None = None
    level: str
    actions: list[TapAction]  # one-tap answers; empty: open_url instead
    open_url: str


class Digest(Contract):
    to: str | None
    subject: str
    text: str
    html: str
    items: list[DigestItem]


class DigestSent(Contract):
    status: str  # "sent" or "not_sent"
    to: str | None
    detail: str
    subject: str


# ---------------------------------------------------------------- the signed links

def _secret() -> bytes:
    env = (os.getenv("DIGEST_SECRET") or "").strip()
    if env:
        return env.encode()
    path = Path(os.getenv("CLAWBACK_STATE_DIR", "state")) / "digest-secret"
    try:
        return path.read_bytes()
    except OSError:
        path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_hex(32).encode()
        path.write_bytes(value)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return value


def sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps({**payload, "x": int(time.time()) + TOKEN_DAYS * 86400},
                                               separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{body}.{sig}"


def verify(token: str) -> dict | None:
    try:
        body, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    want = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    if not hmac.compare_digest(sig, want):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if int(payload.get("x", 0)) < time.time():
        return None
    return payload


def _app_base() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "http://localhost:3000").rstrip("/")


def _api_base() -> str:
    """Where /tap is served: API_PUBLIC_URL, else the site's /api (Caddy strips the prefix on the VM)."""
    return (os.getenv("API_PUBLIC_URL") or f"{_app_base()}/api").rstrip("/")


def tap_url(payload: dict) -> str:
    return f"{_api_base()}/tap/{sign(payload)}"


# ---------------------------------------------------------------- what the email says

def _money(v) -> str:
    return f"${float(v):,.2f}"


def supplier_of(who: tenancy.Caller) -> str:
    return who.supplier_id or suppliers.supplier_of(accounts.get(accounts.DEFAULT))


def build(who: tenancy.Caller) -> Digest:
    from api import supplier_overview as so

    o = so.overview(who)
    t = o.totals
    settings = autopilot.get(supplier_of(who))
    items: list[DigestItem] = []
    for n in o.needs_you:
        open_url = f"{_app_base()}/app"
        actions: list[TapAction] = []  # the item's own one-tap choices (supplier_overview), as signed links
        if n.kind == "question" and n.target_id:
            actions = [TapAction(label=c.label, url=tap_url({"k": "q", "id": n.target_id, "t": c.text, "r": c.rule, "l": c.label}))
                       for c in n.choices]
        elif n.kind == "approval" and n.target_id:
            actions = [TapAction(label=c.label, url=tap_url({"k": "a", "id": n.target_id, "l": c.label})) for c in n.choices]
        if n.link.dispute_id:
            open_url = f"{_app_base()}/app/disputes?account={n.account_id}&id={n.link.dispute_id}"
        items.append(DigestItem(title=n.title, distributor=n.distributor, amount=float(n.amount) if n.amount is not None else None,
                                level=n.risk_level, actions=actions, open_url=open_url))

    back, got, fair = _money(t.disputed_awaiting_reply), _money(t.recovered), _money(t.fair)
    open_n = len(o.open_disputes)
    subject = (f"Clawback: {back} on its way back, {len(items)} thing{'s' if len(items) != 1 else ''} for you"
               if items else f"Clawback: {back} on its way back, nothing needs you")
    lines = [
        "Here’s where your money stands this week.",
        "",
        f"Getting back: {back} in {open_n} open dispute{'s' if open_n != 1 else ''}",
        f"Back in your account: {got}",
        f"Fair charges, accepted: {fair}",
        "",
    ]
    if items:
        lines.append("Needs you:" if len(items) == 1 else f"Needs you ({len(items)}):")
        for it in items:
            # titles name the distributor already ("Northmart kept $1,200 for ..."); prefix only one that doesn't
            lines.append(f"- {it.title}" if it.distributor in it.title else f"- {it.distributor}: {it.title}")
            for a in it.actions:
                lines.append(f"    {a.label}: {a.url}")
            if not it.actions:
                lines.append(f"    Open it: {it.open_url}")
    else:
        lines.append("Nothing needs you. The agents keep checking every payment that comes in.")
    lines += ["", f"Open Clawback: {_app_base()}/app", "", "You get this every Monday. Turn it off in Settings."]
    text = "\n".join(lines)

    def btn(a: TapAction, primary: bool) -> str:
        bg, fg = ("#1f6fe5", "#ffffff") if primary else ("#ffffff", "#001c2e")
        return (f'<a href="{escape(a.url)}" style="display:inline-block;margin:4px 6px 4px 0;padding:10px 16px;'
                f'border:2px solid #001c2e;border-radius:999px;background:{bg};color:{fg};font-weight:800;'
                f'text-decoration:none;box-shadow:0 3px 0 #001c2e">{escape(a.label)}</a>')

    rows = "".join(
        f'<div style="margin:14px 0;padding:16px;border:2px solid #001c2e;border-radius:16px;box-shadow:0 4px 0 #001c2e">'
        f'<div style="font-size:12px;font-weight:900;color:#56697a">{escape(it.distributor)} · {escape(it.level.title())}</div>'
        f'<div style="font-size:17px;font-weight:700;margin:6px 0 10px;color:#001c2e">{escape(it.title)}</div>'
        + ("".join(btn(a, i == 0) for i, a in enumerate(it.actions)) if it.actions
           else btn(TapAction(label="Open in Clawback", url=it.open_url), True))
        + "</div>" for it in items)
    stat = lambda label, v, color: (f'<td style="padding:12px;border:2px solid {color};border-radius:12px">'  # noqa: E731
                                    f'<div style="font-size:12px;font-weight:900;color:{color}">{label}</div>'
                                    f'<div style="font-size:22px;font-weight:900;color:{color}">{v}</div></td>')
    html = (
        '<div style="font-family:Nunito,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#001c2e">'
        '<p style="font-size:16px">Here’s where your money stands this week.</p>'
        f'<div style="font-size:13px;font-weight:900;color:#c22f2e">Getting back</div>'
        f'<div style="font-size:40px;font-weight:900;color:#c22f2e;line-height:1.1">{back}</div>'
        f'<div style="color:#43566a;font-weight:600">in {open_n} open dispute{"s" if open_n != 1 else ""}</div>'
        '<table style="border-collapse:separate;border-spacing:8px 12px;margin:0 -8px"><tr>'
        + stat("Back in your account", got, "#0d7150") + stat("Fair charges", fair, "#1d5fb0") + "</tr></table>"
        + (f'<h2 style="font-size:20px;margin:18px 0 4px">Needs you</h2>{rows}' if items
           else '<p style="font-weight:700">Nothing needs you. The agents keep checking every payment that comes in.</p>')
        + f'<p><a href="{escape(_app_base())}/app" style="color:#1a5fc8;font-weight:800">Open Clawback</a></p>'
        '<p style="color:#56697a;font-size:13px">You get this every Monday. Turn it off in Settings.</p></div>'
    )
    return Digest(to=settings.digest_email, subject=subject, text=text, html=html, items=items)


def send(who: tenancy.Caller) -> DigestSent:
    from api.integrations import gmail, replay

    d = build(who)
    if not d.to:
        return DigestSent(status="not_sent", to=None, detail="Add the email address to send it to, in Settings.", subject=d.subject)
    if replay.demo_mode() or not gmail.configured():
        return DigestSent(status="not_sent", to=d.to, subject=d.subject,
                          detail=gmail.why_simulated() or "Gmail isn't connected on this server, so nothing was sent.")
    msg = EmailMessage()
    msg["From"] = f"Clawback <{gmail.address()}>"
    msg["To"] = d.to
    msg["Subject"] = d.subject
    msg.set_content(d.text)
    msg.add_alternative(d.html, subtype="html")
    try:
        gmail.send(msg.as_bytes(), d.to)
    except gmail.GmailError as e:
        return DigestSent(status="not_sent", to=d.to, detail=str(e), subject=d.subject)
    autopilot.update(supplier_of(who), None, digest_last_sent=datetime.now(timezone.utc))
    return DigestSent(status="sent", to=d.to, detail="Sent from the supplier’s Gmail.", subject=d.subject)


# ---------------------------------------------------------------- acting on a tap

class TapResult(Contract):
    ok: bool
    title: str
    detail: str


def describe(payload: dict) -> str:
    return str(payload.get("l") or ("Approve the credit memo" if payload.get("k") == "a" else "Answer"))


def act(payload: dict) -> TapResult:
    kind, target = payload.get("k"), str(payload.get("id") or "")
    if kind == "q":
        q = next((q for run in pipeline.RUNS.values() for q in run.questions.values() if q.id == target), None)
        if q is None or target not in pipeline.QUESTIONS:
            return TapResult(ok=False, title="That question isn’t open anymore", detail="It may belong to a run that was replaced. Open Clawback to see what needs you now.")
        if not pipeline.is_open(q):
            return TapResult(ok=True, title="Already answered", detail=f"This one was answered: “{q.answer or ''}”. Nothing changed.")
        try:
            ans, rule = pipeline.answer(target, str(payload.get("t") or ""), "owner", save_rule=bool(payload.get("r")))
        except pipeline.QuestionClosed:
            return TapResult(ok=False, title="That question was closed", detail="A newer run of the same payment asked it again. Open Clawback to answer it.")
        if pipeline.is_open(pipeline.RUNS[pipeline.QUESTIONS[target][0]].questions[target]):  # the answer didn't fit
            return TapResult(ok=False, title="That answer didn’t fit this charge",
                             detail="Nothing changed and the question is still open. Open Clawback to answer it in your own words.")
        return TapResult(ok=True, title="Done", detail=f"Your answer is in: “{describe(payload)}”." + (" Saved as a rule, so you won’t be asked again." if rule else ""))
    if kind == "a":
        run = next((r for r in pipeline.RUNS.values() for e in r.events if e.type == "approval" and e.data.id == target), None)
        current = next((e.data for e in reversed(run.events) if e.type == "approval" and e.data.id == target), None) if run else None
        if current is None:
            return TapResult(ok=False, title="That credit memo isn’t here anymore", detail="Open Clawback to see what needs you now.")
        if current.status != "pending":
            return TapResult(ok=True, title="Already decided", detail="This credit memo was already approved or held. Nothing changed.")
        pipeline.decide_approval(target, True, None, False)
        return TapResult(ok=True, title="Sent to QuickBooks", detail=f"{describe(payload)}: done. The disputed money stays open with the distributor.")
    return TapResult(ok=False, title="That link doesn’t work", detail="Open Clawback to see what needs you.")


# ---------------------------------------------------------------- every Monday

_thread: threading.Thread | None = None


def _due(settings: autopilot.Autopilot, now: datetime) -> bool:
    if not (settings.digest_weekly and settings.digest_email):
        return False
    if now.weekday() != 0 or now.hour < 15:
        return False
    return settings.digest_last_sent is None or now - settings.digest_last_sent > timedelta(days=6)


def tick(now: datetime | None = None) -> list[str]:
    """Send every supplier's digest that's due. Returns the suppliers it went to."""
    now = now or datetime.now(timezone.utc)
    sent = []
    for sid, settings in autopilot.every().items():
        if _due(settings, now) and send(tenancy.Caller(supplier_id=sid, via="digest")).status == "sent":
            sent.append(sid)
    return sent


def start_weekly() -> bool:
    """The Monday loop, checked hourly; off with DIGEST_WEEKLY=off or without Gmail."""
    global _thread
    from api.integrations import gmail, replay

    if _thread or os.getenv("DIGEST_WEEKLY", "on").lower() == "off" or replay.demo_mode() or not gmail.configured():
        return False

    def loop():
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001 - one bad week must not stop the loop
                log.exception("weekly digest failed")
            time.sleep(3600)

    _thread = threading.Thread(target=loop, name="digest-weekly", daemon=True)
    _thread.start()
    return True
