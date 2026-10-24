"""What Dana sees, end to end through the real client and recorded API answers, with no network."""

import json
import re
from decimal import Decimal

import httpx
import pytest

from fetch_agent import text as say
from fetch_agent.assistant import Assistant, classify, is_undo
from fetch_agent.client import ClawbackClient
from fetch_agent.models import Summary
from fetch_agent.tests.conftest import load

DANA = "user1dana"
BASE = "https://clawback.example/api"
SUMMARY = "/api/summary"


class FakeApi:
    """Serves queued responses per route and records every request the assistant makes."""

    def __init__(self, **routes):
        self.routes = {k: list(v) for k, v in routes.items()}  # "summary" / "answer" → responses
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        route = "summary" if request.url.path == SUMMARY else "answer"
        nxt = self.routes[route].pop(0) if len(self.routes[route]) > 1 else self.routes[route][0]
        if isinstance(nxt, Exception):
            raise nxt
        if isinstance(nxt, httpx.Response):
            return nxt
        return httpx.Response(200, json=load(nxt) if isinstance(nxt, str) else nxt)

    @property
    def answers(self):
        return [(path, body) for method, path, body in self.calls if method == "POST"]


def assistant(api: FakeApi, owners=frozenset()) -> Assistant:
    http = httpx.Client(base_url=BASE, transport=httpx.MockTransport(api), timeout=10.0)
    return Assistant(ClawbackClient(BASE, "ro-token", http=http), owners=owners)


def dollars(reply: str) -> set[str]:
    return set(re.findall(r"\$[\d,]+(?:\.\d\d)?", reply))


def api_dollars(*fixtures: str) -> set[str]:
    """Every amount the API itself sent, formatted the way the assistant shows money, plus amounts quoted in
    the API's own text fields (the question and dispute reasons)."""
    found: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, float):
            found.add(say.money(Decimal(str(v))))
        elif isinstance(v, str):
            found.update(dollars(v))

    for f in fixtures:
        walk(load(f))
    return found


# ---------------------------------------------------------------- reading the message

@pytest.mark.parametrize("message, intent", [
    ("What did Northmart take this month?", "summary"),
    ("how much is disputed", "summary"),
    ("open disputes", "summary"),
    ("Is anything waiting on me?", "summary"),
    ("Should I accept?", "summary"),
    ("what will you dispute", "summary"),
    ("status", "summary"),
    ("thanks", "summary"),
    ("yes", "summary"),
    ("hi", "help"),
    ("Help", "help"),
    ("", "help"),
    ("accept if notice is at least 14 days", "answer"),
    ("ACCEPT", "answer"),
    ("DISPUTE", "answer"),
    ("Dispute it.", "answer"),
    ("UNDO", "answer"),
    ("undo rule #1", "answer"),
    ("only accept with 14+ days notice", "answer"),
    ("two weeks", "answer"),
    ("do not accept", "answer"),  # Clawback's parser refuses to guess on a negation and asks again
])
def test_classify(message, intent):
    assert classify(message) == intent


def test_undo_is_only_undo():
    assert is_undo("UNDO") and is_undo("please cancel that") and is_undo("Undo the rule.")
    assert not is_undo("cancel the dispute") and not is_undo("accept") and not is_undo("")


# ---------------------------------------------------------------- what Northmart took

def test_what_did_northmart_take_answers_with_the_apis_numbers():
    api = FakeApi(summary=["summary-question.json"])
    reply = assistant(api).respond(DANA, "What did Northmart take this month?")
    assert reply.startswith("Northmart took **$6,850** out of Peak Bar Co.'s latest payment.")
    for line in ("**$4,120** disputed: Northmart took too much", "**$1,530** accepted: fair under the deal",
                 "**$1,200** waiting on your answer",
                 "**Open dispute D-0417** with Northmart: $4,120 over 4 charges (filed, waiting on Northmart).",
                 "- C1, $600: Northmart charged $1.50 per bar, but the deal pays $1.00.",
                 "- C4, $1,540: Earlier March sales already used the deal's 5,000-unit limit",
                 "**Clawback has a question for you (Q-1):**\n> Northmart took $1,200: Display fee (notice Mar 11).",
                 say.HOW_TO_ANSWER):
        assert line in reply
    assert api.calls == [("GET", SUMMARY, None)]


@pytest.mark.parametrize("fixture", ["summary-question.json", "summary-approval.json", "summary-recorded-run.json"])
def test_every_amount_shown_is_one_the_api_sent(fixture):
    reply = assistant(FakeApi(summary=[fixture])).respond(DANA, "What did Northmart take?")
    assert dollars(reply) and dollars(reply) <= api_dollars(fixture)


def test_approvals_waiting_on_sam_are_shown_never_given():
    reply = assistant(FakeApi(summary=["summary-approval.json"])).respond(DANA, "what's pending?")
    assert "Nothing is waiting on your answer." in reply
    assert ("**Waiting on Sam, your bookkeeper:** approve putting the $2,730 Clawback accepted (3 charges) into "
            "QuickBooks.") in reply and "this chat can't move money" in reply


def test_the_recorded_demo_run_says_so():
    reply = assistant(FakeApi(summary=["summary-recorded-run.json"])).respond(DANA, "status")
    assert "No live payment yet" in reply and "**$2,730** accepted" in reply


def test_hello_introduces_itself_then_shows_the_numbers():
    reply = assistant(FakeApi(summary=["summary-question.json"])).respond(DANA, "hi")
    assert reply.startswith(say.INTRO) and "**$6,850**" in reply


@pytest.mark.parametrize("fixture", ["summary-question.json", "summary-approval.json", "summary-recorded-run.json"])
def test_no_finance_jargon(fixture):
    reply = assistant(FakeApi(summary=[fixture])).respond(DANA, "hi").lower()
    for word in ("credit memo", "remittance", "allowance", "deduction", "off-invoice", "chargeback", "ledger"):
        assert word not in reply


# ---------------------------------------------------------------- Dana answers

def test_answer_after_seeing_the_question_saves_rule_1():
    api = FakeApi(summary=["summary-question.json", "summary-question.json", "summary-approval.json"],
                  answer=["answer-rule.json"])
    a = assistant(api)
    a.respond(DANA, "What did Northmart take this month?")
    reply = a.respond(DANA, "accept if notice is at least 14 days")
    assert api.answers == [("/api/questions/Q-1/answer", {"text": "accept if notice is at least 14 days",
                                                         "from_role": "owner"})]
    assert reply.startswith("Saved **Rule #1**: Accept Northmart display fees with at least 14 days' notice; "
                            "otherwise dispute. Clawback will apply it next time without asking. Reply UNDO")
    assert "Now: **$4,120** disputed, **$2,730** accepted, **$0** waiting." in reply
    assert "**Waiting on Sam, your bookkeeper:**" in reply


def test_an_answer_to_a_question_this_chat_never_showed_shows_it_first():
    api = FakeApi(summary=["summary-question.json"])
    reply = assistant(api).respond(DANA, "ACCEPT")
    assert reply.startswith("Here's the question Clawback is asking.") and "(Q-1)" in reply
    assert api.answers == []


def test_nothing_to_answer():
    api = FakeApi(summary=["summary-approval.json"])
    reply = assistant(api).respond(DANA, "ACCEPT")
    assert reply.startswith("Nothing is waiting on your answer right now.") and api.answers == []


def test_accept_once_settles_the_charge_without_a_rule():
    after = load("summary-approval.json")  # the question is gone once ACCEPT settled it
    api = FakeApi(summary=["summary-question.json", "summary-question.json", after], answer=["answer-once.json"])
    a = assistant(api)
    a.respond(DANA, "status")
    reply = a.respond(DANA, "ACCEPT")
    assert api.answers[0][1] == {"text": "ACCEPT", "from_role": "owner"}
    assert reply.startswith("Done. Your answer settles C6 this time only. No rule was saved")


def test_an_answer_clawback_cant_read_keeps_the_question_open():
    unread = {"answer": {"question_id": "Q-1", "from_role": "owner", "text": "hmm not sure",
                         "answered_at": "2026-10-24T11:54:05Z", "rule_id": None}, "rule": None}
    api = FakeApi(summary=["summary-question.json"], answer=[unread])
    a = assistant(api)
    a.respond(DANA, "status")
    reply = a.respond(DANA, "dispute maybe, not sure")
    assert reply.startswith("Clawback couldn't turn that into a rule, so the question is still open.")


def test_undo_after_answering_cancels_rule_1_then_finds_nothing():
    api = FakeApi(summary=["summary-question.json", "summary-question.json", "summary-approval.json",
                           "summary-approval.json", "summary-approval.json"],
                  answer=["answer-rule.json", "answer-undo.json", "answer-undo-nothing.json"])
    a = assistant(api)
    a.respond(DANA, "status")
    a.respond(DANA, "accept if notice is at least 14 days")
    reply = a.respond(DANA, "UNDO")  # nothing is pending now: it goes to the question Dana answered
    assert api.answers[1] == ("/api/questions/Q-1/answer", {"text": "UNDO", "from_role": "owner"})
    assert reply.startswith("Cancelled **Rule #1** (Accept Northmart display fees")
    assert "Next time Clawback will ask you again." in reply
    assert a.respond(DANA, "undo") == "There's no saved rule to undo."


def test_undo_with_nothing_to_point_at():
    api = FakeApi(summary=["summary-approval.json"])
    assert assistant(api).respond(DANA, "UNDO") == say.NO_UNDO_TARGET and api.answers == []


def test_a_replaced_question_shows_the_new_one_and_the_next_answer_goes_there():
    newer = load("summary-question.json")
    newer["pending_question"] = {**newer["pending_question"], "id": "Q-2"}
    closed = httpx.Response(409, json={"detail": "Q-1 closed: run run-b replaced run-a; answer the newer run's question"})
    api = FakeApi(summary=["summary-question.json", "summary-question.json", newer, newer, newer],
                  answer=[closed, "answer-once.json"])
    a = assistant(api)
    a.respond(DANA, "status")
    reply = a.respond(DANA, "ACCEPT")
    assert reply.startswith("That question was replaced: a newer run of the same payment asked again")
    assert "(Q-2)" in reply
    a.respond(DANA, "ACCEPT")
    assert [path for path, _ in api.answers] == ["/api/questions/Q-1/answer", "/api/questions/Q-2/answer"]


def test_a_question_that_is_gone():
    api = FakeApi(summary=["summary-question.json"], answer=[httpx.Response(404, json={"detail": "no open question Q-1"})])
    a = assistant(api)
    a.respond(DANA, "status")
    assert a.respond(DANA, "ACCEPT") == say.gone_text()


def test_owner_addresses_limit_who_can_answer_but_not_who_can_read():
    api = FakeApi(summary=["summary-question.json"], answer=["answer-once.json"])
    a = assistant(api, owners=frozenset({DANA}))
    assert a.respond("user1stranger", "accept if notice is at least 14 days") == say.NOT_OWNER
    assert "**$6,850**" in a.respond("user1stranger", "What did Northmart take?")
    a.respond(DANA, "status")
    a.respond(DANA, "ACCEPT")
    assert [path for path, _ in api.answers] == ["/api/questions/Q-1/answer"]


def test_two_senders_each_need_to_see_the_question():
    api = FakeApi(summary=["summary-question.json"], answer=["answer-once.json"])
    a = assistant(api)
    a.respond(DANA, "status")
    assert a.respond("user1other", "ACCEPT").startswith("Here's the question")
    assert api.answers == []


# ---------------------------------------------------------------- when Clawback is unhappy

@pytest.mark.parametrize("failure, words", [
    (httpx.ConnectError("down"), "I couldn't reach Clawback just now."),
    (httpx.Response(401, json={"detail": "bad token"}), "Clawback turned down my read-only key"),
    (httpx.Response(503, json={"detail": "CLAWBACK_READONLY_TOKEN is not set"}), "isn't set up to share"),
    (httpx.Response(404, text="Not Found"), "couldn't find Clawback at the address"),
])
def test_errors_in_plain_words(failure, words):
    reply = assistant(FakeApi(summary=[failure])).respond(DANA, "What did Northmart take?")
    assert words in reply


def test_an_answer_that_went_through_is_reported_even_if_the_refresh_fails():
    api = FakeApi(summary=["summary-question.json", "summary-question.json", httpx.ConnectError("down"),
                           httpx.ConnectError("down")], answer=["answer-rule.json"])
    a = assistant(api)
    a.respond(DANA, "status")
    reply = a.respond(DANA, "accept if notice is at least 14 days")
    assert reply.startswith("Saved **Rule #1**") and "Now:" not in reply


def test_only_the_two_endpoints_are_ever_called():
    api = FakeApi(summary=["summary-question.json"] * 6 + ["summary-approval.json"],
                  answer=["answer-rule.json", "answer-undo.json"])
    a = assistant(api)
    for message in ("hi", "What did Northmart take this month?", "accept if notice is at least 14 days", "UNDO",
                    "approve the credit memo", "post it to QuickBooks", "status"):
        a.respond(DANA, message)
    assert {(method, path if method == "GET" else re.sub(r"/questions/[^/]+/", "/questions/{id}/", path))
            for method, path, _ in api.calls} <= {("GET", "/api/summary"), ("POST", "/api/questions/{id}/answer")}
    assert all(body["from_role"] == "owner" for _, body in api.answers)


def test_summary_model_reads_numbers_without_rounding():
    s = Summary.model_validate(load("summary-question.json"))
    assert s.totals.accepted == Decimal("1530") and say.money(Decimal("12.5")) == "$12.50"
