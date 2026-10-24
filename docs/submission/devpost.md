# Devpost: Clawback

> **This is the one Devpost draft.** `docs/devpost.md` and `docs/submission/dev-post.md` point here.
> Checked against the code on `main` at commit f55757a (Sat Oct 24 morning), `DECISIONS.md`, and
> `eval/latest.json` / `eval/latest-agent.json` regenerated from that commit.
> **Part 1** is the page text to paste into Devpost. **Part 2** is the proof checklist for each track. It's for
> us, so don't paste it. Fill in every **TODO (needs Devank)** or delete its line before submitting.
> Devpost locks Sun Oct 25 at 9:00 AM PDT; submit by 8:30 AM.
> Every person and company in the demo is fictional. Keep the word "fictional" wherever they appear.

## Before you submit (the Devpost checklist from docs/design.md)

| Item | Status |
| --- | --- |
| Title and tagline | Done (Part 1) |
| Project image: the evidence card for C1 | TODO (needs Devank): a screenshot of C1's evidence panel |
| Video link (unlisted, 2:30 or less, opens with the portal comeback) | TODO (needs Devank) |
| Live URL | TODO (needs Devank): `https://clawback.biz` serving the app. Not checked from here: this session's network can't reach it |
| Public repo | TODO (needs Devank): make it public after the secrets scan, Sun before 8 AM |
| Problem, what it does, how we built it, challenges, what we learned, what's next | Done (Part 1); lessons from each teammate still TODO |
| Hyphenate: seats it fills, real vs simulated, eval score, approvals and refusals | Done (Part 1) |
| Microsoft: one paragraph per criterion | Done (Part 1); time saved vs checking by hand is TODO |
| Anthropic: the community, Claude's role in each agent, where it could go wrong | Done (Part 1); real quotes are TODO |
| Figma, Moss, MLH (Gemini, Tiger Data, Vultr, GoDaddy), Capital One, Notability, Fetch.ai | See Part 2: tag a track only when its proof exists |
| Tag every track we enter and confirm its criteria are met | TODO (needs Devank), from Part 2 |
| Submit by 8:30 AM and check that the page renders | TODO (needs Devank) |

---

# Part 1: the Devpost page

**Title:** Clawback

**Tagline:** Wins back what distributors wrongly take, and never fights a fair charge

**Links:** Video: TODO (needs Devank) · Live: TODO (needs Devank) · Code: https://github.com/devank-yadav/clawback

## Inspiration

When a small food brand sells through a big distributor, it often isn't paid in full. The distributor keeps part of
each payment to cover promotions, display fees and other charges. The brand then has to work out whether each charge
was allowed. Checking one charge means finding the clause in the signed deal, the store sales for that week, any
email that changed the terms, and earlier payments that may already cover it. That takes hours a founder or a
part-time bookkeeper doesn't have, so most charges never get checked. Suppliers have even sued over it: see the class
action against UNFI reported by
[Grocery Dive](https://www.grocerydive.com/news/unfi-class-action-lawsuit-payment-discounts-grocery-natural-foods/732132/).

TODO (needs Devank): one or two real quotes from small-brand founders or bookkeepers, with their role and their
permission. Don't paste a quote we didn't collect.

## What it does

Clawback is a finance agent that checks every charge a distributor takes out of a payment against the signed deal.
It disputes the wrong ones with proof, accepts the fair ones, asks the owner only when the deal is unclear, and
records the result in QuickBooks once a person approves.

**Seats it fills: deductions analyst and collections specialist.**

In our demo, Peak Bar Co. (a fictional snack brand) bills Northmart (a fictional distributor) **$48,200** for March
on invoice INV-3102 and receives **$41,350**. Northmart took **$6,850** back in six charges. Clawback decides all six:

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
  April 7. So Clawback accepts it. Northmart's own Mar 30 email ("Per our call, the Spring Promo rate is $1.50 per unit.") is shown as a
  claim and never applied, because Northmart can't change the deal by itself.
- **It asks once, then remembers.** The display fee is a judgment call, so Clawback asks the owner, Dana Okafor
  (fictional), one question. She answers "accept if notice is at least 14 days." Code turns that into Rule #1 and
  texts back "Saved: accept display fees with 14+ days' notice. Reply UNDO to cancel." In April, a $1,200 fee with
  18 days' notice is accepted and an $800 fee with 5 days' notice is disputed, both by Rule #1, with zero questions.
- **It rehearses the comeback, argues, and concedes with proof.** Before filing dispute D-0417 ($4,120, four lines),
  it predicts Northmart's likely reply to each line and files a line only if it can answer that reply from the
  evidence. On the Northmart portal, "there was no cap" gets §3.2 and the week-by-week sales back. When Northmart
  attaches the signed amendment raising the cap to 6,000 bars, Clawback withdraws $1,000 of C4 and keeps $540
  disputed. The totals become $3,120 disputed and $3,730 accepted.
- **Only people move money.** The $2,730 credit memo (the QuickBooks entry for the accepted charges) waits for the
  controller, Sam Reyes (fictional). If Sam says yes, it's written to QuickBooks and the disputed $4,120 stays unpaid
  on the invoice with a note listing the dispute lines. If Sam says no, nothing is written.
- **It fixes next month's deal.** The Deal Coach suggests edits to the summer draft. Each edit shows what that clause
  cost in March, for example $1,000 on §3.1, the product list, because Northmart charged for Mint.
- **Every decision shows its proof.** Each charge's evidence panel shows the deal sentence, the math, the rehearsed
  comeback and its sources: the sales rows, the email, the rule or the person who approved it.

## How it works

One run, from the payment arriving to the books:

1. **The payment arrives.** Northmart's $41,350 deposit lands in Peak Bar Co.'s Capital One Nessie sandbox account.
   A poller checks every 5 seconds and starts the run. The "Northmart pays" button does the same thing if the poller
   isn't running.
2. **Two models read the deal.** Claude (Reader A) and Gemini (Reader B) each read the deal and both emails into
   typed terms, each with the exact sentence it came from. Code keeps a term only if its sentence is found word for
   word in the document, every number in the term appears in that sentence, and both readers read the same thing.
   A term that fails the sentence check is rejected. A term the readers disagree on goes to a person.
3. **Code does the math.** A plain Python engine works out what each charge should have been: rate, products,
   dates, extensions, the unit cap counted week by week, and earlier payments. No AI computes an amount.
4. **Claude explains each charge.** The Investigator writes a one-line finding with a confidence score and the IDs of
   the evidence it used. Code checks that every number it wrote came from its input and that every ID exists.
5. **A fixed gate decides.** Nine rules in order, from the owner's policy file: a deal that can't be verified is
   skipped; readers who disagree, a discretion clause with no saved rule, or a weak case go to the owner; a match
   within $1 or an undercharge is accepted; a well-supported overcharge up to $5,000 is disputed (or split); a bigger one goes to the
   owner first.
6. **People answer.** The owner gets one question by text (or in the app) and the answer becomes a rule. The
   controller approves the credit memo by text or in the app.
7. **The books are updated.** Code, not an agent, writes the credit memo to the QuickBooks sandbox and notes the
   disputed balance on the invoice.

Every step streams live to the board, and every decision, question, answer, rule, approval, dispute, portal message
and QuickBooks write goes into a hash-chained audit log.

## What's real and what's simulated

**Real:**

- **The AI reading.** Claude and Gemini read the demo deal, both emails and the amendment live, and agreed on every
  term. Claude also runs the Investigator, the Negotiator and the Deal Coach.
- **The math, the decision gate and the rules.** Plain Python with unit tests that reproduce every number above.
- **QuickBooks sandbox writes.** Checked live in the sandbox: the controller's yes posted a $2,730 credit memo,
  applied it to INV-3102 (down to $4,120 open) and noted the disputed lines. `make reset` deletes those writes again,
  so INV-3102 goes back to $6,850 open.
- **The Nessie deposit.** Posted to Capital One's Nessie sandbox; a new Northmart deposit starts the run.
- **The texts.** Owner and controller messages go through Twilio, as SMS or over Twilio's WhatsApp Sandbox (US
  carriers require a business registration before an app can text, and it wouldn't clear by Sunday). Without the
  keys, or offline, questions wait in the app.
- **The eval score.** Computed by `eval/run.py` against an answer key written before the first run (below).

**Simulated:**

- Peak Bar Co., Northmart, Dana Okafor, Sam Reyes and Jordan Lee are all fictional. We wrote the deal, the emails,
  the notices, the charges and the sales data.
- The Northmart portal is our own mock.
- For a demo without Wi-Fi, `DEMO_MODE` replays AI answers recorded from live runs. In that mode, QuickBooks writes
  go to a stand-in and every one is labeled "Simulated" on screen.
- The database (Postgres, with store sales as a Tiger Data hypertable) is created and filled by `make seed`, but a
  run still reads the data files directly, and runs, rules and the audit log live in the app's memory.

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

- The $5,000 limit is checked twice: once per charge in the gate, and again on the whole dispute when it's filed,
  because several small lines can add up to more. D-0417 is $4,120, so it files on the owner's policy.
- The controller answers by text (YES, or NO with a note) or with the Yes / No buttons on the Approvals page. A text
  only counts if it comes from the controller's number, and Twilio's signature is checked.
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
| Readers | — | Claude for Reader A. Reader B: Gemini on the two "vague wording" cases (E28, E29), a second Claude read on the other 28 |

A wrong automatic action means acting where the key says ask, disputing a fair charge, or accepting a wrong one.

To be clear about what this does and doesn't show:

- The agent-mode score was first recorded live on Sat Oct 24 at 3:07 AM PDT with a second Claude read as Reader B.
  At 5:00 AM we re-read the two "vague wording" cases live with Gemini as Reader B. So Gemini is in this score for
  2 of the 30 cases, not all of them.
- Those two cases reached a person in two ways. On E29 ("its core bars"), Claude left the product list out as
  unclear and Gemini read it as "core bars", so the term was disputed and the owner was asked. On E28 ("a reasonable
  per-unit rate"), neither model would invent a rate, so the deal was incomplete and went to the owner. Full write-up:
  [docs/proof/gemini-vs-claude.md](../proof/gemini-vs-claude.md).
- We wrote the 30 cases ourselves, from templates. The deal written by someone outside the team
  (`data/eval/outside-deal.md`) is still a placeholder. TODO (needs Devank): run it cold and report terms found vs a
  key made by hand.

Rehearsal: 5 runs in a row in the browser with no manual fix, each ending at $4,120 disputed, $2,730 accepted and
1 question. In `DEMO_MODE` the board was decided 5.9 seconds after the deposit. TODO (needs Devank): the same
stopwatch on a live run (target: under 60 seconds).

## How we built it

- **Backend:** Python, FastAPI and Pydantic. One run streams every step to the browser as server-sent events, and a
  page refresh replays them.
- **Agents:** Claude for Reader A, the Investigator, the Negotiator, the Deal Coach and the rule writer. Gemini for
  Reader B (`gemini-3.6-flash`, then `gemini-3.5-flash-lite` if it's busy), with a second Claude read if Gemini
  fails. Every agent returns strict JSON checked against a Pydantic schema. If the answer fails the check, the agent
  gets one retry with the error. If that fails too, the item goes to a person.
- **Checks after every agent (code):** sentences found word for word, numbers that match the engine's, evidence IDs
  that exist, and an outbound filter on every message to Northmart.
- **Money math:** `api/engine/`, plain Python with pytest tests for every number in the demo, the April fees and the
  $540 after the amendment.
- **Every outside call** (Claude, Gemini, QuickBooks, Twilio, Nessie) has a timeout and one retry. In `DEMO_MODE`,
  AI answers are replayed from `data/fixtures/` and QuickBooks writes go to a labeled stand-in.
- **Frontend:** Next.js, React, Tailwind CSS and Framer Motion, following the same event stream.
- **Integrations:** QuickBooks Online sandbox (credit memo, linking payment, invoice note), Twilio (SMS or WhatsApp
  Sandbox), Capital One Nessie (deposit and poller).
- **Database:** Postgres with no ORM (psycopg 3). `make seed` creates every table and fills it from the data files;
  on Tiger Data, store sales is a hypertable with a continuous aggregate that the cap query reads.
- **Deploy:** Docker Compose (API, web, Caddy for HTTPS) for a Vultr VM behind our GoDaddy domain, clawback.biz.
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
  longer available. With the SDK's own retries on, a call that hit the rate limit waited through minutes of backoff and looked like a
  hang, so we turned them off and keep exactly one retry ourselves.
- **Texts in the US.** Carriers require a business registration before an app can text, and it wouldn't clear this
  weekend. Texts can go over Twilio's WhatsApp Sandbox instead, with the same webhook, and the in-app inbox is the
  fallback.
- **Tests that reached the real world.** Early test runs used the real keys in `.env`: one reached the live Claude
  API and others left 28 stray credit memos in the QuickBooks sandbox. Now every test runs with the live keys
  blanked and real Claude clients blocked, and `make reset` deletes anything Clawback wrote to the sandbox.
- **A demo that survives bad Wi-Fi.** Replaying recorded AI answers only works if every request is exactly the same
  from run to run, so no run IDs go into a prompt and the payment keeps a fixed ID.

## Accomplishments that we're proud of

- 30 of 30 on the planted charges in both eval modes, with 0 wrong automatic actions (see the notes under Proof).
- It accepts fair charges: $2,730 here, including one that looked wrong until it found the email. It never asks for
  more than the deal allows.
- It backs down with proof: shown the signed amendment, it gives back $1,000 and keeps $540.
- A real QuickBooks sandbox write: the $2,730 credit memo applied to INV-3102, which dropped to $4,120 open, and a
  reset that puts the sandbox back to $6,850 open.
- Claude and Gemini read the deal, both emails and the amendment separately, and agreed on every term.
- The worst failure is a question to a person, never a wrong payment.

## What we learned

- Most of the value in finance automation is the evidence trail. A dispute only works if the other side can see the
  sentence, the sales row and the math.
- Two models that must agree, plus a word-for-word sentence check, catch mistakes a single confident model doesn't.
- Separation of duties maps cleanly onto agents: whoever proposes a credit memo can never be the one who approves it.
- TODO (needs Devank): one honest lesson from each of Devank, Rishi and Manasv.

## What's next for Clawback

- Running from the database (the schema and seed exist), so runs, rules and the audit log survive a restart.
- Matching rules by meaning (Moss), so a differently worded clause still matches a saved rule.
- Real distributor portals through browser automation, as recovery services already do.
- Adapters for NetSuite and Xero beside QuickBooks.
- The same approval and audit model, with least-privilege access to the books, no training on customer data, and
  each brand's data kept separate.
- More conversations with small-brand founders and bookkeepers about the rules they'd want by default.

## Built with

Claude (Anthropic API), Gemini API, Python, FastAPI, Pydantic, pytest, Next.js, React, Tailwind CSS, Framer Motion,
PostgreSQL (psycopg 3), QuickBooks Online API, Twilio, Capital One Nessie, Docker, Caddy.

Add Vultr and GoDaddy once the live URL answers; add Tiger Data, Moss and Figma only once Part 2 says their proof
exists.

## Hyphenate: Autonomous Systems for Finance

Clawback fills two finance seats: the deductions analyst and the collections specialist. It works from sources that
disagree: the signed deal, the broker's email, Northmart's own email, the store sales and earlier payments. Time
matters: the cap fills up week by week, an extension changes which dates count, and a fee needs enough notice. Access
is limited: only the owner, the approved broker or a document signed by both sides can change a deal, and no agent
can approve money or write to the books. The controller can refuse: if Sam says no, nothing posts and Sam's note
shows on the card. Every decision names its gate rule, its evidence and, when people were involved, the person. We
report a real score (30 of 30 in both eval modes, 0 wrong automatic actions, with the caveats in Proof) and say
plainly what's real and what's simulated.

## Microsoft: Built for the Real World

**Customer understanding.** Our customer is a small food or consumer brand that sells through big distributors,
where the founder or a part-time bookkeeper checks every short payment by hand, if at all. They don't need another
dashboard. They need each charge settled with proof, the fair ones accepted without a fight, and one question when
the deal is genuinely unclear. TODO (needs Devank): a real quote, with the person's role.

**Measurable usefulness.** On the demo payment, Clawback decides all six charges: $4,120 disputed with evidence,
$2,730 accepted, and one question to the owner. In rehearsal it ran 5 times in a row with no manual fix, and in
`DEMO_MODE` the board was decided 5.9 seconds after the deposit. On 30 planted charges it scored 30 of 30, amounts
right to the cent, with 0 wrong automatic actions in both eval modes. TODO (needs Devank): time saved vs checking
the same six charges by hand, measured.

**Path to production.** The parts that would change are at the edges: real distributor portals through browser
automation (recovery services already work this way), adapters for NetSuite and Xero beside QuickBooks, and runs
kept in the database instead of today's in-memory state. The core stays the same: two readers, tested math, a fixed gate, and
people approving money, with least-privilege access to the books and each brand's data kept separate.

**Responsible design.** Two models must agree on every term, and every term's sentence must be found word for word.
All amounts come from tested code, and an outbound filter blocks any dollar figure, quote, promise, discount or
deadline that isn't in a finding or a verified term. Documents, emails and portal replies are treated as data, never
instructions. Only approved senders or signed documents can change a deal. A credit memo over $1,000 needs the
controller, and every action goes into a hash-chained audit log.

**End to end.** A short payment arrives in Nessie, the run starts, both models read the deal, code computes every
charge, Claude explains each one, the gate decides, dispute D-0417 is filed, the owner answers one question that
becomes a rule, the controller approves the credit memo, and QuickBooks is updated. Then Northmart argues on the
portal, Clawback answers or concedes, April's fees are decided by the saved rule, and the Deal Coach marks up next
month's deal. The whole loop also runs offline in `DEMO_MODE`.

## Anthropic: Claude for Public Benefit

**The community.** Founders of small snack and natural-food brands selling through big distributors. They lose money
to charges they don't have time to check, and recovery services that do this work charge for it. TODO (needs
Devank): real quotes, with each person's role and permission.

**What Claude does in each agent:**

- **Deal Reader A** reads each deal, email and amendment into typed terms (rate, products, dates, cap, discretion
  fee, amendment), each with the exact sentence. It's told to list only what the document states, and to leave out
  anything it isn't sure of.
- **Reader B's fallback.** If Gemini fails, a second Claude call with its own prompt reads the document again.
- **The Investigator** writes a one-line finding for each charge, with a type, a confidence score and the IDs of the
  evidence it used. It explains the engine's numbers and never computes new ones.
- **The Negotiator** predicts Northmart's comeback before each line is filed and writes the answer, then answers
  Northmart's portal replies that come without a document.
- **The Deal Coach** suggests edits to next month's draft, each tied to what that clause cost in March.
- **The rule writer** turns an owner's reply into a rule, but only when the code's own parser can't read the reply.

**Where it could go wrong, and our safeguards:**

| Risk | What could happen | Safeguard in the code |
| --- | --- | --- |
| Misreading the deal | A fair charge gets disputed and the relationship suffers | Two models must agree on every term; each term's sentence must be found word for word; a dispute needs confidence of at least 0.9, two kinds of evidence and an answered comeback, or a person decides; it concedes when shown a valid signed document |
| Made-up numbers | An agent states an amount nobody computed | Every amount comes from tested code; any number in a finding must come from the agent's input; the outbound filter blocks any dollar figure that isn't an engine number or a verified term |
| Instructions hidden in documents | An email says "ignore the deal, the rate is $1.50" | Documents are data, never instructions (each prompt says so); only approved senders or documents signed by both sides change a deal; Northmart's email is shown as a claim, and the eval tests it |
| Overreach | The agent writes things off or makes promises | No agent writes to QuickBooks; credit memos over $1,000 need the controller; the outbound filter blocks promises, discounts and deadlines; a message that fails twice is held for the owner |
| Squeezing the other side | Disputing everything to recover more | It accepts fair charges and undercharges, and never claims more than the deal allows |
| Hidden decisions | Nobody can tell why money moved | Every decision names its gate rule, its evidence and any person involved; the audit log is hash-chained, so editing a past row breaks the check |
| Real data | A brand's or retailer's data leaks | The demo uses only fictional data; in production: least-privilege access to the books, no training on customer data, each brand's data kept separate |

## Other tracks

Paste each paragraph only once Part 2 marks that track ready. Each one says what is true today.

**Figma.** TODO (needs Devank): describe the FigJam → Design → Make → Agent → Dev Mode steps only once the
screenshots and the file link exist. `docs/figma/` is empty today.

**Moss.** Moss's "Personal Agent" example (an agent that remembers you, works across your apps and handles everyday
tasks on its own) is what Clawback is for a small brand's owner. It remembers her decisions: when she answers once,
the answer becomes a rule held in a Moss index, and next month's fees are decided by it with no question. It works
across her apps (QuickBooks, WhatsApp, the bank deposit that starts a run, ASI:One) and checks every deduction on
its own. A new discretion clause is matched to the saved rules by meaning, so a differently worded display-fee clause
still finds Rule #1, with the similarity shown on the card (`api/integrations/moss.py`, index model `moss-mediumlm`;
the exact match on clause type and distributor stays as the fallback). TODO (needs Devank): the live before/after
from `python -m api.integrations.moss` with the Moss keys, before this paragraph goes in.

**MLH: Best Use of Gemini API.** Gemini is Clawback's second deal reader. Claude and Gemini read every document
separately, and a term only counts when both read the same type and numbers and the sentence is found word for word.
When they disagree, every charge that depends on that term goes to the owner instead of being disputed. On the demo
deal, both emails and the amendment, Gemini agreed with Claude on every term. On a vaguely worded test deal ("$1.00
per unit on its core bars"), Claude left the product list out as unclear and Gemini read it as "core bars", so the
term was disputed and Clawback asked the owner whether Chocolate counts, instead of deciding $1,200 on its own:
[the full example](https://github.com/devank-yadav/clawback/blob/main/docs/proof/gemini-vs-claude.md).

**MLH: Best Use of Tiger Data.** `make seed` builds Clawback's tables in Postgres on Tiger Data. Weekly store sales is a
hypertable on the week, with a continuous aggregate of promoted units, and the cap check is a time query: add up
promoted bars week by week until the 5,000-bar cap is reached. TODO (needs Devank): the schema screenshot and the
cap query's output from the Tiger Data service before this goes in.

**MLH: Best Use of Vultr.** The API, the web app and Caddy (for HTTPS) run with Docker Compose on a Vultr VM.
TODO (needs Devank): the live URL.

**MLH: Best Domain Name from GoDaddy Registry.** clawback.biz, registered with the MLH code and pointed at our Vultr
VM. TODO (needs Devank): the URL answering over HTTPS.

**Capital One: Best Use of Nessie.** The short payment is a real Nessie deposit. When Northmart's $41,350 lands in
Peak Bar Co.'s Nessie checking account, a poller that checks every 5 seconds starts the run and the board fills.
TODO (needs Devank): the clip of a deposit starting the run.

**Notability: Trust the Process.** TODO (needs Devank): planning sketches and standup notes from Notability.

**Fetch.ai: ASI:One Agent Challenge.** The Clawback Assistant (`fetch_agent/`) is a uAgents agent with the Agent
Chat Protocol: the owner asks it in ASI:One what Northmart took and gets the totals, open disputes and the pending
question, and can answer that question in the chat. It's read-only otherwise and never approves money. TODO (needs
Devank): register it on Agentverse and paste its address and an ASI:One chat clip once it's live.

---

# Part 2: proof checklist per track

What Devpost must show comes from the Track plan and Added tracks in `docs/design.md`. "In the repo now" is
checked against commit f55757a. Tag a track on Devpost only when every row says it exists.

### Hyphenate (main prize)

| Devpost must show | In the repo now? |
| --- | --- |
| "Seats it fills: deductions analyst and collections specialist" | Yes: Part 1, What it does |
| Real vs simulated | Yes: Part 1 |
| The eval score | Yes: 30/30 in both modes, from `eval/latest.json` and `eval/latest-agent.json` (regenerate with `make eval` and `DEMO_MODE=true python eval/run.py --mode agent`) |
| How approvals and refusals work | Yes: Part 1; refusal tested in `api/tests/test_books.py` |
| Live scenario box for a judge's own clause | Yes: the `/scenario` screen over `POST /scenario`, with three recorded examples. TODO (needs Devank): the test on 5 unseen clauses written by a non-teammate |
| The judge arguing as Northmart on the portal | Yes: the `/portal` screen (Northmart's look) with five presets; attaching the signed amendment concedes $1,000 and keeps $540 |
| Video opening with the moment | TODO (needs Devank): video link |
| Every number on the evidence card opens its source | Partly: the math line and the comeback's sources open in the evidence panel. TODO (needs Devank): the rest (Rishi's card U2) |

### Microsoft: Built for the Real World

| Devpost must show | In the repo now? |
| --- | --- |
| A paragraph per criterion: customer understanding, measurable usefulness, path to production, responsible design, end to end | Yes: Part 1 |
| Time saved vs checking by hand | TODO (needs Devank): a measured number |
| A real customer quote | TODO (needs Devank) |
| Production path (portals via browser automation, ERP adapters, SOC 2-style controls) | Yes: Part 1 |

### Anthropic: Claude for Public Benefit

| Devpost must show | In the repo now? |
| --- | --- |
| The named community | Yes: Part 1 |
| Real quotes, with roles | TODO (needs Devank). The cut rule says to drop this track if there are no real quotes by Sat noon |
| Claude's role in each agent | Yes: Part 1 |
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
| Before/after: a differently worded clause matched to Rule #1 | Code yes: `api/integrations/moss.py` (Moss SDK 1.21.0), similarity floor 0.85 in `config/policy.yaml`, tested with a fake. TODO (needs Devank): redeem CALHACKS in the Moss portal, set `MOSS_PROJECT_ID` and `MOSS_PROJECT_KEY`, run `python -m api.integrations.moss` for the real scores, record one run, and screenshot the scenario box with a reworded clause |

### MLH: Best Use of Gemini API

| Devpost must show | In the repo now? |
| --- | --- |
| Gemini as Reader B | Yes: `api/agents/reader_b.py`; recorded Gemini reads in `data/fixtures/gemini-reader/` |
| An example where the two models differ and the charge goes to Ask | Yes: [docs/proof/gemini-vs-claude.md](../proof/gemini-vs-claude.md). Eval case E29, recorded live: Claude left the products out, Gemini read "core bars", gate row 2 asked the owner. Replay with `DEMO_MODE=true python eval/run.py --mode agent --cases E28,E29` (needs `GEMINI_API_KEY` set, or Reader B replays as Claude) |
| The run's feed naming Gemini | Yes, when `GEMINI_API_KEY` is set. In `DEMO_MODE` without it, the feed says "a second Claude read", so keep the key in `.env` for the demo |

### MLH: Best Use of Tiger Data

| Devpost must show | In the repo now? |
| --- | --- |
| The schema | Yes: `api/db/migrations/001_init.sql` (every table in the data model, plus events); `make seed` applies it and is safe to run twice |
| `store_sales` as a hypertable and the cap query | Code yes: hypertable on `week_start`, the `promo_units_weekly` continuous aggregate, and the cap query `make seed` prints (`api/db/seed.py`). TODO (needs Devank): a screenshot of the schema and the cap query from the Tiger Data service |
| The app using the database | Not yet: a run still reads `data/` directly. Fine for the track if the Devpost text claims only the schema, seed and cap query |

### MLH: Best Use of Vultr

| Devpost must show | In the repo now? |
| --- | --- |
| The app running on a Vultr VM | Deploy files yes: `docker-compose.yml`, `deploy/Caddyfile`, `docs/deploy.md`, `make deploy-check` |
| The live URL | TODO (needs Devank): `https://clawback.biz/api/health` answering |

### MLH: Best Domain Name from GoDaddy Registry

| Devpost must show | In the repo now? |
| --- | --- |
| The domain | Yes: clawback.biz, registered with the MLH code (`DECISIONS.md`, Oct 24 3:36 AM) |
| The URL serving the app | TODO (needs Devank) |

### Capital One: Best Use of Nessie

| Devpost must show | In the repo now? |
| --- | --- |
| A short deposit starting the run | Code yes: `api/integrations/nessie.py` (poller every 5 s), `POST /payments/northmart`, `scripts/nessie_deposit.py`; a live test deposit was posted on Oct 24 |
| The clip of a deposit starting the run | TODO (needs Devank). The call that lists deposits couldn't be checked against Nessie's docs (they answered 403), so confirm it with the keys while recording |

### Notability: Trust the Process

| Devpost must show | In the repo now? |
| --- | --- |
| Screenshots of planning sketches and standup notes | TODO (needs Devank) |

### Fetch.ai: ASI:One Agent Challenge

| Devpost must show | In the repo now? |
| --- | --- |
| The agent registered on Agentverse, with the Agent Chat Protocol, usable in ASI:One | Code yes: `fetch_agent/` (uAgents mailbox agent, Chat Protocol, 81 tests). TODO (needs Devank): run it against the live API and connect it to Agentverse (`fetch_agent/README.md`) |
| The API it would call | Yes: `GET /summary` (read-only, needs `CLAWBACK_READONLY_TOKEN`) and `POST /questions/{id}/answer` |
| The agent address | TODO (needs Devank) |
| An ASI:One chat clip | TODO (needs Devank). Cut rule: not live in ASI:One by Sat 8 PM |

### Not entered unless confirmed by Sat 4 PM

Elastic, Atlassian, Mana and SpaceXAI: nothing for them is in the repo. Add a paragraph only once the sponsor
confirms and the proof exists.
