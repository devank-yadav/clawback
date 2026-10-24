"""Map api/contracts.py objects onto the engine's plain dataclasses (api/engine/types.py)."""

from __future__ import annotations

from api import contracts
from api.engine import types as eng


def to_engine_term(t: contracts.Term) -> eng.Term:
    return eng.Term(
        id=t.id, type=eng.TermType(t.type), params=dict(t.params), exact_quote=t.exact_quote,
        effective_from=t.effective_from, effective_to=t.effective_to, discretion=t.discretion,
        status=eng.TermStatus(t.status) if t.status != "pending" else eng.TermStatus.DISPUTED,
        source_doc_id=t.source_doc_id, source_approved=t.source_approved,
    )
