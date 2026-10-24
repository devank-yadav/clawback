"""Shared Claude call for every agent: strict JSON via structured outputs, one retry carrying the error.

Outside-call rules (timeout, one retry, DEMO_MODE fixtures) come from api/integrations/replay.py. A model
refusal or a cut-off answer counts as a failed call; validation or a code check failing on the answer gets one
retry with the problem appended; whatever still fails returns None and the caller routes it to Ask.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from api.integrations import replay

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# CLAWBACK_MODEL_<AGENT> puts one agent on another Claude model (e.g. a cheaper Investigator, checked with the eval).
# Unset, the request (and so its recorded answer's key) is exactly as before. READER covers both Claude reads.
MODEL_ENV = {"claude-reader": "CLAWBACK_MODEL_READER", "claude-reader-b": "CLAWBACK_MODEL_READER",
             "claude-investigator": "CLAWBACK_MODEL_INVESTIGATOR", "claude-rehearsal": "CLAWBACK_MODEL_REHEARSAL",
             "claude-portal-reply": "CLAWBACK_MODEL_PORTAL_REPLY", "claude-coach": "CLAWBACK_MODEL_COACH",
             "claude-rule-writer": "CLAWBACK_MODEL_RULE_WRITER"}

T = TypeVar("T")


class Strict(BaseModel):
    """Base for model-facing schemas: structured outputs need additionalProperties false everywhere."""

    model_config = ConfigDict(extra="forbid")


@dataclass
class Answer(Generic[T]):
    value: T | None
    source: Literal["live", "fixture"] = "live"
    attempts: int = 0
    errors: list[str] = field(default_factory=list)


def model_for(service: str) -> str:
    """The model this agent asks: its CLAWBACK_MODEL_<AGENT> setting, else MODEL."""
    return os.getenv(MODEL_ENV.get(service, ""), "").strip() or MODEL


def usage_of(resp) -> dict | None:
    """The tokens a response used, for the run's trace (GET /runs/{id}/trace/summary prices them)."""
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    one_hour = getattr(getattr(u, "cache_creation", None), "ephemeral_1h_input_tokens", None) or 0
    out = {"input_tokens": getattr(u, "input_tokens", None) or 0, "output_tokens": getattr(u, "output_tokens", None) or 0,
           "cache_write_tokens": (getattr(u, "cache_creation_input_tokens", None) or 0) - one_hour,
           "cache_write_1h_tokens": one_hour, "cache_read_tokens": getattr(u, "cache_read_input_tokens", None) or 0}
    out = {k: int(v) for k, v in out.items() if v or k in ("input_tokens", "output_tokens")}
    # Priced differently from the standard table (fast mode, US-only inference): the summary leaves them unpriced.
    if getattr(u, "speed", None) not in (None, "standard"):
        out["speed"] = str(u.speed)
    if getattr(u, "inference_geo", None) not in (None, "global"):
        out["inference_geo"] = str(u.inference_geo)
    return out


def _parse(client: anthropic.Anthropic, req: dict, output_format: type[BaseModel], timeout: float) -> replay.Metered:
    """One call. replay.call_outside owns the timeout and the retry, so the SDK's own retries are off.
    Server-side fallback covers a refusal. The answer is the parsed JSON; its tokens and the model that answered
    ride along for the trace only (call_outside returns and records the JSON alone)."""
    resp = client.with_options(timeout=timeout, max_retries=0).beta.messages.parse(
        model=req["model"], max_tokens=MAX_TOKENS, system=req["system"],
        messages=[{"role": "user", "content": req["user"]}], output_format=output_format,
        betas=[FALLBACK_BETA], fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise ValueError(f"model declined ({getattr(resp.stop_details, 'category', None)})")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise ValueError(f"no complete JSON answer (stop_reason={resp.stop_reason})")
    served = getattr(resp, "model", None)
    return replay.Metered(resp.parsed_output.model_dump(), usage_of(resp), served if isinstance(served, str) else None)


def ask(service: str, system: str, user: str, output_format: type[BaseModel], check: Callable[[dict], T],
        client: anthropic.Anthropic | None = None, live_first: bool = False, **extra) -> Answer[T]:
    """`check` turns the JSON into the result or raises ValueError / ValidationError with the problem.
    `live_first` (the judge's portal replies) tries live even in DEMO_MODE, then the saved answer.
    `extra` joins the request (and its fixture key), e.g. a doc_id."""
    result: Answer[T] = Answer(None)
    for result.attempts in (1, 2):
        prompt = user if not result.errors else (f"{user}\n\nYour previous answer failed validation:\n"
                                                 f"{result.errors[-1]}\nReturn the complete answer again, fixed.")
        request = {"model": model_for(service), "system": system, "user": prompt, **extra}
        try:
            res = replay.call_outside(service, request, live_first=live_first,
                                      fn=lambda req, timeout: _parse(client or anthropic.Anthropic(), req, output_format, timeout))
        except replay.OutsideCallFailed as e:  # live failed twice and nothing saved
            result.errors.append(str(e))
            return result
        result.source = res.source
        try:
            result.value = check(res.response)
            return result
        except (ValidationError, ValueError) as e:
            result.errors.append(str(e))
    return result
