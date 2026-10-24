"""Owner and controller SMS replies, parsed without AI.

The owner answers a discretion question (C6: "accept if notice is at least 14 days") and the answer becomes a
saved rule; UNDO cancels it; "accept" or "dispute" alone settles only this charge. The controller answers an
approval ("yes", or "no" plus a note). Anything else is unclear and gets the question again, never a guess.

The design has Claude word the rule. This parser runs first; Claude is only needed for replies it calls
unclear, and whatever Claude returns should still be built through rule_from_reply so the shape stays fixed.
Replies are data: nothing in them can change the policy, the counterparty or the term type.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from api.contracts import Role, Rule, TermType
from api.engine import types as eng

Op = Literal[">=", ">", "<=", "<"]
Choice = Literal["accept", "dispute"]

MIN_DAYS, MAX_DAYS = 1, 90  # a notice threshold outside this is more likely a typo than a rule

REASK_TEXT = (
    "Sorry, I couldn't turn that into a rule. Reply like \"accept if notice is at least 14 days\", "
    "or ACCEPT or DISPUTE for this charge only."
)
CONTROLLER_REASK_TEXT = "Sorry, I didn't get that. Reply YES to approve, or NO with a note to hold it."


class _Parsed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OwnerReply(_Parsed):
    """kind="rule": decision applies when `fact op value` holds, else_decision when it doesn't.
    kind="once": decision settles this charge only, no rule saved. kind="undo": cancel the newest rule.
    kind="unclear": ask again with REASK_TEXT; reason says why (for the log, not the owner)."""

    kind: Literal["rule", "once", "undo", "unclear"]
    decision: Choice | None = None
    else_decision: Choice | None = None
    fact: str | None = None
    op: Op | None = None
    value: int | None = None
    reason: str = ""

    @property
    def condition(self) -> str | None:
        """The engine's condition string, e.g. "notice_days >= 14" (api/engine/rules.py parses it)."""
        if self.kind != "rule":
            return None
        return f"{self.fact} {self.op} {self.value}"


class ControllerReply(_Parsed):
    kind: Literal["approve", "refuse", "unclear"]
    note: str = ""


# ---------------------------------------------------------------- normalizing

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
}
_NUM_ALT = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
# "a", "an" and "one" only count before a unit ("a week"), so "accept this one if 14 days" has one number.
_WORD_NUM = re.compile(rf"\b(?:({_NUM_ALT})(?=[\s-]*(?:days?|weeks?)\b)|((?!a\b|an\b|one\b)(?:{_NUM_ALT})))\b")


def _norm(text: str) -> str:
    t = text.lower().replace("’", "'").replace("‘", "'").replace("≥", ">=").replace("≤", "<=")
    t = re.sub(r"\bdon't\b|\bdont\b", "do not", t)
    t = re.sub(r"\bwon't\b|\bwont\b", "will not", t)
    return re.sub(r"\s+", " ", t).strip()


def _words(t: str) -> list[str]:
    return re.findall(r"[a-z0-9#']+", t)


_ACCEPT = r"accept|approve|allow|pay|ok|okay|fine"
_DISPUTE = r"dispute|reject|refuse|deny|fight|contest"
_ELSE = re.compile(rf"[,;.]?\s*\b(?:otherwise|else|if not|or)\b[ ,]*(?:i'll |we'll |just |then )?({_ACCEPT}|{_DISPUTE})\w*.*$")

_ONCE_ACCEPT = {"yes", "y", "yep", "yeah", "sure", "ok", "okay", "accept", "accepted", "approve", "approved", "fine"}
_ONCE_DISPUTE = {"no", "n", "nope", "dispute", "disputed", "reject", "refuse", "contest"}
_FILLER = {"it", "this", "that", "one", "this one", "please", "pls", "go", "ahead", "thanks", "thx", "for", "now", "charge"}

_UNDO = re.compile(r"^(?:please )?(?:undo|cancel)(?: (?:that|it|this|rule|#?1|rule #?1|please|the rule))*$")

# One quantity: a number, an optional "+", and days or weeks. "14", "14d", "14+ days", "2 weeks", "a week".
_QTY = re.compile(r"(\d+)\s*(\+)?\s*(d|days?|w|wks?|weeks?)?\b(\+)?")
_UNIT_WEEKS = {"w", "wk", "wks", "week", "weeks"}

_OPS: list[tuple[re.Pattern[str], Op]] = [
    (re.compile(r">=|=>|\b(at least|no less than|not less than|minimum|min|or more|or longer|and up)\b"), ">="),
    (re.compile(r"<=|=<|\b(at most|no more than|not more than|or less|or fewer|or under|max|maximum)\b"), "<="),
    (re.compile(r">|\b(more than|over|greater than|longer than|above|beyond)\b"), ">"),
    (re.compile(r"<|\b(less than|fewer than|under|below|shorter than)\b"), "<"),
]
_INVERT: dict[Op, Op] = {">=": "<", "<": ">=", ">": "<=", "<=": ">"}
_UNSUPPORTED = re.compile(r"[$%]|\b(hours?|hrs?|months?|years?|exactly|between|cents?|dollars?|bucks)\b")
_NEGATION = re.compile(r"\b(not|never|no)\b")
_NEGATED_OPS = re.compile(r"\b(no|not) (less|more|fewer) than\b")


# ---------------------------------------------------------------- owner

def parse_owner_reply(text: str, fact: str = "notice_days") -> OwnerReply:
    """Turn the owner's answer to a discretion question into a rule, a one-off decision, UNDO, or unclear.
    `fact` is what the number measures; display-fee questions use notice_days."""
    t = _norm(text)
    if not t:
        return OwnerReply(kind="unclear", reason="empty reply")
    bare = " ".join(_words(t))
    if _UNDO.match(bare):
        return OwnerReply(kind="undo")

    once = _one_off(bare)
    if once:
        return OwnerReply(kind="once", decision=once)

    if _UNSUPPORTED.search(t):
        return OwnerReply(kind="unclear", reason="mentions money, a percent or a unit other than days or weeks")

    t = _WORD_NUM.sub(lambda m: str(_NUMBER_WORDS[m.group(1) or m.group(2)]), t)
    qtys = list(_QTY.finditer(t))
    if not qtys:
        return OwnerReply(kind="unclear", reason="no notice period")
    if len(qtys) > 1:
        return OwnerReply(kind="unclear", reason="more than one number")
    q = qtys[0]
    days = int(q.group(1)) * (7 if (q.group(3) or "") in _UNIT_WEEKS else 1)
    if not MIN_DAYS <= days <= MAX_DAYS:
        return OwnerReply(kind="unclear", reason=f"{days} days is outside {MIN_DAYS}-{MAX_DAYS}")

    # Split off "otherwise dispute" / "or accept" so the main clause and the else branch are read separately.
    else_word: Choice | None = None
    m = _ELSE.search(t)
    if m:
        else_word = _choice(m.group(1))
        tail, t = t[m.start():], t[: m.start()].strip()
        if _choice_words(tail) - {else_word}:
            return OwnerReply(kind="unclear", reason="the else branch names both decisions")

    main_words = _choice_words(t)
    if len(main_words) > 1:
        return OwnerReply(kind="unclear", reason="names both accept and dispute without an otherwise")
    if _NEGATION.search(_NEGATED_OPS.sub("", t)):
        return OwnerReply(kind="unclear", reason="negation; ask instead of guessing which way it points")

    decision: Choice
    if main_words:
        decision = next(iter(main_words))
    elif else_word:
        decision = "dispute" if else_word == "accept" else "accept"
    else:
        decision = "accept"  # "14" or "two weeks": the notice it takes to accept
    if else_word == decision:
        return OwnerReply(kind="unclear", reason="same decision on both sides")
    if re.search(r"\bunless\b", t):
        if else_word:
            return OwnerReply(kind="unclear", reason="unless plus otherwise")
        decision = "dispute" if decision == "accept" else "accept"  # "dispute unless 14 days" = accept if 14+
    else_decision: Choice = "dispute" if decision == "accept" else "accept"

    op = _op(t, q)
    # Store every rule as "accept when ...", the way Rule #1 reads on the card.
    if decision == "dispute":
        op, decision, else_decision = _INVERT[op], "accept", "dispute"
    if op in ("<", "<="):
        return OwnerReply(kind="unclear", reason="would accept short notice and dispute long notice")
    return OwnerReply(kind="rule", decision=decision, else_decision=else_decision, fact=fact, op=op, value=days)


def _one_off(bare: str) -> Choice | None:
    """"accept", "yes", "no, dispute", "accept this one please": a decision for this charge with no rule."""
    core = [w for w in bare.split() if w not in _FILLER]
    if core and all(w in _ONCE_ACCEPT for w in core):
        return "accept"
    if core and all(w in _ONCE_DISPUTE for w in core):
        return "dispute"
    return None


def _choice(word: str) -> Choice:
    return "dispute" if re.match(rf"({_DISPUTE})", word) else "accept"


def _choice_words(t: str) -> set[Choice]:
    found: set[Choice] = set()
    if re.search(rf"\b({_ACCEPT})(?:s|d|ed|ing)?\b", t):
        found.add("accept")
    if re.search(rf"\b({_DISPUTE})(?:s|d|ed|ing)?\b", t):
        found.add("dispute")
    return found


def _op(t: str, q: re.Match[str]) -> Op:
    if q.group(2) or q.group(4):
        return ">="
    around = t[max(0, q.start() - 24): q.end() + 24]
    for pattern, op in _OPS:
        if pattern.search(around):
            return op
    return ">="


# ---------------------------------------------------------------- rule shapes and texts

_OP_WORDS: dict[Op, str] = {">=": "at least {n}", ">": "more than {n}", "<=": "at most {n}", "<": "fewer than {n}"}
_OP_SHORT: dict[Op, str] = {">=": "{n}+", ">": "more than {n}", "<=": "{n} or fewer", "<": "under {n}"}


def rule_from_reply(
    reply: OwnerReply,
    *,
    rule_id: str,
    pattern_text: str,
    term_type: TermType,
    counterparty: str,
    approver: str,
    learned_at: datetime,
    source_question_id: str | None,
    subject: str = "display fees",
    approver_role: Role = "owner",
) -> Rule:
    """The contracts.Rule for a kind="rule" reply. Everything but the condition and decisions comes from the
    question's context, never from the reply text."""
    if reply.kind != "rule":
        raise ValueError(f"not a rule reply: {reply.kind}")
    n = rule_id.rsplit("-", 1)[-1]
    span = _OP_WORDS[reply.op].format(n=reply.value)
    return Rule(
        id=rule_id,
        label=f"Rule #{n}",
        pattern_text=pattern_text,
        term_type=term_type,
        counterparty=counterparty,
        condition=reply.condition,
        decision=reply.decision,
        else_decision=reply.else_decision,
        summary=f"{reply.decision.capitalize()} {counterparty} {subject} with {span} days' notice; "
        f"otherwise {reply.else_decision}.",
        approver=approver,
        approver_role=approver_role,
        learned_at=learned_at,
        source_question_id=source_question_id,
        status="active",
    )


def to_engine_rule(rule: Rule) -> eng.Rule:
    """contracts.Rule -> the engine's Rule, so api/engine/rules.evaluate can decide with it.
    Lives here until api/adapters.py has one (Devank's call)."""
    return eng.Rule(
        id=rule.id, pattern_text=rule.pattern_text, term_type=eng.TermType(rule.term_type),
        counterparty=rule.counterparty, condition=rule.condition, decision=eng.DecisionKind(rule.decision),
        else_decision=eng.DecisionKind(rule.else_decision), approver=rule.approver,
        learned_at=rule.learned_at.date(), source_question_id=rule.source_question_id or "", status=rule.status,
    )


def confirmation_text(reply: OwnerReply, subject: str = "display fees") -> str:
    """The SMS echoed back after a rule is saved: "Saved: accept display fees with 14+ days' notice. ..." """
    if reply.kind != "rule":
        raise ValueError(f"not a rule reply: {reply.kind}")
    span = _OP_SHORT[reply.op].format(n=reply.value)
    return f"Saved: {reply.decision} {subject} with {span} days' notice. Reply UNDO to cancel."


def undo_rule(rules: list[Rule], source_question_id: str | None = None) -> Rule | None:
    """The newest active rule (from that question, if given), marked undone; None if there's nothing to undo."""
    live = [r for r in rules if r.status == "active" and (source_question_id is None or r.source_question_id == source_question_id)]
    if not live:
        return None
    newest = max(live, key=lambda r: r.learned_at)
    return newest.model_copy(update={"status": "undone"})


def undo_text(rule: Rule | None) -> str:
    if rule is None:
        return "There's no saved rule to undo."
    return f"Undone: {rule.label} is cancelled. I'll ask you next time."


def once_text(reply: OwnerReply, charge_id: str | None) -> str:
    what = f" {charge_id}" if charge_id else " this charge"
    verb = "accept" if reply.decision == "accept" else "dispute"
    return f"OK, I'll {verb}{what}. I didn't save a rule, so I'll ask again next time."


# ---------------------------------------------------------------- controller

_APPROVE = {"yes", "y", "yep", "yeah", "approve", "approved", "ok", "okay", "go", "confirm", "confirmed", "sure", "post"}
_REFUSE = {"no", "n", "nope", "refuse", "refused", "reject", "rejected", "deny", "denied", "hold", "wait", "stop"}


def parse_controller_reply(text: str) -> ControllerReply:
    """YES approves with no conditions; NO (or HOLD, REFUSE) refuses and keeps the rest as the note shown on the
    card. A yes with extra words could be a condition ("yes but only 2 lines"), so it counts as unclear."""
    t = _norm(text)
    words = _words(t)
    if not words:
        return ControllerReply(kind="unclear")
    first = words[0]
    if first in _REFUSE:
        note = re.sub(rf"^\W*{re.escape(first)}\b[\s,.:;!-]*", "", text.strip(), flags=re.IGNORECASE).strip()
        return ControllerReply(kind="refuse", note=note)
    if first in _APPROVE and all(w in _APPROVE or w in _FILLER for w in words):
        return ControllerReply(kind="approve")
    return ControllerReply(kind="unclear")
