# Devpost draft: Clawback

> Draft for the Devpost page (locks Sun Oct 25, 9:00 AM PDT; submit by 8:30 AM). Written from docs/design.md,
> data/CLAUDE.md and what is merged on `main` as of Sat Oct 24, about 1:20 AM PDT.
> Markers: **[BUILT]** merged and tested on `main` · **[PLANNED]** in the plan, not built yet ·
> **[TODO]** a fact we still have to collect. Before submitting, remove every marker; delete any
> **[PLANNED]** line that is still not built, and fill every **[TODO]**.
> All people and companies in the demo are fictional; keep the word "fictional" wherever they appear.

**Title:** Clawback

**Tagline (Devank to pick):**
1. Wins back what distributors wrongly take, and never fights a fair charge. (from docs/design.md)
2. Every deduction checked against the deal, with proof.
3. The deductions analyst a small brand can't afford to hire.

**Project image:** the evidence card for C1 (deal sentence highlighted, the math line, the rehearsed comeback).

---

## Inspiration

When a small food brand sells through a big distributor, the distributor pays its invoices short. It takes
money back for promotions, display fees and other charges, and leaves the brand to work out whether each one
was allowed. Checking a single charge means finding the clause in the signed deal, the store sales for that
week, any email that changed the terms, and earlier payments that may already cover it. That takes hours a
founder doesn't have, so most charges are never checked. Suppliers have even sued over deductions; see the
class action against UNFI reported by Grocery Dive (link in Sources below).

**[TODO]** One or two real quotes from founders or bookkeepers at small brands (name or role, with permission).
Do not paste any quote we did not actually collect.

## What it does

Clawback is a finance agent that does the job of a deductions analyst. In our demo, the fictional snack brand
Peak Bar Co. invoices the fictional distributor Northmart **$48,200** for March and receives **$41,350**.
Northmart took **$6,850** across six charges. Clawback:

1. **Reads the deal and every change to it.** Two different AI models read the signed deal, the broker's
   email and the distributor's notices. Every term must come with a sentence copied word for word from the
   source, and both readers must agree on it.
2. **Computes what the deal allows.** Plain, tested code (not an AI) works out the allowed amount for each
   charge: rate, products covered, dates, the unit cap counted week by week, and earlier payments.
3. **Decides each charge.** It disputes **$4,120**, accepts **$2,730** as fair, and asks the owner **one
   question**:

| Charge | Taken | Decision | Why |
| --- | --- | --- | --- |
| C1 Week 1 promo | $1,800 | Split: $600 disputed, $1,200 accepted | Charged $1.50 a bar; the deal says $1.00 |
| C2 Week 2 promo | $980 | Dispute | Already paid on Mar 14 (NM-2178) |
| C3 Apr 1–7 promo | $330 | Accept | The approved broker extended the promo by email on Mar 28 |
| C4 Week 4 promo | $1,540 | Dispute | The 5,000-bar cap was reached in week 3 |
| C5 Mint promo | $1,000 | Dispute | Mint isn't in the deal |
| C6 Display fee | $1,200 | Ask the owner, then accept | The deal says "at its discretion" |

4. **Asks once, then remembers.** C6 depends on Northmart's discretion, so Clawback texts the owner. She
   answers "accept if notice is at least 14 days." That answer becomes Rule #1. In April, a $1,200 fee with
   18 days' notice is accepted and an $800 fee with 5 days' notice is disputed, with no question asked.
5. **Argues with the other side, and concedes when it's wrong.** Before filing dispute D-0417 it predicts
   Northmart's comeback for each line and checks it can answer it. When Northmart replies "there was no cap,"
   it answers with §3.2 and the week-by-week sales. When Northmart attaches a signed amendment raising the cap
   to 6,000 bars, it withdraws $1,000 of C4 and keeps $540 disputed.
6. **Lets only people move money.** The $2,730 credit memo goes to the controller for approval. If the
   controller says no, nothing posts and the board shows the note. After approval it writes the credit memo
   to QuickBooks and leaves the disputed $4,120 open with a note listing the D-0417 lines.
7. **Fixes next month's deal.** Deal Coach suggests edits to the summer draft, each showing what the weak
   clause cost in March.

Every number on screen opens its source: the deal sentence, the sales row, the email, the rule or the person
who approved it.

**Seats it fills:** deductions analyst and collections specialist.

## How we built it

- **Backend:** Python 3.11, FastAPI and Pydantic. Every AI output is strict JSON checked against a Pydantic
  schema; one retry with the error, then the item goes to Ask.
- **Money math** **[BUILT]**: `api/engine/allowed.py` computes the allowed amount per charge (product, dates,
  amendments, cap across weeks, duplicates). The decision gate (`api/engine/gate.py`) applies the owner's
  written policy (`config/policy.yaml`) in a fixed order of nine rows. Agents never compute amounts.
- **Quote check** **[BUILT]**: a term is used only if its quote is found in the source word for word (spacing
  and hyphens normalized) and every number in the term appears in that quote. A planted fake quote is
  rejected.
- **Deal Reader A (Claude)** **[BUILT]**: reads each document into typed terms with exact quotes and
  character offsets.
- **Deal Reader B (Gemini)** **[PLANNED]**: a second, independent read. If the two disagree on a term, any
  charge that uses it goes to the owner.
- **Investigator, Negotiator, Deal Coach (Claude)** **[PLANNED]**: the finding per charge, the rehearsed
  comeback and portal replies, and the redlines.
- **Outbound filter** **[BUILT]**: every dollar figure and quote in a message to Northmart must match a
  finding or a verified term; no promises, discounts or deadlines.
- **Audit log** **[BUILT]** (hash chain) **[PLANNED]** (page): every action is a row with its actor and
  evidence, chained by hash, so editing a past row breaks the check.
- **Replay layer** **[BUILT]**: every outside call has a timeout, one retry and a `DEMO_MODE` fallback that
  replays saved responses, so the demo runs with Wi-Fi off.
- **Frontend** **[PLANNED]**: Next.js, Tailwind and Framer Motion. The board streams decisions over
  server-sent events; the Northmart portal is a separately styled route we hand to the judge.
- **Integrations** **[PLANNED]**: QuickBooks Online sandbox (credit memo and open balance), Twilio SMS to the
  owner and controller, Capital One Nessie (the short deposit starts the run), Moss (rule matching), Postgres
  on Tiger Data (store sales as a hypertable).
- **Hosting** **[PLANNED]**: a Vultr VM with Caddy for HTTPS behind a GoDaddy domain.
- **Process:** we designed the screens in Figma first **[TODO: screenshots in docs/figma/]**, wrote every
  contract and a full fake run (`web/fixtures/`) in the first hour so the three of us could build in
  parallel, and logged every decision in `DECISIONS.md`.

**Real vs simulated.** Real: the AI reading, the math, the decision rules, the QuickBooks sandbox writes, the
SMS to real phones, the Nessie deposit, the eval score. Simulated: Peak Bar Co. and Northmart are fictional;
we wrote the deal, emails and sales data; the distributor portal is our own mock.

## Challenges we ran into

- **Keeping the AI away from the money.** It's tempting to let a model "work out" the allowed amount. We
  split the job: models only find and quote terms; tested code does all arithmetic; the gate decides.
- **Deals change by email.** The charge that looks wrong (C3, April dates) is fair because the broker
  extended the promo. A Northmart email claiming "the rate is $1.50" looks just as official but must never
  change the deal. We had to model who is allowed to change terms (§6.1 of the deal and the approved-sender
  list) instead of trusting whatever email arrived last.
- **Caps across weeks.** The cap is reached partway through the month, on charges paid in earlier
  remittances, so the engine has to count units across weeks and payments in date order.
- **Making it robust to bad Wi-Fi.** Every outside call goes through one replay layer, so the live demo can
  fall back to saved responses.
- **[TODO]** Anything that actually broke on Saturday (QuickBooks token rotation, Twilio trial limits, etc.).

## Accomplishments that we're proud of

- **[TODO: final eval numbers]** On 30 planted charges written before we ran it: X of 30 correct,
  Y questions, **Z wrong automatic actions**. (Engine-only run on Sat 1:20 AM, using the answer key's terms
  instead of AI reads: 30 of 30, 6 asked, 0 wrong. Report only the final full-pipeline number.)
- It accepts fair charges, including one that looked wrong until it found the email. It's not built to
  dispute everything.
- It concedes when shown a valid signed document.
- The worst failure is a question to a person, never a wrong payment.
- **[TODO]** Time from deposit to decided board (target: under 60 seconds live, under 20 in DEMO_MODE).

## What we learned

- Most of the value in finance automation is in the evidence trail, not the decision itself. A dispute only
  works if the other side can see the sentence, the sales row and the math.
- Having two models agree, plus a word-for-word quote check, catches mistakes that a single confident model
  doesn't.
- Separation of duties maps cleanly onto agents: the agent that proposes a credit memo can never be the one
  that approves it.
- **[TODO]** One honest lesson from each teammate.

## What's next for Clawback

- Real distributor and retailer portals through browser automation (recovery services already work this way).
- Adapters for NetSuite and Xero beside QuickBooks.
- The same approval and audit model, with least-privilege access to the books, no training on customer data,
  and per-brand isolation.
- Talking to more small-brand founders and bookkeepers to check the rules they'd want by default.

## Built with

Claude (Anthropic API), Gemini API **[PLANNED]**, Python, FastAPI, Pydantic, Next.js **[PLANNED]**,
Tailwind **[PLANNED]**, Framer Motion **[PLANNED]**, PostgreSQL / Tiger Data **[PLANNED]**,
QuickBooks Online API **[PLANNED]**, Twilio **[PLANNED]**, Capital One Nessie **[PLANNED]**,
Moss **[PLANNED]**, Vultr **[PLANNED]**, GoDaddy **[PLANNED]**, Caddy **[PLANNED]**, Docker **[PLANNED]**,
Figma **[PLANNED]**, Claude Code, pytest.

Only list a tool once it is really in the product.

## Track notes (one paragraph each; tag a track only when its proof exists)

- **Hyphenate:** sources that disagree (deal vs Northmart's email vs store sales), time (cap across weeks,
  amendment dates), limited access (only approved senders change a deal), a controller who can refuse, and
  proof of what's real (eval score, real vs simulated). Seats: deductions analyst, collections specialist.
- **Microsoft, Built for the Real World:** one short paragraph per criterion: customer understanding,
  measurable usefulness (**[TODO]** time saved vs checking by hand), path to production (see What's next),
  responsible design (see judge-qa.md, "Safety"), end to end.
- **Anthropic, Claude for Public Benefit:** the community is founders of small snack and natural-food brands
  selling through big distributors. Claude reads the deal (Reader A), explains each charge (Investigator),
  argues and concedes (Negotiator) and redlines the next deal (Deal Coach). Where it could go wrong: see the
  risks table in docs/design.md. **[TODO]** quotes with roles.
- **Figma, Moss, MLH (Gemini, Tiger Data, Vultr, GoDaddy), Capital One Nessie, Notability, Fetch.ai:** each
  needs the proof listed in the Track plan in docs/design.md before it is tagged. **[PLANNED]** for all.

## Links

- Video (unlisted): **[TODO]**
- Live URL: **[TODO]**
- Repo (public after the secrets scan, Sun before 8 AM): https://github.com/devank-yadav/clawback

## Sources

- Grocery Dive, class action against UNFI over supplier deductions:
  https://www.grocerydive.com/news/unfi-class-action-lawsuit-payment-discounts-grocery-natural-foods/732132/
- SPS Commerce, Walmart's dispute portal and deadlines:
  https://www.spscommerce.com/community/articles/walmart-apdp-portal-explained-best-practices
