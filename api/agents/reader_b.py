"""Deal Reader B: a second, independent read of the same document (docs/design.md, Agents > 1).

Gemini when GEMINI_API_KEY is set (the Gemini track). Until then, or if Gemini fails or its answer fails
validation twice, a second Claude call with its own prompt (prompts/reader_b.md), as the design allows; the
result names the model, so a run only claims two models when Gemini really answered. Both readers produce the
same JSON (reader.LLMOutput) and go through the same quote check; api/agents/readers.py merges them.

Gemini call: google-genai's Interactions API with JSON output against a schema
(ai.google.dev/gemini-api/docs/structured-output), behind replay.call_outside like every outside call.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

import anthropic
from pydantic import ValidationError

from api import documents
from api.agents import claude, reader
from api.agents.reader import LLMOutput, ReaderResult
from api.contracts import Term
from api.integrations import replay

# GEMINI_MODEL in .env picks another model. gemini-2.5-flash is in the team key's model list (gemini-3.8-flash isn't).
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_SERVICE = "gemini-reader"
CLAUDE_B_SERVICE = "claude-reader-b"
PROMPT = (Path(__file__).parent / "prompts" / "reader_b.md").read_text()


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL


def _ask_gemini(gemini, user: str, timeout: float) -> dict:
    if gemini is None:
        from google import genai

        gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    interaction = gemini.interactions.create(
        model=gemini_model(), input=user, system_instruction=PROMPT, store=False, timeout=timeout,
        response_format={"type": "text", "mime_type": "application/json", "schema": LLMOutput.model_json_schema()},
    )
    return json.loads(interaction.output_text)


def _gemini(doc_id: str, user: str, check, gemini, live_first: bool):
    """One Gemini read with one retry on a validation error. None if Gemini can't give a valid answer."""
    errors: list[str] = []
    for _ in (1, 2):
        prompt = user if not errors else (f"{user}\n\nYour previous answer failed validation:\n{errors[-1]}\n"
                                          "Return the complete answer again, fixed.")
        request = {"model": gemini_model(), "system": PROMPT, "user": prompt, "doc_id": doc_id}
        try:
            res = replay.call_outside(GEMINI_SERVICE, request, live_first=live_first,
                                      fn=lambda req, timeout: _ask_gemini(gemini, req["user"], timeout))
        except replay.OutsideCallFailed as e:
            return None, "live", errors + [str(e)]
        try:
            return check(res.response), res.source, errors
        except (ValidationError, ValueError) as e:
            errors.append(str(e))
    return None, "live", errors


def read_document(doc_id: str, base_terms: Sequence[Term] = (), client: anthropic.Anthropic | None = None,
                  gemini=None, live_first: bool = False) -> ReaderResult:
    doc, text = documents.load(doc_id)
    user = reader._user_message(doc, text)
    check = lambda raw: reader._to_reader_output(raw, doc, text)  # noqa: E731
    errors: list[str] = []
    if gemini is not None or gemini_configured():
        output, source, errors = _gemini(doc_id, user, check, gemini, live_first)
        if output is not None:
            return ReaderResult(doc, _relabel(reader._check(output, doc, text, base_terms), "gemini"), output.unclear,
                                source, 1 + len(errors), errors, model="gemini")
    ans = claude.ask(CLAUDE_B_SERVICE, PROMPT, user, LLMOutput, check, client, live_first=live_first, doc_id=doc_id)
    errors += ans.errors
    if ans.value is None:
        return ReaderResult(doc, [], [f"{doc_id}: Reader B's output failed validation twice; needs a person"],
                            ans.source, ans.attempts, errors, model="claude-b")
    return ReaderResult(doc, _relabel(reader._check(ans.value, doc, text, base_terms), "claude-b"), ans.value.unclear,
                        ans.source, ans.attempts, errors, model="claude-b")


def _relabel(terms: list[Term], who: str) -> list[Term]:
    return [t.model_copy(update={"reader": who}) for t in terms]
