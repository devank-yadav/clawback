"""Postgres for the running app (rows, saved events, GET /db/cap): DATABASE_URL, a short connect timeout, one retry.

Off without DATABASE_URL, in DEMO_MODE (the demo never depends on the network) and without psycopg; callers then use
their fallback (the files, nothing saved, a 503). A connect that fails twice marks the database down for DOWN_FOR
seconds, so callers go straight to their fallback instead of waiting again, and logs one warning per outage. The
URL is never printed: error text is scrubbed of it and of its password.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import weakref
from collections.abc import Callable
from typing import Any, TypeVar

from api.integrations import replay

try:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
except ImportError:  # the app runs on the files without it
    psycopg = None

log = logging.getLogger("clawback.db")

CONNECT_TIMEOUT = 3  # seconds per attempt (libpq's minimum is 2)
RETRY_AFTER = 1.0  # seconds between the two attempts
STATEMENT_TIMEOUT = "5s"
DOWN_FOR = 30.0  # seconds the database is skipped after it couldn't be reached

T = TypeVar("T")


class Unavailable(RuntimeError):
    """No database right now: it's off, or it couldn't be reached. The message never holds the URL."""


class LogOnce:
    """One warning when something starts failing, then nothing until it works again (one line says so)."""

    _every: weakref.WeakSet[LogOnce] = weakref.WeakSet()

    def __init__(self, what: str):
        self.what, self.failing, self._lock = what, False, threading.Lock()
        LogOnce._every.add(self)

    def failed(self, reason: str) -> None:
        with self._lock:
            first, self.failing = not self.failing, True
        if first:
            log.warning("%s: %s", self.what, reason)

    def ok(self) -> None:
        with self._lock:
            was, self.failing = self.failing, False
        if was:
            log.warning("%s: working again", self.what)

    def clear(self) -> None:
        """Forget a failure without saying anything."""
        with self._lock:
            self.failing = False


def url() -> str | None:
    """DATABASE_URL when the database is on."""
    if psycopg is None or replay.demo_mode():
        return None
    return os.getenv("DATABASE_URL") or None


def enabled() -> bool:
    return url() is not None


def _password(database_url: str | None) -> str | None:
    try:
        return conninfo_to_dict(database_url).get("password") if database_url and psycopg else None
    except Exception:  # noqa: BLE001 - a URL libpq can't parse has no password to hide
        return None


def scrub(e: BaseException) -> str:
    """One line about an error, with DATABASE_URL and its password taken out."""
    text = (str(e).strip().splitlines() or [""])[0]
    database_url = os.getenv("DATABASE_URL")
    for secret, name in ((database_url, "DATABASE_URL"), (_password(database_url), "***")):
        if secret:
            text = text.replace(secret, name)
    return f"{type(e).__name__}: {text}" if text else type(e).__name__


_outage = LogOnce("Postgres")
_down_until = 0.0


def connect():
    """A new autocommit connection with a statement timeout, or Unavailable."""
    global _down_until
    database_url = url()
    if database_url is None:
        raise Unavailable("no database (DATABASE_URL isn't set, or DEMO_MODE is on)")
    if time.monotonic() < _down_until:
        raise Unavailable("the database couldn't be reached a moment ago")
    for attempt in (1, 2):
        try:
            # No server-side prepared statements, so a connection pooler in front of the database works too.
            db = psycopg.connect(database_url, autocommit=True, connect_timeout=CONNECT_TIMEOUT, prepare_threshold=None)
            break
        except psycopg.Error as e:
            if attempt == 2:
                _down_until = time.monotonic() + DOWN_FOR
                reason = scrub(e)
                _outage.failed(f"can't connect ({reason}); rows come from data/ and events wait to be saved")
                raise Unavailable(reason) from None
            time.sleep(RETRY_AFTER)
    try:
        db.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
    except BaseException:
        db.close()
        raise
    _outage.ok()
    return db


class Shared:
    """One connection for the request path (rows, replays, GET /db/cap), kept between calls; callers take turns.
    A connection that broke (the server restarted, an idle timeout) is reopened once."""

    def __init__(self):
        self._db = None
        self._lock = threading.Lock()

    def run(self, fn: Callable[[Any], T]) -> T:
        with self._lock:
            for last in (False, True):
                try:
                    if self._db is None or self._db.closed:
                        self._db = connect()
                    return fn(self._db)
                except psycopg.OperationalError:
                    self._close()
                    if last:
                        raise
        raise AssertionError("unreachable")

    def _close(self) -> None:
        db, self._db = self._db, None
        if db is not None:
            try:
                db.close()
            except Exception:  # noqa: BLE001 - it's being thrown away
                pass

    def close(self) -> None:
        with self._lock:
            self._close()


shared = Shared()


def reset() -> None:
    """Drop the shared connection and forget every outage and failure (tests; a DATABASE_URL that changed)."""
    global _down_until
    shared.close()
    _down_until = 0.0
    for problem in list(LogOnce._every):
        problem.clear()
