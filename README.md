# Clawback

Clawback wins back what distributors wrongly take from a small brand's payment, and never fights a fair charge.
Built at Cal Hacks 13.0 for Hyphenate's "Autonomous Systems for Finance" prize. Every company and person in the demo
is fictional.

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
6. **Records the result in QuickBooks**, but only after the controller approves.
7. **Suggests edits to next month's deal**, each showing what the weak clause cost.

## The demo numbers (fictional)

Peak Bar Co. (fictional brand) bills Northmart (fictional distributor) **$48,200** for March and receives
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
| `make demo` | The same with `DEMO_MODE=true`: recorded AI answers, a labeled QuickBooks stand-in, no texts, no network needed. Keep `GEMINI_API_KEY` set so Gemini's recorded reads replay |
| `make test` | Every test in `api/`: engine, gate, sentence check, rules, outbound filter, audit chain, routes, pipeline, data files. Tests never call live services |
| `make eval` | Scores the 30 planted charges in engine mode and saves `eval/latest.json` |
| `make seed` | Creates the database tables and fills them from `data/` (store sales becomes a hypertable on Tiger Data), and seeds the QuickBooks sandbox when the `QBO_*` keys are set. Safe to run twice |
| `make reset` | Between demo runs: deletes what Clawback wrote to QuickBooks (INV-3102 goes back to $6,850 open), then clears runs, questions, rules, approvals and the portal thread |

Also: `make check-data` (the demo data and the eval set match the plan to the cent), `make acceptance` (the P0
acceptance tests), `make record` (the whole demo live, saving every AI answer for `DEMO_MODE`; costs API credits),
`make eval-agent` (agent-mode eval, live; costs API credits), `make deploy-check` (offline check of the deploy files).

To replay the agent-mode eval offline from its recordings: `DEMO_MODE=true python eval/run.py --mode agent`
(saves `eval/latest-agent.json`).

## What's real and what's simulated

- **Real:** the AI reading (Claude and Gemini), the math, the decision rules, the QuickBooks sandbox writes (checked
  live: credit memo applied, INV-3102 down to $4,120 open), the Nessie sandbox deposit that starts a run, texts
  through Twilio when its keys are set (SMS or Twilio's WhatsApp Sandbox), and the eval score.
- **Simulated:** Peak Bar Co., Northmart, Dana Okafor (owner), Sam Reyes (controller) and Jordan Lee (broker) are
  fictional; we wrote the deal, emails, notices, charges and sales. The Northmart portal is our own mock. In
  `DEMO_MODE`, AI answers are replayed and QuickBooks writes go to a stand-in labeled "Simulated".
- **Not yet:** a run reads the data files directly and keeps runs, rules and the audit log in memory; the database
  is seeded but not read at run time.

## Architecture

```
Nessie deposit ─▶ Readers: Claude + Gemini ─▶ sentence + agreement check (code) ─▶ math engine (code)
   ─▶ Investigator (Claude) ─▶ comeback rehearsal (Claude) ─▶ decision gate (code + owner policy + saved rules)
   ─▶ dispute D-0417 to the Northmart portal · one question to the owner · credit memo to the controller
   ─▶ QuickBooks sandbox (code, after approval) · every step streamed to the board and the hash-chained audit log
```

- **AI reads; code decides.** Claude runs Reader A, the Investigator, the Negotiator, the Deal Coach and the rule
  writer; Gemini runs Reader B, with a second Claude read if Gemini fails. Every answer is strict JSON checked by a
  Pydantic schema and then by code; one retry, then a person decides. No agent computes an amount or writes to the
  books.
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
data/     the fictional deal, emails, notices, charges, sales, prior payments, the 30-case eval set, recordings
scripts/  data checks and one-time integration scripts (QuickBooks seed, Nessie deposit, test SMS)
eval/     run.py (engine mode) and agent.py (agent mode)
config/   policy.yaml, the owner's policy
```

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
- **The controller approves money.** A credit memo over $1,000 needs the controller, never the owner or an agent. If
  the controller says no, nothing posts and their note shows on the card. Disputes over $5,000 wait for the owner.
- **The audit chain.** Every decision, question, answer, rule, approval, dispute, portal message and QuickBooks write
  is appended to a sha256 hash chain. `GET /audit/verify` recomputes it, so an edited, missing or reordered row
  breaks the check.
