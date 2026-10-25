"""Email writer (Claude): drafts the dispute email from a dispute's lines (Phase E).

Strict JSON (opening, one paragraph per line, closing). Code builds the subject and the greeting and signature, and
checks the draft: one paragraph per line in order, no number that isn't in the dispute, and every figure and quote
through api/engine/outbound_filter.check_message. One retry with the problems; a draft that still fails is held for
the admin. When the call itself fails (no key, DEMO_MODE with no recording), the code template below writes the draft
from the same lines, so there is always something to review.

Agents never compute amounts: every figure is the dispute's own.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import anthropic

from api import accounts
from api.agents import claude, prompts
from api.agents.claude import Strict
from api.agents.investigator import invented_numbers
from api.contracts import Dispute, Term
from api.engine import outbound_filter, quote_check

SERVICE = "claude-email-writer"
LINE_DEADLINE = {"file_by", "days_left"}  # the brand's own deadline, not an argument to put in the email


class LLMParagraph(Strict):
    charge_id: str
    text: str


class LLMEmail(Strict):
    opening: str
    paragraphs: list[LLMParagraph]
    closing: str


@dataclass
class Draft:
    subject: str
    body: str
    written_by: str  # claude | template
    problems: list[str] = field(default_factory=list)  # non-empty: held for the admin

    @property
    def held(self) -> bool:
        return bool(self.problems)


def usd(amount) -> str:
    return f"${amount:,.2f}"


def subject(dispute: Dispute, account: accounts.Account) -> str:
    """The research's format: "Dispute: [Brand], [Check/Remittance #], [Deduction #], [Amount]"."""
    refs = ", ".join(ln.ref for ln in dispute.lines)
    rem = dispute.remittance_id or account.invoice.id
    return f"Dispute: {account.brand.name}, Remittance {rem}, Deductions {refs}, {usd(dispute.total)} ({dispute.id})"


def greeting(account: accounts.Account) -> str:
    return f"Hello {account.distributor.name} deductions team,"


def signature(account: accounts.Account, portal_url: str | None) -> str:
    owner = account.brand.owner
    lines = ["The dispute packet with every clause, data row and calculation is attached."]
    if portal_url:
        lines.append(f"You can also reply on the dispute page: {portal_url}")
    lines += ["", "Thank you,", owner.name, account.brand.name]
    if owner.email:
        lines.append(owner.email)
    return "\n".join(lines)


def payload(dispute: Dispute, account: accounts.Account) -> str:
    return json.dumps({"dispute": {"id": dispute.id, "remittance": dispute.remittance_id, "invoice": account.invoice.id,
                                   "total": str(dispute.total),
                                   "lines": [ln.model_dump(mode="json", exclude=LINE_DEADLINE) for ln in dispute.lines]}},
                      indent=1, default=str)


def context(dispute: Dispute, terms: Sequence[Term]) -> outbound_filter.OutboundContext:
    """What the email may say: the dispute's own amounts and every number in its lines, its quotes and verified terms."""
    amounts = [dispute.total, *(ln.amount for ln in dispute.lines)]
    for ln in dispute.lines:
        amounts += quote_check.numbers_in(f"{ln.math} {ln.reason}")
    return outbound_filter.OutboundContext.build(
        amounts=amounts, terms=[t.model_dump(mode="json") for t in terms if t.status == "verified"],
        findings=[ln.reason for ln in dispute.lines] + [ln.quote for ln in dispute.lines if ln.quote])


def check_body(body: str, dispute: Dispute, terms: Sequence[Term], account: accounts.Account) -> list[str]:
    """Problems with a body about to go out (the AI's, the template's or the admin's edit); [] means it may go."""
    problems = []
    result = outbound_filter.check_message(body, context(dispute, terms))
    if not result.ok:
        problems.append("outbound filter: " + result.feedback())
    return problems


def assemble(dispute: Dispute, account: accounts.Account, opening: str, paragraphs: list[str], closing: str,
             portal_url: str | None) -> str:
    return "\n\n".join([greeting(account), opening.strip(), *(p.strip() for p in paragraphs), closing.strip(),
                        signature(account, portal_url)])


def template(dispute: Dispute, account: accounts.Account, portal_url: str | None = None) -> str:
    """The draft written by code from the dispute lines alone: every figure is the line's, every quote the clause's."""
    opening = (f"{account.brand.name} is disputing deductions taken on remittance {dispute.remittance_id or account.invoice.id} "
               f"for invoice {account.invoice.id}. Dispute {dispute.id} covers {len(dispute.lines)} "
               f"line{'s' if len(dispute.lines) != 1 else ''} totaling {usd(dispute.total)}.")
    paras = []
    for ln in dispute.lines:
        clause = f" The deal ({ln.clause_ref}) says: \"{ln.quote}\"" if ln.quote and ln.clause_ref else (
            f" The deal says: \"{ln.quote}\"" if ln.quote else "")
        paras.append(f"{ln.ref} ({ln.charge_id}), {usd(ln.amount)} disputed. {ln.reason.rstrip('.')}.{clause} "
                     f"Calculation: {ln.math}".rstrip())
    closing = ("Please review the attached packet and reverse the disputed amounts. If you see any line differently, "
               "reply with the signed document that supports it.")
    return assemble(dispute, account, opening, paras, closing, portal_url)


def draft(dispute: Dispute, terms: Sequence[Term], account: accounts.Account,
          client: anthropic.Anthropic | None = None, portal_url: str | None = None) -> Draft:
    user = payload(dispute, account)
    order = [ln.charge_id for ln in dispute.lines]

    def check(raw: dict) -> str:
        out = LLMEmail.model_validate(raw)
        problems = []
        if [p.charge_id for p in out.paragraphs] != order:
            problems.append(f"write exactly one paragraph per line, in this order: {order}")
        text = "\n".join([out.opening, *(p.text for p in out.paragraphs), out.closing])
        if invented := invented_numbers(text, user):
            problems.append(f"numbers that aren't in the dispute: {[str(n) for n in invented]}")
        body = assemble(dispute, account, out.opening, [p.text for p in out.paragraphs], out.closing, portal_url)
        problems += check_body(body, dispute, terms, account)
        if problems:
            raise ValueError("; ".join(problems))
        return body

    ans = claude.ask(SERVICE, prompts.render("email_writer", account), user, LLMEmail, check, client,
                     dispute_id=dispute.id)
    subj = subject(dispute, account)
    if ans.value:
        return Draft(subj, ans.value, "claude")
    body = template(dispute, account, portal_url)
    call_failed = bool(ans.errors) and "no fixture at" in ans.errors[-1]  # replay.OutsideCallFailed: no answer at all
    if ans.errors and not call_failed:  # the model answered twice and both failed the checks: held for the admin
        return Draft(subj, body, "template", problems=[f"the email writer's draft failed its checks twice: "
                                                       f"{ans.errors[-1][:300]}"])
    return Draft(subj, body, "template", problems=check_body(body, dispute, terms, account))
