"""Both Deal Readers on one document, merged by the code check (docs/design.md, Agents > 1).

Reader A (Claude) and Reader B (Gemini, or a second Claude prompt) read in parallel. Their terms are paired by
type, in the order they appear in the document, and api/engine/quote_check.verify_term decides each pair:
a quote not found word for word, or a number not in its quote -> rejected; only one reader found it, or they
disagree on type or params -> disputed (any charge using it goes to Ask, gate row 2); both agree -> verified.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import zip_longest

import anthropic

from api import documents
from api.agents import reader, reader_b
from api.agents.reader import ReaderResult
from api.contracts import Document, Term
from api.engine import quote_check


@dataclass
class Merged:
    doc: Document
    terms: list[Term]
    unclear: list[str]
    models: tuple[str, str]  # ("claude", "gemini") or ("claude", "claude-b")
    disagreements: list[str] = field(default_factory=list)
    a: ReaderResult | None = None
    b: ReaderResult | None = None

    @property
    def model_ids(self) -> tuple[str | None, str | None]:
        return (None, self.b.model_id if self.b else None)


def _params(t: Term | None) -> str:
    return "nothing" if t is None else ", ".join(f"{k} {v}" for k, v in t.params.items()) or t.type


def merge(text: str, doc: Document, a: list[Term], b: list[Term]) -> tuple[list[Term], list[str]]:
    by_type: dict[str, tuple[list[Term], list[Term]]] = defaultdict(lambda: ([], []))
    for t in sorted(a, key=lambda t: t.char_start):
        by_type[t.type][0].append(t)
    for t in sorted(b, key=lambda t: t.char_start):
        by_type[t.type][1].append(t)
    merged, notes = [], []
    for type_, (ta, tb) in by_type.items():
        for n, (x, y) in enumerate(zip_longest(ta, tb), 1):
            v = quote_check.verify_term(text, x.model_dump(mode="json") if x else None,
                                        y.model_dump(mode="json") if y else None)
            base = x or y
            merged.append(base.model_copy(update={
                "id": f"{doc.id}/{type_}" + (f"-{n}" if n > 1 else ""), "reader": "merged", "status": v.status,
                "char_start": v.char_start if v.char_start is not None else base.char_start,
                "char_end": v.char_end if v.char_end is not None else base.char_end,
                "source_approved": documents.can_change_deal(doc), "reasons": list(v.reasons)}))
            if v.status == quote_check.DISPUTED:
                notes.append(f"{type_}: Reader A read {_params(x)}; Reader B read {_params(y)}")
    return merged, notes


def read_both(doc_id: str, base_terms: Sequence[Term] = (), client: anthropic.Anthropic | None = None,
              client_b: anthropic.Anthropic | None = None, gemini=None, live_first: bool = False) -> Merged:
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(reader.read_document, doc_id, base_terms, client, live_first)
        fb = pool.submit(reader_b.read_document, doc_id, base_terms, client_b or client, gemini, live_first)
        a, b = fa.result(), fb.result()
    _, text = documents.load(doc_id)
    terms, notes = merge(text, a.doc, a.terms, b.terms)
    unclear = list(dict.fromkeys(a.unclear + b.unclear))
    return Merged(a.doc, terms, unclear, ("claude", b.model), notes, a, b)


def read_text_both(text: str, client: anthropic.Anthropic | None = None, gemini=None) -> Merged:
    """The scenario box: both readers on a pasted clause, live first."""
    return read_both(documents.paste(text).id, client=client, gemini=gemini, live_first=True)
