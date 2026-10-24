"""Deal Reader A (Claude): one document -> typed terms, each with an exact quote (docs/design.md, Agents > 1).

Flow: Claude returns strict JSON (structured outputs) -> Pydantic validation against api/contracts.py
(one retry with the error appended; what still fails goes to `unclear`) -> code check with
api/engine/quote_check.py (quote not found or a number not in the quote -> rejected). Whether a term can
change the deal comes from the document (approved sender or signed by both), never from the model.

Run:  python -m api.agents.reader spring-promo broker-2026-03-28 northmart-2026-03-30
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import anthropic

from api import documents
from api.contracts import TERM_PARAMS, Document, ReaderOutput, ReaderTerm, Term, TermType
from api.engine import quote_check
from api.agents import claude
from api.agents.claude import Strict

MODEL = claude.MODEL
SERVICE = "claude-reader"  # fixtures in data/fixtures/claude-reader/
PROMPT = (Path(__file__).parent / "prompts" / "reader.md").read_text()


# What the model fills in. Strict JSON schemas can't hold a free-form dict, so params is one flat object
# with every field nullable; code keeps only the fields the term's type uses (TERM_PARAMS).
class LLMParams(Strict):
    rate: str | None
    products: list[str] | None
    start: str | None
    end: str | None
    max_units: int | None
    max_fee: str | None
    extra_units: int | None


class LLMTerm(Strict):
    type: TermType
    params: LLMParams
    effective_from: str | None
    effective_to: str | None
    exact_quote: str
    discretion: bool


class LLMOutput(Strict):
    terms: list[LLMTerm]
    unclear: list[str]


@dataclass
class ReaderResult:
    doc: Document
    terms: list[Term]
    unclear: list[str]
    source: Literal["live", "fixture"]
    attempts: int
    errors: list[str] = field(default_factory=list)
    model: str = "claude"  # who read it: "claude" (Reader A), "gemini" or "claude-b" (Reader B)


def _user_message(doc: Document, text: str) -> str:
    when = doc.received_at.date().isoformat() if doc.received_at else "unknown"
    return (f"Document ID: {doc.id}\nKind: {doc.kind}\nSender: {doc.sender or 'not stated'}\nDocument date: {when}\n\n"
            f"<document>\n{text}\n</document>")


def _to_reader_output(raw: dict, doc: Document, text: str) -> ReaderOutput:
    """LLM JSON -> contracts.ReaderOutput. Raises ValidationError on anything the contract rejects."""
    out = LLMOutput.model_validate(raw)
    terms = []
    for t in out.terms:
        used = TERM_PARAMS[t.type].model_fields
        params = {k: v for k, v in t.params.model_dump().items() if v is not None and k in used}
        span = quote_check.find_quote(text, t.exact_quote) or (0, 0)
        terms.append(ReaderTerm(type=t.type, params=params, effective_from=t.effective_from,
                                effective_to=t.effective_to, exact_quote=t.exact_quote, char_start=span[0],
                                char_end=span[1], discretion=t.discretion, source_doc_id=doc.id))
    return ReaderOutput(terms=terms, unclear=out.unclear)


def read_document(doc_id: str, base_terms: Sequence[Term] = (), client: anthropic.Anthropic | None = None,
                  live_first: bool = False) -> ReaderResult:
    """Read one document. `base_terms` are the deal's verified terms, used only to date an extension
    that states its end but not its start (it starts the day after the deal's date_range ends)."""
    doc, text = documents.load(doc_id)
    ans = claude.ask(SERVICE, PROMPT, _user_message(doc, text), LLMOutput, lambda raw: _to_reader_output(raw, doc, text),
                     client, live_first=live_first, doc_id=doc_id)
    if ans.value is None:
        return ReaderResult(doc, [], [f"{doc_id}: reader output failed validation twice; needs a person"],
                            ans.source, ans.attempts, ans.errors)
    output = ans.value
    return ReaderResult(doc, _check(output, doc, text, base_terms), output.unclear, ans.source, ans.attempts,
                        ans.errors)


def read_text(text: str, client: anthropic.Anthropic | None = None) -> ReaderResult:
    """The scenario box: read a pasted clause. Tries live first (the judge's own words have no recording yet)."""
    return read_document(documents.paste(text).id, client=client, live_first=True)


def _check(output: ReaderOutput, doc: Document, text: str, base_terms: Sequence[Term]) -> list[Term]:
    """Quote check on every term, plus the document's right to change the deal."""
    base_end = next((t.params.get("end") for t in base_terms if t.type == "date_range"), None)
    terms, seen = [], {}
    for t in output.terms:
        data = t.model_dump()
        if t.type == "amendment" and t.effective_from is None and t.effective_to and base_end:
            data["effective_from"] = _day_after(base_end)
        qc = quote_check.check_quote(text, data)
        n = seen[t.type] = seen.get(t.type, 0) + 1
        terms.append(Term.model_validate({
            **data, "id": f"{doc.id}/{t.type}" + (f"-{n}" if n > 1 else ""), "reader": "claude",
            "status": quote_check.VERIFIED if qc.ok else quote_check.REJECTED,
            "char_start": qc.char_start if qc.ok else data["char_start"],
            "char_end": qc.char_end if qc.ok else data["char_end"],
            "source_approved": documents.can_change_deal(doc), "reasons": list(qc.reasons),
        }))
    return terms


def _day_after(d: Any) -> str:
    day = d if isinstance(d, date) else date.fromisoformat(str(d))
    return (day + timedelta(days=1)).isoformat()


def main(doc_ids: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    base: list[Term] = []
    for doc_id in doc_ids:
        r = read_document(doc_id, base_terms=base)
        if r.doc.kind == "deal":
            base = [t for t in r.terms if t.status == "verified"]
        role = "can change the deal" if documents.can_change_deal(r.doc) else "claim only (sender can't change the deal)"
        print(f"\n{doc_id}  [{r.source}, {r.attempts} attempt(s)]  {role}")
        for t in r.terms:
            print(f"  {t.status:9} {t.type:15} {json.dumps(t.params, default=str):55} "
                  f"{t.effective_from or ''}..{t.effective_to or ''}  discretion={t.discretion}")
            for why in t.reasons:
                print(f"            {why}")
        for u in r.unclear:
            print(f"  unclear: {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["spring-promo", "broker-2026-03-28", "northmart-2026-03-30"]))
