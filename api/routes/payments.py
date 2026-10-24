"""The payment screen's "Northmart pays" button (F15).

With Nessie keys: post the $41,350 deposit to the Nessie sandbox. If the poller is running it starts the run
when it sees the deposit (within 5 seconds); if not, this starts it for that deposit. Without keys, or in
DEMO_MODE, the run starts directly: the button is the fallback the design names.
"""

from fastapi import APIRouter, HTTPException

from api import pipeline
from api.contracts import PaymentResponse
from api.integrations import nessie, replay

router = APIRouter(tags=["payments"])


@router.post("/payments/northmart", response_model=PaymentResponse)
def northmart_pays() -> PaymentResponse:
    client = None if replay.demo_mode() else nessie.client()
    if client is None:
        run = pipeline.start("march")
        why = "DEMO_MODE" if replay.demo_mode() else "no Nessie keys"
        return PaymentResponse(via="direct", deposit_id=None, run_id=run.id,
                               message=f"Run started directly ({why}).")
    try:
        deposit = client.post_deposit()
    except nessie.NessieError as e:
        raise HTTPException(502, f"Nessie didn't take the deposit: {e}") from None
    if nessie.poller and nessie.poller.running:
        return PaymentResponse(via="nessie", deposit_id=deposit.id, run_id=None,
                               message="Deposit posted to Nessie; the run starts when the poller sees it (within 5 s).")
    run = pipeline.start_for_deposit(deposit)
    return PaymentResponse(via="nessie", deposit_id=deposit.id, run_id=run.id,
                           message="Deposit posted to Nessie; the run started for it.")
