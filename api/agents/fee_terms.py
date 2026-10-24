"""Fee terms in one canonical form, whichever reader wrote them (docs/design.md, Agents > 1, "Code check after").

Two readers can state the same fee differently: "MCB processing fee" or "MCB", "5%", "5" or "0.05", "$65.00" or "65",
per left out or "incident", requires_proof false or missing. The quote check and the readers' agreement compare
params, so both readers' fee_schedule params are put in this form first (reader._to_reader_output), and the merge then
compares only what prices the fee (readers.merge). Nothing here invents a value: a number that isn't written in the
quote still fails the quote check, and a fee name the account doesn't list is kept as written.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from api.engine import quote_check

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")


def _words(name: str) -> str:
    return " ".join(re.sub(r"[^\w%]+", " ", str(name)).lower().split())


def fee_code(name: str, vocabulary: Iterable[str]) -> str:
    """The account's own name for the fee (fees/fees.yaml codes): an exact match ignoring case and punctuation, else
    the longest listed name the reader's name contains as whole words ("MCB processing fee" -> "MCB"), else the name
    as written."""
    vocab = list(dict.fromkeys(vocabulary))
    got = _words(name)
    for v in vocab:
        if _words(v) == got:
            return v
    inside = [v for v in vocab if re.search(rf"\b{re.escape(_words(v))}\b", got)]
    return max(inside, key=lambda v: len(_words(v))) if inside else str(name).strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    m = _NUMBER.search(str(value).replace("$", ""))
    if not m:
        return None
    try:
        return Decimal(m.group().replace(",", ""))
    except InvalidOperation:
        return None


def _plain(d: Decimal) -> str:
    out = format(d.normalize(), "f")
    return out if "." not in out else out.rstrip("0").rstrip(".") or "0"


def rate(value: Any, basis: str | None, quote: str) -> str | None:
    """A rate as a plain decimal string. A percent written as a fraction (0.05 for "5%") becomes the percent, but only
    when the quote writes that percent and not the fraction."""
    d = _decimal(value)
    if d is None:
        return None
    if basis == "percent" and 0 < d < 1:
        written = set(quote_check.numbers_in(quote))
        if d not in written and (d * 100) in written:
            d = d * 100
    return _plain(d)


_SCOPE_LEAD = re.compile(r"^(?:each|every|all|any|a|an|the)\s+", re.I)
_SCOPE_TAIL = re.compile(r"\s+(?:p\.?\s?o\.?'?s?|purchase\s+orders?|orders?)\.?$", re.I)


def scope(value: Any) -> str | None:
    """The kind of purchase order a fee applies to, without the words around it: "each new store P.O." and "new
    store" are the same scope (the one purchases' po_type names)."""
    if value is None:
        return None
    out = " ".join(str(value).split())
    out = _SCOPE_TAIL.sub("", _SCOPE_LEAD.sub("", out)).strip()
    return out or None


def canonical(params: dict, quote: str, vocabulary: Iterable[str]) -> dict:
    """fee_schedule params in one form: the account's fee name, plain decimal rate / min / max (a minimum or maximum
    of 0 is none), applies_to without "each ... P.O.", per "incident" when unstated, requires_proof false when unstated,
    no empty tiers."""
    out = dict(params)
    if out.get("fee_code"):
        out["fee_code"] = fee_code(out["fee_code"], vocabulary)
    basis = out.get("basis")
    if out.get("rate") is not None:
        out["rate"] = rate(out["rate"], basis, quote)
    for key in ("min", "max"):
        d = _decimal(out.get(key))
        out[key] = _plain(d) if d else None
    if out.get("applies_to") is not None:
        out["applies_to"] = scope(out["applies_to"])
    out["per"] = out.get("per") or "incident"
    out["requires_proof"] = bool(out.get("requires_proof"))
    tiers = out.get("tiers") or None
    if tiers:
        tiers = [{"from_days": int(t["from_days"]), "to_days": None if t.get("to_days") is None else int(t["to_days"]),
                  "rate": rate(t["rate"], basis, quote)} for t in tiers]
    out["tiers"] = tiers
    return {k: v for k, v in out.items() if v is not None}


_ONCE = {"per_po": "flat"}  # the engine prices both once per group of backup lines (allowed.py "Fee schedules")


def _priced_key(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k not in ("requires_proof", "per")}
    if out.get("basis") in _ONCE:
        out["basis"] = _ONCE[out["basis"]]
    return out


def priced_alike(a: dict, b: dict) -> bool:
    """Two readers' canonical fee_schedule params price the fee the same way. requires_proof is left out: the merge
    keeps it if either reader found it (a person then checks the backup), rather than disputing the whole fee. `per`
    is left out too: "per incident" vs "per invoice" names the same single charge (live, Claude and Gemini split on it
    for KeHE §6.4 while agreeing on 5% and the $65 minimum); agreed() then keeps the readers apart on it only where a
    minimum or maximum makes it change the price. basis "per_po"
    and "flat" are the same price: the engine charges both once per purchase order's lines (live, the readers split on
    Five Below's "$100 per Purchase Order administrative fee")."""
    return quote_check.readers_agree({"type": "fee_schedule", "params": _priced_key(a)},
                                     {"type": "fee_schedule", "params": _priced_key(b)})


def agreed(a: dict, b: dict) -> tuple[dict, dict]:
    """Two priced-alike params with the fields that don't price the fee made one, so the quote check's agreement test
    sees one term: requires_proof if either reader found it; Reader A's basis when one wrote per_po and the other flat;
    and Reader A's `per` when there is no minimum or maximum for it to group (with one, "per invoice" vs "per incident"
    changes the price, and the readers still disagree)."""
    proof = bool(a.get("requires_proof") or b.get("requires_proof"))
    a, b = {**a, "requires_proof": proof}, {**b, "requires_proof": proof}
    if a.get("basis") != b.get("basis") and a.get("basis") in _ONCE.keys() | _ONCE.values():
        b["basis"] = a.get("basis")
    if not any(p.get(k) for p in (a, b) for k in ("min", "max")):
        b.pop("per", None)
        if "per" in a:
            b["per"] = a["per"]
    return a, b
