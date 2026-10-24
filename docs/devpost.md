# Devpost draft: Clawback

> DRAFT for Devank to approve Saturday night. Facts only from docs/design.md.
> Placeholders to fill: [EVAL SCORE], [WRONG AUTO ACTIONS], [QUOTE 1–3 with roles], [VIDEO URL], [LIVE URL],
> [REPO URL], [FIGMA FILE URL], [AGENT ADDRESS]. Tag a track only when its proof below exists.

**Title:** Clawback
**Tagline:** Wins back what distributors wrongly take, and never fights a fair charge
**Links:** Video [VIDEO URL] · Live [LIVE URL] · Code [REPO URL]

---

## Inspiration

Small food brands sell through big distributors, and the distributor pays each invoice short: it takes back promo
allowances and fees in the same payment. Checking each charge against the signed deal takes hours nobody has, so
the money is often just written off.

[QUOTE 1, with the person's role]

## What it does

Clawback is a finance agent for that check. In our demo, fictional Peak Bar Co. invoices fictional Northmart
$48,200 and receives $41,350. Clawback reads the promo deal, the emails and the store sales, and decides all six
charges:

- **Disputes $4,120 with proof:** a rate above the deal's $1.00 a bar, a week already paid on an earlier payment,
  units past the 5,000-bar cap, and a product the deal doesn't cover.
- **Accepts $2,730 as fair**, including a charge that looked wrong until it found the broker's email extending
  the promo.
- **Asks the owner one question**, about a display fee charged "at its discretion". The answer becomes Rule #1,
  and next month two fees are decided by that rule with no question asked.
- **Argues back live:** before filing, it predicts Northmart's comeback and checks it can answer it. When the
  judge, playing Northmart, attaches the signed amendment raising the cap, it concedes $1,000 and keeps $540
  disputed.
- **Records the result in QuickBooks** only after the controller approves the credit memo by SMS.
- **Rewrites next month's deal,** marking each weak clause with what it cost this month.

## How we built it

- **Two AI readers:** Claude and Gemini each read every document into typed terms with the exact sentence quoted.
  A term counts only if the quote is found word for word and both models agree; if they disagree, the charge goes
  to a person.
- **Code does the math:** a Python engine with unit tests computes what each charge should be (rates, product
  lists, dates, caps across weeks, duplicates). The AI never computes an amount.
- **A fixed decision gate** applies the owner's written policy in order: skip, ask, apply a saved rule, accept,
  dispute, or ask before filing over $5,000.
- **Four Claude roles:** Deal Reader, Investigator (one-line finding with evidence and confidence), Negotiator
  (rehearses the comeback, files the dispute, answers replies) and Deal Coach (redlines next month's draft).
  Every output is strict JSON validated by Pydantic and checked by code afterwards.
- **Stack:** FastAPI, Next.js + Tailwind + Framer Motion, Postgres on Tiger Data, server-sent events to a live
  board, Twilio SMS, the QuickBooks Online sandbox, a Capital One Nessie deposit as the trigger, Moss for rule
  matching, hosted on Vultr behind a GoDaddy domain.
- **DEMO_MODE** replays saved AI and QuickBooks responses, so the live demo never depends on Wi-Fi.

## What's real and what's simulated

- **Real:** the AI reading, the math, the decision rules, the QuickBooks sandbox writes, the SMS to real phones,
  the Nessie deposit, the eval score.
- **Simulated:** Peak Bar Co. and Northmart are fictional; we wrote the deal, emails and sales data; the
  distributor portal is our own mock.

## Proof: the eval

30 planted charges with the answer key written before the first run: 12 that should be disputed, 12 accepted and
6 asked about. They include the hard cases: a distributor email claiming a new rate, a broker's approved
extension, an undercharge, a fee within $1, vague wording where the readers disagree, and an overcharge above
$5,000.

**Score:** [EVAL SCORE] correct decisions out of 30, [N]/30 amounts right to the cent, [WRONG AUTO ACTIONS] wrong
automatic actions (target 0), [N] unnecessary questions.

## Challenges we ran into

- [Fill from the build: e.g. two models wording the same term differently, QuickBooks refresh tokens rotating,
  getting the cap math right across weeks.]

## Accomplishments that we're proud of

- It accepts fair charges: it never asks for more than the deal allows.
- Every number on screen opens its source: a sentence, a data row, a rule or a person.
- [Fill from the build.]

## What we learned

- [Fill from the build.]

## What's next

- Real distributor portals through browser automation, as recovery services already do.
- Adapters for NetSuite and Xero beside QuickBooks.
- The same approval and audit model, with SOC 2-style controls.

---

## Track paragraphs

### Hyphenate: Autonomous Systems for Finance

Clawback fills two finance seats: the deductions analyst and the collections specialist. It works from sources
that disagree (the deal, the broker's email, the distributor's own email, store sales and our promo plan), within
limited access: no agent can post to the books. A controller who did not propose a credit memo approves it, and if
they refuse, nothing posts and the board shows their note. Everything is traceable to a sentence, a row, a rule
or a person, and we report a real score on 30 planted charges: [EVAL SCORE] with [WRONG AUTO ACTIONS] wrong
automatic actions. Judges can paste their own clause and charge into the scenario box.

### Microsoft: Built for the Real World

- **Customer understanding:** small food and consumer brands that sell through big distributors, where the founder
  or a part-time bookkeeper checks deductions. [QUOTE 2, with role]
- **Measurable usefulness:** on the demo payment it disputes $4,120 and accepts $2,730 with one question, and the
  board is decided in under 60 seconds live. On the test set: [EVAL SCORE].
- **Path to production:** real portals through browser automation, ERP adapters (NetSuite, Xero) beside
  QuickBooks, and the same approval and audit model with SOC 2-style controls.
- **Responsible design:** two models must agree, quotes are checked word for word, all amounts come from tested
  code, an outbound filter blocks any figure not in a finding, documents are data and never instructions, and
  people approve every money movement.
- **End to end:** a deposit arrives, every charge is decided, disputes are filed and answered, the owner's
  question is asked once, and QuickBooks is updated after the controller says yes.

### Anthropic: Claude for Public Benefit

Our community is founders of small snack and natural-food brands selling through big distributors, who lose money
to deductions they don't have time to check. [QUOTE 3, with role] Claude does four jobs: reads each deal into
terms with exact quotes, explains each charge in one line with evidence and confidence, rehearses and writes the
dispute, and redlines next month's deal. **Where it could go wrong:** misreading a deal (two models must agree;
low confidence goes to a person; it concedes when shown a valid document); made-up numbers (amounts come only
from tested code); instructions hidden in documents (only approved senders or signed documents change a deal);
overreach (it can't post to the books or offer discounts or deadlines); squeezing the other side (it accepts fair
charges and undercharges); hidden decisions (every decision is cited, and the audit log is hash-chained).

### Figma

We designed in Figma before writing code: a FigJam storyboard of the architecture and demo, Figma Design frames
for the board, evidence card, portal, coach and results, a clickable Figma Make prototype for our first team
walkthrough, Figma Agent variants (dark theme, phone layout), and Dev Mode hand-off to our Next.js components.
Screenshots of each step: docs/figma/. File: [FIGMA FILE URL].

### Moss

Moss is Clawback's rule memory. When the owner answers a question once, the answer becomes a rule; Moss matches
new deal wording to saved rules, so a differently worded discretion clause next month still matches Rule #1 and
the owner isn't asked twice. [Before/after screenshot]

### MLH: Best Use of Gemini API

Gemini is our second deal reader. Every term must be read the same way by Claude and by Gemini; when the two
models differ, the charge goes to a person instead of being decided. [Disagreement example]

### MLH: Best Use of Tiger Data

All of Clawback's state lives in Postgres on Tiger Data. Store sales is a hypertable on the week, with a
continuous aggregate for running promoted units per promo, which is what the cap check reads. [Schema screenshot +
the cap query]

### MLH: Best Use of Vultr

The API and the web app run on a Vultr VM with Docker Compose, behind Caddy for HTTPS. [LIVE URL]

### MLH: Best Domain Name from GoDaddy Registry

Registered with the MLH code and pointed at our Vultr VM: [LIVE URL].

### Capital One: Best Use of Nessie

A Nessie deposit is the trigger: when Northmart's short $41,350 payment lands in Peak Bar Co.'s Nessie checking
account, Clawback starts the run and the board fills. [Clip of the deposit starting the run]

### Notability: Trust the Process

We planned in Notability: sketches of the flow and our standup notes across the weekend. [Screenshots]

### Fetch.ai: ASI:One Agent Challenge

Clawback Assistant is an agent registered on Agentverse with the Agent Chat Protocol, usable in ASI:One. The owner
asks "What did Northmart take this month?" and gets the totals and open disputes; it can also deliver the pending
owner question and take the answer. It is read-only otherwise and never approves money. Agent: [AGENT ADDRESS].
[ASI:One chat clip]

### Conditional (only if built and confirmed by Saturday 4 PM)

Elastic, Atlassian, Mana, SpaceXAI: add a paragraph only once the sponsor confirms and the proof exists.
