"""The uagents side: an Agentverse mailbox agent that speaks the Agent Chat Protocol, so ASI:One can talk to it.

Written against uagents 0.26.1 / uagents-core 0.4.12 (pinned in requirements.txt), following Fetch.ai's
ASI:One-compatible agent example: mailbox=True, the chat protocol from uagents_core.contrib.protocols.chat
included with publish_manifest=True, an acknowledgement for every ChatMessage, then the reply as a new
ChatMessage that ends the session. Doc links are in fetch_agent/README.md.

Run: make fetch-agent (or python -m fetch_agent). Keys (.env): CLAWBACK_API_URL, CLAWBACK_READONLY_TOKEN,
CLAWBACK_AGENT_SEED; optional CLAWBACK_OWNER_ADDRESSES.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

from fetch_agent import text as say
from fetch_agent.assistant import Assistant, classify
from fetch_agent.client import ClawbackClient

ROOT = Path(__file__).resolve().parent.parent
PROFILE = Path(__file__).resolve().parent / "AGENTVERSE.md"  # the README Agentverse and ASI:One read
NAME = "Clawback Assistant"
PORT = 8001  # the API is on 8000; only the local inspector and /connect use this port (mailbox needs no inbound)
DESCRIPTION = ("Tells a small snack brand what its distributor took out of a payment, which charges Clawback is "
               "disputing or accepting, and passes the owner's answer to Clawback's one question.")


def message_text(msg: ChatMessage) -> str:
    return "".join(item.text for item in msg.content if isinstance(item, TextContent))


def reply_message(text: str) -> ChatMessage:
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                       content=[TextContent(type="text", text=text), EndSessionContent(type="end-session")])


def build_protocol(assistant: Assistant) -> Protocol:
    proto = Protocol(spec=chat_protocol_spec)

    @proto.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
        text = message_text(msg)
        if not text.strip():  # a start-session with no words yet: nothing to answer
            return
        ctx.logger.info(f"Chat from {sender} ({classify(text)})")  # the address is what CLAWBACK_OWNER_ADDRESSES lists
        try:
            reply = await asyncio.to_thread(assistant.respond, sender, text)  # the HTTP calls block; keep the loop free
        except Exception:
            ctx.logger.exception("Couldn't answer the chat")
            reply = say.OOPS
        await ctx.send(sender, reply_message(reply))

    @proto.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
        ctx.logger.debug(f"{sender} got message {msg.acknowledged_msg_id}")

    return proto


def build_agent(seed: str, assistant: Assistant, publish_manifest: bool = True) -> Agent:
    agent = Agent(name=NAME, seed=seed, port=PORT, mailbox=True, publish_agent_details=True,
                  readme_path=str(PROFILE), description=DESCRIPTION)
    agent.include(build_protocol(assistant), publish_manifest=publish_manifest)
    return agent


def settings() -> tuple[str, str, str, frozenset[str]]:
    """(API URL, read-only token, agent seed, owner addresses) from the environment; exits naming what's missing."""
    names = ("CLAWBACK_API_URL", "CLAWBACK_READONLY_TOKEN", "CLAWBACK_AGENT_SEED")
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)} (see fetch_agent/README.md)")
    owners = frozenset(a.strip() for a in os.getenv("CLAWBACK_OWNER_ADDRESSES", "").split(",") if a.strip())
    return os.environ["CLAWBACK_API_URL"], os.environ["CLAWBACK_READONLY_TOKEN"], os.environ["CLAWBACK_AGENT_SEED"], owners


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_url, token, seed, owners = settings()
    agent = build_agent(seed, Assistant(ClawbackClient(api_url, token), owners=owners))
    print(f"{NAME}: {agent.address}, reading {api_url}; "
          + (f"{len(owners)} address(es) may answer" if owners else "anyone who chats may answer Clawback's question"))
    agent.run()


if __name__ == "__main__":
    main()
