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
    model       the model that answered a live call, else the model asked (None for Moss and QuickBooks)
    prompt      the prompt file and the first line of the system prompt; Moss and QuickBooks name the operation
    input       the request exactly as sent: system prompt + user content, or the payload
    output      the parsed answer (live or recorded); None when the call failed
    latency_ms, status (live · recorded · failed), attempts, error
    usage       a live call's tokens ({input_tokens, output_tokens, ...}); None for a recorded or failed call
GET /runs/{run_id}/trace/summary adds them up by agent and model, with the cost from config/pricing.yaml.
Secrets never land here: a value of any secret env var (replay's own scan), a field named like a key or token,
and anything shaped like an API key or a bearer token are replaced by "[redacted]".

Where the pipeline enters the contexts (Devank wires these; until then nothing is recorded):
- run_context(run.id) around the work of each entry point that runs agents for a run:
    api/pipeline._guarded         (the run's own thread: readers, Investigator, comebacks, Moss, QuickBooks)
    api/pipeline.answer           (the owner's reply: rule writer, Moss, then the charges decided again)
    api/pipeline.decide_approval  (the admin's yes: the QuickBooks writes)
    api/disputes.post             (the portal: Negotiator's reply, or the readers on an attached document)
    api/scenario.run              (the scenario box)
- charge_context(c.id) around each turn of the per-charge loop in api/pipeline._process.
- api/agents/readers.read_both runs the two readers on a thread pool, and a new thread starts with no context:
  that pool is a ContextPool (below), not a plain ThreadPoolExecutor, so the readers' calls are recorded.
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
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel

log = logging.getLogger("clawback.trace")

MAX_RUNS = 100  # the oldest run's trace goes first
MAX_PER_RUN = 500  # a March run makes about 20 calls; past this, a run's later calls are counted, not kept
MAX_TEXT = 50_000  # characters kept of any one string (a pasted portal reply could be anything)
PROMPTS = Path(__file__).resolve().parent / "agents" / "prompts"
PRICING = Path(__file__).resolve().parents[1] / "config" / "pricing.yaml"
REDACTED = "[redacted]"

AGENTS = {
    "claude-reader": "Deal reader (Claude)",
    "gemini-reader": "Deal reader (Gemini)",
    "claude-reader-b": "Deal reader (second Claude read)",
    "claude-investigator": "Investigator",
    "claude-investigator-ops": "Investigator (operations)",
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
    usage: dict[str, Any] | None = None


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
           attempts: int = 0, error: str | None = None, run_id: str | None = None, charge_id: str | None = None,
           usage: dict | None = None, model: str | None = None) -> TraceEntry | None:
    """One call, against run_id (default: the current run context). `usage` and `model` are what a live call
    reported (its tokens, the model that answered). Returns the entry, or None when there's no run, the run is
    full, or anything about recording failed: recording never raises."""
    try:
        run_id = run_id or _run.get()
        if not run_id:
            return None
        charge_id = charge_id or _charge.get() or _request_field(request, "charge_id")
        secrets = _secret_values()
        entry = dict(at=at, agent=AGENTS.get(service, service), service=service, run_id=run_id,
                     charge_id=charge_id, model=model or _request_field(request, "model"),
                     prompt=_prompt(service, request), input=_clean(request, secrets),
                     output=_clean(response, secrets), latency_ms=int(latency_ms), status=status,
                     attempts=int(attempts), error=_clean(error, secrets),
                     usage=_clean(dict(usage), secrets) if usage and status == "live" else None)
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


_prompt_files: list[tuple[re.Pattern[str], str]] | None = None


def _prompt_file(system: str) -> str | None:
    """Which api/agents/prompts/ file this system prompt is. The agents send each file with its {brand}-style
    placeholders filled for the run's account, so a placeholder matches any text."""
    global _prompt_files
    if _prompt_files is None:
        _prompt_files = []
        for p in sorted(PROMPTS.glob("*.md")):
            parts = re.split(r"\{[a-z_]+\}", p.read_text().strip())
            _prompt_files.append((re.compile(".+?".join(map(re.escape, parts)), re.S), f"api/agents/prompts/{p.name}"))
    return next((name for pattern, name in _prompt_files if pattern.fullmatch(system.strip())), None)


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


# ---------------------------------------------------------------- summary: calls, tokens, time, cost

AI_SERVICES = ("claude-", "gemini-")  # the model calls; Moss and QuickBooks aren't AI time
TOKENS = ("input_tokens", "output_tokens", "cache_write_tokens", "cache_write_1h_tokens", "cache_read_tokens")
PRICE_OF = {"input_tokens": "input", "output_tokens": "output", "cache_write_tokens": "cache_write_5m",
            "cache_write_1h_tokens": "cache_write_1h", "cache_read_tokens": "cache_read"}
MTOK = Decimal(1_000_000)


class AgentSummary(BaseModel):
    agent: str
    model: str | None
    calls: int
    live: int
    recorded: int
    failed: int
    input_tokens: int
    output_tokens: int
    ai_ms: int
    cost_usd: float | None  # None: a live call here reported no tokens, or its model has no price


class TraceSummary(BaseModel):
    run_id: str
    calls: int
    live: int
    recorded: int
    failed: int
    metered_calls: int  # live calls that reported their tokens (a recorded answer costs nothing now)
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    ai_ms: int  # the Claude and Gemini calls' time added up; the two readers overlap, so it can pass wall_ms
    wall_ms: int | None  # the run's first event to the decided board; None while it's still deciding
    cost_usd: float | None  # the live calls at config/pricing.yaml prices; None if any of them can't be priced
    unpriced_models: list[str]
    pricing_sources: list[str]
    by_agent: list[AgentSummary]


def load_pricing(path: Path = PRICING) -> tuple[dict[str, dict], list[str]]:
    """Per-million-token prices by model id, and the pages they were copied from. A missing file prices nothing."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        return {}, []
    return raw.get("models") or {}, list(raw.get("sources") or [])


def _prices_for(model: str | None, pricing: dict[str, dict]) -> dict | None:
    """Exact model id, else the longest id it starts with (a served "gemini-3.6-flash-001" is gemini-3.6-flash)."""
    if not model:
        return None
    if model in pricing:
        return pricing[model] or None
    prefix = max((m for m in pricing if model.startswith(m)), key=len, default=None)
    return (pricing[prefix] or None) if prefix else None


def call_cost(model: str | None, usage: dict | None, pricing: dict[str, dict]) -> Decimal | None:
    """What one live call cost in USD, or None when it can't be priced: no tokens reported, no price for its model
    or for a kind of token it used, or a pricing mode the table doesn't cover (fast mode, US-only inference)."""
    if not usage or usage.get("speed") or usage.get("inference_geo"):
        return None
    prices = _prices_for(model, pricing)
    if not prices:
        return None
    longer = prices.get("long_prompt")  # e.g. Haiku 5.5 prompts over 100,000 tokens (cache reads and writes count)
    prompt = sum(int(usage.get(k, 0)) for k in TOKENS if k != "output_tokens")
    if longer and prompt > int(longer["over_input_tokens"]):
        prices = longer
    total = Decimal(0)
    for kind, key in PRICE_OF.items():
        n = int(usage.get(kind, 0))
        if n:
            if prices.get(key) in (None, ""):
                return None
            total += n * Decimal(str(prices[key])) / MTOK
    return total


def summarize(run_id: str, started_at: datetime | None = None, decided_at: datetime | None = None,
              pricing: tuple[dict[str, dict], list[str]] | None = None) -> TraceSummary:
    """The run's calls added up by agent and model: tokens from live calls, AI time, wall time, and the cost."""
    models, sources = pricing if pricing is not None else load_pricing()
    entries = trace_for(run_id)
    rows: dict[tuple[str, str | None], dict] = {}
    unpriced: set[str] = set()
    for e in entries:
        r = rows.setdefault((e.agent, e.model), {"calls": 0, "live": 0, "recorded": 0, "failed": 0, "input_tokens": 0,
                                                 "output_tokens": 0, "ai_ms": 0, "cost": Decimal(0)})
        r["calls"] += 1
        r[e.status] += 1
        if e.service.startswith(AI_SERVICES):
            r["ai_ms"] += e.latency_ms
        if e.usage:
            r["input_tokens"] += int(e.usage.get("input_tokens", 0))
            r["output_tokens"] += int(e.usage.get("output_tokens", 0))
        if e.status == "live" and e.service.startswith(AI_SERVICES):
            cost = call_cost(e.model, e.usage, models)
            if cost is None:
                r["cost"] = None
                unpriced.add(e.model or e.service)
            elif r["cost"] is not None:
                r["cost"] += cost
    by_agent = [AgentSummary(agent=a, model=m, calls=r["calls"], live=r["live"], recorded=r["recorded"],
                             failed=r["failed"], input_tokens=r["input_tokens"], output_tokens=r["output_tokens"],
                             ai_ms=r["ai_ms"], cost_usd=None if r["cost"] is None else _usd(r["cost"]))
                for (a, m), r in rows.items()]
    costs = [r["cost"] for r in rows.values()]
    tokens = lambda kind: sum(int(e.usage.get(kind, 0)) for e in entries if e.usage)  # noqa: E731
    return TraceSummary(
        run_id=run_id, calls=len(entries), live=sum(e.status == "live" for e in entries),
        recorded=sum(e.status == "recorded" for e in entries), failed=sum(e.status == "failed" for e in entries),
        metered_calls=sum(1 for e in entries if e.usage), input_tokens=tokens("input_tokens"),
        output_tokens=tokens("output_tokens"),
        cache_write_tokens=tokens("cache_write_tokens") + tokens("cache_write_1h_tokens"),
        cache_read_tokens=tokens("cache_read_tokens"), ai_ms=sum(r.ai_ms for r in by_agent),
        wall_ms=int((decided_at - started_at).total_seconds() * 1000) if started_at and decided_at else None,
        cost_usd=None if any(c is None for c in costs) else _usd(sum(costs, Decimal(0))),
        unpriced_models=sorted(unpriced), pricing_sources=sources, by_agent=by_agent)


def _usd(amount: Decimal) -> float:
    return float(amount.quantize(Decimal("0.000001")))
