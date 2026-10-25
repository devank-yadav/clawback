"""The payment screen's "Northmart pays" button (F15), for any account: POST /payments/{account}.
POST /payments/northmart is Peak Bar's (the screens and the demo script call it by that name).

With Nessie keys: post the account's deposit (its invoice's received amount, described as its nessie_description:
Peak Bar's $41,350 "Northmart remittance INV-3102") to the Nessie sandbox. If the poller is running it starts the run
when it sees the deposit (within 5 seconds) and this waits up to 10 s to return that run; if not, this starts it
for that deposit. Without keys, or in DEMO_MODE, the run starts directly: the button is the fallback the design names.
"""

import time

from fastapi import APIRouter, Depends, HTTPException

from api import accounts, pipeline, tenancy
from api.auth import limit
from api.contracts import FoundPayment, PaymentResponse, PaymentSync
from api.integrations import nessie, replay
from api.routes.runs import account_or_404
from api.tenancy import Caller, current_supplier

router = APIRouter(tags=["payments"])

POLLER_WAIT_S = 10.0  # the design's bar: a deposit starts the run within 10 seconds


def _poller_run(deposit_id: str) -> pipeline.Run | None:
    """Wait for the poller to see this deposit, so the button gets the run it started (not the previous one)."""
    end = time.monotonic() + POLLER_WAIT_S
    while (run := pipeline.run_for_deposit(deposit_id)) is None and time.monotonic() < end:
        time.sleep(0.1)
    return run


@router.post("/payments/sync", response_model=PaymentSync, dependencies=[Depends(limit("runs"))])
def sync_payments(who: Caller = Depends(current_supplier)) -> PaymentSync:
    """"Check for new payments": one look at the bank (Nessie) and QuickBooks, as their pollers do every few
    seconds. A payment found starts its account's run. When they have nothing new for this supplier, the next
    payment due arrives the way a bank deposit does (its invoice's received amount on the account's own path), so
    the button always shows the agents at work on the newest payment."""
    from api import story
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
        due = _next_due(who, story.NEXT_PAYMENT)
        if due is not None:
            paid = _pays(due.id, who)
            found.append(FoundPayment(source="bank", account_id=due.id, distributor=due.distributor.name,
                                      amount=due.invoice.received, invoice_id=due.invoice.id, run_id=paid.run_id))
    if not found:
        return PaymentSync(checked=checked, found=[], message="No new payments.")
    names = ", ".join(f"{f.distributor} paid ${f.amount:,.2f} on {f.invoice_id}" if f.amount is not None
                      else f"{f.distributor} paid {f.invoice_id}" for f in found)
    return PaymentSync(checked=checked, found=found, message=f"{names}. The agents are checking it.")


def _next_due(who: Caller, first: str) -> accounts.Account | None:
    """The caller's next tracked distributor whose invoice-month payment hasn't been checked yet (Northmart first)."""
    from api import suppliers

    supplier = who.supplier_id or suppliers.supplier_of(accounts.get(first))  # scripts and laptops: Peak Bar's
    mine = [a for a in accounts.every() if suppliers.supplier_of(a) == supplier and tenancy.can_see(who, a)
            and a.id not in suppliers._off(supplier)]
    mine.sort(key=lambda a: (a.id != first, a.id))
    return next((a for a in mine if pipeline.latest(a.invoice.month, a) is None), None)


@router.post("/payments/northmart", response_model=PaymentResponse, dependencies=[Depends(limit("runs"))])
def northmart_pays(who: Caller = Depends(current_supplier)) -> PaymentResponse:
    return _pays(accounts.DEFAULT, who)


@router.post("/payments/{account}", response_model=PaymentResponse, dependencies=[Depends(limit("runs"))])
def account_pays(account: str, who: Caller = Depends(current_supplier)) -> PaymentResponse:
    return _pays(account, who)


def _pays(account_id: str, who: Caller) -> PaymentResponse:
    account = account_or_404(account_id, who)
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

