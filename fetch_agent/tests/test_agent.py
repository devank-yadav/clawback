"""The uagents wiring: Agent Chat Protocol spec, acknowledgement then reply, mailbox agent. Skipped without uagents
(pip install -r fetch_agent/requirements.txt). Nothing here runs the agent, so nothing reaches Agentverse."""

import asyncio
import logging

import httpx
import pytest

pytest.importorskip("uagents")

from uagents_core.contrib.protocols.chat import (  # noqa: E402
    ChatAcknowledgement, ChatMessage, EndSessionContent, StartSessionContent, TextContent, chat_protocol_spec,
)
from uagents_core.models import Model  # noqa: E402
from uagents_core.protocol import ProtocolSpecification  # noqa: E402

from fetch_agent import agent as fa  # noqa: E402
from fetch_agent import connect  # noqa: E402
from fetch_agent import text as say  # noqa: E402
from fetch_agent.assistant import Assistant  # noqa: E402
from fetch_agent.client import ClawbackClient  # noqa: E402
from fetch_agent.tests.conftest import load  # noqa: E402

SEED = "clawback assistant test seed, not a real one"
CHAT_DIGEST = ProtocolSpecification.compute_digest(chat_protocol_spec.manifest())


class FakeCtx:
    def __init__(self):
        self.sent: list[tuple[str, Model]] = []
        self.logger = logging.getLogger("fake-ctx")

    async def send(self, destination, message):
        self.sent.append((destination, message))


def summary_assistant() -> Assistant:
    http = httpx.Client(base_url="https://clawback.example/api", timeout=10.0,
                        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=load("summary-question.json"))))
    return Assistant(ClawbackClient("https://clawback.example/api", "ro-token", http=http))


def on_chat(proto):
    return proto.signed_message_handlers[Model.build_schema_digest(ChatMessage)]


def test_the_protocol_is_the_agent_chat_protocol():
    proto = fa.build_protocol(summary_assistant())
    assert proto.digest == CHAT_DIGEST
    assert Model.build_schema_digest(ChatAcknowledgement) in proto.signed_message_handlers


def test_a_chat_message_is_acknowledged_then_answered_and_the_session_ends():
    ctx, msg = FakeCtx(), ChatMessage(content=[StartSessionContent(), TextContent(text="What did Northmart take this month?")])
    asyncio.run(on_chat(fa.build_protocol(summary_assistant()))(ctx, "user1dana", msg))
    (to1, ack), (to2, reply) = ctx.sent
    assert to1 == to2 == "user1dana"
    assert isinstance(ack, ChatAcknowledgement) and ack.acknowledged_msg_id == msg.msg_id
    assert isinstance(reply, ChatMessage) and isinstance(reply.content[-1], EndSessionContent)
    assert fa.message_text(reply).startswith("Northmart took **$6,850**")


def test_a_bare_start_session_is_only_acknowledged():
    ctx = FakeCtx()
    asyncio.run(on_chat(fa.build_protocol(summary_assistant()))(ctx, "user1dana", ChatMessage(content=[StartSessionContent()])))
    assert [type(m) for _, m in ctx.sent] == [ChatAcknowledgement]


def test_an_unexpected_error_still_gets_a_reply():
    class Broken(Assistant):
        def respond(self, sender, message):
            raise RuntimeError("bug")

    ctx = FakeCtx()
    asyncio.run(on_chat(fa.build_protocol(Broken(None)))(ctx, "user1dana", ChatMessage(content=[TextContent(text="hi")])))
    assert fa.message_text(ctx.sent[-1][1]) == say.OOPS


@pytest.fixture
def event_loop_set():
    """Agent() takes the current event loop, and an earlier asyncio.run() leaves none set."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    asyncio.set_event_loop(None)
    loop.close()


def test_the_agent_is_a_mailbox_agent_with_the_chat_protocol_and_its_profile(event_loop_set):
    agent = fa.build_agent(SEED, summary_assistant(), publish_manifest=False)
    assert agent.agent_type == "mailbox" and CHAT_DIGEST in agent.protocols
    assert agent.name == "Clawback Assistant" and fa.PROFILE.is_file()
    assert agent.address == fa.build_agent(SEED, summary_assistant(), publish_manifest=False).address  # seed fixes it


def test_settings_name_what_is_missing(monkeypatch):
    with pytest.raises(SystemExit) as e:
        fa.settings()
    assert "CLAWBACK_API_URL, CLAWBACK_READONLY_TOKEN, CLAWBACK_AGENT_SEED" in str(e.value)
    monkeypatch.setenv("CLAWBACK_API_URL", "https://clawback.example/api")
    monkeypatch.setenv("CLAWBACK_READONLY_TOKEN", "ro")
    monkeypatch.setenv("CLAWBACK_AGENT_SEED", SEED)
    monkeypatch.setenv("CLAWBACK_OWNER_ADDRESSES", " user1dana, ,user1sam ")
    assert fa.settings() == ("https://clawback.example/api", "ro", SEED, frozenset({"user1dana", "user1sam"}))


def test_connect_sends_the_key_as_the_inspectors_mailbox_request():
    assert connect.connect_request("av-key") == {"user_token": "av-key", "agent_type": "mailbox"}
    assert connect.URL == "http://127.0.0.1:8001/connect"


def test_connect_names_the_missing_key():
    with pytest.raises(SystemExit) as e:
        connect.main()
    assert "AGENTVERSE_API_KEY" in str(e.value)
