"""The payment screen's "Northmart pays" button (F15), for any account: POST /payments/{account}.
POST /payments/northmart is Peak Bar's (the screens and the demo script call it by that name).

With Nessie keys: post the account's deposit (its invoice's received amount, described as its nessie_description:
Peak Bar's $41,350 "Northmart remittance INV-3102") to the Nessie sandbox. If the poller is running it starts the run
when it sees the deposit (within 5 seconds) and this waits up to 10 s to return that run; if not, this starts it
for that deposit. Without keys, or in DEMO_MODE, the run starts directly: the button is the fallback the design names.
"""

import time

from fastapi import APIRouter, Depends, HTTPException

from api import accounts, pipeline
from api.auth import limit
from api.contracts import PaymentResponse
from api.integrations import nessie, replay
from api.routes.runs import account_or_404

router = APIRouter(tags=["payments"])

POLLER_WAIT_S = 10.0  # the design's bar: a deposit starts the run within 10 seconds


def _poller_run(deposit_id: str) -> pipeline.Run | None:
    """Wait for the poller to see this deposit, so the button gets the run it started (not the previous one)."""
    end = time.monotonic() + POLLER_WAIT_S
    while (run := pipeline.run_for_deposit(deposit_id)) is None and time.monotonic() < end:
        time.sleep(0.1)
    return run


@router.post("/payments/northmart", response_model=PaymentResponse, dependencies=[Depends(limit("runs"))])
def northmart_pays() -> PaymentResponse:
    return _pays(accounts.DEFAULT)


@router.post("/payments/{account}", response_model=PaymentResponse, dependencies=[Depends(limit("runs"))])
def account_pays(account: str) -> PaymentResponse:
    return _pays(account)


def _pays(account_id: str) -> PaymentResponse:
    account = account_or_404(account_id)
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
