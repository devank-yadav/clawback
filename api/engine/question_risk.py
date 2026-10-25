"""How much a question to the admin matters, like a flagged risk in a code review: a level, a kind, one sentence and
the details behind it. Plain code from the engine's numbers and the clause (no AI call), so recordings don't change.

Level, from the amount at stake (config/policy.yaml `question_risk`):
- high: at least high_usd ($1,000), or at least high_pct_of_payment (5%) of the payment;
- medium: at least medium_usd ($250);
- low: otherwise;
then raised one step (never past high) when any of these holds: the clause is discretionary and the deal gives no
notice period in days; the dispute window has deadline_days (14) or fewer left; the two readers disagree.

Kind, the first rule that matches:
1. legal: the readers disagree on the deal's wording;
2. deadline: the dispute window has deadline_days or fewer left;
3. relationship: a fee the distributor may charge at its discretion (a fee_discretion term);
4. legal: any other discretion, notice or contract-term question;
5. financial: otherwise, the amount itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

POLICY = Path(__file__).resolve().parents[2] / "config" / "policy.yaml"
LEVELS = ("low", "medium", "high")
MAX_WORDS = 25


@dataclass(frozen=True)
class Thresholds:
    high_usd: Decimal = Decimal("1000")
    high_pct_of_payment: Decimal = Decimal("5")
    medium_usd: Decimal = Decimal("250")
    deadline_days: int = 14


def load_thresholds(path: Path = POLICY) -> Thresholds:
    raw = (yaml.safe_load(path.read_text()) or {}).get("question_risk") or {}
    d = Thresholds()
    return Thresholds(high_usd=Decimal(str(raw.get("high_usd", d.high_usd))),
                      high_pct_of_payment=Decimal(str(raw.get("high_pct_of_payment", d.high_pct_of_payment))),
                      medium_usd=Decimal(str(raw.get("medium_usd", d.medium_usd))),
                      deadline_days=int(raw.get("deadline_days", d.deadline_days)))


@dataclass(frozen=True)
class Facts:
    """What the question is about, from the engine and the clause."""

    amount: Decimal  # at stake: what was taken on the charge
    payment: Decimal | None  # the payment it was taken from
    what: str  # "display fee"
    distributor: str
    clause_ref: str | None = None  # "§5.4"
    quote: str | None = None
    term_type: str | None = None  # the clause's type: fee_discretion, promo_rate, ...
    discretionary: bool = False
    notice_period_days: int | None = None  # the deal's notice period, if it states one in days
    notice_date: date | None = None
    notice_days: int | None = None  # days of notice actually given
    days_left: int | None = None  # in the dispute window
    file_by: date | None = None
    readers_disagree: bool = False
    disagreement: str | None = None
    rule_label: str | None = None  # "Rule #1": what the answer becomes
    discretion_words: tuple[str, ...] = ("at its discretion", "sole judgment", "reasonable", "may")


@dataclass(frozen=True)
class Risk:
    level: str
    kind: str
    reason: str
    details: list[tuple[str, str]] = field(default_factory=list)
    raised_by: tuple[str, ...] = ()  # why the level went up a step


def day(d: date, year: bool = True) -> str:
    """"Mar 11, 2026" (or "Mar 11"), the same on every platform."""
    return f"{d:%b} {d.day}, {d.year}" if year else f"{d:%b} {d.day}"


def usd(x: Decimal) -> str:
    return f"${x:,.0f}" if x == x.to_integral_value() else f"${x:,.2f}"


def base_level(f: Facts, t: Thresholds) -> str:
    pct = (f.amount * 100 / f.payment) if f.payment else Decimal(0)
    if f.amount >= t.high_usd or pct >= t.high_pct_of_payment:
        return "high"
    return "medium" if f.amount >= t.medium_usd else "low"


def raisers(f: Facts, t: Thresholds) -> tuple[str, ...]:
    why = []
    if f.discretionary and f.notice_period_days is None:
        why.append("discretionary clause with no notice period")
    if f.days_left is not None and f.days_left <= t.deadline_days:
        why.append(f"dispute window closes in {f.days_left} days")
    if f.readers_disagree:
        why.append("the two readers disagree")
    return tuple(why)


def level(f: Facts, t: Thresholds) -> tuple[str, tuple[str, ...]]:
    lv, why = base_level(f, t), raisers(f, t)
    if why:
        lv = LEVELS[min(LEVELS.index(lv) + 1, len(LEVELS) - 1)]
    return lv, why


def kind(f: Facts, t: Thresholds) -> str:
    if f.readers_disagree:
        return "legal"
    if f.days_left is not None and f.days_left <= t.deadline_days:
        return "deadline"
    if f.term_type == "fee_discretion":
        return "relationship"
    if f.discretionary or f.term_type in ("notice_period", "amendment", "date_range", "product_scope", "unit_cap"):
        return "legal"
    return "financial"


def _phrase(f: Facts) -> str | None:
    """The discretion words the clause turns on, as written ("at its discretion")."""
    for w in f.discretion_words:
        if f.quote and (m := re.search(rf"\b{re.escape(w)}\b", f.quote, re.IGNORECASE)):
            return m.group(0)
    return None


def _fit(*parts: str) -> str:
    """The sentence, dropping trailing parts until it is MAX_WORDS words or fewer."""
    keep = [p for p in parts if p]
    while len(" ".join(keep).split()) > MAX_WORDS and len(keep) > 1:
        keep.pop()
    text = " ".join(keep).strip().rstrip(";,")
    words = text.split()
    text = " ".join(words[:MAX_WORDS])
    return text if text.endswith(".") else text.rstrip(".,;") + "."


def reason(f: Facts, k: str) -> str:
    amt, ref = usd(f.amount), f.clause_ref or "the deal"
    rule = "your answer becomes a rule for every future fee." if f.rule_label or k == "relationship" else ""
    if k == "legal" and f.readers_disagree:
        what = (f.term_type or "wording").replace("_", " ")
        return _fit(f"Clawback's two readers read {ref}'s {what} differently;", f"{amt} turns on your reading.")
    if k == "deadline":
        when = f" on {day(f.file_by, year=False)}" if f.file_by else ""
        return _fit(f"{amt} {f.what}: the dispute window closes in {f.days_left} days{when};", "decide before then.")
    phrase = _phrase(f)
    notice = " with written notice" if f.quote and "notice" in f.quote.lower() else ""
    if phrase:
        return _fit(f"{amt} {f.what} rests on {ref} '{phrase}'{notice};", rule or "the deal leaves it to judgment.")
    pct = f" ({f.amount * 100 / f.payment:.1f}% of the payment)" if f.payment else ""
    return _fit(f"{amt} {f.what}{pct} isn't settled by {ref};", rule or "your answer decides it.")


def details(f: Facts) -> list[tuple[str, str]]:
    out = []
    if f.clause_ref or f.quote:
        out.append(("Clause", " ".join(x for x in (f.clause_ref, f'"{f.quote}"' if f.quote else None) if x)))
    if f.notice_date:
        out.append(("Notice date", day(f.notice_date)))
    if f.notice_days is not None:
        out.append(("Days of notice", f"{f.notice_days} days"))
    if f.notice_period_days is not None:
        out.append(("Notice the deal requires", f"{f.notice_period_days} days"))
    out.append(("Amount", f"${f.amount:,.2f}" + (f" of a ${f.payment:,.2f} payment" if f.payment else "")))
    if f.days_left is not None:
        out.append(("Dispute window", f"{f.days_left} days left" + (f", file by {day(f.file_by)}" if f.file_by else "")))
    if f.readers_disagree and f.disagreement:
        out.append(("Readers disagree", f.disagreement))
    if f.rule_label:
        out.append(("What your answer does", f"Becomes {f.rule_label}: applied to every future {f.what} from "
                                             f"{f.distributor}, without asking again"))
    else:
        out.append(("What your answer does", "Settles this charge only"))
    return out


def assess(f: Facts, t: Thresholds | None = None) -> Risk:
    t = t or load_thresholds()
    lv, why = level(f, t)
    k = kind(f, t)
    return Risk(lv, k, reason(f, k), details(f), why)
