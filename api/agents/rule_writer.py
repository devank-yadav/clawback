"""Turn the owner's free-text answer into a rule (docs/design.md, "Rules and matching").

Claude proposes fact / op / value / decisions; code builds the condition and checks it parses with
api/engine/rules.py. The rule is echoed back to the owner with an UNDO option.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

import anthropic

from api import accounts
from api.agents import claude, prompts
from api.agents.claude import Strict
from api.contracts import Question, Rule, Term
from api.engine.rules import parse_condition

SERVICE = "claude-rule-writer"
FACTS = ("notice_days", "amount")
Verdict = Literal["accept", "dispute", "ask"]


class LLMRule(Strict):
    understood: bool
    fact: Literal["notice_days", "amount"] | None
    op: Literal[">=", ">", "<=", "<", "=="] | None
    value: float | None
    decision: Verdict
    else_decision: Verdict
    summary: str


def write_rule(question: Question, answer: str, term: Term, counterparty: str, facts: dict, rule_number: int,
               approver: str, learned_at: datetime, client: anthropic.Anthropic | None = None,
               account: accounts.Account | str | None = None, rule_id: str | None = None) -> Rule | None:
    """None when the answer doesn't say what to do (the question stays open). The rule is labeled Rule #<rule_number>
    (its number among the account's rules); its id is rule_id, rule-<rule_number> by default."""
    user = json.dumps({"question": question.text, "owner_answer": answer,
                       "clause": {"type": term.type, "quote": term.exact_quote},
                       "facts": {f: facts.get(f) for f in FACTS}}, indent=1, default=str)

    def check(raw: dict) -> Rule | None:
        r = LLMRule.model_validate(raw)
        if not r.understood:
            return None
        if r.fact is None:  # applies always
            condition = "amount >= 0"
        elif r.op is None or r.value is None:
            raise ValueError("a rule with a fact needs op and value")
        else:
            condition = f"{r.fact} {r.op} {r.value:g}"
        parse_condition(condition)
        return Rule(id=rule_id or f"rule-{rule_number}", label=f"Rule #{rule_number}", pattern_text=term.exact_quote,
                    term_type=term.type, counterparty=counterparty, condition=condition, decision=r.decision,
                    else_decision=r.else_decision, summary=r.summary, approver=approver, approver_role="owner",
                    learned_at=learned_at, source_question_id=question.id, status="active")

    return claude.ask(SERVICE, prompts.render("rule_writer", account), user, LLMRule, check, client,
                      charge_id=question.charge_id).value


def echo(rule: Rule) -> str:
    """The confirmation text back to the owner."""
    return f"Saved: {rule.summary} Reply UNDO to cancel."
