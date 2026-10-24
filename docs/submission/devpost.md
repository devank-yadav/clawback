# Devpost: Clawback

> **This is the one Devpost draft.** `docs/devpost.md` and `docs/submission/dev-post.md` point here.
> Checked against `main` at commit 53571d2 (Sat Oct 24, late morning), `DECISIONS.md` and `eval/published/`. Written
> for the product as it's being finished on Sat Oct 24: four accounts, new charge types (shortages, price mismatches,
> spoilage), every run generated live, "How Clawback decided", the remittance upload, and real roles with per-visitor
> limits. Those land from other sessions today, so Part 2 marks each one TODO until it's checked on clawback.biz.
> **Part 1** is the page text to paste into Devpost. **Part 2** is the proof checklist for each track. It's for
> us, so don't paste it. Fill in every **TODO (needs Devank)** or delete its line before submitting.
> Devpost locks Sun Oct 25 at 9:00 AM PDT; submit by 8:30 AM.
> **The app shows no "fictional" labels** (the accounts are styled like real businesses), so this page is where we
> say it. Keep the real-vs-simulated section and the word "fictional" next to every company and person.

## Before you submit (the Devpost checklist from docs/design.md)

| Item | Status |
| --- | --- |
| Title and tagline | Done (Part 1) |
| Project image: the evidence card for C1 | TODO (needs Devank): a screenshot of C1's evidence panel |
| Video link (unlisted, 2:30 or less, opens with the portal comeback) | TODO (needs Devank) |
| Live URL | Done: `https://clawback.biz`, live since Sat 7:45 AM (`DECISIONS.md`). Open it once before submitting |
| Public repo | TODO (needs Devank): make it public after the secrets scan, Sun before 8 AM |
| Problem, what it does, how we built it, challenges, what we learned, what's next | Done (Part 1); lessons from each teammate still TODO |
| The four accounts, the new charge types, the trace, the upload, the sign-ins and limits | TODO (needs Devank): check each against clawback.biz once merged, and fill in the account names and totals (Part 1, "Four accounts") |
| Hyphenate: seats it fills, real vs simulated, eval score, approvals and refusals | Done (Part 1) |
| Microsoft: one paragraph per criterion | Done (Part 1); time saved vs checking by hand and the live run time are TODO |
| Anthropic: the community, Claude's role in each agent, where it could go wrong | Done (Part 1); real quotes are TODO |
| Figma, Moss, MLH (Gemini, Tiger Data, Vultr, GoDaddy), Capital One, Notability, Fetch.ai | See Part 2: tag a track only when its proof exists |
| Tag every track we enter and confirm its criteria are met | TODO (needs Devank), from Part 2 |
| Submit by 8:30 AM and check that the page renders | TODO (needs Devank) |

---

# Part 1: the Devpost page

**Title:** Clawback

**Tagline:** Wins back what distributors wrongly take, and never fights a fair charge

**Links:** Video: TODO (needs Devank) · Live: https://clawback.biz · Code: https://github.com/devank-yadav/clawback

## Inspiration

When a small food brand sells through a big distributor, it often isn't paid in full. The distributor keeps part of
each payment to cover promotions, display fees, shortages, spoilage and other charges. The brand then has to work out
whether each charge was allowed. Checking one charge means finding the clause in the signed deal, the store sales or
delivery records for that week, any email that changed the terms, and earlier payments that may already cover it.
That takes hours a founder or a part-time bookkeeper doesn't have, so most charges never get checked. Suppliers have
even sued over it: see the class action against UNFI reported by
[Grocery Dive](https://www.grocerydive.com/news/unfi-class-action-lawsuit-payment-discounts-grocery-natural-foods/732132/).

TODO (needs Devank): one or two real quotes from small-brand founders or bookkeepers, with their role and their
permission. Don't paste a quote we didn't collect.

## What it does

Clawback is a finance agent that checks every charge a distributor takes out of a payment against the signed deal.
It disputes the wrong ones with proof, accepts the fair ones, asks the owner only when the deal is unclear, and
records the result in QuickBooks once the controller approves.

**Seats it fills: deductions analyst and collections specialist.**

### Four accounts, all generated live

The live site has four accounts, each a brand, its distributor and a month of charges. Every company is fictional,
styled to look like a real business; none is a customer. Each run on https://clawback.biz is generated live: both
AI readers, the plain-code math, the Investigator, the rehearsed comeback, the decision gate, the owner's question,
the controller's approval and the QuickBooks sandbox writes.

| Account (all fictional) | What it shows | Result |
| --- | --- | --- |
| Peak Bar Co. (snack bars) ← Northmart | The full story below: a rate above the deal, a charge already paid, an extension by email, a unit cap, a product the deal doesn't cover, and a fee left to the distributor's judgment | $4,120 disputed · $2,730 accepted · 1 question |
| TODO (needs Devank): name (a drinks brand) ← distributor | A shortage the delivery records disprove, a price mismatch that's partly right, spoilage above the deal's allowance, and an overcharge above $5,000 that waits for the owner's OK | TODO (needs Devank): from the screen |
| TODO (needs Devank): name ← distributor (a clean month) | Every charge is fair, so every charge is accepted. Clawback never fights a fair charge | TODO (needs Devank): from the screen |
| TODO (needs Devank): name ← distributor (a tough distributor) | A rate change the distributor claims in its own email (shown, never applied), a repeat charge, a charge outside the deal's dates, and a vague clause, so it asks | TODO (needs Devank): from the screen |

Charge types: promotional allowances, display and other fees, shortages, price mismatches and spoilage. Each is
checked against a second source: the deal's clauses, the store sales, the delivery records, the agreed price, the
deal's spoilage allowance, and earlier payments.

### The Peak Bar story

Peak Bar Co. (a fictional snack brand) bills Northmart (a fictional distributor) **$48,200** for March on invoice
INV-3102 and receives **$41,350**. Northmart took **$6,850** back in six charges. Clawback decides all six:

| Charge | Taken | Decision | Disputed | Accepted | Why |
| --- | --- | --- | --- | --- | --- |
| C1 Week 1 promo, 1,200 bars × $1.50 | $1,800 | Split | $600 | $1,200 | The deal (§3.1) says $1.00 a bar |
| C2 Week 2 promo | $980 | Dispute | $980 | — | Week 2 was already paid on Mar 14 (NM-2178) |
| C3 Apr 1–7 promo, 330 bars | $330 | Accept | — | $330 | The approved broker extended the promo by email on Mar 28 |
| C4 Week 4 promo, 1,540 bars | $1,540 | Dispute | $1,540 | — | The 5,000-bar cap (§3.2) was used up by weeks 1–3: 1,200 + 980 + 2,820 |
| C5 Mint promo, 1,000 bars | $1,000 | Dispute | $1,000 | — | Mint isn't one of the deal's products |
| C6 Display fee | $1,200 | Ask, then Rule #1, then Accept | — | $1,200 | §5.4 leaves the fee to Northmart's discretion, so the owner decides once |
| **Total** | **$6,850** | | **$4,120** | **$2,730** | **1 question** |

- **The email that turns a charge fair.** C3 looks wrong (April dates on a March promo), but the broker, Jordan Lee
  (fictional), is on the owner's list of people who can change the deal, and his Mar 28 email extended it through
  April 7. So Clawback accepts it. Northmart's own Mar 30 email ("Per our call, the Spring Promo rate is $1.50 per
  unit.") is shown as a claim and never applied, because Northmart can't change the deal by itself.
- **It asks once, then remembers.** The display fee is a judgment call, so Clawback asks the owner, Dana Okafor
  (fictional), one question. She answers "accept if notice is at least 14 days." Code turns that into Rule #1 and
  texts back "Saved: accept display fees with 14+ days' notice. Reply UNDO to cancel." In April, a $1,200 fee with
  18 days' notice is accepted and an $800 fee with 5 days' notice is disputed, both by Rule #1, with zero questions.
- **It rehearses the comeback, argues, and concedes with proof.** Before filing dispute D-0417 ($4,120, four lines),
  it predicts Northmart's likely reply to each line and files a line only if it can answer that reply from the
  evidence. On the Northmart portal, "there was no cap" gets §3.2 and the week-by-week sales back. When Northmart
  attaches the signed amendment raising the cap to 6,000 bars, Clawback withdraws $1,000 of C4 and keeps $540
  disputed. The totals become $3,120 disputed and $3,730 accepted.
- **Only the controller moves money.** The $2,730 credit memo (the QuickBooks entry for the accepted charges) waits
  for the controller, Sam Reyes (fictional). Only the controller's sign-in, or a text from the controller's phone,
  can approve it. If Sam says yes, it's written to QuickBooks and the disputed $4,120 stays unpaid on the invoice
  with a note listing the dispute lines. If Sam says no, nothing is written.
- **It fixes next month's deal.** The Deal Coach suggests edits to the summer draft. Each edit shows what that clause
  cost in March, for example $1,000 on §3.1, the product list, because Northmart charged for Mint.

### Every decision shows its proof

- **The evidence card.** Each charge shows the deal sentence, the math, the rehearsed comeback and its sources: the
  sales rows, the email, the rule or the person who approved it. Every number opens its source.
- **How Clawback decided.** Each charge also lists every AI call made for it, in order: which model answered (Claude
  or Gemini) and the check code ran on the answer. If Gemini didn't answer and a second Claude read stood in, it says
  so.
- **The audit log.** Every decision, question, answer, rule, approval, dispute, portal message and QuickBooks write
  goes into a hash-chained log. Editing a past row breaks the check.

### Bring your own payment slip

A brand can drop its distributor's remittance (the payment slip listing what was taken) as a PDF. Claude reads it into
charges, and code checks every line and the totals before Clawback uses them.

## How it works

One run, from the payment arriving to the books:

1. **The payment arrives.** Northmart's $41,350 deposit lands in Peak Bar Co.'s Capital One Nessie sandbox account.
   A poller checks every 5 seconds and starts the run. The "Northmart pays" button does the same thing if the poller
   isn't running. Or the brand uploads the payment slip as a PDF.
2. **Two models read the deal.** Claude (Reader A) and Gemini (Reader B) each read the deal and its emails into
   typed terms, each with the exact sentence it came from. Code keeps a term only if its sentence is found word for
   word in the document, every number in the term appears in that sentence, and both readers read the same thing.
   A term that fails the sentence check is rejected. A term the readers disagree on goes to a person.
3. **Code does the math.** A plain Python engine works out what each charge should have been: rate, products,
   dates, extensions, the unit cap counted week by week, earlier payments, and for the new charge types the
   delivery records, the agreed price and the spoilage allowance. No AI computes an amount.
4. **Claude explains each charge.** The Investigator writes a one-line finding with a confidence score and the IDs of
   the evidence it used. Code checks that every number it wrote came from its input and that every ID exists.
5. **A fixed gate decides.** Nine rules in order, from the owner's policy file: a deal that can't be verified is
   skipped; readers who disagree, a discretion clause with no saved rule, or a weak case go to the owner; a match
   within $1 or an undercharge is accepted; a well-supported overcharge up to $5,000 is disputed (or split); a bigger
   one goes to the owner first.
6. **People answer.** The owner gets one question by WhatsApp or SMS (or in the app, signed in as the owner) and the
   answer becomes a rule. The controller approves the credit memo by text or in the app, signed in as the controller.
7. **The books are updated.** Code, not an agent, writes the credit memo to the QuickBooks sandbox and notes the
   disputed balance on the invoice.

Every step streams live to the board, and "How Clawback decided" shows each AI call behind each charge.

## What's real and what's simulated

**Real:**

- **The AI reading.** Claude and Gemini read every document on the live site, and the trace shows which model
  answered each read. On the demo deal, both emails and the amendment they agreed on every term. Claude also runs the
  Investigator, the Negotiator, the Deal Coach, the rule writer and the remittance reader.
- **The math, the decision gate and the rules.** Plain Python with unit tests that reproduce every Peak Bar number.
- **QuickBooks sandbox writes.** Checked live in the sandbox: the controller's yes posted a $2,730 credit memo,
  applied it to INV-3102 (down to $4,120 open) and noted the disputed lines. `make reset` deletes those writes again,
  so INV-3102 goes back to $6,850 open.
- **The Nessie deposit.** Posted to Capital One's Nessie sandbox; a new Northmart deposit starts the run.
- **The texts.** Owner and controller messages go to real phones through Twilio's WhatsApp Sandbox (US carriers
  require a business registration before an app can text, and it wouldn't clear by Sunday), or SMS. The in-app inbox
  is the fallback.
- **The database.** On the live site the deal, charges, sales and earlier payments are read from Postgres on Tiger
  Data, every run's events are saved there, and a run replays after a restart.
- **Rule memory.** Saved rules are indexed in Moss and matched by meaning.
- **The eval score.** Computed by `eval/run.py` against an answer key written before the first run (below).

**Simulated:**

- Every brand and distributor in the four accounts is fictional, as are Dana Okafor, Sam Reyes and Jordan Lee. We
  wrote the deals, the emails, the notices, the charges, the sales and delivery data, and the sample payment slip.
- The Northmart portal is our own mock.
- Saved rules and the audit chain are still held in the app's memory (Moss holds a copy of each rule for matching).
  TODO (needs Devank): delete this line if they move into Postgres today.
- For a demo without Wi-Fi, our backup laptop runs `DEMO_MODE`, which replays AI answers recorded from live runs. In
  that mode, QuickBooks writes go to a stand-in and every one is labeled "Simulated" on screen. The live site doesn't
  use it.

## How approvals and refusals work

No agent can approve anything or write to the books. People approve money, and the person who approves is never the
one who proposed it.

| Action | Proposed by | Approved by | If the answer is no, or there's no answer |
| --- | --- | --- | --- |
| File a dispute totaling up to $5,000 | Negotiator | The owner's standing policy (set once in `config/policy.yaml`) | — |
| File a dispute totaling over $5,000 | Negotiator | The owner | Held as a draft |
| Credit memo over $1,000 for accepted charges | Bookkeeper (code) | The controller only, never the owner or an agent | Nothing posts; Sam's note shows on the card; Dana is told it was held |
| Credit memo of $1,000 or less | Bookkeeper (code) | The owner's standing policy | — |
| A new rule from the owner's answer | The gate | The owner, by answering; the confirmation offers UNDO | UNDO cancels the rule for next time |

- **Real roles.** In the app, only the controller's sign-in can approve a credit memo and only the owner's sign-in can
  answer the owner's question; one role's sign-in never works for the other. By text, only a reply from the
  controller's or owner's own number counts, and Twilio's signature is checked.
- **Per-visitor limits.** The site is public and every run spends real AI calls, so each visitor can start 3 live runs
  per 10 minutes and make 20 other AI requests (the scenario box, portal replies, the Deal Coach), and the whole site
  30 runs an hour.
- The $5,000 limit is checked twice: once per charge in the gate, and again on the whole dispute when it's filed,
  because several small lines can add up to more. D-0417 is $4,120, so it files on the owner's policy.
- After a yes, code writes the memo with one line per accepted charge, applies it to INV-3102, and notes the disputed
  lines on the invoice. Every write carries a request ID made from the approval ID, so a retry never posts twice.
- The owner's answer becomes a rule only for a discretion clause. "ACCEPT" or "DISPUTE" on its own settles that one
  charge and saves no rule. A reply the code can't read goes to Claude's rule writer, and if that can't read it
  either, the owner is asked again.
- The $1,000 conceded on C4 gets its own credit memo. At exactly $1,000 it posts on policy.

## Proof: the eval

We planted 30 charges in `data/eval/charges-30.csv` and wrote the answer key (`data/eval/answer-key.csv`) before the
first run: 12 the key says to dispute, 12 to accept, and 6 to ask about. They include the hard cases: Northmart's own
email claiming a change, broker extensions, an undercharge, a charge $0.60 over the deal (within the $1 tolerance),
vague wording, and an overcharge above $5,000.

| | Engine mode | Agent mode |
| --- | --- | --- |
| What it tests | The math engine and the decision gate alone. Each case row stands in for the AI: the deal terms come from the row, and a reader disagreement is simulated where the key expects one | The whole pipeline. Each case becomes a signed deal document (plus its email) that both readers read, then the Investigator and the comeback rehearsal run before the gate |
| Correct decisions | 30 of 30 | 30 of 30 |
| Amounts right to the cent | 30 of 30 | 30 of 30 |
| Asked a person | 6 | 6 |
| Wrong automatic actions (target 0) | 0 | 0 |
| Unnecessary questions | 0 | 0 |
| Readers | — | Recorded with Claude for both readers: Reader B was a second Claude call with its own prompt. Gemini re-read the two "vague wording" cases (E28, E29) afterwards |

A wrong automatic action means acting where the key says ask, disputing a fair charge, or accepting a wrong one.

To be clear about what this does and doesn't show:

- The agent-mode score was recorded live on Sat Oct 24 at 3:07 AM PDT, before Gemini answered on our key, so Reader B
  was a second Claude call and the score file says `two_models: false`. At 5:00 AM we re-read the two "vague
  wording" cases live with Gemini as Reader B. So this score shows two models on 2 of the 30 cases, not all of them.
  TODO (needs Devank): if the agent eval is re-run with Gemini on all 30, replace this paragraph with that score.
- Those two cases reached a person in two ways. On E29 ("its core bars"), Claude left the product list out as
  unclear and Gemini read it as "core bars", so the term was disputed and the owner was asked. On E28 ("a reasonable
  per-unit rate"), neither model would invent a rate, so the deal was incomplete and went to the owner. Full write-up:
  [docs/proof/gemini-vs-claude.md](../proof/gemini-vs-claude.md).
- We wrote the 30 cases ourselves, from templates. The deal written by someone outside the team
  (`data/eval/outside-deal.md`) is still a placeholder. TODO (needs Devank): run it cold and report terms found vs a
  key made by hand.
- The 30 cases cover promotional allowances and fees. Shortages, price mismatches and spoilage are in the accounts
  but not in the score. TODO (needs Devank): update this line if eval cases for them are added.
- So you don't have to trust our cases: the scenario box at https://clawback.biz/scenario takes a clause and a charge
  you write, and decides it live with both readers.

Rehearsal: 5 runs in a row in the browser with no manual fix, each ending at $4,120 disputed, $2,730 accepted and
1 question. Replaying recorded answers (`DEMO_MODE`), the board was decided 5.9 seconds after the deposit. TODO (needs
Devank): the same stopwatch on a live run on clawback.biz (target: under 60 seconds), and its AI cost.

## How we built it

- **Backend:** Python, FastAPI and Pydantic. One run streams every step to the browser as server-sent events, and a
  page refresh replays them.
- **Agents:** Claude for Reader A, the Investigator, the Negotiator, the Deal Coach, the rule writer and the
  remittance reader. Gemini for Reader B (`gemini-3.6-flash`, then `gemini-3.5-flash-lite` if it's busy), with a
  second Claude read if Gemini fails. Every agent returns strict JSON checked against a Pydantic schema. If the answer
  fails the check, the agent gets one retry with the error. If that fails too, the item goes to a person.
- **Checks after every agent (code):** sentences found word for word, numbers that match the engine's, evidence IDs
  that exist, remittance lines and totals that add up, and an outbound filter on every message to the distributor.
- **Money math:** `api/engine/`, plain Python with pytest tests for every number in the Peak Bar demo, the April fees
  and the $540 after the amendment.
- **Every outside call** (Claude, Gemini, Moss, QuickBooks, Twilio, Nessie) has a timeout and one retry. In
  `DEMO_MODE`, AI answers are replayed from `data/fixtures/` and QuickBooks writes go to a labeled stand-in.
- **Rule memory:** Moss (`moss-mediumlm` index) matches a new discretion clause to saved rules by meaning; an exact
  match on clause type and distributor is the fallback.
- **Frontend:** Next.js, React, Tailwind CSS and Framer Motion, following the same event stream.
- **Integrations:** QuickBooks Online sandbox (credit memo, linking payment, invoice note), Twilio (WhatsApp Sandbox
  or SMS), Capital One Nessie (deposit and poller).
- **Database:** Postgres on Tiger Data with no ORM (psycopg 3). `make seed` creates every table and fills it from the
  data files; store sales is a hypertable with a continuous aggregate that the cap query reads. The live app reads its
  rows from it and saves every event.
- **Deploy:** Docker Compose (API, web, Caddy for HTTPS) on a Vultr VM at clawback.biz, a GoDaddy Registry domain.
- **Roles and limits:** owner and controller sign-ins checked on every action, and per-visitor limits on live runs.
- **Assistant:** the Clawback Assistant, a Fetch.ai uAgents agent in ASI:One that reads the totals and can deliver the
  owner's question.
- **Process:** we wrote the data contracts and a full fake run with the exact demo numbers in the first hour, so the
  frontend and the data work could start while the agents were being built. We logged every decision in
  `DECISIONS.md`.

## Challenges we ran into

- **Keeping the AI away from the money.** We kept moving work out of the models and into tested code until the
  models only did what code can't: read deals that are all worded differently and notice when an email changes them.
- **Deals change by email.** C3 is fair because the approved broker extended the promo. Northmart's "the rate is
  $1.50" email looks just as official and must never change the deal. We had to model who is allowed to change terms
  instead of trusting the latest email.
- **The cap fills up across payments.** It's reached partway through the month, on charges paid in earlier payments,
  so the engine counts units week by week in date order.
- **Getting two models to answer.** Forcing a tool call returned an error on our Claude model, so Reader A uses
  structured outputs with a strict schema instead. On Gemini, one model had no quota on our key and another was no
  longer available. With the SDK's own retries on, a call that hit the rate limit waited through minutes of backoff
  and looked like a hang, so we turned them off and keep exactly one retry ourselves. That's also why our recorded
  agent eval ran with Claude as both readers.
- **Texts in the US.** Carriers require a business registration before an app can text, and it wouldn't clear this
  weekend. Texts go over Twilio's WhatsApp Sandbox instead, with the same webhook, and the in-app inbox is the
  fallback.
- **A public link that spends real money.** Every live run calls the AI many times, and anyone with the URL can start
  one. So approving money and answering the owner's question need that role's sign-in, and each visitor's live runs
  are limited.
- **Tests that reached the real world.** Early test runs used the real keys in `.env`: one reached the live Claude
  API and others left 28 stray credit memos in the QuickBooks sandbox. Now every test runs with the live keys
  blanked and real Claude clients blocked, and `make reset` deletes anything Clawback wrote to the sandbox.
- **A demo that survives bad Wi-Fi.** Replaying recorded AI answers only works if every request is exactly the same
  from run to run, so no run IDs go into a prompt and the payment keeps a fixed ID.

## Accomplishments that we're proud of

- 30 of 30 on the planted charges in both eval modes, with 0 wrong automatic actions (see the notes under Proof).
- Four accounts generated live on a public URL, including a clean month where every charge is accepted.
- It accepts fair charges: $2,730 for Peak Bar, including one that looked wrong until it found the email. It never
  asks for more than the deal allows.
- It backs down with proof: shown the signed amendment, it gives back $1,000 and keeps $540.
- A real QuickBooks sandbox write: the $2,730 credit memo applied to INV-3102, which dropped to $4,120 open, and a
  reset that puts the sandbox back to $6,850 open.
- Every AI call behind every charge is on screen, with the model that answered it.
- The worst failure is a question to a person, never a wrong payment.

## What we learned

- Most of the value in finance automation is the evidence trail. A dispute only works if the other side can see the
  sentence, the sales row and the math.
- Two models that must agree, plus a word-for-word sentence check, catch mistakes a single confident model doesn't.
- Separation of duties maps cleanly onto agents: whoever proposes a credit memo can never be the one who approves it.
- TODO (needs Devank): one honest lesson from each of Devank, Rishi and Manasv.

## What's next for Clawback

- Rules and the audit chain stored in the database too (runs already are), so everything survives a restart.
- The agent eval re-run with Gemini on every case, and eval cases for shortages, price mismatches and spoilage.
- Getting distributors' payment slips straight from email, beside today's upload.
- Real distributor portals through browser automation, as recovery services already do.
- Adapters for NetSuite and Xero beside QuickBooks.
- The same approval and audit model, with least-privilege access to the books, no training on customer data, and
  each brand's data kept separate.
- More conversations with small-brand founders and bookkeepers about the rules they'd want by default.

## Built with

Claude (Anthropic API), Gemini API, Python, FastAPI, Pydantic, pytest, Next.js, React, Tailwind CSS, Framer Motion,
PostgreSQL (psycopg 3), Tiger Data, Moss, QuickBooks Online API, Twilio, Capital One Nessie, Fetch.ai uAgents,
Docker, Caddy, Vultr, GoDaddy Registry.

Add Figma only once Part 2 says its proof exists.

## Hyphenate: Autonomous Systems for Finance

Clawback fills two finance seats: the deductions analyst and the collections specialist. It works from sources that
disagree: the signed deal, the broker's email, the distributor's own email, the payment slip, the store sales,
delivery records and earlier payments, and two AI models that must read each term the same way. Time matters: the
cap fills up week by week, an extension changes which dates count, and a fee needs enough notice. Access is limited:
only the owner, the approved broker or a document signed by both sides can change a deal; only the controller's
sign-in can approve money and only the owner's can answer the owner's question; no agent can approve money or write
to the books. The controller can refuse: if Sam says no, nothing posts and Sam's note shows on the card. Every
decision names its gate rule, its evidence and, when people were involved, the person, and "How Clawback decided"
shows every AI call behind it. Four accounts run live, including a clean month where every charge is accepted. We
report a real score (30 of 30 in both eval modes, 0 wrong automatic actions, with the caveats in Proof), let you test
your own clause in the scenario box, and say plainly what's real and what's simulated.

## Microsoft: Built for the Real World

**Customer understanding.** Our customer is a small food or drink brand that sells through big distributors, where
the founder or a part-time bookkeeper checks every short payment by hand, if at all. They don't need another
dashboard. They need each charge settled with proof, the fair ones accepted without a fight, and one question when
the deal is genuinely unclear. They get the distributor's payment slip as a PDF, not a spreadsheet, so that's what
Clawback reads. TODO (needs Devank): a real quote, with the person's role.

**Measurable usefulness.** On the Peak Bar payment, Clawback decides all six charges: $4,120 disputed with evidence,
$2,730 accepted, and one question to the owner. In rehearsal it ran 5 times in a row with no manual fix, and
replaying recorded answers the board was decided 5.9 seconds after the deposit. On 30 planted charges it scored 30 of
30, amounts right to the cent, with 0 wrong automatic actions in both eval modes. TODO (needs Devank): a live run's
time and AI cost, and the time saved vs checking the same six charges by hand, measured.

**Path to production.** Clawback starts from what a brand already has: the payment slip (upload the PDF), the signed
deal and its emails, and QuickBooks through Intuit's API. None of it needs a distributor's portal login. The parts
that would change are at the edges: disputes sent by email or through real portals with browser automation (recovery
services already work this way), adapters for NetSuite and Xero beside QuickBooks, and rules and the audit chain
moved into the database beside the runs. The core stays the same: two readers, tested math, a fixed gate, and
people approving money, with sign-ins per role, least-privilege access to the books and each brand's data kept
separate.

**Responsible design.** Two models must agree on every term, and every term's sentence must be found word for word.
All amounts come from tested code, and an outbound filter blocks any dollar figure, quote, promise, discount or
deadline that isn't in a finding or a verified term. Documents, emails and portal replies are treated as data, never
instructions. Only approved senders or signed documents can change a deal. A credit memo over $1,000 needs the
controller's sign-in, every AI call is shown per charge, and every action goes into a hash-chained audit log.

**End to end.** A short payment arrives in Nessie (or the brand uploads the payment slip), the run starts, both
models read the deal, code computes every charge, Claude explains each one, the gate decides, dispute D-0417 is
filed, the owner answers one question that becomes a rule, the controller approves the credit memo, and QuickBooks
is updated. Then Northmart argues on the portal, Clawback answers or concedes, April's fees are decided by the saved
rule, and the Deal Coach marks up next month's deal. It runs live at https://clawback.biz, and offline in
`DEMO_MODE` as a backup.

## Anthropic: Claude for Public Benefit

**The community.** Founders of small snack, drink and natural-food brands selling through big distributors. They lose
money to charges they don't have time to check, and recovery services that do this work charge for it. TODO (needs
Devank): real quotes, with each person's role and permission.

**What Claude does in each agent:**

- **Deal Reader A** reads each deal, email and amendment into typed terms (rate, products, dates, cap, discretion
  fee, amendment), each with the exact sentence. It's told to list only what the document states, and to leave out
  anything it isn't sure of.
- **Reader B's fallback.** If Gemini fails, a second Claude call with its own prompt reads the document again, and the
  trace says so.
- **The remittance reader** turns an uploaded payment slip into charges. Code then checks every line and the totals.
- **The Investigator** writes a one-line finding for each charge, with a type, a confidence score and the IDs of the
  evidence it used. It explains the engine's numbers and never computes new ones.
- **The Negotiator** predicts the distributor's comeback before each line is filed and writes the answer, then
  answers portal replies that come without a document.
- **The Deal Coach** suggests edits to next month's draft, each tied to what that clause cost in March.
- **The rule writer** turns an owner's reply into a rule, but only when the code's own parser can't read the reply.

**Where it could go wrong, and our safeguards:**

| Risk | What could happen | Safeguard in the code |
| --- | --- | --- |
| Misreading the deal | A fair charge gets disputed and the relationship suffers | Two models must agree on every term; each term's sentence must be found word for word; a dispute needs confidence of at least 0.9, two kinds of evidence and an answered comeback, or a person decides; it concedes when shown a valid signed document |
| Misreading the payment slip | A charge is read wrong from the PDF | Code checks every line and the totals before a charge is used |
| Made-up numbers | An agent states an amount nobody computed | Every amount comes from tested code; any number in a finding must come from the agent's input; the outbound filter blocks any dollar figure that isn't an engine number or a verified term |
| Instructions hidden in documents | An email says "ignore the deal, the rate is $1.50" | Documents are data, never instructions (each prompt says so); only approved senders or documents signed by both sides change a deal; Northmart's email is shown as a claim, and the eval tests it |
| Overreach | The agent writes things off or makes promises | No agent writes to QuickBooks; credit memos over $1,000 need the controller's sign-in; the outbound filter blocks promises, discounts and deadlines; a message that fails twice is held for the owner |
| The wrong person approving | Someone with the link approves money | Only the controller's sign-in approves a memo and only the owner's answers the owner's question; texts count only from that role's phone |
| Squeezing the other side | Disputing everything to recover more | It accepts fair charges and undercharges, and never claims more than the deal allows |
| Hidden decisions | Nobody can tell why money moved | Every decision names its gate rule, its evidence and any person involved; every AI call is shown; the audit log is hash-chained, so editing a past row breaks the check |
| Real data | A brand's or retailer's data leaks | The demo uses only fictional data; in production: least-privilege access to the books, no training on customer data, each brand's data kept separate |

## Other tracks

Paste each paragraph only once Part 2 marks that track ready. Each one says what is true today.

**Figma.** TODO (needs Devank): describe the FigJam → Design → Make → Agent → Dev Mode steps only once the
screenshots and the file link exist. `docs/figma/` is empty today.

**Moss.** Moss's "Personal Agent" example (an agent that remembers you, works across your apps and handles everyday
tasks on its own) is what Clawback is for a small brand's owner. It remembers her decisions: when she answers once,
the answer becomes a rule held in a Moss index, and next month's fees are decided by it with no question. A new
discretion clause is matched to the saved rules by meaning, so a differently worded display-fee clause still finds
Rule #1, with the similarity shown on the card (`api/integrations/moss.py`, index model `moss-mediumlm`). Measured
live: Rule #1's own sentence and a reworded display-fee clause score 1.00, a late-delivery penalty 0.79, a spoilage
fee 0.67 and the promo-rate clause 0.35; the gate takes a match only at 0.85 or more, with the same kind of clause
and the same distributor, and otherwise falls back to matching clause type and distributor. Honest limit: Moss also
scores other similar discretionary fees (a slotting fee, a circular-ad fee) at 1.00, so it can't yet tell those
apart.

**MLH: Best Use of Gemini API.** Gemini is Clawback's second deal reader. Claude and Gemini read every document
separately, and a term only counts when both read the same type and numbers and the sentence is found word for word.
When they disagree, every charge that depends on that term goes to the owner instead of being disputed. On the demo
deal, both emails and the amendment, Gemini agreed with Claude on every term. On a vaguely worded test deal ("$1.00
per unit on its core bars"), Claude left the product list out as unclear and Gemini read it as "core bars", so the
term was disputed and Clawback asked the owner whether Chocolate counts, instead of deciding $1,200 on its own:
[the full example](https://github.com/devank-yadav/clawback/blob/main/docs/proof/gemini-vs-claude.md). On the live
site, "How Clawback decided" names the model behind every read.

**MLH: Best Use of Tiger Data.** Clawback's data lives in Postgres on Tiger Data: the deal, charges, sales and earlier
payments the live app reads, and every run's events. Weekly store sales is a hypertable on the week, with a
continuous aggregate of promoted units, and the cap check is a time query: add up promoted bars week by week until
the 5,000-bar cap is reached (`GET /api/db/cap` answers from it). TODO (needs Devank): the schema screenshot and the
cap query's output from the Tiger Data service before this goes in.

**MLH: Best Use of Vultr.** The API, the web app and Caddy (for HTTPS) run with Docker Compose on a Vultr VM, live at
https://clawback.biz.

**MLH: Best Domain Name from GoDaddy Registry.** clawback.biz, registered with the MLH code and pointed at our Vultr
VM, serving the app over HTTPS.

**Capital One: Best Use of Nessie.** The short payment is a real Nessie deposit. When Northmart's $41,350 lands in
Peak Bar Co.'s Nessie checking account, a poller that checks every 5 seconds starts the run and the board fills.
TODO (needs Devank): the clip of a deposit starting the run.

**Notability: Trust the Process.** TODO (needs Devank): planning sketches and standup notes from Notability.

**Fetch.ai: ASI:One Agent Challenge.** The Clawback Assistant (`fetch_agent/`) is a uAgents agent with the Agent
Chat Protocol, registered on Agentverse: the owner asks it in ASI:One what Northmart took and gets the totals, open
disputes and the pending question, and can answer that question in the chat. It's read-only otherwise and never
approves money. Agent address: `agent1qtqhltj3d3u46j3nelxphsn8ezgzwhgrpx54r7m6m0x7l3mg08h757x2pa2`. TODO (needs
Devank): an ASI:One chat clip.

---

# Part 2: proof checklist per track

What Devpost must show comes from the Track plan and Added tracks in `docs/design.md`. "In the repo now" is
checked against commit 53571d2 and `DECISIONS.md`. Tag a track on Devpost only when every row says it exists.

### Built today (check each on clawback.biz before pasting Part 1)

| Part 1 says | In the repo now? |
| --- | --- |
| Four accounts, each with its own run | TODO (needs Devank): merged, and the names and totals filled into Part 1's account table |
| Shortages, price mismatches and spoilage checked against delivery records, the agreed price and the spoilage allowance | TODO (needs Devank): merged with engine tests, and Part 1's wording matches what the engine checks |
| Every run generated live on clawback.biz | Yes for Peak Bar (the VM runs with `DEMO_MODE=false`, `DECISIONS.md` Sat 6:45 AM). TODO (needs Devank): the other three accounts |
| "How Clawback decided": every AI call per charge, with the model that answered | TODO (needs Devank): merged, and the fields on screen match Part 1 |
| Remittance upload: Claude reads the PDF, code checks every line and the totals | TODO (needs Devank): merged, and a sample PDF in the repo |
| Only the controller's sign-in approves, only the owner's answers | Yes: `api/auth.py` (`OWNER_TOKEN`, `CONTROLLER_TOKEN`), `api/tests/test_auth.py`, `DECISIONS.md` Sat 10:50 AM. TODO (needs Devank): the sign-in screens |
| 3 live runs per visitor per 10 minutes, 20 other AI requests, 30 runs an hour site-wide | Yes: `api/auth.py` defaults, on the deployed site (`DECISIONS.md` Sat 10:50 AM) |
| Saved rules and the audit chain held in memory | Yes, true at 53571d2 (`api/pipeline.py`, `api/audit.py`). Delete that line in Part 1 if they move to Postgres |

### Hyphenate (main prize)

| Devpost must show | In the repo now? |
| --- | --- |
| "Seats it fills: deductions analyst and collections specialist" | Yes: Part 1, What it does |
| Real vs simulated | Yes: Part 1 |
| The eval score | Yes: 30/30 in both modes, `eval/published/engine.json` and `eval/published/agent.json` (agent: readers Claude + Claude, `two_models: false`); regenerate with `make eval` and `DEMO_MODE=true python eval/run.py --mode agent` |
| How approvals and refusals work | Yes: Part 1; refusal tested in `api/tests/test_books.py`, roles in `api/tests/test_auth.py` |
| Live scenario box for a judge's own clause | Yes: the `/scenario` screen over `POST /scenario`, both readers live, with three recorded examples. TODO (needs Devank): the test on 5 unseen clauses written by a non-teammate |
| The judge arguing as Northmart on the portal | Yes: the `/portal` screen (Northmart's look) with five presets; attaching the signed amendment concedes $1,000 and keeps $540 |
| Video opening with the moment | TODO (needs Devank): video link |
| Every number on the evidence card opens its source | Yes: live runs link every math step to its evidence (`DECISIONS.md` Sat 7:20 AM). Click through C1 once on clawback.biz |

### Microsoft: Built for the Real World

| Devpost must show | In the repo now? |
| --- | --- |
| A paragraph per criterion: customer understanding, measurable usefulness, path to production, responsible design, end to end | Yes: Part 1 |
| Time saved vs checking by hand | TODO (needs Devank): a measured number |
| A live run's time and AI cost | TODO (needs Devank): measured on clawback.biz |
| A real customer quote | TODO (needs Devank) |
| Production path (no portal login needed, portals via browser automation, ERP adapters, SOC 2-style controls) | Yes: Part 1 |

### Anthropic: Claude for Public Benefit

| Devpost must show | In the repo now? |
| --- | --- |
| The named community | Yes: Part 1 |
| Real quotes, with roles | TODO (needs Devank). The cut rule says to drop this track if there are no real quotes by Sat noon |
| Claude's role in each agent | Yes: Part 1 (the remittance reader once the upload is merged) |
| Where it could go wrong, and the safeguards | Yes: Part 1 |

### Figma

| Devpost must show | In the repo now? |
| --- | --- |
| Screenshots of each step: FigJam → Design → Make → Agent → Dev Mode | TODO (needs Devank): `docs/figma/` is empty |
| The Figma file link | TODO (needs Devank) |
| Claude Code reading a Figma frame through Figma's MCP server (Added tracks) | TODO (needs Devank): screenshot |

### Moss

| Devpost must show | In the repo now? |
| --- | --- |
| Before/after: a differently worded clause matched to Rule #1 | Yes, live (Oct 24): `python -m api.integrations.moss` on the `clawback-rules` index (`moss-mediumlm`) scores Rule #1's own §5.4 sentence 1.00, a reworded display-fee clause ("in its sole judgment … once it has told Supplier in writing") 1.00, a late-delivery penalty 0.79, a spoilage fee 0.67 and the promo-rate clause 0.35; the 0.85 floor sits between them. March and April are recorded with Moss, so the card reads "matched by Moss, similarity 1.00" offline too. Honest limit: Moss scores any similar discretionary fee (a slotting fee, a circular-ad fee) at 1.00 as well. TODO (needs Devank): screenshot the scenario box with the reworded clause |

### MLH: Best Use of Gemini API

| Devpost must show | In the repo now? |
| --- | --- |
| Gemini as Reader B | Yes: `api/agents/reader_b.py`; recorded Gemini reads in `data/fixtures/gemini-reader/` |
| An example where the two models differ and the charge goes to Ask | Yes: [docs/proof/gemini-vs-claude.md](../proof/gemini-vs-claude.md). Eval case E29, recorded live: Claude left the products out, Gemini read "core bars", gate row 2 asked the owner. Replay with `DEMO_MODE=true python eval/run.py --mode agent --cases E28,E29` (needs `GEMINI_API_KEY` set, or Reader B replays as Claude) |
| The run naming Gemini | Yes in the feed when Gemini answers. TODO (needs Devank): a screenshot of "How Clawback decided" with a Gemini row from clawback.biz |

### MLH: Best Use of Tiger Data

| Devpost must show | In the repo now? |
| --- | --- |
| The schema | Yes: `api/db/migrations/001_init.sql` and `002_source_rows.sql` (every table in the data model, plus events); `make seed` applies it and is safe to run twice |
| `store_sales` as a hypertable and the cap query | Yes: hypertable on `week_start`, the `promo_units_weekly` continuous aggregate, `GET /api/db/cap` on the VM (`DECISIONS.md` Sat 9:45 AM). TODO (needs Devank): a screenshot of the schema and the cap query from the Tiger Data service |
| The app using the database | Yes: the VM reads its rows from Postgres and saves every event (PR #57, `DECISIONS.md` Sat 9:45 AM) |

### MLH: Best Use of Vultr

| Devpost must show | In the repo now? |
| --- | --- |
| The app running on a Vultr VM | Yes: Vultr VM, Docker Compose, Caddy (`docs/deploy.md`, `DECISIONS.md` Sat 7:45 AM) |
| The live URL | Yes: `https://clawback.biz`, smoke check passing (`DECISIONS.md` Sat 7:45 AM). Open it before submitting |

### MLH: Best Domain Name from GoDaddy Registry

| Devpost must show | In the repo now? |
| --- | --- |
| The domain | Yes: clawback.biz, registered with the MLH code (`DECISIONS.md`, Oct 24 3:36 AM) |
| The URL serving the app | Yes: HTTPS certificates for clawback.biz and www (`DECISIONS.md` Sat 7:45 AM) |

### Capital One: Best Use of Nessie

| Devpost must show | In the repo now? |
| --- | --- |
| A short deposit starting the run | Code yes: `api/integrations/nessie.py` (poller every 5 s), `POST /payments/northmart`, `scripts/nessie_deposit.py`; the VM runs the poller (`DECISIONS.md` Sat 7:45 AM) |
| The clip of a deposit starting the run | TODO (needs Devank). The call that lists deposits couldn't be checked against Nessie's docs (they answered 403), so confirm it with the keys while recording |

### Notability: Trust the Process

| Devpost must show | In the repo now? |
| --- | --- |
| Screenshots of planning sketches and standup notes | TODO (needs Devank) |

### Fetch.ai: ASI:One Agent Challenge

| Devpost must show | In the repo now? |
| --- | --- |
| The agent registered on Agentverse, with the Agent Chat Protocol, usable in ASI:One | Yes: `fetch_agent/` (uAgents mailbox agent, Chat Protocol), running on the VM as the `clawback-agent` service and registered on Agentverse (`DECISIONS.md` Sat 9:45 AM) |
| The API it calls | Yes: `GET /summary` (read-only, needs `CLAWBACK_READONLY_TOKEN`) and `POST /questions/{id}/answer` (with the owner's token) |
| The agent address | Yes: `agent1qtqhltj3d3u46j3nelxphsn8ezgzwhgrpx54r7m6m0x7l3mg08h757x2pa2` |
| An ASI:One chat clip | TODO (needs Devank). Cut rule: not live in ASI:One by Sat 8 PM |

### Not entered unless confirmed by Sat 4 PM

Elastic, Atlassian, Mana and SpaceXAI: nothing for them is in the repo. Add a paragraph only once the sponsor
confirms and the proof exists.
