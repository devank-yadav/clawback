"""Peak Bar Co.'s history before today, so Home opens on a real month of work, not zeros.

Built by replaying recorded runs (api/integrations/replay.replaying): no AI call, no text, no QuickBooks write, no
network, and the same every time. Runs at startup when Peak Bar has no runs yet, and after POST /demo/reset, on a
background thread, so /health answers at once. DEMO_STORY=off turns it off (the tests).

The month it shows:
- KeHE, Walmart and Five Below: last month's payments checked; their questions answered for those charges only,
  the fair-charge memos approved, the disputes sent.
- UNFI: checked, dispute sent, and UNFI's desk replied agreeing to one line (a recorded reply), so recovered is
  real, with its evidence.
- Sam's Club: checked; its discretionary sampling fee is a question waiting on the admin, and its dispute and memo
  wait too.
- Northmart: not run. Its March payment is the next one to arrive (POST /payments/sync delivers it).

Each step uses the product's own paths (pipeline.start, pipeline.answer, pipeline.decide_approval,
dispute_email.send_dispute, disputes.post), so everything it leaves behind is what those leave behind.
scripts/record_missing.py --story runs the same steps live to record whatever a replay is missing.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from api import accounts, pipeline
from api.integrations import replay

log = logging.getLogger("clawback.story")

SETTLED = ("peak-bar-kehe", "peak-bar-walmart", "peak-bar-five-below")
REPLIED = "peak-bar-unfi"
WAITING = "peak-bar-sams"
NEXT_PAYMENT = accounts.DEFAULT  # Northmart's March payment: the live moment
AGREEMENT = {  # the desk's reply, as recorded (the Negotiator's answer to it is in data/fixtures/)
    REPLIED: ("Agreed, Peak Bar Peanut Butter wasn't part of the MCB deal. We'll credit deduction 60412326 back on the "
              "next remittance."),
}

_lock = threading.Lock()
status = {"state": "not_built", "seconds": None, "detail": None}


def enabled() -> bool:
    return os.getenv("DEMO_STORY", "on").strip().lower() not in ("off", "0", "false", "no")


def _known(aid: str) -> accounts.Account | None:
    try:
        return accounts.get(aid)
    except accounts.UnknownAccount:
        return None


class _NoEmailWriter:
    """The story's dispute emails are the code template: no email-writer call, live or recorded."""

    def __init__(self):
        raise RuntimeError("the history's emails are written by the template")


def _settle(run: pipeline.Run, answer: bool = True, approve: bool = True, send: bool = True) -> None:
    from api import dispute_email

    if answer:
        for qid, q in list(run.questions.items()):
            if pipeline.is_open(q):
                pipeline.answer(qid, "accept", "owner", save_rule=False)
    if approve:
        for e in list(run.events):
            if e.type == "approval" and e.data.status == "pending":
                try:
                    pipeline.decide_approval(e.data.id, True)
                except ValueError:
                    pass
    if send:
        for dispute_id in dict.fromkeys(e.data.id for e in run.events if e.type == "dispute"):
            d = dispute_email.latest(run, dispute_id)
            if d and d.status in ("ready_to_send", "draft"):
                try:
                    dispute_email.send_dispute(run, d, "owner", client=_NoEmailWriter)
                except dispute_email.NotReady as err:
                    log.warning("story: %s not sent (%s)", dispute_id, err)


def steps(client=None) -> list[str]:
    """The history, in order. Returns the run ids it made."""
    from api import disputes

    made = []
    for aid in (*SETTLED, REPLIED, WAITING):
        a = _known(aid)
        if a is None:
            continue
        run = pipeline.start(a.invoice.month, client, background=False, account=a)
        made.append(run.id)
        if aid == WAITING:
            continue  # its question, dispute and memo wait on the admin
        _settle(run)
        if aid in AGREEMENT:
            d = next((e.data for e in reversed(run.events) if e.type == "dispute"), None)
            if d is not None:
                with accounts.using(a):
                    disputes.post(d.id, AGREEMENT[aid], client=client)
    return made


def built() -> bool:
    ids = {aid for aid in (*SETTLED, REPLIED, WAITING)}
    return any(r.account.id in ids for r in pipeline.RUNS.values())


def build() -> dict:
    """Replay the history if it isn't there. Idempotent: a second call while it's there does nothing."""
    if not enabled():
        return {"state": "off"}
    with _lock:
        if built():
            status.update(state="built")
            return dict(status)
        started = time.monotonic()
        status.update(state="building")
        try:
            with replay.replaying():
                made = steps()
            status.update(state="built", seconds=round(time.monotonic() - started, 2), detail=f"{len(made)} runs")
        except Exception as e:  # noqa: BLE001 - the app works without its history; say why in the log
            log.exception("story: the history couldn't be built")
            status.update(state="failed", detail=f"{type(e).__name__}: {e}"[:300])
        return dict(status)


def build_later() -> threading.Thread | None:
    """At startup or after a reset: build on a background thread so nothing waits on it."""
    if not enabled():
        return None
    t = threading.Thread(target=build, name="story", daemon=True)
    t.start()
    return t
