"""Connect the running agent to its Agentverse mailbox with AGENTVERSE_API_KEY, no browser needed.

Does what the Agent Inspector's "Connect" → "Mailbox" button does: POST /connect on the agent's own port with
{"user_token": <key>, "agent_type": "mailbox"}. The agent then proves its address to Agentverse and registers
itself as a mailbox agent (uagents 0.26.1: Agent._handle_connect → uagents.mailbox.register_in_agentverse;
uagents-core's register_chat_agent sends the API key as the same user_token). The agent only takes /connect
from 127.0.0.1, so run this on the machine the agent runs on, while it runs.

Run: make fetch-agent-connect (or python -m fetch_agent.connect). Key (.env): AGENTVERSE_API_KEY.
"""

from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

from fetch_agent.agent import PORT, ROOT

URL = f"http://127.0.0.1:{PORT}/connect"
TIMEOUT_S = 30.0  # the agent makes three calls to Agentverse before it answers


def connect_request(api_key: str) -> dict[str, str]:
    return {"user_token": api_key, "agent_type": "mailbox"}


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = os.getenv("AGENTVERSE_API_KEY")
    if not key:
        sys.exit("Missing in .env: AGENTVERSE_API_KEY")
    try:
        r = httpx.post(URL, json=connect_request(key), timeout=TIMEOUT_S)
    except httpx.TransportError as e:
        sys.exit(f"The agent isn't answering on {URL} ({e.__class__.__name__}). Start it first: make fetch-agent")
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or not body.get("success"):
        sys.exit(f"Agentverse didn't connect the mailbox ({r.status_code}): {body.get('detail') or r.text[:300]}\n"
                 "A 500 means the agent couldn't finish talking to Agentverse; the agent's log has the reason.")
    print("Connected: the agent is registered on Agentverse as a mailbox agent. Its log should now show it "
          "picking up mail; open agentverse.ai → Agents to see it.")


if __name__ == "__main__":
    main()
