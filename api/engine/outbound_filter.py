"""Outbound filter (code) for every message the Negotiator sends to Northmart (docs/design.md, Agents > Negotiator).

A message passes only if:
1. every quoted passage ("..." or curly quotes) is part of a verified term's exact quote or a finding's text,
2. every dollar figure outside those quotes equals an allowed amount (engine numbers, finding values,
   verified term params), and
3. outside those quotes it makes no promise, discount or deadline, unless that exact phrase is one the owner's
   policy set (`allowed_phrases`).

The caller retries the Negotiator once with the violations; a second failure holds the message for the owner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Mapping

from api.engine.quote_check import normalize, param_numbers

# $1,540 · $ 1540.00 · USD 1,540 · 1,540 dollars · 1540 USD
_AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_DOLLARS = re.compile(
    rf"\$\s?(?P<a>{_AMOUNT})|\bUSD\s?(?P<b>{_AMOUNT})|(?P<c>{_AMOUNT})\s?(?:dollars?|USD)\b",
    re.IGNORECASE,
)
# Straight or curly double quotes; at least two words inside, so a lone "quoted" word reads as emphasis.
_QUOTED = re.compile(r"[\"“”](?P<q>[^\"“”]+?)[\"“”]")

_DAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_MONTHS = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
           r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_WHEN = rf"(?:{_DAYS}|{_MONTHS}\b|\d{{1,2}}/\d{{1,2}}|\d{{4}}-\d{{2}}-\d{{2}}|tomorrow|today|tonight|eod|cob|end of)"

COMMITMENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "promise": (
        r"\bpromis(?:e|es|ed|ing)\b",
        r"\bguarantee",
        r"\bwe (?:will|shall|can) (?:pay|refund|credit|reimburse|accept|honou?r|cover|waive|drop|absorb)\b",
        r"\bwe'll (?:pay|refund|credit|reimburse|accept|honou?r|cover|waive|drop|absorb)\b",
        r"\b(?:i|we) commit\b",
        r"\bin exchange for\b",
        r"\bgoing forward we\b",
    ),
    "discount": (
        r"\bdiscount",
        r"\brebate",
        r"\bwaiv(?:e|ed|er|ing)\b",
        r"\bwrite[- ]?off\b",
        r"\bforgiv(?:e|en|eness)\b",
        r"\bgoodwill\b",
        r"\bsplit the difference\b",
        r"\bsettle (?:for|at)\b",
        r"\bmeet (?:you )?(?:in the middle|halfway)\b",
        r"\d+(?:\.\d+)?\s?%\s*off\b",
        r"\bpercent off\b",
    ),
    "deadline": (
        r"\bdeadline",
        r"\bno later than\b",
        r"\bwithin \d+ (?:business |calendar |working )?(?:days?|hours?|weeks?)\b",
        rf"\bby (?:the )?{_WHEN}",
        rf"\bbefore (?:the )?{_WHEN}",
        r"\bexpir(?:e|es|ed|y|ation)\b",
        r"\bor else\b",
        r"\bfinal notice\b",
        r"\bimmediately\b",
    ),
}
_COMPILED = {kind: tuple(re.compile(p, re.IGNORECASE) for p in pats) for kind, pats in COMMITMENT_PATTERNS.items()}


@dataclass(frozen=True)
class Violation:
    kind: str    # quote | amount | promise | discount | deadline
    text: str    # the offending text as written
    detail: str


@dataclass(frozen=True)
class FilterResult:
    ok: bool
    violations: tuple[Violation, ...] = ()

    def feedback(self) -> str:
        """One line per violation, to append to the Negotiator's retry prompt."""
        return "\n".join(f"- {v.kind}: {v.text!r} ({v.detail})" for v in self.violations)


@dataclass(frozen=True)
class OutboundContext:
    """What a message may say: built from the findings and verified terms behind it."""
    amounts: frozenset[Decimal] = frozenset()
    quotes: tuple[str, ...] = ()           # verified exact quotes and finding text, normalized
    allowed_phrases: tuple[str, ...] = ()  # policy-set commitments, normalized and casefolded

    @classmethod
    def build(
        cls,
        amounts: Iterable[Any] = (),
        terms: Iterable[Mapping[str, Any]] = (),
        findings: Iterable[str] = (),
        allowed_phrases: Iterable[str] = (),
    ) -> "OutboundContext":
        """`amounts`: engine numbers and data values (taken, allowed, delta, disputed...). `terms`: verified
        terms only (exact_quote + params; their params numbers become allowed amounts). `findings`: finding text."""
        nums = {n for a in amounts for n in param_numbers(a)}
        quotes: list[str] = []
        for t in terms:
            nums.update(param_numbers(t.get("params")))
            if t.get("exact_quote"):
                quotes.append(normalize(t["exact_quote"]))
        quotes.extend(normalize(f) for f in findings if f)
        return cls(
            amounts=frozenset(n.normalize() for n in nums),
            quotes=tuple(quotes),
            allowed_phrases=tuple(normalize(p).casefold() for p in allowed_phrases if p.strip()),
        )


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    """Replace spans with spaces so later checks skip them but offsets stay put."""
    chars = list(text)
    for s, e in spans:
        chars[s:e] = " " * (e - s)
    return "".join(chars)


def check_message(text: str, ctx: OutboundContext) -> FilterResult:
    violations: list[Violation] = []

    # 1. Quoted passages must come from a verified term or a finding. Checked passages are blanked out
    #    so the figures and wording inside a real clause don't trip checks 2 and 3.
    quoted_spans: list[tuple[int, int]] = []
    for m in _QUOTED.finditer(text):
        inner = normalize(m.group("q")).strip(" .,;:")
        if len(inner.split()) < 2:
            continue
        quoted_spans.append(m.span())
        if not any(inner in q for q in ctx.quotes):
            violations.append(Violation("quote", m.group("q"), "not in any verified term or finding"))
    rest = _blank(text, quoted_spans)

    # Policy-set phrases are exempt from check 3 (they may contain a deadline the owner chose).
    folded = rest.casefold()
    exempt: list[tuple[int, int]] = []
    for phrase in ctx.allowed_phrases:
        for pm in re.finditer(r"\s+".join(re.escape(w) for w in phrase.split()), folded):
            exempt.append(pm.span())

    # 2. Dollar figures.
    for m in _DOLLARS.finditer(rest):
        raw = m.group("a") or m.group("b") or m.group("c")
        value = Decimal(raw.replace(",", "")).normalize()
        if value not in ctx.amounts:
            violations.append(Violation("amount", m.group().strip(), "not an engine number, data value or verified term"))

    # 3. Promises, discounts, deadlines.
    rest = _blank(rest, exempt)
    for kind, patterns in _COMPILED.items():
        for p in patterns:
            for m in p.finditer(rest):
                violations.append(Violation(kind, m.group(), f"no {kind} unless the owner's policy set it"))

    return FilterResult(not violations, tuple(violations))


__all__ = ["COMMITMENT_PATTERNS", "Violation", "FilterResult", "OutboundContext", "check_message"]
