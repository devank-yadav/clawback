"""Both Deal Readers on one document, merged by the code check (docs/design.md, Agents > 1).

Reader A (Claude) and Reader B (Gemini, or a second Claude prompt) read in parallel. Their terms are paired by
type, in the order they appear in the document, and api/engine/quote_check.verify_term decides each pair:
a quote not found word for word, or a number not in its quote -> rejected; only one reader found it, or they
disagree on type or params -> disputed (any charge using it goes to Ask, gate row 2); both agree -> verified.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from itertools import zip_longest

import anthropic

from api import documents
from api.agents import fee_terms, reader, reader_b
from api.agents.reader import ReaderResult
from api.contracts import Document, Term
from api.engine import quote_check
from api.trace import ContextPool


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


def _pair_key(t: Term) -> tuple[str, str]:
    """Terms are paired by type, in document order. A document states many fee schedules, so those pair by fee name
    too: one reader finding an extra fee then disputes only that fee, not every fee after it."""
    return t.type, " ".join(str(t.params.get("fee_code", "")).lower().split()) if t.type == "fee_schedule" else ""


def _pairs(type_: str, ta: list[Term], tb: list[Term]) -> list[tuple[Term | None, Term | None]]:
    """The two readers' terms of one key, paired. Fee schedules pair a term with the other reader's that prices it
    the same way first (one reader quoting an extra schedule under the same fee name, such as a short-shipment
    chargeback named "Receipt of backorder", then disputes only that one), the rest in document order."""
    if type_ != "fee_schedule":
        return list(zip_longest(ta, tb))
    pairs: list[tuple[Term | None, Term | None]] = []
    left = list(tb)
    alone: list[Term] = []
    for x in ta:
        y = next((y for y in left if fee_terms.priced_alike(x.params, y.params)), None)
        if y is None:
            alone.append(x)
        else:
            left.remove(y)
            pairs.append((x, y))
    pairs += list(zip_longest(alone, left))
    return sorted(pairs, key=lambda p: min(t.char_start for t in p if t is not None))


def merge(text: str, doc: Document, a: list[Term], b: list[Term]) -> tuple[list[Term], list[str]]:
    by_type: dict[tuple[str, str], tuple[list[Term], list[Term]]] = defaultdict(lambda: ([], []))
    for t in sorted(a, key=lambda t: t.char_start):
        by_type[_pair_key(t)][0].append(t)
    for t in sorted(b, key=lambda t: t.char_start):
        by_type[_pair_key(t)][1].append(t)
    merged, notes = [], []
    count: dict[str, int] = defaultdict(int)
    for (type_, _), (ta, tb) in by_type.items():
        for x, y in _pairs(type_, ta, tb):
            n = count[type_] = count[type_] + 1
            update = {}
            if type_ == "fee_schedule" and x and y and fee_terms.priced_alike(x.params, y.params):
                # Priced the same way: backup required or a judgment call if either reader says so.
                pa, pb = fee_terms.agreed(x.params, y.params)
                x, y = x.model_copy(update={"params": pa}), y.model_copy(update={"params": pb})
                update["discretion"] = x.discretion or y.discretion
            v = quote_check.verify_term(text, x.model_dump(mode="json") if x else None,
                                        y.model_dump(mode="json") if y else None)
            base = x or y
            merged.append(base.model_copy(update={
                **update, "id": f"{doc.id}/{type_}" + (f"-{n}" if n > 1 else ""), "reader": "merged", "status": v.status,
                "char_start": v.char_start if v.char_start is not None else base.char_start,
                "char_end": v.char_end if v.char_end is not None else base.char_end,
                "source_approved": documents.can_change_deal(doc), "reasons": list(v.reasons)}))
            if v.status == quote_check.DISPUTED:
                notes.append(f"{type_}: Reader A read {_params(x)}; Reader B read {_params(y)}")
    return merged, notes


def read_both(doc_id: str, base_terms: Sequence[Term] = (), client: anthropic.Anthropic | None = None,
              client_b: anthropic.Anthropic | None = None, gemini=None, live_first: bool = False) -> Merged:
    with ContextPool(max_workers=2) as pool:  # keeps the run context, so both readers reach the run's trace
        fa = pool.submit(reader.read_document, doc_id, base_terms, client, live_first)
        fb = pool.submit(reader_b.read_document, doc_id, base_terms, client_b or client, gemini, live_first)
        a, b = fa.result(), fb.result()
    _, text = documents.load(doc_id)
    terms, notes = merge(text, a.doc, a.terms, b.terms)
    unclear = list(dict.fromkeys(a.unclear + b.unclear))
    return Merged(a.doc, terms, unclear, ("claude", b.model), notes, a, b)


def recheck(m: Merged, base_terms: Sequence[Term]) -> Merged:
    """A read_both made without base_terms, checked and merged again with them: the same Merged read_both(doc_id,
    base_terms) gives. base_terms isn't in the readers' requests, so a run reads every document at once and then
    checks them in document order (api/pipeline._read_terms), each with the deal terms read before it."""
    if not base_terms:
        return m
    _, text = documents.load(m.doc.id)

    def again(r: ReaderResult | None) -> ReaderResult | None:
        if r is None or r.output is None:
            return r
        terms = reader._check(r.output, r.doc, text, base_terms)
        return replace(r, terms=terms if r.model == "claude" else reader_b._relabel(terms, r.model))

    a, b = again(m.a), again(m.b)
    terms, notes = merge(text, a.doc, a.terms, b.terms)
    return replace(m, terms=terms, disagreements=notes, a=a, b=b)


def read_text_both(text: str, client: anthropic.Anthropic | None = None, gemini=None) -> Merged:
    """The scenario box: both readers on a pasted clause, live first."""
    return read_both(documents.paste(text).id, client=client, gemini=gemini, live_first=True)
