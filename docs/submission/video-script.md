# Video script: 3 minutes

> Talking points, not lines to memorize. Know each beat's point, the screen behind it and the number to say; word
> it your own way. Facts and numbers come from [demo-script.md](demo-script.md), [judge-qa.md](judge-qa.md),
> [sources.md](sources.md) and data/CLAUDE.md. Peak Bar's numbers are fixed: never round them.
>
> - **Structure:** Intro → Problem → Use case → Call to action. The motion piece (`clawback-demo.mp4`, about 48 s)
>   can supply the intro card and the closing card; everything in between is a screen recording of the real app.
> - **Say "ours" once** (beat 3): Peak Bar, Northmart and their numbers are ours; the contracts from SEC filings
>   and the court cases are real. No other "fictional" labels.
> - **Real companies:** say only what the source says ("Omaha Industries sued UNFI in 2024, saying…"). Never say
>   what Clawback would have won for them; say what it would have checked and flagged.
> - **Captions on every line.** Real UI from 0:20 at the latest.

## The beats

### 1. Intro: the hook (0:00–0:20)

**Screen:** the motion piece's intro card (Clawback wordmark, the underline pulling back), then cut to the landing
page at clawback.biz.

**Points to land:**
- Clawback wins back what distributors wrongly take from a small brand's payments, and never fights a fair charge.
- It's built for a finance seat that small brands don't have: the deductions analyst.

**Transition:** "Here's why that seat matters."

### 2. Problem: real brands, real short pays (0:20–0:50)

**Screen:** the landing page's case section (Omaha's bar showing about 82%), then the motion piece's remittance
slip: $48,200 invoiced, $41,350 received, −$6,850.

**Points to land:**
- Omaha Industries sued UNFI in 2024, saying UNFI charged back $268,816.94 on about $326,780 of product, about
  82%, and never accounted for it.
- TeaSquares' founder said the company invoiced KeHE $32,000 and was paid $21,000.
- Distributors take money back as promo fees, display fees and "adjustments", and checking each one against the
  signed deal takes hours a small brand doesn't have. So it gets written off.

**Transition:** "So we built the analyst."

### 3. Use case: one payment, start to finish (0:50–2:30)

Recorded live on clawback.biz, signed in as Dana (Peak Bar Co.'s owner, the admin).

**3a. The payment arrives (0:50–1:05).** Home → **Check for new payments** → Northmart's payment opens on the
Agents page.
- Say it once: "Peak Bar and Northmart are ours, and so are their numbers. The AI, the math and the QuickBooks
  books are real."
- Northmart paid $41,350 on a $48,200 invoice: $6,850 short, in six charges.
- Point at the seven steps across the top: Payment in → Read the deal → Check each charge → File the dispute →
  Your answer → Your approval → QuickBooks. Three are AI, two are plain code, two are Dana.

**3b. Reading the deal (1:05–1:20).** The Read the deal step, the contract with highlights.
- Two different models, Claude and Gemini, read the deal and the emails separately.
- A term counts only if both read it the same way and its sentence is found in the contract word for word.

**3c. Checking each charge (1:20–1:45).** Open C1, then C3.
- C1: they charged $1.50 a bar, §3.1 says $1.00. Code does the math: $600 disputed, the fair $1,200 accepted.
- C3 looks wrong (April dates on a March promo), but the approved broker extended it by email. Accepted.
  It doesn't fight fair charges.
- Code, not AI, computes every amount.

**3d. The one question (1:45–2:00).** Your answer step: the question card with its risk badge.
- The display fee is "at its discretion", a judgment call, so it asks the owner, once.
- Dana answers "accept if notice is at least 14 days." That becomes Rule #1. This fee had 20 days' notice, so it's
  accepted, and next month it won't ask.

**3e. The dispute and the books (2:00–2:30).** The result (the claw pulls $4,120 into the dispute bar), then
Review and send on D-0417, then the approval, then QuickBooks.
- $4,120 disputed, $2,730 accepted, one question.
- The dispute goes out with proof for each line: the clause, the sales rows and the math. Dana reviews it first.
- Money is the one thing no agent touches: only Dana approves the $2,730 credit memo. QuickBooks gets the credit,
  and $4,120 stays open with the dispute lines.
- Optional, if there's time: Northmart replies "there was no cap"; Clawback answers with §3.2 and the weekly sales.
  Shown the signed amendment, it concedes $1,000 and keeps $540 disputed.

### 4. Call to action (2:30–3:00)

**Screen:** Home with Peak Bar's distributors (KeHE, Walmart, Five Below, UNFI, Sam's Club, Northmart), then the
motion piece's closing card with clawback.biz.

**Points to land:**
- Peak Bar's other distributors run on real contracts, word for word from SEC filings: KeHE's vendor policies,
  Walmart's and Five Below's supplier agreements, and UNFI's, with its redactions kept. Where a number is
  blacked out, Clawback asks instead of guessing.
- The proof: 30 of 30 on 30 planted charges, zero wrong automatic actions, and the same decisions on every live
  run.
- About a minute and about 38 cents of Claude per payment.
- Watch it decide every charge, live, at clawback.biz.

## Numbers to have ready

| What | Number |
| --- | --- |
| Peak Bar ← Northmart | $48,200 invoiced · $41,350 paid · $6,850 taken in 6 charges |
| Result | $4,120 disputed · $2,730 accepted · 1 question |
| Per charge | C1 $600 disputed + $1,200 accepted · C2 $980 · C3 $330 accepted · C4 $1,540 · C5 $1,000 · C6 $1,200 asked → accepted |
| After the amendment | C4: $1,000 conceded, $540 still disputed |
| A live run | 65–73 s, 13–14 Claude calls, about $0.38 of Claude |
| Eval | 30 of 30, 0 wrong automatic actions (we wrote the cases) |
| Omaha v. UNFI | $268,816.94 charged back on about $326,780 (about 82%) |
| TeaSquares | $32,000 invoiced to KeHE, $21,000 paid |

## Recording notes

- Record each beat as its own clip, so one mistake doesn't mean redoing three minutes.
- Use Presenter mode to make the payment arrive and Northmart reply on cue.
- Before each take: run `make reset` against the live site (Manasv).
- If the run is slow on camera, cut the wait: show the seven steps moving, then jump to the decided board.
