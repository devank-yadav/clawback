"""The owner's Settings (api/autopilot.py) and the weekly summary (api/digest.py).

GET  /settings/autopilot          the signed-in supplier's limits
PUT  /settings/autopilot          change any of them (the owner)
GET  /digest/preview              this week's summary, as it would be sent
POST /digest/send                 send it now to the address in Settings
GET  /tap/{token}                 a one-tap link from the email: a confirm page (no sign-in: the signed token is the key)
POST /tap/{token}                 the confirm button: answers the question or approves the memo, once
"""

from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import Field

from api import autopilot, digest
from api.auth import limit, require_role
from api.contracts import Contract, Money
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["settings"])


class AutopilotChange(Contract):
    run_on_arrival: bool | None = None
    send_disputes_under: Money | None = None
    post_fair_under: Money | None = None
    digest_email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    digest_weekly: bool | None = None
    # Explicit "turn this limit off": a null above means "leave as is".
    clear: list[str] = []


@router.get("/settings/autopilot", response_model=autopilot.Autopilot)
def get_autopilot(who: Caller = Depends(current_supplier)) -> autopilot.Autopilot:
    return autopilot.get(digest.supplier_of(who))


@router.put("/settings/autopilot", response_model=autopilot.Autopilot, dependencies=[Depends(require_role("owner"))])
def put_autopilot(req: AutopilotChange, who: Caller = Depends(current_supplier)) -> autopilot.Autopilot:
    changes = {k: v for k, v in req.model_dump(exclude={"clear"}).items() if v is not None}
    for name in req.clear:
        if name not in ("send_disputes_under", "post_fair_under", "digest_email"):
            raise HTTPException(422, f"can't clear {name!r}")
        changes[name] = None
    for name in ("send_disputes_under", "post_fair_under"):
        if changes.get(name) is not None and changes[name] <= 0:
            raise HTTPException(422, f"{name} must be more than $0 (or cleared)")
    by = who.user.name if who.user else None
    return autopilot.update(digest.supplier_of(who), by, **changes)


@router.get("/digest/preview", response_model=digest.Digest)
def preview(who: Caller = Depends(current_supplier)) -> digest.Digest:
    return digest.build(who)


@router.post("/digest/send", response_model=digest.DigestSent,
             dependencies=[Depends(require_role("owner")), Depends(limit("ai"))])
def send_now(who: Caller = Depends(current_supplier)) -> digest.DigestSent:
    return digest.send(who)


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{escape(title)} · Clawback</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f2f8ff;color:#001c2e;
font-family:Nunito,ui-rounded,system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif;padding:16px}}
main{{max-width:440px;width:100%;background:#fff;border:2px solid #001c2e;border-radius:20px;box-shadow:0 4px 0 #001c2e;padding:28px}}
h1{{font-size:26px;line-height:1.15;margin:0 0 8px}} p{{color:#43566a;font-weight:600;font-size:16px;line-height:1.5;margin:0 0 16px}}
button,a.btn{{display:inline-flex;align-items:center;justify-content:center;min-height:50px;padding:0 22px;border:2px solid #001c2e;
border-radius:999px;background:#1f6fe5;color:#fff;font:inherit;font-size:16px;font-weight:800;text-decoration:none;
box-shadow:inset 0 2px 0 rgba(255,255,255,.45),0 4px 0 #1450b8;cursor:pointer}}
a.ghost{{background:#fff;color:#001c2e;box-shadow:0 4px 0 #001c2e;margin-left:8px}}
.mark{{font-weight:900;color:#1a5fc8;font-size:14px;margin-bottom:12px}}
</style></head><body><main><div class="mark">clawback</div>{body}</main></body></html>""")


@router.get("/tap/{token}", response_class=HTMLResponse)
def tap_confirm(token: str) -> HTMLResponse:
    payload = digest.verify(token)
    if payload is None:
        return _page("Link expired", "<h1>This link has expired</h1><p>Links in the weekly summary work for 14 days. "
                     f'Open Clawback to see what needs you now.</p><a class="btn" href="{escape(digest._app_base())}/app">Open Clawback</a>')
    what = escape(digest.describe(payload))
    return _page("Confirm", f"<h1>{what}?</h1><p>Tap to confirm. It applies to this one item only.</p>"
                 f'<form method="post"><button type="submit">Confirm</button>'
                 f'<a class="btn ghost" href="{escape(digest._app_base())}/app">Open Clawback instead</a></form>')


@router.post("/tap/{token}", response_class=HTMLResponse, dependencies=[Depends(limit("runs"))])
def tap_act(token: str) -> HTMLResponse:
    payload = digest.verify(token)
    if payload is None:
        return _page("Link expired", "<h1>This link has expired</h1><p>Open Clawback to see what needs you now.</p>")
    r = digest.act(payload)
    return _page(r.title, f"<h1>{escape(r.title)}</h1><p>{escape(r.detail)}</p>"
                 f'<a class="btn" href="{escape(digest._app_base())}/app">Open Clawback</a>')
