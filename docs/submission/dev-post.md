# DEV post draft: MLH x DEV Writing Challenge

> **Do not publish from this file as is.** This post is public. Draft written Sat Oct 24 from docs/devpost.md,
> docs/submission/devpost.md, docs/design.md and DECISIONS.md.

## Publish checklist (Sun, after the Devpost is in at 8:30 AM)

- [ ] Devpost submitted first. This post goes out after it.
- [ ] Sign in at dev.to with the account linked to your MLH Cal Hacks registration.
- [ ] Open the official template at https://dev.to/mlh-hackathon. Keep its sections (What I Built, Demo, MLH
      partner tech used, Hackathon experience). If the template's headings or wording differ from this draft,
      the template wins.
- [ ] Check the closing date of this month's window on that page, and post before it closes.
- [ ] Tags: `#mlhacks` (required), plus the template's `devchallenge` and `hackathon`.
- [ ] Fill every `[PLACEHOLDER]` below. Delete any MLH tech line whose status note still says not in the product.
- [ ] Remove every `>` note in this file.
- [ ] Scan the final text: no API keys, `.env` values, phone numbers, emails other than `*.example`, or link to
      the repo while it is private (link it only after it goes public on Sunday).
- [ ] **Devank reads the final text and says go** before anyone clicks Publish.
- [ ] After publishing, share the link in the Cal Hacks Slack so it gets reads.

---

**Title:** We built an AI deductions analyst that disputes $4,120 with proof and never fights a fair charge

**Tags:** #mlhacks #devchallenge #hackathon

*This is a submission for the MLH x DEV Writing Challenge. Peak Bar Co. and Northmart are fictional companies
we made up for the demo.*

## What I Built

When a small snack brand sells through a big distributor, it doesn't always get paid in full. The distributor
takes money back for promotions and fees, and the brand has to work out whether each charge was allowed.
Checking one charge means finding the right clause in the signed deal, the store sales for that week, any email
that changed the terms, and earlier payments that may already cover it. Most founders never have time, so most
charges never get checked.

At Cal Hacks 13.0 our team of three built **Clawback**, a finance agent that does that checking.

Here's the demo story. Peak Bar Co. invoices Northmart **$48,200** for March. Northmart pays **$41,350**, which
means it took **$6,850** back in six charges. Clawback reads the deal, the emails and the store sales, and
decides each charge:

| Charge | Taken | What Clawback did | Why |
| --- | --- | --- | --- |
| Week 1 promo | $1,800 | Disputed $600, accepted $1,200 | Charged $1.50 a bar; the deal says $1.00 |
| Week 2 promo | $980 | Disputed | Already paid on Mar 14 |
| Apr 1–7 promo | $330 | Accepted | The broker extended the promo by email |
| Week 4 promo | $1,540 | Disputed | The 5,000-bar cap was reached in week 3 |
| Mint promo | $1,000 | Disputed | Mint isn't in the deal |
| Display fee | $1,200 | Asked the owner, then accepted | The deal says "at its discretion" |

In total it **disputes $4,120 with proof, accepts $2,730 as fair, and asks the owner one question**.

The charge I like most is the April one. It looks wrong, because April dates on a March promo should be
outside the deal. But the brand's broker had emailed on March 28 to extend the promo through April 7, and he's
on the list of people allowed to change the deal. So Clawback accepts it. When Northmart's own email claims "the
rate is $1.50," Clawback shows it as a claim and never applies it, because Northmart can't change the deal on
its own.

The display fee depends on Northmart's judgment, so Clawback texts the owner once. She answers "accept if notice
is at least 14 days," and that becomes Rule #1. The next month, a fee with 18 days' notice is accepted and one
with 5 days' notice is disputed, without asking again.

A few design rules held the whole thing together:

- **AI never touches the money math.** The models read the deal and quote it word for word, and plain Python
  with unit tests computes every amount.
- **Two readers must agree.** Two separate AI reads of each document must produce the same terms, and every
  quote must be found in the source. If they disagree, a person decides.
- **Only people move money.** A controller approves the $2,730 credit memo before it's written to QuickBooks.
  If they say no, nothing posts.
- **It concedes when it's wrong.** If Northmart attaches a signed amendment raising the cap to 6,000 bars,
  Clawback withdraws $1,000 of the week 4 charge and keeps $540 disputed.

**Real vs simulated:**

- **Real:** the AI reading, the math, the decision rules, the QuickBooks sandbox writes, the texts to real
  phones, the Nessie deposit, the eval score.
- **Simulated:** Peak Bar Co. and Northmart are fictional; we wrote the deal, emails and sales data; the
  distributor portal is our own mock.

> Before publishing, drop any "Real" item that isn't live in the final run (for example the Nessie deposit or
> QuickBooks writes if they fell back to fixtures).

**How well it works:** on 30 planted charges with the answer key written before we ran it, Clawback got
**[EVAL SCORE] of 30** right, with **[WRONG AUTO ACTIONS] wrong automatic actions** and **[ASKED] questions**.

> Fill from the final `make eval` run (agent mode). As of Sat 3:07 AM the live agent-mode score was 30/30,
> 6 asked, 0 wrong automatic actions, but the cases come from our own templates and Reader B was a second Claude
> read, not Gemini (DECISIONS.md). Use the final number and say honestly how the cases were written.

## Demo

- Video: [VIDEO URL]
- Try it: [LIVE URL]
- Devpost: [DEVPOST URL]

> Embed the video with the template's embed syntax if it supports it. Link the repo only once it's public.

## MLH partner tech used

> Keep a line only if it is really in the product at publish time. Status as of Sat Oct 24, 3:30 AM PDT is in
> each note.

- **Gemini API:** the second deal reader. Claude reads every deal and email, Gemini reads them again on its own,
  and a term only counts when both agree and the quote is found word for word. When they disagree, the charge
  goes to the owner instead of being disputed.
  > Code is merged (Reader B), but it falls back to a second Claude read when the Gemini key is missing or fails.
  > Keep this line only if the recorded run shows Gemini answered.
- **Tiger Data:** our Postgres database. Weekly store sales are stored in a TimescaleDB hypertable, which makes
  the cap check a simple time query: add up promoted bars week by week until the 5,000 cap is reached.
  > Not built yet: no database code on main.
- **Vultr:** the app runs on a Vultr VM with Docker Compose (API, web app, and Caddy for HTTPS).
  > Deploy files are merged (docs/deploy.md); the VM is not up yet.
- **GoDaddy:** our domain, [DOMAIN], points at the Vultr VM.
  > Not registered yet.

## Hackathon experience

> Devank, Rishi and Manasv: replace this section with your own words. The draft below only uses facts from our
> plan; add what actually happened.

We were three people on a weekend deadline, so the first thing we did was write the contracts: the data shapes
for every term, charge, decision and event, plus a full fake run of the demo with the exact numbers. That let
the frontend and the data work start in the first hour while the agents were still being written. Every
decision went into a one-line log so nobody had to ask twice.

The hardest part wasn't the AI. It was deciding where the AI should stop. We kept moving work out of the models
and into tested code until the models only did the part code can't: reading deals that are all written
differently and noticing when an email changes them.

[ONE LINE ABOUT WHAT BROKE AND HOW WE FIXED IT]

[ONE LINE FROM EACH OF US ABOUT WHAT WE LEARNED]

Thanks to MLH and the Cal Hacks 13.0 organizers.
