"""Shared Claude call for every agent: strict JSON via structured outputs, one retry carrying the error.

Outside-call rules (timeout, one retry, DEMO_MODE fixtures) come from api/integrations/replay.py. A model
refusal or a cut-off answer counts as a failed call; validation or a code check failing on the answer gets one
retry with the problem appended; whatever still fails returns None and the caller routes it to Ask.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

import anthropic
from pydantic import BaseModel, ConfigDict, ValidationError

from api.integrations import replay

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

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


def _parse(client: anthropic.Anthropic, req: dict, output_format: type[BaseModel], timeout: float) -> dict:
    """One call. replay.call_outside owns the timeout and the retry, so the SDK's own retries are off.
    Server-side fallback covers a refusal."""
    resp = client.with_options(timeout=timeout, max_retries=0).beta.messages.parse(
        model=req["model"], max_tokens=MAX_TOKENS, system=req["system"],
        messages=[{"role": "user", "content": req["user"]}], output_format=output_format,
        betas=[FALLBACK_BETA], fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise ValueError(f"model declined ({getattr(resp.stop_details, 'category', None)})")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise ValueError(f"no complete JSON answer (stop_reason={resp.stop_reason})")
    return resp.parsed_output.model_dump()


def ask(service: str, system: str, user: str, output_format: type[BaseModel], check: Callable[[dict], T],
        client: anthropic.Anthropic | None = None, live_first: bool = False, **extra) -> Answer[T]:
    """`check` turns the JSON into the result or raises ValueError / ValidationError with the problem.
    `live_first` (the judge's portal replies) tries live even in DEMO_MODE, then the saved answer.
    `extra` joins the request (and its fixture key), e.g. a doc_id."""
    result: Answer[T] = Answer(None)
    for result.attempts in (1, 2):
        prompt = user if not result.errors else (f"{user}\n\nYour previous answer failed validation:\n"
                                                 f"{result.errors[-1]}\nReturn the complete answer again, fixed.")
        request = {"model": MODEL, "system": system, "user": prompt, **extra}
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
