"""What the AI did on a run: every outside call it made, in order, with what was sent and what came back.

api/integrations/replay.call_outside records each call it makes against the run (and charge) entered here, and
GET /runs/{run_id}/trace serves them (api/routes/trace.py). A call made outside a run context isn't recorded.
The store is in memory: the newest MAX_RUNS runs, the first MAX_PER_RUN calls of each, gone after a restart.

One entry per call_outside (so a validation retry, or a Gemini model that didn't answer, is its own entry):
    seq         1, 2, 3 ... in the order the calls finished (the two readers of a document run side by side)
    at          when the call started
    agent       "Deal reader (Claude)", "Investigator", "Negotiator: comeback", "QuickBooks", ...
    service     the call_outside service name (claude-reader, gemini-reader, moss, qbo, ...)
    run_id, charge_id
    model       the model asked (None for Moss and QuickBooks)
    prompt      the prompt file and the first line of the system prompt; Moss and QuickBooks name the operation
    input       the request exactly as sent: system prompt + user content, or the payload
    output      the parsed answer (live or recorded); None when the call failed
    latency_ms, status (live · recorded · failed), attempts, error
Secrets never land here: a value of any secret env var (replay's own scan), a field named like a key or token,
and anything shaped like an API key or a bearer token are replaced by "[redacted]".

Where the pipeline enters the contexts (Devank wires these; until then nothing is recorded):
- run_context(run.id) around the work of each entry point that runs agents for a run:
    api/pipeline._guarded         (the run's own thread: readers, Investigator, comebacks, Moss, QuickBooks)
    api/pipeline.answer           (the owner's reply: rule writer, Moss, then the charges decided again)
    api/pipeline.decide_approval  (the controller's yes: the QuickBooks writes)
    api/disputes.post             (the portal: Negotiator's reply, or the readers on an attached document)
    api/scenario.run              (the scenario box)
- charge_context(c.id) around each turn of the per-charge loop in api/pipeline._process.
- api/agents/readers.read_both runs the two readers on a thread pool, and a new thread starts with no context:
  build that pool with ContextPool (below) instead of ThreadPoolExecutor, or the readers' calls aren't recorded.
A charge_id the request itself carries (the Investigator's and the comeback's do) is used when no charge
context is set.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import threading
from collections import OrderedDict
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

log = logging.getLogger("clawback.trace")

MAX_RUNS = 100  # the oldest run's trace goes first
MAX_PER_RUN = 500  # a March run makes about 20 calls; past this, a run's later calls are counted, not kept
MAX_TEXT = 50_000  # characters kept of any one string (a pasted portal reply could be anything)
PROMPTS = Path(__file__).resolve().parent / "agents" / "prompts"
REDACTED = "[redacted]"

AGENTS = {
    "claude-reader": "Deal reader (Claude)",
    "gemini-reader": "Deal reader (Gemini)",
    "claude-reader-b": "Deal reader (second Claude read)",
    "claude-investigator": "Investigator",
    "claude-rehearsal": "Negotiator: comeback",
    "claude-portal-reply": "Negotiator: portal reply",
    "claude-coach": "Deal Coach",
    "claude-rule-writer": "Rule writer",
    "moss": "Rule memory (Moss)",
    "qbo": "QuickBooks",
}

_run: contextvars.ContextVar[str | None] = contextvars.ContextVar("clawback_trace_run", default=None)
_charge: contextvars.ContextVar[str | None] = contextvars.ContextVar("clawback_trace_charge", default=None)


class TraceEntry(BaseModel):
    seq: int
    at: datetime
    agent: str
    service: str
    run_id: str
    charge_id: str | None = None
    model: str | None = None
    prompt: str | None = None
    input: Any = None
    output: Any = None
    latency_ms: int = 0
    status: Literal["live", "recorded", "failed"]
    attempts: int = 0
    error: str | None = None


class _Trace:
    def __init__(self) -> None:
        self.entries: list[TraceEntry] = []
        self.dropped = 0


_store: OrderedDict[str, _Trace] = OrderedDict()
_lock = threading.Lock()


# ---------------------------------------------------------------- contexts

@contextmanager
def run_context(run_id: str) -> Iterator[None]:
    """Outside calls made inside this block (in this thread, or a ContextPool it starts) belong to run_id."""
    token = _run.set(run_id)
    try:
        yield
    finally:
        _run.reset(token)


@contextmanager
def charge_context(charge_id: str) -> Iterator[None]:
    """Inside a run_context: the calls in this block are about charge_id."""
    token = _charge.set(charge_id)
    try:
        yield
    finally:
        _charge.reset(token)


def current_run() -> str | None:
    return _run.get()


def current_charge() -> str | None:
    return _charge.get()


class ContextPool(ThreadPoolExecutor):
    """A ThreadPoolExecutor whose tasks run in the submitting thread's context (a copy per task), so the calls
    they make still land in the run's trace. A drop-in for ThreadPoolExecutor."""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)


# ---------------------------------------------------------------- recording

def reset() -> None:
    with _lock:
        _store.clear()


def known(run_id: str) -> bool:
    with _lock:
        return run_id in _store


def trace_for(run_id: str, charge_id: str | None = None) -> list[TraceEntry]:
    """The run's calls in order (empty for a run that made none, or one this process never saw)."""
    with _lock:
        t = _store.get(run_id)
        entries = list(t.entries) if t else []
    return [e for e in entries if charge_id is None or e.charge_id == charge_id]


def record(service: str, request: Any, response: Any = None, *, status: str, at: datetime, latency_ms: int = 0,
           attempts: int = 0, error: str | None = None, run_id: str | None = None,
           charge_id: str | None = None) -> TraceEntry | None:
    """One call, against run_id (default: the current run context). Returns the entry, or None when there's no
    run, the run is full, or anything about recording failed: recording never raises."""
    try:
        run_id = run_id or _run.get()
        if not run_id:
            return None
        charge_id = charge_id or _charge.get() or _request_field(request, "charge_id")
        secrets = _secret_values()
        entry = dict(at=at, agent=AGENTS.get(service, service), service=service, run_id=run_id,
                     charge_id=charge_id, model=_request_field(request, "model"),
                     prompt=_prompt(service, request), input=_clean(request, secrets),
                     output=_clean(response, secrets), latency_ms=int(latency_ms), status=status,
                     attempts=int(attempts), error=_clean(error, secrets))
        with _lock:
            t = _store.get(run_id)
            if t is None:
                t = _store[run_id] = _Trace()
                while len(_store) > MAX_RUNS:
                    _store.popitem(last=False)
            if len(t.entries) >= MAX_PER_RUN:
                t.dropped += 1
                if t.dropped == 1:
                    log.warning("trace for %s is full (%d calls); later calls aren't kept", run_id, MAX_PER_RUN)
                return None
            e = TraceEntry(seq=len(t.entries) + 1, **entry)
            t.entries.append(e)
        return e
    except Exception:  # noqa: BLE001 - the trace is a window on the run, never a reason for it to fail
        log.debug("trace: couldn't record a %s call", service, exc_info=True)
        return None


def _request_field(request: Any, name: str) -> str | None:
    value = request.get(name) if isinstance(request, Mapping) else None
    return value if isinstance(value, str) and value else None


_prompt_files: dict[str, str] | None = None


def _prompt_file(system: str) -> str | None:
    """Which api/agents/prompts/ file this system prompt is (the agents send the files verbatim)."""
    global _prompt_files
    if _prompt_files is None:
        _prompt_files = {p.read_text().strip(): f"api/agents/prompts/{p.name}" for p in sorted(PROMPTS.glob("*.md"))}
    return _prompt_files.get(system.strip())


def _prompt(service: str, request: Any) -> str | None:
    if not isinstance(request, Mapping):
        return None
    system = request.get("system")
    if isinstance(system, str) and system.strip():
        first = next(line.strip() for line in system.splitlines() if line.strip())
        return f"{_prompt_file(system) or service}: {first}"
    if service == "moss" and request.get("op"):
        return f"Moss {request['op']}"
    if service == "qbo" and request.get("method"):
        return f"QuickBooks {request['method']} {request.get('path', '')}".strip()
    return None


# ---------------------------------------------------------------- secrets and size

# Field names that hold credentials (the requests never carry them; this is the second line of defence).
_SECRET_FIELD = re.compile(r"(^|_)(key|token|secret|sid|password)$|^(authorization|api_?key|access_?token)$", re.I)
# Shapes of credentials in free text: Anthropic and Google API keys, and a bearer token.
_SECRET_TEXT = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|(?<=Bearer )[A-Za-z0-9._~+/=\-]{8,}")


def _secret_values() -> list[str]:
    """Values of secret env vars, from replay's own scan (the one that keeps them out of fixture files)."""
    from api.integrations.replay import _secrets

    return sorted(_secrets(os.environ), key=len, reverse=True)


def _clean(value: Any, secrets: list[str]) -> Any:
    """A JSON-safe copy with secrets redacted and long strings cut."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        for s in secrets:
            if s in value:
                value = value.replace(s, REDACTED)
        value = _SECRET_TEXT.sub(REDACTED, value)
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + f"... [cut {len(value) - MAX_TEXT} characters]"
    if isinstance(value, Mapping):
        return {str(k): REDACTED if _SECRET_FIELD.search(str(k)) and v not in (None, "") else _clean(v, secrets)
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_clean(v, secrets) for v in value]
    if hasattr(value, "model_dump"):
        return _clean(value.model_dump(mode="json"), secrets)
    return _clean(json.loads(json.dumps(value, default=str)) if not isinstance(value, (bytes, bytearray))
                  else value.decode(errors="replace"), secrets)
