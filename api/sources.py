"""What each place a payment can arrive from has seen on this server, for the Connections page (api/library.py).

Three sources start a run with no clicks: the bank (Nessie deposits, api/integrations/nessie.py), QuickBooks
(payments recorded against an account's invoice, api/integrations/qbo_source.py) and the remittance inbox (emails,
api/inbound_email.py). Each one notes here when it last looked (a poll) or heard (a webhook), its last error while it
lasts, and what it found: the deposit, payment or email, the account it belongs to and the run it started or matched.
Memory only: a restart starts the list again (the runs themselves are saved with their events).
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime

KEEP = 50  # items kept per source, newest last
SOURCES = ("bank", "quickbooks", "inbox")


@dataclass(frozen=True)
class Seen:
    at: datetime
    text: str  # what it found, in words: "Deposit dep-1 of $41,350 (“Northmart remittance INV-3102”)"
    account: str | None  # the account it belongs to; None when it belongs to none (history, interest, junk)
    run_id: str | None  # the run it started, or the run of the same payment it matched


@dataclass
class State:
    checked_at: datetime | None = None
    error: str | None = None  # the last look's failure; cleared by the next look that works
    seen: deque[Seen] = field(default_factory=lambda: deque(maxlen=KEEP))


_lock = threading.Lock()
_states: dict[str, State] = {s: State() for s in SOURCES}


def _now() -> datetime:
    return datetime.now().astimezone()


def checked(source: str, error: str | None = None) -> None:
    """The source looked (or a webhook reached it): when, and whether it worked."""
    with _lock:
        s = _states[source]
        s.checked_at, s.error = _now(), error


def saw(source: str, text: str, account: str | None = None, run_id: str | None = None) -> Seen:
    item = Seen(_now(), text, account, run_id)
    with _lock:
        _states[source].seen.append(item)
    return item


def state(source: str) -> State:
    """A copy of what the source has noted."""
    with _lock:
        s = _states[source]
        return replace(s, seen=deque(s.seen, maxlen=KEEP))


def last(source: str, account: str | None = None) -> Seen | None:
    """The newest thing the source found for this account (any account's when none is given)."""
    with _lock:
        items = list(_states[source].seen)
    return next((i for i in reversed(items) if account is None or i.account == account), None)


def reset() -> None:
    with _lock:
        for s in SOURCES:
            _states[s] = State()
