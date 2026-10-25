"""Every outside call goes through here (F11): timeout, one retry, and the DEMO_MODE fixture fallback.

docs/design.md, "DEMO_MODE":
- RECORD_FIXTURES=1 saves every response to data/fixtures/<service>/<key>.json, keyed by a hash of the request.
- DEMO_MODE=true serves the saved response instead of calling out, after a short delay so cards still stream.
- live_first=True (scenario box, judge's portal replies) tries live even in DEMO_MODE, then falls back.

The request passed in is the logical request (model, prompt, schema, entity), never headers or credentials:
it is hashed into the key and saved next to the response. Recording refuses to write any secret from the
environment it finds in either.

    result = call_outside("claude", {"model": m, "system": s, "messages": msgs}, lambda req, timeout: ...)
    result.response   # the JSON the service returned (live or saved)
    result.source     # "live" or "fixture"

Inside a run (api/trace.run_context) each call is also recorded for GET /runs/{id}/trace: what was sent, what came
back, live or recorded or failed. Recording never raises and never changes what the call returns.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, Mapping

from api import trace

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"
TIMEOUT_S = 30.0  # api/CLAUDE.md: every outside call
LIVE_FIRST_TIMEOUT_S = 20.0  # scenario box and portal replies
RETRIES = 1
DEMO_DELAY_S = 0.4
# Env names whose values must never land in a fixture file.
_SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_SID", "_PASSWORD")


class OutsideCallFailed(RuntimeError):
    """Live failed after the retry and no fixture exists (or DEMO_MODE found no fixture)."""


class SecretInFixture(ValueError):
    """Recording would have written a secret from the environment to disk."""


@dataclass
class CallResult:
    service: str
    key: str
    response: Any
    source: str  # live · fixture
    attempts: int = 0
    latency_ms: int = 0
    errors: list[str] = field(default_factory=list)
    usage: dict | None = None  # what a live call used (tokens), when its fn returned a Metered answer
    model: str | None = None  # the model that answered, when the service says


@dataclass(frozen=True)
class Metered:
    """What fn may return instead of the bare response: the response plus what the call used (tokens, the model that
    answered), for the run's trace. call_outside unwraps it, so the response it returns and records is the same."""

    response: Any
    usage: dict | None = None
    model: str | None = None


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


_forced: ContextVar[bool] = ContextVar("clawback_forced_replay", default=False)


def demo_mode() -> bool:
    return _flag("DEMO_MODE") or _forced.get()


def forced() -> bool:
    """Inside replaying(): the recordings answer every call, whatever the server's mode."""
    return _forced.get()


@contextmanager
def replaying() -> Iterator[None]:
    """Replay only, on this thread (and the pools that copy its context): every AI and outside call is answered from
    data/fixtures/ at once, nothing calls out, no text or QuickBooks write leaves. The startup history (api/story.py)
    is built this way, so it costs nothing and never depends on the network."""
    token = _forced.set(True)
    try:
        yield
    finally:
        _forced.reset(token)


def record_missing() -> bool:
    """RECORD_MISSING=1 with RECORD_FIXTURES=1: a call that already has a recording replays it; only the missing ones
    go live and get saved (scripts/record_missing.py). Never overwrites a recording."""
    return _flag("RECORD_MISSING")


def recording() -> bool:
    return _flag("RECORD_FIXTURES")


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "model_dump"):  # Pydantic models from api/contracts.py
        return value.model_dump(mode="json")
    raise TypeError(f"not JSON-serializable: {type(value).__name__}")


def canonical(request: Any) -> str:
    return json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default)


def request_key(service: str, request: Any) -> str:
    """Same service + same request (any key order) -> same 16-hex key."""
    return hashlib.sha256(f"{service}\n{canonical(request)}".encode()).hexdigest()[:16]


def fixture_path(service: str, key: str, fixtures_dir: Path | None = None) -> Path:
    return (fixtures_dir or FIXTURES) / service / f"{key}.json"


def load_fixture(service: str, key: str, fixtures_dir: Path | None = None) -> Any | None:
    p = fixture_path(service, key, fixtures_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text())["response"]


def _secrets(env: Mapping[str, str]) -> list[str]:
    return [v for k, v in env.items() if k.upper().endswith(_SECRET_SUFFIXES) and len(v) >= 8]


def _equivalent_fixture(service: str, request: Any, equivalent: Callable[[Any], Any],
                        fixtures_dir: Path | None = None) -> Any | None:
    try:
        want = canonical(equivalent(request))
    except Exception:  # noqa: BLE001 - a request the normalizer can't read has no equivalent
        return None
    for p in sorted((fixtures_dir or FIXTURES).joinpath(service).glob("*.json")):
        try:
            saved = json.loads(p.read_text())
            if canonical(equivalent(saved["request"])) == want:
                return saved["response"]
        except Exception:  # noqa: BLE001 - not this one
            continue
    return None


def save_fixture(service: str, key: str, request: Any, response: Any, fixtures_dir: Path | None = None,
                 env: Mapping[str, str] | None = None) -> Path:
    body = json.dumps({"service": service, "request_hash": key, "request": request, "response": response,
                       "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                      indent=2, sort_keys=True, ensure_ascii=False, default=_default)
    leaked = [s for s in _secrets(os.environ if env is None else env) if s in body]
    if leaked:
        raise SecretInFixture(f"refusing to record {service}/{key}: it contains a value from a secret env var")
    p = fixture_path(service, key, fixtures_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(body + "\n")
    tmp.replace(p)  # atomic: a crash mid-write never leaves half a fixture
    return p


@contextmanager
def _traced(service: str, request: Any, result: CallResult, demo: bool) -> Iterator[None]:
    """Record the call in the run's trace (api/trace.py) once it returns or raises. Every return path hands back
    `result` itself, so its fields are the outcome. Outside a run context this does nothing."""
    if not trace.current_run():
        yield
        return
    at, started = datetime.now().astimezone(), time.monotonic()
    try:
        yield
    except Exception as e:
        _trace_call(service, request, result, at, started, e, demo)
        raise
    _trace_call(service, request, result, at, started, None, demo)


def _trace_call(service: str, request: Any, result: CallResult, at: datetime, started: float,
                failed: Exception | None, demo: bool) -> None:
    try:
        if failed is None:
            trace.record(service, request, result.response, status="live" if result.source == "live" else "recorded",
                         at=at, latency_ms=result.latency_ms, attempts=result.attempts,
                         error="; ".join(result.errors) or None, usage=result.usage, model=result.model)
            return
        if isinstance(failed, OutsideCallFailed):
            why = "DEMO_MODE is on" if demo and not result.attempts else "; ".join(result.errors)
            error = f"{why}; no recorded answer to fall back on"
        else:
            error = "; ".join([*result.errors, f"{type(failed).__name__}: {failed}"])
        trace.record(service, request, None, status="failed", at=at, attempts=result.attempts, error=error,
                     latency_ms=int((time.monotonic() - started) * 1000))
    except Exception:  # noqa: BLE001 - the trace never changes how a call ends
        pass


_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="outside-call")


def _live_once(fn: Callable[[Any, float], Any], request: Any, timeout: float) -> Any:
    """fn gets the timeout too (pass it to the SDK); the future enforces it if the SDK doesn't."""
    future = _pool.submit(fn, request, timeout)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout:
        future.cancel()
        raise TimeoutError(f"no answer in {timeout:g}s") from None


def call_outside(
    service: str,
    request: Any,
    fn: Callable[[Any, float], Any],
    *,
    timeout: float | None = None,
    retries: int = RETRIES,
    live_first: bool = False,
    fixtures_dir: Path | None = None,
    demo: bool | None = None,
    record: bool | None = None,
    delay: float = DEMO_DELAY_S,
    equivalent: Callable[[Any], Any] | None = None,
) -> CallResult:
    """Run fn(request, timeout) with the project's outside-call rules. See the module docstring.
    `equivalent`: when no recording matches the request exactly, one whose request is the same once both pass through
    it is replayed instead (the Negotiator's replies: the same reply and evidence, before or after a rule was saved)."""
    demo = demo_mode() if demo is None else demo
    record = recording() if record is None else record
    timeout = timeout if timeout is not None else (LIVE_FIRST_TIMEOUT_S if live_first else TIMEOUT_S)
    key = request_key(service, request)
    started = time.monotonic()
    result = CallResult(service, key, None, "fixture")

    def from_fixture(why: str) -> CallResult:
        saved = load_fixture(service, key, fixtures_dir)
        if saved is None and equivalent is not None:
            saved = _equivalent_fixture(service, request, equivalent, fixtures_dir)
        if saved is None:
            raise OutsideCallFailed(f"{service}/{key}: {why}; no fixture at {fixture_path(service, key, fixtures_dir)}")
        if demo and delay and not _forced.get():
            time.sleep(delay)
        result.response, result.source = saved, "fixture"
        result.latency_ms = int((time.monotonic() - started) * 1000)
        return result

    with _traced(service, request, result, demo):  # GET /runs/{id}/trace
        if demo and (not live_first or _forced.get()):
            return from_fixture("DEMO_MODE is on")
        if record and record_missing() and load_fixture(service, key, fixtures_dir) is not None:
            return from_fixture("recorded already")

        for _ in range(1 + max(0, retries)):
            result.attempts += 1
            try:
                response = _live_once(fn, request, timeout)
            except Exception as e:  # noqa: BLE001 - any failure counts; the next step is retry, then fixture
                result.errors.append(f"{type(e).__name__}: {e}")
                continue
            if isinstance(response, Metered):
                response, result.usage, result.model = response.response, response.usage, response.model
            if record:
                save_fixture(service, key, request, response, fixtures_dir)
            result.response, result.source = response, "live"
            result.latency_ms = int((time.monotonic() - started) * 1000)
            return result
        return from_fixture(f"live failed {result.attempts}x ({result.errors[-1]})")


async def acall_outside(
    service: str,
    request: Any,
    fn: Callable[[Any, float], Awaitable[Any]],
    *,
    timeout: float | None = None,
    retries: int = RETRIES,
    live_first: bool = False,
    fixtures_dir: Path | None = None,
    demo: bool | None = None,
    record: bool | None = None,
    delay: float = DEMO_DELAY_S,
) -> CallResult:
    """call_outside for async SDK clients (AsyncAnthropic, httpx.AsyncClient). Same rules."""
    demo = demo_mode() if demo is None else demo
    record = recording() if record is None else record
    timeout = timeout if timeout is not None else (LIVE_FIRST_TIMEOUT_S if live_first else TIMEOUT_S)
    key = request_key(service, request)
    started = time.monotonic()
    result = CallResult(service, key, None, "fixture")

    async def from_fixture(why: str) -> CallResult:
        saved = load_fixture(service, key, fixtures_dir)
        if saved is None:
            raise OutsideCallFailed(f"{service}/{key}: {why}; no fixture at {fixture_path(service, key, fixtures_dir)}")
        if demo and delay:
            await asyncio.sleep(delay)
        result.response, result.source = saved, "fixture"
        result.latency_ms = int((time.monotonic() - started) * 1000)
        return result

    with _traced(service, request, result, demo):
        if demo and not live_first:
            return await from_fixture("DEMO_MODE is on")

        for _ in range(1 + max(0, retries)):
            result.attempts += 1
            try:
                response = await asyncio.wait_for(fn(request, timeout), timeout)
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"{type(e).__name__}: {e or 'timed out'}")
                continue
            if isinstance(response, Metered):
                response, result.usage, result.model = response.response, response.usage, response.model
            if record:
                save_fixture(service, key, request, response, fixtures_dir)
            result.response, result.source = response, "live"
            result.latency_ms = int((time.monotonic() - started) * 1000)
            return result
        return await from_fixture(f"live failed {result.attempts}x ({result.errors[-1]})")
