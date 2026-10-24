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


def canonical(params: dict, quote: str, vocabulary: Iterable[str]) -> dict:
    """fee_schedule params in one form: the account's fee name, plain decimal rate / min / max (a minimum or maximum
    of 0 is none), per "incident" when unstated, requires_proof false when unstated, no empty tiers."""
    out = dict(params)
    if out.get("fee_code"):
        out["fee_code"] = fee_code(out["fee_code"], vocabulary)
    basis = out.get("basis")
    if out.get("rate") is not None:
        out["rate"] = rate(out["rate"], basis, quote)
    for key in ("min", "max"):
        d = _decimal(out.get(key))
        out[key] = _plain(d) if d else None
    out["per"] = out.get("per") or "incident"
    out["requires_proof"] = bool(out.get("requires_proof"))
    tiers = out.get("tiers") or None
    if tiers:
        tiers = [{"from_days": int(t["from_days"]), "to_days": None if t.get("to_days") is None else int(t["to_days"]),
                  "rate": rate(t["rate"], basis, quote)} for t in tiers]
    out["tiers"] = tiers
    return {k: v for k, v in out.items() if v is not None}


def priced_alike(a: dict, b: dict) -> bool:
    """Two readers' canonical fee_schedule params price the fee the same way. requires_proof is left out: the merge
    keeps it if either reader found it (a person then checks the backup), rather than disputing the whole fee. `per`
    is left out too: "per incident" vs "per invoice" names the same single charge (live, Claude and Gemini split on it
    for KeHE §6.4 while agreeing on 5% and the $65 minimum), and it never changes one charge's amount."""
    def key(p: dict) -> dict:
        return {k: v for k, v in p.items() if k not in ("requires_proof", "per")}
    return quote_check.readers_agree({"type": "fee_schedule", "params": key(a)}, {"type": "fee_schedule", "params": key(b)})
