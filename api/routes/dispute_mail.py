"""Dispute email (api/dispute_email.py): review, edit and send each dispute, follow the thread, answer replies.

Every route needs the caller's supplier to own the dispute's run (api/tenancy.py): 404 otherwise. Sending and
editing are the admin's (require_role). `run_id` picks the run when a dispute number repeats across runs; without it,
the caller's newest run that filed the dispute.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from api import dispute_email, tenancy
from api.auth import require_role
from api.contracts import (
    DisputeEmail, DisputeEmailEdit, DisputeSendRequest, DisputeSendResponse, DisputeThread, SupplierNotification,
)
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["disputes"])


def _found(who: Caller, dispute_id: str, run_id: str | None):
    if run_id and not tenancy.can_see_run(who, run_id):
        raise HTTPException(404, f"unknown dispute {dispute_id}")
    found = dispute_email.find(dispute_id, run_id, tenancy.supplier_filter(who))
    if found is None:
        raise HTTPException(404, f"unknown dispute {dispute_id}")
    return found


def _thread(run, dispute) -> DisputeThread:
    return DisputeThread(dispute=dispute, run_id=run.id, messages=dispute_email.thread(run, dispute.id),
                         emails=dispute_email.emails_of(run.id, dispute.id))


@router.get("/disputes", response_model=list[DisputeThread])
def list_disputes(account: str | None = Query(default=None), who: Caller = Depends(current_supplier)) -> list[DisputeThread]:
    """Every dispute the caller's live runs filed (the newest version of each), newest run first."""
    if account:
        tenancy.account_or_404(who, account)
    out = []
    for run in reversed(tenancy.visible_runs(who)):
        if account and run.account.id != account:
            continue
        ids = list(dict.fromkeys(e.data.id for e in run.events if e.type == "dispute"))
        out += [_thread(run, dispute_email.latest(run, i)) for i in ids]
    return out


@router.get("/disputes/{dispute_id}/thread", response_model=DisputeThread)
def get_thread(dispute_id: str, run_id: str | None = Query(default=None),
               who: Caller = Depends(current_supplier)) -> DisputeThread:
    return _thread(*_found(who, dispute_id, run_id))


@router.get("/disputes/{dispute_id}/email", response_model=DisputeEmail)
def get_email(dispute_id: str, run_id: str | None = Query(default=None),
              who: Caller = Depends(current_supplier)) -> DisputeEmail:
    """The dispute's email: drafted on the first look (Claude, checked; the code template if the call fails)."""
    run, dispute = _found(who, dispute_id, run_id)
    return dispute_email.email_for(run, dispute)


@router.post("/disputes/{dispute_id}/email/redraft", response_model=DisputeEmail,
             dependencies=[Depends(require_role("owner"))])
def redraft(dispute_id: str, run_id: str | None = Query(default=None),
            who: Caller = Depends(current_supplier)) -> DisputeEmail:
    run, dispute = _found(who, dispute_id, run_id)
    return dispute_email.email_for(run, dispute, redraft=True)


@router.put("/disputes/{dispute_id}/email", response_model=DisputeEmail, dependencies=[Depends(require_role("owner"))])
def edit_email(dispute_id: str, req: DisputeEmailEdit, run_id: str | None = Query(default=None),
               who: Caller = Depends(current_supplier)) -> DisputeEmail:
    """The admin's edit: saved as ready if it passes the outbound filter, else held with the problems listed."""
    run, dispute = _found(who, dispute_id, run_id)
    try:
        return dispute_email.edit(dispute_email.email_for(run, dispute), req.subject, req.body)
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e


@router.post("/disputes/{dispute_id}/send", response_model=DisputeSendResponse,
             dependencies=[Depends(require_role("owner"))])
def send(dispute_id: str, req: DisputeSendRequest | None = None, run_id: str | None = Query(default=None),
         who: Caller = Depends(current_supplier)) -> DisputeSendResponse:
    """The admin's "Review and send": emails the dispute with its packet and files it. 409 when the email is held
    or the dispute was already sent; a Mailgun failure comes back as email.status "failed" (send again to retry)."""
    run, dispute = _found(who, dispute_id, run_id)
    emailed = any(e.kind == "dispute" and e.status in ("sent", "outbox") for e in dispute_email.emails_of(run.id, dispute_id))
    if emailed or dispute.status in ("filed", "withdrawn", "resolved"):  # answered on the portal first: may still go
        raise HTTPException(409, f"{dispute_id} is already {'sent' if emailed else dispute.status}")
    req = req or DisputeSendRequest()
    try:
        filed, email = dispute_email.send_dispute(run, dispute, "owner", req.subject, req.body)
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e
    return DisputeSendResponse(dispute=filed, email=email)


@router.post("/disputes/{dispute_id}/replies/{email_id}/send", response_model=DisputeEmail,
             dependencies=[Depends(require_role("owner"))])
def send_reply(dispute_id: str, email_id: str, req: DisputeSendRequest | None = None,
               run_id: str | None = Query(default=None), who: Caller = Depends(current_supplier)) -> DisputeEmail:
    """Send the Negotiator's drafted answer to the distributor's email (optionally edited)."""
    run, _ = _found(who, dispute_id, run_id)
    mine = {e.id for e in dispute_email.emails_of(run.id, dispute_id)}
    if email_id not in mine:
        raise HTTPException(404, f"unknown email {email_id}")
    req = req or DisputeSendRequest()
    try:
        return dispute_email.send_reply(email_id, req.subject, req.body)
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e
    except KeyError:
        raise HTTPException(404, f"unknown email {email_id}") from None


@router.get("/notifications", response_model=list[SupplierNotification])
def notifications(who: Caller = Depends(current_supplier)) -> list[SupplierNotification]:
    return dispute_email.notifications(tenancy.supplier_filter(who))


@router.get("/outbox", response_model=list[DisputeEmail])
def outbox(who: Caller = Depends(current_supplier)) -> list[DisputeEmail]:
    """Every dispute email and reply, drafted or sent: with no Mailgun keys (or DEMO_MODE) this is where they went."""
    return dispute_email.outbox(tenancy.supplier_filter(who))
