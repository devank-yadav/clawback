"""Code check after the Deal Readers (docs/design.md, Agents > Deal Reader).

A term reaches the math engine only if:
1. its exact_quote is found in the source text (whitespace and hyphen/dash variants normalized),
2. every number in its params appears in that quote, and
3. both readers (Claude and Gemini) produced the same type and params.

Quote or number check fails -> "rejected". Readers disagree (or only one found the term) -> "disputed".
Both pass -> "verified". These are the `terms.status` values in the data model.

Terms are plain mappings (dicts, or a Pydantic model's .model_dump()) with keys
type, params, exact_quote and optionally char_start / char_end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

VERIFIED = "verified"
REJECTED = "rejected"
DISPUTED = "disputed"

# Hyphen and dash variants (and table cell marks, below) all count as the same separator as a space; the soft hyphen
# is dropped.
_DASHES = "-‐‑‒–—―−﹘﹣－"
_QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'",
           "“": '"', "”": '"', "„": '"', "‟": '"'}
_SOFT_HYPHEN = "­"
# Contracts converted from SEC HTML join table cells with " | " and keep the filing's bullets, so a quote that runs
# across cells ("Incorrect carton marking 3% of cost up to $750") or leaves a bullet out is still the same words.
_CELL_MARKS = "|·•●▪"
# The filing's own mojibake: UTF-8 punctuation read as Latin-1 leaves an "Â" in front ("CompanyÂ’s", "Â“"). A reader
# quoting "Company's" quotes the same word, so that "Â" is dropped when a quote mark, dash or space follows it.
_MOJIBAKE = "Â"

# A number as written in a contract: 5,000 / 1.00 / $1,500 / 1500. Sign is ignored.
_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.,])\d+(?:\.\d+)?(?![\w])")
_NUMERIC_STRING = re.compile(r"^\s*[-+]?\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*$")


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized text plus, for each normalized char, its index in the original text."""
    out: list[str] = []
    index: list[int] = []
    pending_sep: int | None = None  # index of the first char of a separator run
    for i, ch in enumerate(text):
        if ch == _SOFT_HYPHEN:
            continue
        if ch == _MOJIBAKE and i + 1 < len(text) and (text[i + 1] in _QUOTES or text[i + 1] in _DASHES
                                                     or text[i + 1].isspace()):
            continue
        if ch.isspace() or ch in _DASHES or ch in _CELL_MARKS:
            if pending_sep is None:
                pending_sep = i
            continue
        if pending_sep is not None:
            if out:  # leading separators are dropped
                out.append(" ")
                index.append(pending_sep)
            pending_sep = None
        out.append(_QUOTES.get(ch, ch))
        index.append(i)
    return "".join(out), index


def normalize(text: str) -> str:
    """Collapse runs of whitespace, hyphens/dashes and table cell marks into one space; straighten curly quotes; drop
    the filing's "Â" mojibake; trim."""
    return _normalize_with_map(text)[0]


def find_quote(source: str, quote: str, near: int | None = None) -> tuple[int, int] | None:
    """Return (char_start, char_end) of the quote in the original source, or None if not found.

    If the quote occurs more than once, the occurrence starting closest to `near` (the reader's
    char_start) wins; otherwise the first one.
    """
    needle = normalize(quote)
    if not needle:
        return None
    hay, index = _normalize_with_map(source)
    starts = [m.start() for m in re.finditer(re.escape(needle), hay)]
    if not starts:
        return None
    if near is not None:
        starts.sort(key=lambda s: abs(index[s] - near))
    s = starts[0]
    e = s + len(needle) - 1
    return index[s], index[e] + 1


def numbers_in(text: str) -> list[Decimal]:
    """Every number written in digits in the text, as Decimal (commas removed, sign ignored)."""
    return [Decimal(m.group().replace(",", "")) for m in _NUMBER.finditer(text)]


def param_numbers(params: Any) -> list[Decimal]:
    """Every numeric value in params, recursing into dicts and lists.

    Numeric strings ("1.00", "5,000", "$1,500") count; dates and other strings do not; booleans do not.
    """
    found: list[Decimal] = []
    if isinstance(params, bool) or params is None:
        return found
    if isinstance(params, (int, float, Decimal)):
        found.append(abs(Decimal(str(params))))
    elif isinstance(params, str):
        m = _NUMERIC_STRING.match(params)
        if m:
            found.append(Decimal((m.group(1) + (m.group(2) or "")).replace(",", "")))
    elif isinstance(params, Mapping):
        for v in params.values():
            found.extend(param_numbers(v))
    elif isinstance(params, (list, tuple, set, frozenset)):
        for v in params:
            found.extend(param_numbers(v))
    return found


def missing_numbers(params: Any, quote: str) -> list[Decimal]:
    """Numbers in params that do not appear in the quote (compared by value, so 1 == 1.00)."""
    in_quote = set(numbers_in(quote))
    return [n for n in param_numbers(params) if n not in in_quote]


@dataclass(frozen=True)
class QuoteCheck:
    ok: bool
    char_start: int | None = None  # where the quote really is in the source
    char_end: int | None = None
    reasons: tuple[str, ...] = ()


def check_quote(source: str, term: Mapping[str, Any]) -> QuoteCheck:
    """Checks 1 and 2 for one reader's term."""
    quote = term.get("exact_quote") or ""
    span = find_quote(source, quote, near=term.get("char_start"))
    reasons: list[str] = []
    if span is None:
        reasons.append("quote not found in source")
    missing = missing_numbers(term.get("params"), quote)
    if missing:
        reasons.append("params numbers not in quote: " + ", ".join(str(n) for n in missing))
    if reasons:
        return QuoteCheck(False, None, None, tuple(reasons))
    return QuoteCheck(True, span[0], span[1])


def _canon(value: Any) -> Any:
    """Comparable form of a params value: numbers by value, strings case- and spacing-insensitive,
    lists order-insensitive."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        return ("n", Decimal(str(value)).normalize())
    if isinstance(value, str):
        if _NUMERIC_STRING.match(value):
            return ("n", param_numbers(value)[0].normalize())
        return ("s", normalize(value).casefold())
    if isinstance(value, Mapping):
        return ("m", tuple(sorted((str(k), _canon(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple, set, frozenset)):
        return ("l", tuple(sorted((_canon(v) for v in value), key=repr)))
    return ("o", repr(value))


def readers_agree(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Check 3: same type and same params."""
    return a.get("type") == b.get("type") and _canon(a.get("params") or {}) == _canon(b.get("params") or {})


@dataclass(frozen=True)
class TermVerdict:
    status: str  # verified | rejected | disputed
    char_start: int | None = None
    char_end: int | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _row_from_other_reader(source: str, a: Mapping[str, Any], b: Mapping[str, Any],
                           checks: list[QuoteCheck]) -> list[QuoteCheck]:
    """Two readers that agree on the params, where one quoted a fee table's row with its rate cell ("New Distribution
    Center | 10") and the other only the row's name ("New Distribution Center"): the shorter quote is found word for
    word inside the longer one's span, so the longer quote's numbers count for both. Nothing else is excused: the
    shorter quote must still be found, inside the other reader's verified span."""
    out = list(checks)
    for me, other, t in ((0, 1, a), (1, 0, b)):
        mine, theirs = checks[me], checks[other]
        if mine.ok or not theirs.ok or mine.reasons[0].startswith("quote not found"):
            continue
        span = find_quote(source, t.get("exact_quote") or "", near=theirs.char_start)
        if span and theirs.char_start <= span[0] and span[1] <= theirs.char_end:  # type: ignore[operator]
            out[me] = QuoteCheck(True, theirs.char_start, theirs.char_end)
    return out


def verify_term(source: str, a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> TermVerdict:
    """Merge one term from reader A (Claude) and reader B (Gemini) into a verdict.

    Pass None for a reader that did not return this term. Quote failures are checked first, so a
    term whose quote is invented is rejected even if the other reader disagrees.
    """
    present = [(name, t) for name, t in (("reader A", a), ("reader B", b)) if t is not None]
    if not present:
        return TermVerdict(REJECTED, reasons=("no reader returned the term",))
    checks = [check_quote(source, t) for _, t in present]
    if len(present) == 2 and readers_agree(a, b):  # type: ignore[arg-type]
        checks = _row_from_other_reader(source, a, b, checks)  # type: ignore[arg-type]
    reasons = [f"{name}: {r}" for (name, _), qc in zip(present, checks) for r in qc.reasons]
    if reasons:
        return TermVerdict(REJECTED, reasons=tuple(reasons))
    span = checks[0]
    if len(present) == 1:
        missing = "reader B" if b is None else "reader A"
        return TermVerdict(DISPUTED, span.char_start, span.char_end, (f"{missing} did not return the term",))
    if not readers_agree(a, b):  # type: ignore[arg-type]
        return TermVerdict(DISPUTED, span.char_start, span.char_end, ("readers disagree on type or params",))
    return TermVerdict(VERIFIED, span.char_start, span.char_end)


__all__ = [
    "VERIFIED", "REJECTED", "DISPUTED", "normalize", "find_quote", "numbers_in", "param_numbers",
    "missing_numbers", "QuoteCheck", "check_quote", "readers_agree", "TermVerdict", "verify_term",
]
