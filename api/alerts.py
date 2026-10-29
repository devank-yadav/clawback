"""The email the owner gets when the agents finish checking a payment (Settings: alert_on_check, to digest_email).

Payments start in the background (api/autopilot.py run_on_arrival), so nobody is watching when the agents decide. The
first time a run is decided (every charge settled, or waiting on the owner's answer), this says so: what the
distributor kept, what's being disputed, what was fair, and what needs the owner, with the weekly summary's one-tap
answers (api/digest.py: signed links, a confirm page, act once). Once per run: an answer later that finishes the run
sends nothing more.

Nothing goes without an address in Settings, or in DEMO_MODE, or without Gmail: the run's log says why, so the owner
can see it on the payment's page. Only a distributor's own months count (not the scenario box or the eval).
"""

from __future__ import annotations

import logging
import threading
from html import escape

from api import autopilot, digest, suppliers
from api.contracts import Contract

log = logging.getLogger("clawback.alerts")

_lock = threading.Lock()
_alerted: set[str] = set()  # run ids already told about


class Alert(Contract):
    run_id: str
    to: str | None
    subject: str
    text: str
    html: str
    items: list[digest.DigestItem]


class AlertSent(Contract):
    run_id: str
    status: str  # "sent", "not_sent", "off"
    to: str | None
    detail: str
    subject: str


SENT: dict[str, AlertSent] = {}  # the latest outcome per run, for the payment's log and the tests


def reset() -> None:
    with _lock:
        _alerted.clear()
        SENT.clear()


def build(run) -> Alert:
    """The email for one decided run: its own totals and its own needs-you items (the same ones Home shows)."""
    from api import supplier_overview as so

    settings = autopilot.of_account(run.account)
    them = run.distributor
    t = next((e.data for e in reversed(run.events) if e.type == "totals"), None)
    items = digest.items_of(so._needs_you([run]))
    disputed = t.disputed if t else 0
    n = len(items)
    things = f"{n} thing{'s' if n != 1 else ''} for you" if n else "nothing needs you"
    subject = (f"{them}’s payment is checked: {digest._money(disputed)} to get back, {things}" if disputed
               else f"{them}’s payment is checked: every charge was fair, {things}")
    head = f"The agents finished checking {them}’s payment."
    facts = [] if t is None else [
        f"{them} kept: {digest._money(t.taken)}",
        f"Getting back (disputed): {digest._money(t.disputed)}",
        f"Fair charges, accepted: {digest._money(t.accepted)}",
    ] + ([f"Waiting on you: {digest._money(t.waiting)}"] if t.waiting else [])
    lines = [head, "", *facts, ""]
    if items:
        lines.append("Needs you:" if n == 1 else f"Needs you ({n}):")
        lines += digest.item_lines(items)
    else:
        lines.append("Nothing needs you: the agents handled every charge.")
    page = f"{digest._app_base()}/app/agents?account={run.account.id}&run={run.id}"
    lines += ["", f"See the payment: {page}", "", "Turn these emails off in Settings."]
    html = (
        '<div style="font-family:Nunito,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#001c2e">'
        f'<p style="font-size:16px">{escape(head)}</p>'
        + "".join(f'<div style="font-weight:700;margin:2px 0">{escape(f)}</div>' for f in facts)
        + (f'<h2 style="font-size:20px;margin:18px 0 4px">Needs you</h2>{digest.item_rows(items)}' if items
           else '<p style="font-weight:700">Nothing needs you: the agents handled every charge.</p>')
        + f'<p><a href="{escape(page)}" style="color:#1a5fc8;font-weight:800">See the payment</a></p>'
        '<p style="color:#56697a;font-size:13px">Turn these emails off in Settings.</p></div>'
    )
    return Alert(run_id=run.id, to=settings.digest_email, subject=subject, text="\n".join(lines), html=html, items=items)


def on_decided(run) -> AlertSent | None:
    """Called when a run is first decided (api/pipeline.py _after_decisions). Once per run; never raises."""
    if run.kind not in run.account.months or run.account.id in suppliers._off(suppliers.supplier_of(run.account)):
        return None
    with _lock:
        if run.id in _alerted:
            return None
        _alerted.add(run.id)
    try:
        settings = autopilot.of_account(run.account)
        owner = run.name("owner")
        if not settings.alert_on_check:
            return None
        a = build(run)
        if not a.to:
            out = AlertSent(run_id=run.id, status="off", to=None, subject=a.subject,
                            detail="No email address in Settings, so nobody was emailed.")
        else:
            status, detail = digest.deliver(a.to, a.subject, a.text, a.html)
            out = AlertSent(run_id=run.id, status=status, to=a.to, detail=detail, subject=a.subject)
        SENT[run.id] = out
        if out.status == "sent":
            run.log(f"Emailed {owner} that the check is done: “{a.subject}”.", "good", "gate")
        elif out.status == "not_sent":
            run.log(f"Didn't email {owner} that the check is done: {out.detail}", "info", "gate")
        return out
    except Exception:  # noqa: BLE001 - an email must never break a run
        log.exception("alert for %s failed", run.id)
        return None
