"""What the assistant does with one chat message. No uagents here, so it runs and tests without the network.

classify() reads the message: a status question ("What did Northmart take this month?"), an answer to Clawback's
question ("accept if notice is at least 14 days", ACCEPT, DISPUTE, UNDO), or hello/help. Anything unsure is
treated as a status question: showing the numbers never changes anything, an answer does.

Answers go only to the question this chat last showed the sender. If the waiting question changed since (a newer
run asked again), the new one is shown first. Clawback's own parser decides what the answer means
(api/replies.py); this code only passes the text on and reports what came back.
"""

from __future__ import annotations

import re
from typing import Literal

from fetch_agent import text as say
from fetch_agent.client import ClawbackClient, ClawbackError
from fetch_agent.models import Summary

Intent = Literal["summary", "answer", "help"]

_HELP = {"help", "hi", "hello", "hey", "start", "menu", "what can you do", "who are you", "what are you"}
# Status questions can mention a decision word ("what will you dispute?"), so they're checked first.
_ASKING = re.compile(r"^(what|whats|what's|how|which|why|when|where|who|show|list|summary|status)\b")
_DECISION = re.compile(r"\b(accept|dispute|approve|reject|refuse|undo|cancel)\b")
_NOTICE = re.compile(r"\bnotice\b|\b\d+\s*\+?\s*(d|days?|w|wks?|weeks?)\b|\b(one|two|three|four|a)\s+weeks?\b")
_UNDO = {"undo", "cancel"}
_UNDO_FILLER = {"that", "it", "this", "the", "my", "last", "rule", "#1", "1", "please", "answer"}


def _norm(message: str) -> str:
    return re.sub(r"\s+", " ", message.lower().replace("’", "'")).strip().rstrip(".!")


def is_undo(message: str) -> bool:
    words = re.findall(r"[a-z0-9#]+", _norm(message))
    return bool(_UNDO & set(words)) and all(w in _UNDO | _UNDO_FILLER for w in words)


def classify(message: str) -> Intent:
    t = _norm(message)
    if not t or t.rstrip("?") in _HELP:
        return "help"
    if is_undo(t):
        return "answer"
    if t.endswith("?") or _ASKING.match(t):
        return "summary"
    if _DECISION.search(t) or _NOTICE.search(t):
        return "answer"
    return "summary"


class Memory:
    """Per sender: the question this chat last showed them, and the last one they answered (UNDO goes there)."""

    def __init__(self) -> None:
        self.shown: dict[str, str] = {}
        self.answered: dict[str, str] = {}


class Assistant:
    def __init__(self, client: ClawbackClient, owners: frozenset[str] = frozenset(), memory: Memory | None = None):
        self.client = client
        self.owners = owners  # agent addresses allowed to answer; empty means anyone who can chat with the agent
        self.memory = memory or Memory()

    def respond(self, sender: str, message: str) -> str:
        intent = classify(message)
        try:
            if intent == "answer":
                return self._answer(sender, message)
            s = self.client.summary()
            if s.pending_question:
                self.memory.shown[sender] = s.pending_question.id
            return say.summary_text(s, intro=intent == "help")
        except ClawbackError as e:
            return say.error_text(e)

    def _answer(self, sender: str, message: str) -> str:
        if self.owners and sender not in self.owners:
            return say.NOT_OWNER
        s = self.client.summary()
        q = s.pending_question
        if is_undo(message):  # UNDO works on any question the API knows, answered or not
            qid = (q.id if q else None) or self.memory.answered.get(sender) or self.memory.shown.get(sender)
            if qid is None:
                return say.NO_UNDO_TARGET
            try:
                return say.undo_text(self.client.answer(qid, message))
            except ClawbackError as e:
                return say.gone_text() if e.status == 404 else say.error_text(e)
        if q is None:
            return say.nothing_to_answer_text(s)
        if self.memory.shown.get(sender) != q.id:
            self.memory.shown[sender] = q.id
            return say.show_first_text(q)
        try:
            resp = self.client.answer(q.id, message)
        except ClawbackError as e:
            if e.status == 409:  # a newer run of the same payment replaced the question
                new_q = self._summary_or_none()
                new_q = new_q.pending_question if new_q else None
                if new_q:
                    self.memory.shown[sender] = new_q.id
                return say.replaced_text(new_q)
            if e.status == 404:
                return say.gone_text()
            raise
        self.memory.answered[sender] = q.id
        return say.answered_text(resp, q, self._summary_or_none())

    def _summary_or_none(self) -> Summary | None:
        """A fresh summary to report the result; the answer already went through, so a failure here isn't one."""
        try:
            return self.client.summary()
        except ClawbackError:
            return None
