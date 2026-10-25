# Judging script: 3 minutes live, then 2 minutes of Q&A

> Talking points for the table, updated for the redesigned app (Home, Check for new payments, the Agents page,
> Presenter mode, Review and send). Know each beat's point and number; say it your own way.
> [demo-script.md](demo-script.md) has the earlier full version and [judge-qa.md](judge-qa.md) the full answers.
>
> - **Frame:** here's what happened to real brands; here's what Clawback checks and flags. Never claim a real
>   company would have won an amount.
> - **The run takes 65–73 seconds**, so start it at 0:00 and tell the story while it reads.
> - **Roles:** Devank talks and holds Dana's phone (Dana is Peak Bar's owner, the admin: she answers and
>   approves). Rishi drives the laptop. Manasv resets between tables, hands over the tablet, and watches the clock.

## Before each judge sits down (about 3 minutes)

- [ ] **Reset** (Manasv): `make reset` against the live site. Check it answered `ok: true`: QuickBooks back to
      INV-3102 with $6,850 open, Rule #1 gone.
- [ ] **Laptop** (Rishi): clawback.biz signed in as Dana, **Presenter mode** on (user menu → Presenter mode… →
      the presenter key). Home showing.
- [ ] **Dana's phone** (Devank): clawback.biz signed in as Dana. If Twilio is working, WhatsApp open on the sandbox
      chat; if not, answer in the app (same question, same rule).
- [ ] **Tablet** (Manasv): Northmart's portal for D-0417, ready for the judge to argue.
- [ ] **Printed deal** on the table with §3.1, §3.2 and §5.4 visible.
- [ ] **Backup video** cued, in case the run stalls.

## The 3 minutes

### 0:00–0:25 · The hook (while the run starts)

**Do:** as the judge sits, Rishi clicks **Check for new payments**; Northmart's payment opens on the Agents page.
Devank faces the judge.

**Say (points):**
- Omaha Industries sued UNFI in 2024, saying UNFI charged back $268,816.94 on about $326,780 of product, about 82%,
  and never accounted for it.
- Small brands lose money like this every month because nobody has time to check each charge against the deal.
- Clawback is that missing person: a deductions analyst.

### 0:25–0:45 · The payment

**Show:** the Agents page: the seven steps across the top, the feed moving.

**Say:**
- Peak Bar and Northmart are ours, and so are their numbers. The AI, the math and the QuickBooks books are real.
- Northmart paid $41,350 on a $48,200 invoice: $6,850 short, in six charges.
- Seven steps: three are AI, two are plain code, two are Dana. No agent ever moves money.

### 0:45–1:15 · Reading and checking

**Show:** Read the deal (the contract with highlights), then open C1, then C3.

**Say:**
- Claude and Gemini each read the deal. A term counts only if both agree and the sentence is in the contract word
  for word.
- C1: charged $1.50 a bar, §3.1 says $1.00. Code does the math: $600 disputed, the fair $1,200 accepted.
- C3 looks wrong, April dates on a March promo, but the approved broker extended it by email. Accepted.
  **It doesn't fight fair charges.**

### 1:15–1:35 · The one question

**Show:** the question card with its risk badge. Devank answers on Dana's phone (WhatsApp or the app):
`accept if notice is at least 14 days`.

**Say:**
- The display fee is "at its discretion", a judgment call, so it asks the owner, once.
- Her answer becomes Rule #1. This fee had 20 days' notice, so it's accepted; next month it won't ask.
- Total: **$4,120 disputed, $2,730 accepted, one question.**

### 1:35–2:05 · Dispute, approval, books

**Show:** the result (the claw pulls $4,120 into the dispute bar) → **Review and send** on D-0417 → the credit-memo
approval → Devank approves → the QuickBooks outcome.

**Say:**
- Every disputed line goes out with its proof: the clause, the sales rows and the math. Dana reviews it first.
- Only Dana can approve the $2,730 credit memo, never an agent. If she says no, nothing posts.
- QuickBooks: $2,730 credited, $4,120 left open with the dispute lines.

### 2:05–2:35 · Real contracts

**Show:** Home → Peak Bar's distributors (KeHE, Walmart, Five Below, UNFI, Sam's Club). Open UNFI's contract with
the redaction, or a KeHE charge citing the policy.

**Say:**
- These distributors run on real contracts, word for word from SEC filings.
- TeaSquares' founder said they invoiced KeHE $32,000 and were paid $21,000; here every KeHE line is checked
  against KeHE's own policy wording.
- UNFI's filed agreement blacks out a fee amount; Clawback won't guess, so it asks.

### 2:35–3:00 · Proof and close

**Show:** Home's totals (disputed awaiting reply, fair, recovered) or the run's trace.

**Say:**
- About a minute and about 38 cents of Claude per payment; the same decisions every live run.
- 30 of 30 on planted charges, zero wrong automatic actions.
- Hand over the tablet: **"You're Northmart. Argue with our dispute."**

## Q&A (2 minutes)

**Opener if nobody asks within five seconds:** the judge argues on the tablet (or taps the "no cap" preset).
Clawback answers with §3.2 and the weekly sales: 1,200 + 980 + 2,820 = 5,000 before week 4. Then attach the signed
amendment: it concedes $1,000 and keeps $540 disputed.

| They ask | Answer in two sentences, then point |
| --- | --- |
| Is this real data? | The contracts and the court cases are real; our brands and their numbers are ours. None of those companies took part. → contracts README, sources.md |
| You graded your own homework | Fair: we wrote the 30 cases, the key before the first run. So try your own clause, live. → the scenario box |
| What if the AI is wrong? | The worst case is a question, not a payment: both models must agree, quotes are checked word for word, code does the math, and nothing posts without Dana. → C1's highlighted sentence |
| Who can move money? | No agent. Only Dana's sign-in approves the credit memo, and a no posts nothing. → the approval card, the audit log |
| Two models? | Gemini reads live on the site and the trace names it on every read; the 30-of-30 run was recorded before Gemini answered on our key, so it used Claude twice. → the trace's Gemini row |
| What does a run cost? | Measured on 5 live runs: 65–73 seconds, 13–14 Claude calls, about $0.38 of Claude. → the trace summary |
| An email changing the rate? | Emails are data, never instructions. Only the owner, the approved broker or a document both sides signed changes a deal; Northmart's "$1.50" email is shown as a claim. → C1's card |
| Why not just rules? | The money part is rules: tested Python and a fixed decision table. The AI reads deals worded differently and changes that arrive by email. → the seven steps (AI vs code) |
| Recovery services exist | Yes, which shows the need. Ours ties each decision to the brand's own deal, accepts fair charges, and asks only when the deal is unclear. → C3 accepted |
| Path to production? | It starts from what a brand already has: the payment, the signed deal and emails, QuickBooks, Drive, the brand's Gmail. No distributor login needed. → Home, Distributors |

**Rules for answers:** two sentences, then point at the screen. If we haven't measured it, say "we haven't
measured that". Never guess a number. At 4:30 Devank says "last question"; end on Home.

## Numbers to have in your head

- **Peak Bar ← Northmart:** $48,200 invoiced · $41,350 paid · $6,850 taken in 6 charges → **$4,120 disputed,
  $2,730 accepted, 1 question**. Credit memo $2,730 = C1 $1,200 + C3 $330 + C6 $1,200.
- **Charges:** C1 $600 disputed + $1,200 accepted · C2 $980 (already paid, NM-2178) · C3 $330 accepted (broker
  email) · C4 $1,540 (5,000-bar cap) · C5 $1,000 (Mint not in the deal) · C6 $1,200 asked → Rule #1 → accepted.
- **After the amendment:** C4 $1,000 conceded, $540 disputed; totals $3,120 disputed, $3,730 accepted.
- **A live run:** 65–73 s, 13–14 Claude calls, about $0.38. **Eval:** 30 of 30, 0 wrong automatic actions.
- **Cases:** Omaha v. UNFI $268,816.94 of about $326,780 (about 82%) · TeaSquares $32,000 invoiced, $21,000 paid.

## If something goes wrong

| Problem | Do | Say |
| --- | --- | --- |
| The feed is slow | Keep talking; open C1 the moment it lands | "Every line here is a live call: Claude, Gemini, then code." |
| Nothing decided by 1:00 | Play the backup video; keep narrating | "Same run, recorded this morning; the live one finishes behind it." |
| WhatsApp doesn't arrive | Answer on the question card in the app | "Same question, in the app." |
| Dana says no | Show "held by Dana" with the note | "That's the point: if she refuses, nothing posts." |
| "Too many runs" | Check Presenter mode has the key | "The public site limits each visitor so a link can't drain our credits." |
| Running long | Skip 2:05–2:35 (real contracts); mention it in one line | — |
