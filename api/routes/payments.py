"""The payment screen's "Northmart pays" button (F15), for any account: POST /payments/{account}.
POST /payments/northmart is Peak Bar's (the screens and the demo script call it by that name).

A payment the distributor sends from its portal (POST /portal/payments/{account}) doesn't start anything: it waits
on the Agents page as "1 payment received" (GET /payments/pending) until the admin presses "Run the agents"
(POST /payments/pending/{id}/run), which starts it the way the button above does.

With Nessie keys: post the account's deposit (its invoice's received amount, described as its nessie_description:
Peak Bar's $41,350 "Northmart remittance INV-3102") to the Nessie sandbox. If the poller is running it starts the run
when it sees the deposit (within 5 seconds) and this waits up to 10 s to return that run; if not, this starts it
for that deposit. Without keys, or in DEMO_MODE, the run starts directly: the button is the fallback the design names.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException

from api import accounts, autopilot, fee_accounts, pipeline, rows, tenancy
from api.auth import limit
from api.contracts import (
    Charge, DraftLine, FoundPayment, PaymentDraft, PaymentResponse, PaymentSync, PendingPayment, PortalPaymentRequest,
)
from api.engine import totals
from api.integrations import nessie, replay
from api.routes.runs import account_or_404
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["payments"])

POLLER_WAIT_S = 10.0  # the design's bar: a deposit starts the run within 10 seconds

# Payments sent from a distributor's portal, waiting for "Run the agents". In memory: a demo reset clears them.
_PENDING: dict[str, PendingPayment] = {}
_EDITED: dict[str, list[Charge]] = {}  # a waiting payment's lines, when the distributor edited them on its portal
_sent = 0


@dataclass(frozen=True)
class PortalPayment:
    """What the distributor sent from its portal with lines it edited: the run's arrival (pipeline._arrived)."""

    id: str
    amount: Decimal
    description: str
    source: str = "portal"


def reset() -> None:
    global _sent
    _PENDING.clear()
    _EDITED.clear()
    _sent = 0


def _poller_run(deposit_id: str) -> pipeline.Run | None:
    """Wait for the poller to see this deposit, so the button gets the run it started (not the previous one)."""
    end = time.monotonic() + POLLER_WAIT_S
    while (run := pipeline.run_for_deposit(deposit_id)) is None and time.monotonic() < end:
        time.sleep(0.1)
    return run


@router.post("/payments/sync", response_model=PaymentSync, dependencies=[Depends(limit("runs"))])
def sync_payments(who: Caller = Depends(current_supplier)) -> PaymentSync:
    """"Check for new payments": one look at the bank (Nessie) and QuickBooks, as their pollers do every few
    seconds. A payment their pollers see starts its account's run. Nothing else counts: when they have nothing new,
    the answer is "No new payments" (a demo payment comes from the distributor's portal or the presenter menu)."""
    from api.integrations import qbo_source

    checked: list[str] = []
    found: list[FoundPayment] = []
    if not replay.demo_mode():
        if nessie.poller:
            checked.append("bank")
            for d in nessie.poller.tick():
                run = pipeline.run_for_deposit(d.id)
                if run and tenancy.can_see(who, run.account):
                    found.append(FoundPayment(source="bank", account_id=run.account.id, distributor=run.distributor,
                                              amount=d.amount, invoice_id=run.account.invoice.id, run_id=run.id))
        if qbo_source.poller:
            checked.append("quickbooks")
            for p in qbo_source.poller.tick():
                run = pipeline.latest(account=p.account_id)
                if run and tenancy.can_see(who, run.account):
                    found.append(FoundPayment(source="quickbooks", account_id=run.account.id,
                                              distributor=run.distributor, amount=getattr(p, "amount", None),
                                              invoice_id=run.account.invoice.id, run_id=run.id))
    if not found:
        return PaymentSync(checked=checked, found=[], message="No new payments.")
    names = ", ".join(f"{f.distributor} paid ${f.amount:,.2f} on {f.invoice_id}" if f.amount is not None
                      else f"{f.distributor} paid {f.invoice_id}" for f in found)
    started = any(f.run_id for f in found)
    return PaymentSync(checked=checked, found=found,
                       message=f"{names}. " + ("The agents are checking it." if started else "New payment received."))


@router.post("/payments/northmart", response_model=PaymentResponse, dependencies=[Depends(limit("runs"))])
def northmart_pays(who: Caller = Depends(current_supplier)) -> PaymentResponse:
    return _pays(accounts.DEFAULT, who)


@router.post("/payments/{account}", response_model=PaymentResponse, dependencies=[Depends(limit("runs"))])
def account_pays(account: str, who: Caller = Depends(current_supplier)) -> PaymentResponse:
    return _pays(account, who)


def _pays(account_id: str, who: Caller, edited: list[Charge] | None = None) -> PaymentResponse:
    return _start(account_or_404(account_id, who), edited)


def _start(account: accounts.Account, edited: list[Charge] | None = None) -> PaymentResponse:
    """Start the agents on the account's payment: a Nessie deposit when the keys are set, else directly. A payment the
    distributor edited on its portal starts directly with its own lines and the amount they leave paid."""
    if edited is not None:
        paid = _paid(account, edited)
        arrival = PortalPayment(id=f"portal-{uuid.uuid4().hex[:8]}", amount=paid,
                                description=f"{len(edited)} deduction{'s' if len(edited) != 1 else ''} taken")
        run = pipeline.start(None, account=account, charges=edited, deposit=arrival)
        return PaymentResponse(via="direct", deposit_id=None, run_id=run.id,
                               message=f"Run started for the ${paid:,.2f} payment sent from the portal.")
    client = None if replay.demo_mode() else nessie.client()
    if client is None:
        run = pipeline.start(None, account=account)
        why = "DEMO_MODE" if replay.demo_mode() else "no Nessie keys"
        return PaymentResponse(via="direct", deposit_id=None, run_id=run.id,
                               message=f"Run started directly ({why}).")
    try:
        deposit = client.post_deposit(account.invoice.received, account.config.nessie_description)
    except nessie.NessieError as e:
        raise HTTPException(502, f"Nessie didn't take the deposit: {e}") from None
    if nessie.poller and nessie.poller.running:
        run = _poller_run(deposit.id)
        return PaymentResponse(via="nessie", deposit_id=deposit.id, run_id=run.id if run else None,
                               message="Deposit posted to Nessie; the poller saw it and started the run." if run else
                               f"Deposit posted to Nessie; the poller hasn't started the run after {POLLER_WAIT_S:.0f} s "
                               "(GET /runs/latest finds it).")
    run = pipeline.start_for_deposit(deposit, account=account)
    nessie.note(deposit, account.id, run)  # the poller isn't running, so the Connections page hears it from here
    return PaymentResponse(via="nessie", deposit_id=deposit.id, run_id=run.id,
                           message="Deposit posted to Nessie; the run started for it.")


# ---------------------------------------------------------------- the distributor's payment, as it edits it

def _invoice_lines(a: accounts.Account) -> list[Charge]:
    """The deductions the invoice month's payment carries as is (the run's own source, pipeline._process)."""
    month = a.invoice.month
    with accounts.using(a):
        return fee_accounts.charges(a, month) if fee_accounts.has_fees(a) else rows.charges(month, account=a)


def _is_fee(c: Charge) -> bool:
    return c.units <= 1 and c.product in (None, "", "none")


def _edited(a: accounts.Account, req: PortalPaymentRequest) -> list[Charge]:
    """The invoice's lines as the distributor set them: units and rate per line, a line left out is not taken."""
    base = {c.id: c for c in _invoice_lines(a)}
    out, seen = [], set()
    for ln in req.lines:
        c = base.get(ln.id)
        if c is None:
            raise HTTPException(422, f"{a.distributor.name}'s invoice has no line {ln.id!r}")
        if ln.id in seen:
            raise HTTPException(422, f"line {ln.id} is listed twice")
        seen.add(ln.id)
        units = 1 if _is_fee(c) else ln.units
        out.append(c.model_copy(update={"units": units, "rate": ln.rate, "amount": totals.line_amount(units, ln.rate)}))
    return out


def _paid(a: accounts.Account, lines: list[Charge]) -> Decimal:
    return totals.total_of([a.invoice.expected, -totals.total_of(c.amount for c in lines)])


def _draft(a: accounts.Account, lines: list[Charge]) -> PaymentDraft:
    base = [(c.id, c.units, c.rate) for c in _invoice_lines(a)]
    return PaymentDraft(
        account_id=a.id, distributor=a.distributor.name, brand=a.brand.name, invoice_id=a.invoice.id,
        expected=a.invoice.expected, taken=totals.total_of(c.amount for c in lines), paid=_paid(a, lines),
        edited=[(c.id, c.units, c.rate) for c in lines] != base,
        lines=[DraftLine(id=c.id, ref=c.ref, code=c.code, description=c.description, product=c.product, units=c.units,
                         rate=c.rate, amount=c.amount, fee=_is_fee(c)) for c in lines])


@router.get("/portal/payments/{account}/draft", response_model=PaymentDraft)
def portal_draft(account: str) -> PaymentDraft:
    """The payment the distributor's portal starts from: the invoice and the deductions it carries as is."""
    a = account_or_404(account)  # the portal is the distributor's side: no supplier sign-in
    return _draft(a, _invoice_lines(a))


@router.post("/portal/payments/{account}/preview", response_model=PaymentDraft)
def portal_preview(account: str, req: PortalPaymentRequest) -> PaymentDraft:
    """The same payment with the distributor's edits: each line's amount and what's left paid, computed here."""
    a = account_or_404(account)
    return _draft(a, _edited(a, req))


@router.post("/portal/payments/{account}", response_model=PendingPayment, dependencies=[Depends(limit("runs"))])
def portal_pays(account: str, req: PortalPaymentRequest | None = Body(None)) -> PendingPayment:
    """The distributor's portal: "Send payment" on its invoice. Without a body it is the invoice's received amount, as
    the bank deposit would carry; with the lines the distributor edited, exactly those lines and what they leave paid.
    The supplier sees it as received. A second press while it waits returns the same one."""
    a = account_or_404(account)  # the portal is the distributor's side: no supplier sign-in
    return _receive(a, "portal", _edited(a, req) if req is not None else None)


def _receive(a: accounts.Account, source: str, edited: list[Charge] | None = None) -> PendingPayment:
    """The account's payment, received and waiting for "Run the agents"; one already waiting is returned as is."""
    global _sent
    waiting = next((p for p in _PENDING.values() if p.account_id == a.id), None)
    if waiting is not None:
        return waiting
    _sent += 1
    p = PendingPayment(id=f"PAY-{a.id}-{_sent}", account_id=a.id, distributor=a.distributor.name,
                       invoice_id=a.invoice.id, expected=a.invoice.expected,
                       received=_paid(a, edited) if edited is not None else a.invoice.received,
                       source=source, received_at=datetime.now(timezone.utc))
    _PENDING[p.id] = p
    if edited is not None:
        _EDITED[p.id] = edited
    if autopilot.of_account(a).run_on_arrival:  # the owner's Settings: received payments start the agents at once
        started = _start(a, edited)
        _PENDING.pop(p.id, None)
        _EDITED.pop(p.id, None)
        return p.model_copy(update={"run_id": started.run_id})
    return p


@router.get("/payments/pending", response_model=list[PendingPayment])
def pending(who: Caller = Depends(current_supplier)) -> list[PendingPayment]:
    """Payments received and waiting for "Run the agents", oldest first: the caller's accounts only."""
    return [p for p in _PENDING.values() if tenancy.can_see(who, p.account_id)]


@router.post("/payments/pending/{payment_id}/run", response_model=PaymentResponse,
             dependencies=[Depends(limit("runs"))])
def run_pending(payment_id: str, who: Caller = Depends(current_supplier)) -> PaymentResponse:
    """"Run the agents" on a received payment: it starts like the payment button (a Nessie deposit when the keys are
    set, else directly) and stops waiting."""
    p = _PENDING.get(payment_id)
    if p is None:
        raise HTTPException(404, f"no payment {payment_id!r} waiting")
    started = _pays(p.account_id, who, _EDITED.get(payment_id))  # 404s an account the caller can't see
    _PENDING.pop(payment_id, None)
    _EDITED.pop(payment_id, None)
    return started
