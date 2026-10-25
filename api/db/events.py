"""Every event a run streams, saved to the events table (docs/design.md, API: "Events are also saved to an `events`
table, so a refresh replays them"), and read back for a run that is no longer in memory: after a restart, GET
/runs/{id}/events replays it and GET /runs/latest finds it.

Run.emit calls record() for every event, with the run's account (the events table's account_id). record() only
queues it: one background thread writes the queue in batches, so a run never waits on the database and never fails
because of it. A write that fails is logged once (until
writes work again), kept, and tried again after PAUSE seconds; if the database stays away until MAX_QUEUED events
wait, newer ones aren't saved (also logged once). Nothing is saved when the database is off (api/db/conn.py).

A demo reset (POST /demo/reset) forgets the runs so far: they're no longer served from here, what their threads
still emit isn't saved, and their rows are deleted, so after the reset the table is empty, as after a fresh seed.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from api import accounts
from api.contracts import Event, EventAdapter
from api.db import conn

try:
    from psycopg.types.json import Jsonb
except ImportError:  # conn.enabled() is False without psycopg, so nothing is queued
    Jsonb = None

log = logging.getLogger("clawback.db")

MAX_QUEUED = 10_000
BATCH = 500
PAUSE = 5.0  # seconds before a failed write is tried again

INSERT = ("INSERT INTO events (run_id, id, type, at, data, account_id) VALUES (%s, %s, %s, %s, %s, %s) "
          "ON CONFLICT (run_id, id) DO NOTHING")
SELECT = "SELECT run_id, id, type, at, data FROM events WHERE run_id = %s ORDER BY id"
# An account's newest run of a kind: its "run" events carry the kind, and the first one is when it started.
LATEST = ("SELECT run_id FROM events WHERE account_id = %s AND type = 'run' AND data->>'kind' = %s "
          "GROUP BY run_id HAVING min(at) > %s ORDER BY min(at) DESC LIMIT 1")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Forget:
    """Queued by a demo reset: delete every event up to `before`, in order with the inserts queued ahead of it."""
    before: datetime


@dataclass(frozen=True)
class _Statement:
    """Queued by write_later(): one statement (a saved rule, an audit row), in order with what's queued ahead of it."""
    query: str
    params: tuple = ()


def _write(db, batch: list[Any]) -> None:
    with db.transaction(), db.cursor() as cur:
        rows = []
        for item in batch:
            if isinstance(item, (_Forget, _Statement)):
                if rows:
                    cur.executemany(INSERT, rows)
                    rows = []
                if isinstance(item, _Forget):
                    cur.execute("DELETE FROM events WHERE at <= %s", (item.before,))
                else:
                    cur.execute(item.query, item.params)
            else:
                rows.append((item.run_id, item.id, item.type, item.at, Jsonb(item.data.model_dump(mode="json")),
                             _accounts.get(item.run_id, accounts.DEFAULT)))
        if rows:
            cur.executemany(INSERT, rows)


def _close(db) -> None:
    if db is not None:
        try:
            db.close()
        except Exception:  # noqa: BLE001 - it's being thrown away
            pass


class Writer:
    """The queue and the one thread that writes it, on its own connection."""

    def __init__(self, max_queued: int = MAX_QUEUED):
        self.queue: queue.Queue = queue.Queue(maxsize=max_queued)
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None
        self.failing = conn.LogOnce("events: saving to Postgres")
        self.full = conn.LogOnce("events")
        self._lock = threading.Lock()

    def put(self, item: Any) -> None:
        """Never blocks: a full queue drops the item (logged once)."""
        if self.thread is None or not self.thread.is_alive():
            with self._lock:
                if self.thread is None or not self.thread.is_alive():
                    self.thread = threading.Thread(target=self._work, name="events-writer", daemon=True)
                    self.thread.start()
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            self.full.failed(f"{self.queue.maxsize:,} events already wait for the database; newer ones aren't saved")

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait until everything queued so far is written. False if that took longer than `timeout`."""
        deadline = time.monotonic() + timeout
        with self.queue.all_tasks_done:
            while self.queue.unfinished_tasks:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.queue.all_tasks_done.wait(left)
        return True

    def stop(self, timeout: float = 2.0) -> None:
        """End the thread; whatever is still queued isn't written."""
        self.stopping.set()
        try:
            self.queue.put_nowait(None)  # wakes the thread if it waits for work
        except queue.Full:
            pass
        if self.thread is not None:
            self.thread.join(timeout)

    def _take(self, batch: list[Any], block: bool) -> bool:
        try:
            item = self.queue.get(block=block)
        except queue.Empty:
            return False
        if item is None:
            self.queue.task_done()
        else:
            batch.append(item)
        return True

    def _work(self) -> None:
        db, batch = None, []
        while not self.stopping.is_set():
            if not batch:
                self._take(batch, block=True)
            while len(batch) < BATCH and self._take(batch, block=False):
                pass
            if not batch:
                continue
            try:
                if db is None or db.closed:
                    db = conn.connect()
                _write(db, batch)
            except Exception as e:  # noqa: BLE001 - keep the batch and try again; the run never hears of it
                # A database that's down is conn.connect()'s one warning; a connection that broke just reconnects.
                if not isinstance(e, conn.Unavailable) and not getattr(db, "broken", False):
                    self.failing.failed(f"{conn.scrub(e)}; trying again every {PAUSE:g} s")
                _close(db)
                db = None
                self.stopping.wait(PAUSE)
                continue
            self.failing.ok()
            self.full.clear()  # once writes go through, a full queue is news again
            for _ in batch:
                self.queue.task_done()
            batch = []
        _close(db)


_writer = Writer()
_reading = conn.LogOnce("events: reading from Postgres")
_runs_lock = threading.Lock()
_seen: set[str] = set()  # runs this process has saved events for
_accounts: dict[str, str] = {}  # run id -> its account
_forgotten: set[str] = set()  # runs from before a demo reset
_reset_at: datetime | None = None


def record(ev: Any, account_id: str = accounts.DEFAULT) -> None:
    """Queue one emitted event of an account's run for the events table. Never blocks and never raises."""
    try:
        if not conn.enabled() or ev.run_id in _forgotten:
            return
        with _runs_lock:
            _seen.add(ev.run_id)
            _accounts[ev.run_id] = account_id
        _writer.put(ev)
    except Exception as e:  # noqa: BLE001 - saving must never break a run
        _writer.failing.failed(f"couldn't queue an event ({type(e).__name__}: {e})")


def write_later(query: str, params: tuple = ()) -> None:
    """Queue one more statement for the writer thread (api/db/state.py saves rules and audit rows this way): written
    in order with the events, never blocking the caller, tried again while the database is away."""
    try:
        if conn.enabled():
            _writer.put(_Statement(query, params))
    except Exception as e:  # noqa: BLE001 - saving must never break a run
        _writer.failing.failed(f"couldn't queue a statement ({type(e).__name__}: {e})")


def flush(timeout: float = 5.0) -> bool:
    return _writer.flush(timeout)


def reset() -> None:
    """A demo reset: forget every run so far (see the module docstring)."""
    global _reset_at
    with _runs_lock:
        _forgotten.update(_seen)
        _seen.clear()
        _reset_at = datetime.now().astimezone()
    if conn.enabled():
        _writer.put(_Forget(_reset_at))


def _event(row: tuple) -> Event:
    run_id, id_, type_, at, data = row
    # Postgres gives the instant back in its own time zone; the run streamed it in this machine's, so show it that way.
    return EventAdapter.validate_python({"id": id_, "run_id": run_id, "at": at.astimezone(), "type": type_, "data": data})


def _read(fn) -> Any:
    """fn(db) on the shared connection, or None when there's no database or the read failed (logged once)."""
    if not conn.enabled():
        return None
    try:
        got = conn.shared.run(fn)
    except conn.Unavailable:
        return None
    except Exception as e:  # noqa: BLE001 - a replay that can't be read is a run that isn't there
        _reading.failed(conn.scrub(e))
        return None
    _reading.ok()
    return got


def load(run_id: str) -> list[Event] | None:
    """A saved run's events in order, or None: no database, the read failed, or there's no such run (or it started
    before a demo reset)."""
    rows = _read(lambda db: db.execute(SELECT, (run_id,)).fetchall())
    if not rows or (_reset_at is not None and rows[0][3] <= _reset_at):
        return None
    try:
        return [_event(r) for r in rows]
    except Exception as e:  # noqa: BLE001 - saved by an older version of the contracts
        _reading.failed(f"run {run_id} doesn't fit api/contracts.py any more ({conn.scrub(e)})")
        return None


def account_of(run_id: str) -> str | None:
    """The account a run belongs to: one recorded by this process, else the events table's (None: unknown)."""
    if run_id in _accounts:
        return _accounts[run_id]
    row = _read(lambda db: db.execute("SELECT account_id FROM events WHERE run_id = %s LIMIT 1", (run_id,)).fetchone())
    return row[0] if row else None


def latest_run(kind: str, account_id: str = accounts.DEFAULT) -> str | None:
    """An account's newest saved run of a kind that started after the last demo reset, if there is one."""
    row = _read(lambda db: db.execute(LATEST, (account_id, kind, _reset_at or EPOCH)).fetchone())
    return row[0] if row else None
