"""Peak Bar Co.'s history before today, so Home opens on a real month of work, not zeros.

Built by replaying recorded runs (api/integrations/replay.replaying): no AI call, no text, no QuickBooks write, no
network, and the same every time. Runs at startup when Peak Bar has no runs yet, and after POST /demo/reset, on a
background thread, so /health answers at once. DEMO_STORY=off turns it off (the tests).

The month it shows:
- Five Below: last month's payment checked; its questions answered for those charges only, the fair-charge memo
  approved, the dispute sent. (KeHE and Walmart aren't fully recorded, so they wait for their payment: SETTLED.)
- UNFI: checked, dispute sent, and UNFI's desk replied agreeing to one line, so recovered is real, with its
  evidence. The Negotiator's reading of that reply must be recorded (scripts/record_missing.py --story); until it
  is, the replay holds the reply for the owner and recovered stays 0.
- Sam's Club: checked; its discretionary sampling fee is a question waiting on the admin, and so is its memo. Its
  dispute went out and Sam's desk pushed back without a document; the admin was told.
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

# Only accounts whose whole run is recorded: a replay with a missing answer would send that charge to Ask, and the
# history would show the admin "accepting" what the agents never checked. KeHE has no recordings and Walmart's stop
# where the recording budget ran out, so both wait for their payment instead (POST /payments/sync delivers them
# after Northmart's, live).
SETTLED = ("peak-bar-five-below",)
REPLIED = "peak-bar-unfi"
WAITING = "peak-bar-sams"
NEXT_PAYMENT = accounts.DEFAULT  # Northmart's March payment: the live moment
# UNFI's desk accepts one line with its portal's Accept action (read by code, no AI): recovered, with evidence.
AGREEMENT = {REPLIED: (["U5"], "Accepted: Peak Bar Peanut Butter wasn't part of the MCB deal. Deduction 60412326 will "
                              "be credited on the next remittance.")}
# Sam's Club's desk pushes back on a line without a document. The Negotiator answers it from a recording when one
# exists for this exact reply; without one the replay holds it for the admin, who is told either way.
CLAIM = {WAITING: "There was no cap on that promo. The deduction stands."}

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
        if aid == WAITING:  # its question and memo wait on the admin; its dispute went out and got pushback
            _settle(run, answer=False, approve=False)
        else:
            _settle(run)
        d = next((e.data for e in reversed(run.events) if e.type == "dispute"), None)
        if d is None:
            continue
        if aid in AGREEMENT:
            cids, text = AGREEMENT[aid]
            disputes.post(d.id, text, client=client, agree_charge_ids=cids)
        if aid in CLAIM:
            disputes.post(d.id, CLAIM[aid], client=client)
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
