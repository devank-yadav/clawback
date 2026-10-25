"""Dispute email (api/dispute_email.py): review and edit each dispute's email, put it in the supplier's Gmail Drafts,
mark it sent, follow the thread, answer replies. Clawback never sends an email itself.

Every route needs the caller's supplier to own the dispute's run (api/tenancy.py): 404 otherwise. Drafting,
editing and marking sent are the admin's (require_role). `run_id` picks the run when a dispute number repeats across runs; without it,
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


def _draft(dispute_id: str, req: DisputeSendRequest | None, run_id: str | None, who: Caller) -> DisputeSendResponse:
    run, dispute = _found(who, dispute_id, run_id)
    if dispute.status in ("filed", "withdrawn", "resolved"):  # answered on the portal first: it may still be drafted
        raise HTTPException(409, f"{dispute_id} is already {dispute.status}")
    req = req or DisputeSendRequest()
    try:
        now, email = dispute_email.draft_dispute(run, dispute, "owner", req.subject, req.body)
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e
    return DisputeSendResponse(dispute=now, email=email)


@router.post("/disputes/{dispute_id}/draft", response_model=DisputeSendResponse,
             dependencies=[Depends(require_role("owner"))])
def create_gmail_draft(dispute_id: str, req: DisputeSendRequest | None = None, run_id: str | None = Query(default=None),
                       who: Caller = Depends(current_supplier)) -> DisputeSendResponse:
    """The admin's "Create Gmail draft": the reviewed email, to the distributor's desk with the packet PDF, goes to
    the supplier's Gmail Drafts (email.status "drafted"; "outbox" with no Gmail keys or in DEMO_MODE; "failed" if
    Gmail didn't take it: try again). Clawback never sends; the dispute stays ready_to_send until the email is sent.
    409 when the email is held or already drafted."""
    return _draft(dispute_id, req, run_id, who)


@router.post("/disputes/{dispute_id}/send", response_model=DisputeSendResponse, include_in_schema=False,
             dependencies=[Depends(require_role("owner"))])
def send(dispute_id: str, req: DisputeSendRequest | None = None, run_id: str | None = Query(default=None),
         who: Caller = Depends(current_supplier)) -> DisputeSendResponse:
    """The old name of POST /disputes/{id}/draft, kept so an older screen still works. It drafts; it never sends."""
    return _draft(dispute_id, req, run_id, who)


def _dispute_email_id(run, dispute_id: str) -> str:
    found = next((e.id for e in dispute_email.emails_of(run.id, dispute_id) if e.kind == "dispute"), None)
    if found is None:
        raise HTTPException(409, f"{dispute_id} has no email yet: create the Gmail draft first")
    return found


@router.post("/disputes/{dispute_id}/sent", response_model=DisputeSendResponse,
             dependencies=[Depends(require_role("owner"))])
def i_sent_it(dispute_id: str, run_id: str | None = Query(default=None),
              who: Caller = Depends(current_supplier)) -> DisputeSendResponse:
    """The admin's "I sent it": the drafted email went out from Gmail, so the dispute is filed. (The poller does the
    same on its own when the email shows in Gmail's Sent.) 409 if it isn't drafted yet or is already marked sent."""
    run, _ = _found(who, dispute_id, run_id)
    try:
        filed, email = dispute_email.mark_sent(_dispute_email_id(run, dispute_id))
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e
    return DisputeSendResponse(dispute=filed or dispute_email.latest(run, dispute_id), email=email)


def _reply_of(who: Caller, dispute_id: str, email_id: str, run_id: str | None):
    run, _ = _found(who, dispute_id, run_id)
    if email_id not in {e.id for e in dispute_email.emails_of(run.id, dispute_id) if e.kind == "reply"}:
        raise HTTPException(404, f"unknown email {email_id}")
    return run


@router.post("/disputes/{dispute_id}/replies/{email_id}/draft", response_model=DisputeEmail,
             dependencies=[Depends(require_role("owner"))])
def draft_reply(dispute_id: str, email_id: str, req: DisputeSendRequest | None = None,
                run_id: str | None = Query(default=None), who: Caller = Depends(current_supplier)) -> DisputeEmail:
    """The Negotiator's answer to the distributor's email (optionally edited) into Gmail Drafts."""
    _reply_of(who, dispute_id, email_id, run_id)
    req = req or DisputeSendRequest()
    try:
        return dispute_email.draft_reply(email_id, req.subject, req.body)
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e


@router.post("/disputes/{dispute_id}/replies/{email_id}/sent", response_model=DisputeEmail,
             dependencies=[Depends(require_role("owner"))])
def reply_sent(dispute_id: str, email_id: str, run_id: str | None = Query(default=None),
               who: Caller = Depends(current_supplier)) -> DisputeEmail:
    """"I sent it" for a reply: it joins the dispute's thread."""
    _reply_of(who, dispute_id, email_id, run_id)
    try:
        return dispute_email.mark_sent(email_id)[1]
    except dispute_email.NotReady as e:
        raise HTTPException(409, str(e)) from e


@router.get("/notifications", response_model=list[SupplierNotification])
def notifications(who: Caller = Depends(current_supplier)) -> list[SupplierNotification]:
    return dispute_email.notifications(tenancy.supplier_filter(who))


@router.get("/outbox", response_model=list[DisputeEmail])
def outbox(who: Caller = Depends(current_supplier)) -> list[DisputeEmail]:
    """Every dispute email and reply of the caller's, whatever its status: with no Gmail keys (or in DEMO_MODE),
    drafts wait here instead of in Gmail Drafts."""
    return dispute_email.outbox(tenancy.supplier_filter(who))
