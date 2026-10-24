"""Deal Reader B: a second, independent read of the same document (docs/design.md, Agents > 1).

Gemini when GEMINI_API_KEY is set (the Gemini track): GEMINI_MODEL first, then GEMINI_FALLBACK_MODEL if it's busy
(503), out of quota (429) or not available (404). If neither gives a valid answer, a second Claude call with its
own prompt (prompts/reader_b.md), as the design allows. The result names the model, so a run only claims two
models when Gemini really answered. Both readers produce the same JSON (reader.LLMOutput) and go through the same
quote check; api/agents/readers.py merges them.

Gemini call: google-genai's models.generate_content with JSON output against the schema (response_json_schema),
behind replay.call_outside like every outside call. The SDK's own retries are off (one attempt): with them on,
a 429 waited through minutes of backoff and looked like a hang. replay.call_outside does the one retry.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

import anthropic
from pydantic import ValidationError

from api import accounts, documents
from api.agents import claude, prompts, reader
from api.agents.reader import LLMOutput, ReaderResult
from api.contracts import Term
from api.integrations import replay

# Tried on the team key: gemini-3.8-flash answers 429 (no quota), gemini-2.5-flash 404 (no longer available);
# gemini-3.6-flash (Google's general-purpose model) works but is sometimes busy, gemini-3.5-flash-lite is fast.
# GEMINI_MODEL / GEMINI_FALLBACK_MODEL in .env override them (e.g. gemini-3.8-flash once billing is on).
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_GEMINI_FALLBACK = "gemini-3.5-flash-lite"
GEMINI_SERVICE = "gemini-reader"
CLAUDE_B_SERVICE = "claude-reader-b"


def prompt(account: accounts.Account | str | None = None) -> str:
    return prompts.render("reader_b", account)


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL


def gemini_models() -> list[str]:
    """The models Reader B tries, in order."""
    fallback = os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or DEFAULT_GEMINI_FALLBACK
    return list(dict.fromkeys((gemini_model(), fallback)))


def usage_of(response) -> dict | None:
    """The tokens a Gemini response used, for the run's trace: the prompt, and everything generated (the answer
    and any thinking; thinking_tokens says how much of it was thinking)."""
    u = getattr(response, "usage_metadata", None)
    if u is None:
        return None
    thinking = getattr(u, "thoughts_token_count", None) or 0
    out = {"input_tokens": int(getattr(u, "prompt_token_count", None) or 0),
           "output_tokens": int((getattr(u, "candidates_token_count", None) or 0) + thinking)}
    return {**out, "thinking_tokens": int(thinking)} if thinking else out


def _ask_gemini(gemini, model: str, system: str, user: str, timeout: float) -> replay.Metered:
    from google.genai import types

    if gemini is None:
        from google import genai

        gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(
            timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1)))
    response = gemini.models.generate_content(model=model, contents=user, config=types.GenerateContentConfig(
        system_instruction=system, response_mime_type="application/json",
        response_json_schema=LLMOutput.model_json_schema()))
    served = getattr(response, "model_version", None)
    return replay.Metered(json.loads(response.text), usage_of(response), served if isinstance(served, str) else None)


def _gemini(doc_id: str, system: str, user: str, check, gemini, live_first: bool):
    """Each Gemini model in turn, each with one retry on a validation error.
    Returns (output or None, source, errors, the model that answered)."""
    errors: list[str] = []
    for model in gemini_models():
        failed: list[str] = []
        for _ in (1, 2):
            prompt = user if not failed else (f"{user}\n\nYour previous answer failed validation:\n{failed[-1]}\n"
                                              "Return the complete answer again, fixed.")
            request = {"model": model, "system": system, "user": prompt, "doc_id": doc_id}
            try:
                res = replay.call_outside(GEMINI_SERVICE, request, live_first=live_first, fn=lambda req, timeout:
                                          _ask_gemini(gemini, req["model"], req["system"], req["user"], timeout))
            except replay.OutsideCallFailed as e:
                failed.append(str(e))
                break  # busy, out of quota or not available: the next model
            try:
                return check(res.response), res.source, errors + failed, model
            except (ValidationError, ValueError) as e:
                failed.append(str(e))
        errors += failed
    return None, "live", errors, None


def read_document(doc_id: str, base_terms: Sequence[Term] = (), client: anthropic.Anthropic | None = None,
                  gemini=None, live_first: bool = False) -> ReaderResult:
    doc, text = documents.load(doc_id)
    system, user = prompt(documents.account_of(doc_id)), reader._user_message(doc, text)
    check = lambda raw: reader._to_reader_output(raw, doc, text)  # noqa: E731
    errors: list[str] = []
    if gemini is not None or gemini_configured():
        output, source, errors, model = _gemini(doc_id, system, user, check, gemini, live_first)
        if output is not None:
            return ReaderResult(doc, _relabel(reader._check(output, doc, text, base_terms), "gemini"), output.unclear,
                                source, 1 + len(errors), errors, model="gemini", model_id=model)
    ans = claude.ask(CLAUDE_B_SERVICE, system, user, LLMOutput, check, client, live_first=live_first, doc_id=doc_id)
    errors += ans.errors
    if ans.value is None:
        return ReaderResult(doc, [], [f"{doc_id}: Reader B's output failed validation twice; needs a person"],
                            ans.source, ans.attempts, errors, model="claude-b")
    return ReaderResult(doc, _relabel(reader._check(ans.value, doc, text, base_terms), "claude-b"), ans.value.unclear,
                        ans.source, ans.attempts, errors, model="claude-b")


def _relabel(terms: list[Term], who: str) -> list[Term]:
    return [t.model_copy(update={"reader": who}) for t in terms]
