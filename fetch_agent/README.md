# Clawback Assistant (Fetch.ai ASI:One Agent Challenge)

An Agentverse agent that Dana, the owner of Peak Bar Co., chats with in ASI:One. Every name is fictional.

- **"What did Northmart take this month?"** (or "status", "what's waiting on me?", "hi") → it calls
  `GET {CLAWBACK_API_URL}/summary` with `Authorization: Bearer {CLAWBACK_READONLY_TOKEN}` and answers in plain
  words: what Northmart took, what's disputed, what's accepted, what's waiting, each open dispute with its charges,
  the question waiting on Dana, and anything waiting on Sam (the bookkeeper).
- **Dana's answer** ("accept if notice is at least 14 days", ACCEPT, DISPUTE, UNDO) → it calls
  `POST {CLAWBACK_API_URL}/questions/{id}/answer` with `{"text": ..., "from_role": "owner"}` and reports what the
  API returned: the rule it saved or cancelled, a one-off decision, or that Clawback couldn't read the answer.
  A 409 means a newer run replaced the question: it says so and shows the new one.
- **Never:** approves money, calls any other endpoint, or computes an amount. Every dollar figure is the API's
  number, formatted (`tests/test_assistant.py` checks each one against the API's response).

## Files

| File | What it is |
| --- | --- |
| `agent.py` | The uagents agent: mailbox agent, Agent Chat Protocol, acknowledgement + reply |
| `assistant.py` | Pure logic: reads the message (status, answer, hello) and decides what to call |
| `client.py` | The two HTTP calls: 10 s timeout, one retry |
| `text.py` | Every sentence it says |
| `models.py` | The fields it reads from `Summary` / `AnswerResponse` (mirrors `api/contracts.py`) |
| `connect.py` | Connects the running agent to its Agentverse mailbox with `AGENTVERSE_API_KEY` (no browser) |
| `AGENTVERSE.md` | The agent's public profile README on Agentverse. ASI:One reads it to decide when to use the agent |
| `tests/` | Offline tests; `tests/fixtures/` holds real API responses recorded in DEMO_MODE |

## Environment (`.env` at the repo root; names are in `.env.example`)

| Name | Needed for | Value |
| --- | --- | --- |
| `CLAWBACK_API_URL` | the agent | `https://clawback.biz/api` (Caddy strips `/api`), or `http://localhost:8000` on a laptop |
| `CLAWBACK_READONLY_TOKEN` | the agent and the API | The same value on both sides. The API answers `/summary` with 503 without it |
| `CLAWBACK_AGENT_SEED` | the agent | A long random secret. It fixes the agent's address: never commit it, never change it after registering. Make one with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `AGENTVERSE_API_KEY` | `make fetch-agent-connect` only | Your Agentverse API key |
| `CLAWBACK_OWNER_ADDRESSES` | optional | Comma-separated sender addresses allowed to answer Clawback's question. Empty means anyone who can chat with the agent (judges included). Everyone can always read the summary |

## Run it locally

```bash
python3.11 -m venv fetch_agent/.venv        # its own venv: uagents pins its own packages
fetch_agent/.venv/bin/pip install -r fetch_agent/requirements.txt
make fetch-agent                            # = fetch_agent/.venv/bin/python -m fetch_agent
```

To try it against your laptop's API, run `DEMO_MODE=true make api` with `CLAWBACK_READONLY_TOKEN` set, set
`CLAWBACK_API_URL=http://localhost:8000`, and press "Northmart pays" (or `POST /runs`) so there's a live run.

Startup prints the agent's address, then uagents logs `Agent inspector available at https://agentverse.ai/inspect/?uri=http%3A//127.0.0.1%3A8001&address=agent1q...`
and `Starting mailbox client for https://agentverse.ai`. Until the mailbox is connected (step 4 below) it also
logs `Agent mailbox not found: create one using the agent inspector`. Port 8001 is only for that inspector and
`/connect`, which uagents accepts only from 127.0.0.1. A mailbox agent needs outbound HTTPS only, so don't open
8001 in a firewall.

## Devank: what to do with the Agentverse key once https://clawback.biz/api is live

Run the agent on the Vultr VM so it stays up through judging. It needs no Caddy route, no compose change and
no open port.

1. **Check the API answers** (on the VM, in `/opt/clawback` after the rsync in docs/deploy.md step c, so
   `fetch_agent/` is there too):
   `curl -s https://clawback.biz/api/summary -H "Authorization: Bearer $(grep ^CLAWBACK_READONLY_TOKEN= .env | cut -d= -f2-)"`
   should print JSON with `totals`. A 503 means the API's `.env` has no `CLAWBACK_READONLY_TOKEN`: add one and
   run `docker compose up -d` so the api container picks it up.
2. **Add to that `.env`:** `CLAWBACK_API_URL=https://clawback.biz/api`, `CLAWBACK_AGENT_SEED=<new secret>` and
   `AGENTVERSE_API_KEY=<your key>`. The agent shares `CLAWBACK_READONLY_TOKEN` with the API.
3. **Install and start it** in a session that survives logout (Ubuntu may need
   `sudo apt-get install -y python3-venv make tmux` first):
   `python3 -m venv fetch_agent/.venv && fetch_agent/.venv/bin/pip install -r fetch_agent/requirements.txt`, then
   `tmux new -s agent 'make fetch-agent'` (detach with Ctrl-b d). Note the `agent1q...` address it prints.
4. **Connect the mailbox (once):** in a second shell on the same machine, `make fetch-agent-connect`. It posts
   your key to the agent's local `/connect`, which is what the inspector's **Connect → Mailbox** button does.
   It prints `Connected` when Agentverse accepts it. Browser alternative: open the inspector link from the log
   while signed in to agentverse.ai and click **Connect → Mailbox**. On the VM, first run
   `ssh -L 8001:127.0.0.1:8001 <vm>` on your laptop, because the inspector page talks to 127.0.0.1:8001.
5. **Check it registered:** the log stops saying "Agent mailbox not found"; `fetch_agent/.venv/bin/av agent <agent1q...>`
   (uagents-core's Agentverse CLI) shows its record; on agentverse.ai → Agents, "Clawback Assistant" lists the
   AgentChatProtocol and shows `AGENTVERSE.md` as its README. Add an avatar there: Agentverse's discovery guide
   says the README, an avatar and the chat protocol are what keep an agent discoverable.
6. **Test it in ASI:One:** on the agent's Agentverse page, click **Chat with Agent** (opens ASI:One). Send
   "What did Northmart take this month?". With a live March run waiting on Dana, the reply starts
   "Northmart took **$6,850** out of Peak Bar Co.'s latest payment." and ends with Clawback's question. Then
   send "accept if notice is at least 14 days" → "Saved **Rule #1** ...", and "UNDO" → "Cancelled **Rule #1** ...".
   It's also at https://asi1.ai. How readily ASI:One picks it for a general question depends on the profile
   README and on Agentverse's own checks of the agent, so it may not be chosen right away.
7. **Optional, lock answering to Dana's phone:** after one message, copy your sender address from the log line
   `Chat from <address> (...)` into `CLAWBACK_OWNER_ADDRESSES` and restart the agent. Leave it empty if judges
   should answer the question too.
8. **Devpost evidence** (design doc, Added tracks): a clip of the ASI:One chat and the agent address.

If the VM reboots, run step 3 again. The registration persists (uagents-core: Agentverse registrations are
permanent), so step 4 is only needed again if the log says "Agent mailbox not found". Never change
`CLAWBACK_AGENT_SEED`: a new seed is a new agent with a new address. `make reset` on the API clears Rule #1;
the agent keeps nothing worth resetting (a restart clears which question each chat has seen).

## How it decides

- **Status or answer?** Questions ("...?", "what/how/which/show..."), "status" and anything unclear get the
  summary, since showing numbers changes nothing. A message with a decision word (accept, dispute, undo...) or
  a notice period ("14 days", "two weeks") is an answer. Clawback's own parser (`api/replies.py`) decides what the
  answer means. The agent passes the text on unchanged.
- **Answers go only to the question this chat showed.** If the waiting question isn't the one this chat last
  showed that sender (a newer run asked again, or the chat never showed it), the agent shows it and asks for the
  answer again instead of posting.
- **UNDO** goes to the waiting question, or else to the one this chat last answered, so Rule #1 can be cancelled
  after the question is gone.
- **What happened:** a saved rule comes back in the response. With no rule, a fresh `GET /summary` tells a
  one-off ACCEPT/DISPUTE (question gone) from a reply Clawback couldn't read (same question still open).
- **Retries:** `GET /summary` retries once on a network error or 5xx. The answer `POST` retries only if the request
  never left (connection refused, connect timeout). If an UNDO went through but its reply was lost, sending it
  again would cancel a second rule.
- **No DEMO_MODE fallback here.** The API it calls is what replays in DEMO_MODE, and ASI:One needs the network
  anyway. If Clawback can't be reached, the agent says so rather than showing stale numbers.

## Tests

`python -m pytest -q fetch_agent` runs offline with no keys: `.env` is never read and sockets only reach
localhost. In the API's `.venv` (httpx and pydantic, no uagents) the uagents wiring tests are skipped. In
`fetch_agent/.venv`, `make fetch-agent-test` runs all of them. `tests/test_contract_sync.py` validates the
recorded fixtures against `api/contracts.py`, so an API change that would break the agent fails a test.

Also checked by hand from the cloud session, offline: the real API in DEMO_MODE on localhost, this agent and a
test "Dana" agent in one uagents Bureau, chatting over the Agent Chat Protocol with outbound network blocked.
Every message got an acknowledgement, then a reply ending the session, for the summary, the Rule #1 answer and
UNDO. Separately, `make fetch-agent-connect` against the running agent reached uagents' `/connect` handler,
which then tried Agentverse; that call was blocked in the sandbox.

## Fetch.ai sources

Fetch.ai's doc sites (uagents.fetch.ai, innovationlab.fetch.ai, docs.agentverse.ai) were blocked from the cloud
session that wrote this. The pages below were found by web search. The code was checked against the pinned package
source (uagents 0.26.1, uagents-core 0.4.12) and the uAgents GitHub repo. Where a page and the pinned source
differ, the pinned source is what runs.

- uAgents, "Create an ASI:One compatible Agent using the chat protocol": https://uagents.fetch.ai/docs/examples/asi-1
  (`mailbox=True`, `publish_agent_details=True`, `agent.include(protocol, publish_manifest=True)`, acknowledge every
  message, reply with `TextContent` and `EndSessionContent`)
- Innovation Lab, same guide (startup logs, inspector, Connect → Mailbox):
  https://innovationlab.fetch.ai/resources/docs/next/examples/chat-protocol/asi-compatible-uagents
- Agentverse, "Enable the Chat Protocol": https://docs.agentverse.ai/documentation/getting-started/enable-chat-protocol
- Agentverse, "Create a ASI:One Compatible Agent": https://docs.agentverse.ai/documentation/advanced-usages/asi-one-compatible-agent
- Agentverse, agent discovery setup guide (README, avatar, chat protocol): https://docs.agentverse.ai/documentation/agent-discovery/setup-guide
- Agentverse Marketplace (the README is what ASI:One reads): https://docs.agentverse.ai/documentation/getting-started/agentverse-marketplace
- uagents-core README (API-key registration with `register_chat_agent`, the `av` CLI, permanent registrations):
  https://github.com/fetchai/uAgents/blob/main/python/uagents-core/README.md
- uAgents repo: https://github.com/fetchai/uAgents. Chat models: `uagents_core/contrib/protocols/chat/__init__.py`
  (`AgentChatProtocol` 0.3.0). Inspector `/connect`: `uagents/agent.py` (`_handle_connect`) and `uagents/asgi.py`
  (local callers only)
- Cal Hacks Fetch.ai resources doc (track rules): linked in docs/design.md, Added tracks

## Troubleshooting

| You see | Means |
| --- | --- |
| `Agent mailbox not found: create one using the agent inspector` | Step 4 hasn't run yet |
| `make fetch-agent-connect` says the agent isn't answering | Start the agent first, on the same machine |
| `Ledger unavailable` or `not enough funds to register on Almanac contract` | Harmless: uagents registers through the Almanac API first and skips the on-chain contract without funds |
| Reply "Clawback turned down my read-only key" | The agent's and the API's `CLAWBACK_READONLY_TOKEN` differ |
| Reply "Clawback isn't set up to share its numbers yet" | The API has no `CLAWBACK_READONLY_TOKEN` (503) |
| Reply "I couldn't find Clawback at the address I was given" | `CLAWBACK_API_URL` is wrong (404); on the VM it ends in `/api` |
| Reply "No live payment yet: ..." | The API has no live run: press "Northmart pays" |
