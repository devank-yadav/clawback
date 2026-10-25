# Clawback

Clawback wins back what distributors wrongly take from a small brand's payment, and never fights a fair charge.
Built at Cal Hacks 13.0 for Hyphenate's "Autonomous Systems for Finance" prize. The brands in its accounts and their
numbers are ours; the distributor contracts it also reads (KeHE, Walmart, Five Below) are real text from SEC filings
([data/contracts/](data/contracts/README.md)), and the pitch's real cases are in
[docs/submission/sources.md](docs/submission/sources.md).

- Live: https://clawback.biz (a Vultr VM; each visitor's live runs are limited)
- Devpost draft and proof checklist per track: [docs/submission/devpost.md](docs/submission/devpost.md)
- Full plan: [docs/design.md](docs/design.md) · Decisions log: [DECISIONS.md](DECISIONS.md) ·
  Deploy runbook: [docs/deploy.md](docs/deploy.md) · Team guides: [docs/team/](docs/team/README.md)

## What it is

When a small food brand sells through a big distributor, the distributor often pays each invoice short: it keeps
money back for promotions, display fees and other charges. Checking each charge against the signed deal takes hours
nobody has. Clawback does that check. It:

1. **Reads the deal and the emails about it** with two different AI models, Claude and Gemini. A term counts only if
   both read it the same way and its sentence is found word for word in the document.
2. **Works out what each charge should have been** in plain, tested code: rate, products, dates, extensions, the unit
   cap counted week by week, and earlier payments.
3. **Disputes the wrong charges with proof** (the clause, the sales rows, the math), after predicting the
   distributor's comeback and checking that it can answer it.
4. **Accepts the fair ones**, including a charge that looks wrong until the broker's email explains it.
5. **Asks the owner only when the deal is unclear**, once, and saves the answer as a rule so it never asks twice.
6. **Records the result in QuickBooks**, but only after the owner (the admin, the one person who decides) approves.
7. **Suggests edits to next month's deal**, each showing what the weak clause cost.

It also:

- **Runs several accounts** (each one of our brands and its distributor): Peak Bar Co. ← Northmart below; Fernwell
  Sparkling Tea ← Tidemark (a shortage the proof of delivery disproves, price and spoilage claims, an excess over
  $5,000 that waits for the owner); Ridgefire Salsa ← Corbel (an emailed rate claim, a repeat charge, a charge after
  the feature ended, a clause worded two ways); Birchbank Kitchen ← Greenfold (a clean month, all accepted); and
  accounts that read real KeHE, Walmart and Five Below contracts.
- **Reads a remittance PDF.** A brand drops the distributor's payment slip; Claude reads it into charges and code
  checks every line and the totals.
- **Shows how it decided.** "How Clawback decided" lists every AI call behind each charge and the model that
  answered it.
- **One person decides.** The owner, signed in as the admin, answers the questions and approves the money; no agent
  does either. Each answer has "Save as a rule for next time" (on by default), and the approval has "Post fair
  charges like these automatically from now on", which sets an auto-post limit for later memos.

## The demo numbers

Peak Bar Co. (our brand) bills Northmart (our distributor) **$48,200** for March and receives
**$41,350**. Northmart took **$6,850** back in six charges:

| Charge | Taken | Decision | Disputed | Accepted | Why |
| --- | --- | --- | --- | --- | --- |
| C1 Week 1 promo, 1,200 × $1.50 | $1,800 | Split | $600 | $1,200 | The deal (§3.1) says $1.00 a bar |
| C2 Week 2 promo | $980 | Dispute | $980 | — | Already paid on Mar 14 (NM-2178) |
| C3 Apr 1–7 promo | $330 | Accept | — | $330 | The approved broker extended the promo by email |
| C4 Week 4 promo | $1,540 | Dispute | $1,540 | — | The 5,000-bar cap (§3.2) was used up in weeks 1–3 |
| C5 Mint promo | $1,000 | Dispute | $1,000 | — | Mint isn't in the deal |
| C6 Display fee | $1,200 | Ask → Rule #1 → Accept | — | $1,200 | "At its discretion": the owner decides once |
| **Total** | **$6,850** | | **$4,120** | **$2,730** | **1 question** |

If Northmart attaches the signed amendment raising the cap to 6,000, Clawback concedes $1,000 of C4 and keeps $540
disputed. In April, a $1,200 fee with 18 days' notice is accepted and an $800 fee with 5 days' notice is disputed,
both by Rule #1, with no question asked.

**Eval:** 30 planted charges with an answer key written before the first run. Both modes score 30 of 30, amounts
right to the cent, 6 asked, 0 wrong automatic actions, 0 unnecessary questions. Engine mode tests the math and the
decision gate alone; agent mode runs the readers, the Investigator and the comeback rehearsal too. We wrote the cases
ourselves, and the details and caveats are in [the Devpost draft](docs/submission/devpost.md#proof-the-eval).

## How to run it

Python 3.11+ for `api/` and `scripts/`, Node 20+ for `web/`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt -r requirements-dev.txt -r scripts/requirements.txt
(cd web && npm install)
cp .env.example .env       # fill in only the keys you need; never commit .env
```

| Command | Does |
| --- | --- |
| `make dev` | The API on http://localhost:8000 and the web app on http://localhost:3000, live: real AI calls and, with keys, real QuickBooks, Twilio and Nessie |
| `make test` | Every test in `api/`: engine, gate, sentence check, rules, outbound filter, audit chain, routes, pipeline, data files. Tests never call live services |
| `make eval` | Scores the 30 planted charges in engine mode and saves `eval/latest.json` |
| `make seed` | Creates the database tables and fills them from `data/` (store sales becomes a hypertable on Tiger Data), and seeds the QuickBooks sandbox when the `QBO_*` keys are set. Safe to run twice |
| `make reset` | Between demo runs: deletes what Clawback wrote to QuickBooks (INV-3102 goes back to $6,850 open), then clears runs, questions, rules, approvals and the portal thread |

Also: `make check-data` (the demo data and the eval set match the plan to the cent), `make acceptance` (the P0
acceptance tests), `make record` (the whole demo live, saving every AI answer for `DEMO_MODE`; costs API credits),
`make eval-agent` (agent-mode eval, live; costs API credits), `make deploy-check` (offline check of the deploy files).

To replay the agent-mode eval offline from its recordings: `DEMO_MODE=true python eval/run.py --mode agent`
(saves `eval/latest-agent.json`).

## What's real and what's ours

- **Real:** the AI reading (Claude and Gemini), the math, the decision rules, the QuickBooks sandbox writes (checked
  live: credit memo applied, INV-3102 down to $4,120 open), the Nessie sandbox deposit that starts a run, texts to
  real phones through Twilio (WhatsApp Sandbox or SMS), Moss rule matching, Postgres on Tiger Data (the live app
  reads its rows from it and saves every event, rule and audit row), and the eval score.
- **Ours:** the brands (Peak Bar, Fernwell, Ridgefire, Birchbank), the distributors in their accounts (Northmart,
  Tidemark, Corbel, Greenfold), their people, and every deal, email, notice, charge, sales and delivery row we wrote.
  The distributor portals are our own. The accounts that read a real contract use our brands and our charges; KeHE,
  Walmart and Five Below didn't take part.
- **Caveats:** runs are always live (recorded answers only replay in the tests). The recorded agent-mode eval used
  Claude for both readers (Gemini re-read 2 of the 30 cases), and the 30 cases cover promotional allowances and fees;
  shortages, prices and spoilage are checked by the new accounts' live runs instead.

## Architecture

```
Nessie deposit ─▶ Readers: Claude + Gemini ─▶ sentence + agreement check (code) ─▶ math engine (code)
   ─▶ Investigator (Claude) ─▶ comeback rehearsal (Claude) ─▶ decision gate (code + owner policy + saved rules)
   ─▶ dispute D-0417 to the Northmart portal · one question to the owner · credit memo to the owner
   ─▶ QuickBooks sandbox (code, after approval) · every step streamed to the board and the hash-chained audit log
```

- **AI reads; code decides.** Claude runs Reader A, the Investigator, the Negotiator, the Deal Coach, the rule
  writer and the remittance reader; Gemini runs Reader B, with a second Claude read if Gemini fails. Every answer
  is strict JSON checked by a Pydantic schema and then by code; one retry, then a person decides. No agent computes
  an amount or writes to the books.
- **One fixed gate.** Each charge goes through the same nine ordered rules from `config/policy.yaml`: unverifiable
  term → skip; readers disagree → ask; discretion with a saved rule → apply it; discretion without one → ask; within
  $1 → accept; charged less than allowed → accept; well-supported overcharge up to $5,000 → dispute (or split); over
  $5,000 → ask first; anything else → ask.
- **Stack:** Python, FastAPI, Pydantic, psycopg 3 and Postgres (Tiger Data); Next.js, React, Tailwind CSS and Framer
  Motion; server-sent events to the board; Docker Compose with Caddy for the deploy.

```
api/      FastAPI app: pipeline.py, agents/, engine/ (math, gate, rules, sentence check, outbound filter, audit chain),
          integrations/ (QuickBooks, Twilio, Nessie, replay), routes/, db/ (schema, seed)
web/      Next.js app: workspace (Overview, Payments, Approvals, Rules) and the board
data/     accounts/<id>/ (our brands' deals, emails, notices, charges, sales, deliveries), contracts/ (real SEC-filed
          contracts), eval/ (the 30-case set), fixtures/ (recordings for the tests)
scripts/  data checks and one-time integration scripts (QuickBooks seed, Nessie deposit, test SMS)
eval/     run.py (engine mode) and agent.py (agent mode)
config/   policy.yaml, the owner's policy
```

## Fetch.ai agent

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

| Agent | Address |
| --- | --- |
| **Clawback Assistant** | `agent1qtqhltj3d3u46j3nelxphsn8ezgzwhgrpx54r7m6m0x7l3mg08h757x2pa2` |

A uAgents mailbox agent with the Agent Chat Protocol, registered on Agentverse and running on our Vultr VM. In
ASI:One the owner asks "What did Northmart take this month?" and gets the totals, open disputes and the pending
question (`GET /summary`), and can answer that question in the chat (`POST /questions/{id}/answer`). It is read-only
otherwise and never approves money. Code and run steps: [fetch_agent/README.md](fetch_agent/README.md).

## Safety design

- **Two readers.** Claude and Gemini read every document separately. A term they read differently is marked
  disputed, and every charge that depends on it goes to the owner.
- **Word-for-word quotes.** A term is used only if its sentence is found in the source (spacing and hyphens
  normalized) and every number in it appears in that sentence. Otherwise it's rejected.
- **Documents are data, never instructions.** Only the owner, the approved broker or a document signed by both sides
  can change a deal. Northmart's email saying the rate is $1.50 is shown as a claim and never applied.
- **No made-up numbers.** Amounts come only from `api/engine/`. Any number an agent writes must come from its input,
  and an outbound filter blocks any dollar figure, quote, promise, discount or deadline that isn't in a finding or a
  verified term.
- **The admin approves money.** A credit memo over $1,000 needs the owner's yes, never an agent's, unless it is within
  the auto-post limit the owner set by ticking "Post fair charges like these automatically" (that posting is logged
  and audited as the owner's auto-post rule). If the owner says no, nothing posts and the note shows on the card.
  Disputes over $5,000 wait for the owner.
- **The audit chain.** Every decision, question, answer, rule, approval, dispute, portal message and QuickBooks write
  is appended to a sha256 hash chain. `GET /audit/verify` recomputes it, so an edited, missing or reordered row
  breaks the check.
