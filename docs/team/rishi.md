# Clawback: Rishi's guide

## Your role in 30 seconds

**You own everything judges see, plus every job that needs a human: sign-ups, conversations, deployment and recording.** Devank owns the AI agents and the money logic; Manasv runs AI-driven jobs (data, test set, scripts, writing).

- **What we're building:** Clawback, a finance agent for small food brands. A distributor (fictional Northmart) takes $6,850 out of a $48,200 payment; Clawback checks each charge against the deal, disputes $4,120 with proof, accepts $2,730 as fair, and asks the owner one question. Main prize: Hyphenate.
- **See it first:** the clickable prototype (https://claude.ai/artifact/LQm2ZyZ8d8oQ5fRbh2VmFR) is what your screens should look and feel like.
- **You own:** `web/` (all screens), deployment (Vultr + domain), sign-ups and keys, sponsor questions, real quotes, screen recording.
- **Don't touch:** `api/engine/`, `api/agents/`, `config/policy.yaml`, `data/`. Your screens never compute money or call AI models; they only display events.
- **Ask Devank:** anything about how a charge is decided, or if an event shape in `api/contracts.py` doesn't give you what a screen needs.
- **Full plan, if you need it:** `docs/design.md`.

## Setup on your laptop

About 10 minutes. The repo is pushed and your invite is accepted; your issues are #1–10.

1. Clone and switch to your branch (it already exists):

```bash
git clone https://github.com/devank-yadav/clawback.git && cd clawback
git checkout web
git pull origin main   # at the start of each session, to pick up Devank's contracts and fixture
```

2. Install Claude Code if you don't have it (`npm install -g @anthropic-ai/claude-code`) and sign in with your own Claude account.
3. Make sure your git name and email are yours (`git config user.name`); commits are authored by you, with no AI co-author lines. The repo's `.claude/settings.json` already turns those off.
4. Start Claude Code in the repo (`claude`) and paste:

> "I'm Rishi. Read CLAUDE.md, docs/team/rishi.md and web/CLAUDE.md. Do card R1: scaffold the Next.js app in web/ (Tailwind, Framer Motion) with the design tokens in web/CLAUDE.md and the payment screen. Use the scenario numbers directly until web/fixtures/run-events.json exists."

Do the sign-ups below first (they block everyone), then R1. Start R2 once Devank says the fixture file is pushed (about 12:30 AM).

5. Keys never go in the repo, Slack or the group chat. They live in `.env` on laptops only (the repo has `.env.example` with the names).

## Tonight first: sign-ups and keys

Do this in the first hour while Devank writes the contracts; everyone else is blocked on these keys. Send each key to Devank through a private channel (a shared password-manager note or AirDrop), never the group chat or Slack.

- [ ] **Tiger Data (Tiger Cloud):** create an account, claim the MLH offer (ask at the MLH table or check mlh.link/calhacks13), create a service. Send: the connection string → `DATABASE_URL`.
- [ ] **QuickBooks sandbox:** developer.intuit.com → create an app with the Accounting scope (a sandbox company comes with it) → copy the development client ID and secret → open the OAuth 2.0 Playground, pick the app and the accounting scope, get tokens. Send: `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_REALM_ID` (company ID), `QBO_REFRESH_TOKEN`. Send the refresh token right away; it rotates.
- [ ] **Twilio:** trial account → get a trial number → add **your phone (owner)** and **Manasv's phone (controller)** as verified caller IDs (the trial only texts verified numbers). Send: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`, `OWNER_PHONE`, `CONTROLLER_PHONE`.
- [ ] **Capital One Nessie:** get an API key at nessieisreal.com. Send: `NESSIE_API_KEY`.
- [ ] **Gemini:** Google AI Studio → create an API key. Send: `GEMINI_API_KEY`.
- [ ] **Agentverse (Fetch.ai):** create an account at agentverse.ai, get an API key. Send: `AGENTVERSE_API_KEY`.
- [ ] **Vultr:** create the account and apply the MLH credit now; others in Slack report verification delays. Don't create a server yet.
- [ ] **GoDaddy:** get the MLH domain code and register a short domain. Send: the domain.
- [ ] **Mana and Atlassian:** post in #spons-mana: "Does a project qualify if part of it (an inbox app) is built in Mana and pushed to our GitHub?" Post in #spons-atlassian: "Does the security-for-agents track require a Forge app?" Forward answers to Devank.

Devank uses his own Claude API key for the product; you don't need one.

## Your task cards

Each card is one Claude Code session: paste the prompt, check the "done when," commit, move on. All screens read events shaped like `web/fixtures/run-events.json`; when Devank's live stream is ready, only the data source changes.

| Card | Build | Prompt to paste | Done when | By |
| --- | --- | --- | --- | --- |
| R1 | Next.js scaffold | "Scaffold web/ with Next.js, Tailwind and Framer Motion using the tokens in web/CLAUDE.md. Payment screen at / showing expected $48,200, received $41,350 and a large red −$6,850 from the fixture." | `npm run dev` shows the payment screen | Sat 1 AM |
| R2 | Board | "Build /board: a useRunEvents hook that replays web/fixtures/run-events.json with short delays; three meters; a live feed; Dispute, Accept and Ask columns with cards that drop in." | Replay ends at $4,120 disputed and $2,730 accepted | Sat 2 AM |
| R3 | Evidence card | "Add the evidence drawer: highlighted deal sentence, the charge, the math line, the rehearsed comeback, source chips; every number links to its source." | Every card opens and every number is clickable | Sat 10 AM |
| R4 | Northmart portal | "Build /portal in a different theme (the distributor's site): dispute D-0417 lines, reply box, 4 preset replies, and an 'attach signed amendment' preset. POST replies to the API." | Works on a phone and a tablet | Sat noon |
| R5 | Results, April, Deal Coach | "Build /results (totals, QuickBooks posts, eval score), /april (two fees decided by Rule #1, 0 questions) and /coach (redlines with dollar amounts)." | All three match the prototype | Sat 4 PM |
| R6 | Scenario box, audit log | "Build /scenario (paste a clause and a charge, show the returned decision with evidence) and /audit (every action with a Verify chain button)." | Both call the API stubs | Sat 8 PM |
| R7 | Switch to live data | "Point useRunEvents at GET /runs/{id}/events (server-sent events) with reconnect; keep the fixture as fallback when DEMO_MODE is on." | Live run fills the board | After Devank says the stream is ready |
| R8 | Deploy | "Create docker-compose.yml (api, web, caddy) and a Caddyfile for our domain; deploy steps for a Vultr Ubuntu VM." Then create the VM, point the domain's A record at it, run `docker compose up -d` | The board opens over HTTPS on a phone | Sat 8 PM |

**Human jobs (only you can do these):**

- **Sponsor questions, Saturday morning:** MLH table (how many MLH prizes one project can enter; Tiger Data and Vultr codes), SpaceXAI ("does coding in Cursor with Claude Code count?"), Moss (SDK + key for Devank).
- **Real quotes:** ask anyone who has worked at a food, drink or consumer brand: "How do you handle promo deductions from distributors?" Write their exact words, their role, and whether we can quote them. Two good quotes matter more than any feature.
- **Microsoft workshop,** Sat 10:00–10:45 AM, Theatre: note what they say about their five criteria; send notes to Manasv for the Devpost text.
- **Hyphenate mixer,** Sat 2–4 PM, Gate 6: show the board on your phone; ask "Would you hire this?" and "What would make you trust it?"
- **Recording,** Sat 9 PM: capture the screen while Devank narrates; Manasv runs `make reset` between takes.

## Next prompts (Sat morning, UI only)

The API side of every screen below is built and tested, and Devank owns all of it. Paste one prompt at a time into
Claude Code in `web/`. Every prompt includes these rules: live mode follows the API, fixture mode keeps working,
nothing on screen computes money, works at phone width, run `npm run lint` and `npm run build` before each commit,
and don't touch `api/`, `data/` or `config/`. In order of demo value:

| # | Screen | Paste into Claude Code |
| --- | --- | --- |
| U1 | `/portal` (judge beat, P0) | "Build /portal: Northmart's own site look, not ours. Load the dispute with GET /portal/disputes/D-0417 (its lines: charge, amount, reason, clause quote, math) and the thread with GET /portal/disputes/D-0417/messages. A reply box posts POST /portal/disputes/D-0417/messages with {text, attachment_doc_id}. Show the preset buttons from GET /portal/presets (send the preset's text, plus attachment_doc_id 'amendment-1' for the signed-amendment preset). Each POST returns Northmart's message plus Clawback's answer when one goes out; a held reply returns only Northmart's. New messages also arrive on the run stream as portal_message events. After the amendment, the dispute's C4 line drops to $540 and the board shows the $1,000 concession. Big type; works on a tablet." |
| U2 | Clickable evidence (F7, P0) | "In the evidence panel, make every number and source open its source. A MathPart (api/contracts.py) with an evidence_id is clickable and opens GET /evidence/{id}?run_id={run}: a deal sentence (quote with offsets, highlighted), a data row table, an email (sender, approved or not), a rule (who approved it, when) or an approval. Source chips open the same view. Acceptance: on C1 to C6, every number on the card opens what it came from." |
| U3 | `/results` scoreboard (F12) | "Build /results: the run's final totals event (disputed, accepted, waiting, questions), the ledger_post events (credit memo and open-balance note; show the API's note, which says 'Simulated' in DEMO_MODE; 'failed' and 'held' states included), and the score from GET /eval/latest (cases, correct, amounts_correct, asked, wrong_automatic, unnecessary_questions; say 'agent mode' or 'engine mode' from its mode field). End on '$4,120 disputed, $2,730 accepted, one question.'" |
| U4 | `/april` | "Build /april: a button calls POST /replay/april, then follow its events_url like the March board. Two display fees: A1 ($1,200, 18 days' notice) accepted and A2 ($800, 5 days) disputed, both 'Applied Rule #1', and the line '0 questions asked' from the log. If Rule #1 isn't saved yet (March not answered), the API asks Dana; show that question instead." |
| U5 | `/coach` | "Build /coach: POST /coach returns redlines on the summer draft. Each has clause_ref, original_quote (strike it through; quote has the offsets), suggested_text, reason and dollars_at_stake. Show 'This clause cost $X in March.' Redlines are suggestions; there's no send button." |
| U6 | `/scenario` | "Build /scenario: three example buttons from GET /scenario/examples fill the form; POST /scenario with {clause, charge} returns decision, finding, evidence, terms (each verified or rejected word for word) and rehearsal. Show the decision card like the board's, with its evidence. Allow up to 30 s, with a spinner." |
| U7 | `/audit` | "Build /audit: GET /audit lists every action (time, actor, action, object, evidence, hash) and a 'Verify chain' button calls GET /audit/verify and shows OK or the first broken row." |
| U8 | Copy fix | "Before 'Northmart pays' is pressed, the overview says 'Your March payment is being checked against the deal.' Say it's waiting for Northmart's payment instead, until the run starts." |

## Timeline, checkpoints and rules

| When (PDT) | You |
| --- | --- |
| Fri 11:30 PM–midnight | Sign-ups and keys |
| Midnight–2 AM | R1, then R2 |
| **1 AM checkpoint** | Keys sent; payment screen runs |
| 2–6 AM | Sleep |
| Sat 6 AM–noon | R3, R4; sponsor questions; Microsoft workshop at 10 |
| **Noon gate** | Board, evidence card and portal work on the fixture |
| Sat noon–4 PM | R5; quotes; Hyphenate mixer 2–4 PM |
| **4 PM checkpoint** | All screens exist; R7 if the stream is ready |
| Sat 4–9 PM | R6, R8 (deploy), polish |
| 9 PM | Record the clean run |
| **10 PM freeze** | Bug fixes only |
| Sat 10 PM–Sun 2 AM | Rough cut of the video |
| Sun 6–8:30 AM | Final cut and upload (unlisted) |
| Sun 10:30 AM | Present with Devank |

**Rules:**

- Work on your `web` branch; Devank merges at each checkpoint.
- One card per Claude Code session; run `npm run lint` and `npm run build` before committing.
- Big type, few words, no finance jargon on screen; it must work on a phone.
- Respect reduced-motion settings in every animation.
- Stuck for 45 minutes → tell Devank right away.
- By Saturday 9 PM, be able to run `make demo` and `make reset` alone.
