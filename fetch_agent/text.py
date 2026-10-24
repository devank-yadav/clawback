"""Everything the assistant says, in plain words. Pure functions of the API's answers.

Amounts are the API's numbers, formatted as they come ($4,120, $12.50); nothing here adds, subtracts or splits
them. Every name is fictional: Peak Bar Co., Northmart, Dana (owner, the one person who approves).
"""

from __future__ import annotations

from decimal import Decimal

from fetch_agent.client import ClawbackError
from fetch_agent.models import AnswerResponse, Approval, Dispute, Question, Summary

BRAND, DISTRIBUTOR = "Peak Bar Co.", "Northmart"

HOW_TO_ANSWER = ("Reply here with a rule like \"accept if notice is at least 14 days\", "
                 "or ACCEPT or DISPUTE for this charge only.")
INTRO = (f"I'm the Clawback Assistant for {BRAND}. Clawback checks every charge {DISTRIBUTOR} takes out of your "
         "payment against your signed promo deal. Ask me \"What did Northmart take this month?\", or answer "
         "Clawback's question here. I can't approve or move money.")
NOT_OWNER = ("Only Dana, the owner, can answer Clawback's questions here. I can still tell you what Northmart took: "
             "ask \"What did Northmart take this month?\"")
NO_UNDO_TARGET = "There's no answer from this chat to undo. Reply UNDO to Clawback's text, or use the Clawback inbox."
OOPS = "Something went wrong on my side. Try again in a minute."

_DISPUTE_STATUS = {"draft": "not filed yet", "filed": "filed, waiting on Northmart", "answered": "Northmart replied"}


def money(v: Decimal) -> str:
    """$4,120 for whole dollars, $12.50 otherwise."""
    return f"${v:,.0f}" if v == v.to_integral_value() else f"${v:,.2f}"


def _charges(n: int) -> str:
    return f"{n} charge" if n == 1 else f"{n} charges"


def summary_text(s: Summary, intro: bool = False) -> str:
    parts = [INTRO] if intro else []
    parts += [_totals(s), _disputes(s.open_disputes), _question_or_nothing(s.pending_question)]
    parts += [_approval(a) for a in s.pending_approvals]
    return "\n\n".join(p for p in parts if p)


def _totals(s: Summary) -> str:
    t = s.totals
    lines = [f"{DISTRIBUTOR} took **{money(t.taken)}** out of {BRAND}'s latest payment.",
             f"- **{money(t.disputed)}** disputed: Northmart took too much, and Clawback is asking for it back",
             f"- **{money(t.accepted)}** accepted: fair under the deal"]
    if t.waiting:
        lines.append(f"- **{money(t.waiting)}** waiting on " + ("your answer" if s.pending_question else "a person"))
    if t.undecided:
        lines.append(f"- **{money(t.undecided)}** still being checked")
    if t.skipped:
        lines.append(f"- {_charges(t.skipped)} couldn't be checked against the deal")
    if s.run_id is None:
        lines.append("\n_No live payment yet: these are the numbers from Clawback's recorded demo run._")
    return "\n".join(lines)


def _disputes(disputes: list[Dispute]) -> str:
    if not disputes:
        return "No open disputes."
    blocks = []
    for d in disputes:
        status = _DISPUTE_STATUS.get(d.status, d.status)
        head = f"**Open dispute {d.id}** with {d.counterparty}: {money(d.total)} over {_charges(len(d.lines))} ({status})."
        blocks.append("\n".join([head] + [f"- {ln.charge_id}, {money(ln.amount)}: {ln.reason}" for ln in d.lines]))
    return "\n\n".join(blocks)


def question_text(q: Question) -> str:
    return f"**Clawback has a question for you ({q.id}):**\n> {q.text}\n\n{HOW_TO_ANSWER}"


def _question_or_nothing(q: Question | None) -> str:
    return question_text(q) if q else "Nothing is waiting on your answer."


def _approval(a: Approval) -> str:
    """Approvals are shown, never given: people approve in the Clawback inbox or by text."""
    if a.kind == "credit_memo":
        return (f"**Waiting on you:** approve putting the {money(a.amount)} Clawback accepted "
                f"({_charges(len(a.lines))}) into QuickBooks. Answer by text or in the Clawback inbox; this chat "
                "can't move money.")
    if a.kind == "dispute_over_limit":
        return (f"**Waiting on you:** a {money(a.amount)} dispute needs your OK before Clawback files it. "
                "Approve it in the Clawback inbox; this chat can't approve money.")
    return f"**Waiting on you:** {a.text} This chat can't approve money."


def _now(s: Summary | None) -> str:
    """The meters after an answer, from a fresh GET /summary (left out if that call failed)."""
    if s is None:
        return ""
    t = s.totals
    line = f"Now: **{money(t.disputed)}** disputed, **{money(t.accepted)}** accepted, **{money(t.waiting)}** waiting."
    return "\n\n".join([line] + [_approval(a) for a in s.pending_approvals])


def _join(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------- answers

def answered_text(resp: AnswerResponse, q: Question, after: Summary | None) -> str:
    """What happened to Dana's answer. The API returns a rule only when it saved one; with no rule, the fresh
    summary tells a one-off decision (question gone) from a reply it couldn't read (same question still open)."""
    if resp.rule and resp.rule.status == "active":
        return _join(f"Saved **{resp.rule.label}**: {resp.rule.summary} Clawback will apply it next time without "
                     "asking. Reply UNDO to cancel it.", _now(after))
    if after and after.pending_question and after.pending_question.id == q.id:
        return ("Clawback couldn't turn that into a rule, so the question is still open. Reply like \"accept if "
                "notice is at least 14 days\", or ACCEPT or DISPUTE for this charge only.")
    what = q.charge_id or "this charge"
    return _join(f"Done. Your answer settles {what} this time only. No rule was saved, so Clawback will ask again "
                 "next time.", _now(after))


def undo_text(resp: AnswerResponse) -> str:
    if resp.rule and resp.rule.status == "undone":
        return (f"Cancelled **{resp.rule.label}** ({resp.rule.summary}) Next time Clawback will ask you again. "
                "Charges it already decided stay as they are.")
    return "There's no saved rule to undo."


def show_first_text(q: Question) -> str:
    return _join("Here's the question Clawback is asking. Send your answer again once you've read it:", question_text(q))


def replaced_text(new_q: Question | None) -> str:
    head = "That question was replaced: a newer run of the same payment asked again, so your answer wasn't used."
    if new_q is None:
        return _join(head, "Nothing is waiting on your answer now.")
    return _join(head, question_text(new_q))


def nothing_to_answer_text(s: Summary) -> str:
    return _join("Nothing is waiting on your answer right now.", _now(s))


def gone_text() -> str:
    return "That question isn't open any more, so your answer wasn't used. Ask \"what's waiting on me?\" to check."


# ---------------------------------------------------------------- errors

def error_text(e: ClawbackError) -> str:
    if e.status is None:
        return "I couldn't reach Clawback just now. Try again in a minute."
    if e.status in (401, 403):
        return "Clawback turned down my read-only key, so I can't show the numbers right now."
    if e.status == 503:
        return "Clawback isn't set up to share its numbers yet."
    if e.status == 404:
        return "I couldn't find Clawback at the address I was given."
    return f"Clawback answered with an error ({e.status}). Try again in a minute."
