# Live pitch: 3 minutes, then 2 minutes of Q&A

> What we say and click at the judging table on Sunday. Frame: **here's what happened; had they used Clawback,
> here's what it would have checked and flagged.** Never claim Clawback would have won a specific amount.
>
> - **Real facts are told the way their source tells them** ("Omaha Industries sued UNFI in 2024, saying …"). Every
>   one is in [sources.md](sources.md); say nothing about a real company that isn't there.
> - **What's ours, said once at 0:26:** Peak Bar, Northmart and every number in their story are ours. The contracts
>   from SEC filings and the court cases are real. No "fictional" or "simulated" labels beyond that one line.
> - **Peak Bar's numbers are fixed** (data/CLAUDE.md). Never round them.
> - **Measured:** 5 live Peak Bar runs, identical decisions every time ($4,120 disputed, 1 question), 65–73 seconds
>   from deposit to a decided board, 13–14 Claude calls, about $0.38 of Claude per run. So the run starts at 0:00,
>   and the Omaha story plays while it reads.
> - **Roles:** Devank narrates and holds the owner's phone (Dana). Rishi drives the laptop. Manasv holds the
>   controller's phone (Sam) and runs the reset between tables.
> - ✂ marks a line to cut if we're running long.

## The script

| Time | Do | Say |
| --- | --- | --- |
| 0:00–0:26 | As the judge sits, Rishi clicks **Northmart pays** on Peak Bar (silently). Devank faces the judge. | "In January 2024, Omaha Industries sued UNFI, the grocery distributor. It says UNFI charged back $268,816.94 on about $326,780 of product sold to Giant Food, about 82 percent, as unacceptable product, and never returned it, disposed of it or accounted for it. Had Omaha used Clawback, every one of those chargebacks would have been checked for proof, and flagged where there was none." |
| 0:26–0:44 | Laptop: Peak Bar's payment, the feed already moving. | "Here's Clawback, live. Peak Bar and Northmart are ours, and so are their numbers. The AI, the math, the phones and the QuickBooks books are real. Northmart just paid $41,350 on a $48,200 invoice: $6,850 short, in six charges." |
| 0:44–1:10 | Narrate the feed; open C1 when it lands (§3.1 highlighted, the math line), then C3 and its email. | "Claude and Gemini each read the deal and the emails; plain code does the math. Week 1: they charged $1.50 a bar, §3.1 says $1.00, so $600 is disputed and the fair $1,200 accepted. This one looks wrong, April dates on a March promo, but the approved broker extended it by email. Accepted. It doesn't fight fair charges." |
| 1:10–1:28 | Dana's phone buzzes. Devank reads it aloud and replies `accept if notice is at least 14 days`. Rule #1 appears; C6 moves to Accept. | "The display fee is 'at its discretion': a judgment call, so it asks the owner, once. She sets a rule: 14 days' notice. This one had 20, so it's accepted, and next month it won't ask. $4,120 disputed, $2,730 accepted, one question." |
| 1:28–1:48 | Open C4 → **How Clawback decided**. Read only the rows the screen shows. | "Every AI call behind this charge: Claude and Gemini each read the 5,000-bar cap, code found the sentence word for word and did the math, Claude wrote the finding and rehearsed Northmart's comeback before filing, and the gate, plain code, made the call. The whole run: about 38 cents of Claude, just over a minute." |
| 1:48–2:05 | Manasv, signed in as the controller on Sam's phone, taps **Approve**. The QuickBooks post appears. | "Money is the one thing no agent touches. Only the controller's sign-in approves the $2,730 credit memo, not the owner's, not an agent. Sam says yes: QuickBooks gets $2,730 credited and $4,120 left open with the dispute lines." |
| 2:05–2:35 | Switch to the real-contract account (run in setup). Open the charge that cites KeHE's policy, sentence highlighted. TODO (needs Devank): the account's name and the charge to open, once it's merged. | "This account runs on a real contract: KeHE's 2015 vendor policies, word for word from an SEC filing. TeaSquares' founder said on the Foodbevy podcast that the company invoiced KeHE $32,000 in 2019 and was paid $21,000. Our brand here faces that kind of short pay, and Clawback checks every line against KeHE's own wording and flags what the policy doesn't support." |
| ✂ 2:35–2:47 | Account switcher: Fernwell, Ridgefire, Birchbank. | "Three more: a sparkling tea whose delivery records disprove a shortage, a salsa whose distributor's emailed rate is never applied, and a clean month, every charge accepted. It never fights a fair charge." |
| 2:47–3:00 | Open `/results`. | "Peak Bar: $4,120 disputed, $2,730 accepted, one question, the same in five live runs. And on 30 planted charges: 30 of 30, zero wrong automatic actions." |

If the real-contract account isn't merged by Sunday morning, replace 2:05–2:35 with the ✂ tour plus `/april` ("Next
month: two display fees decided by Rule #1, zero questions").

**Plan B.** If no card has landed by 1:00, play the backup video from the Peak Bar beats and keep narrating; the
live site keeps running and the board is there for Q&A. There is no offline mode any more (`make demo` is gone).

## Before the judge sits down (setup, about 4 minutes)

- [ ] **Reset the live site** (Manasv): `make reset API=https://clawback.biz/api CLAWBACK_ADMIN_TOKEN=<token>`.
      QuickBooks goes back to INV-3102 with $6,850 open, and Rule #1 is gone. Check it answered `ok: true`.
- [ ] **Presenter's laptop carries the admin token**, so our own runs skip the 3-runs-per-10-minutes visitor limit
      (the web app sends it on limited calls). TODO (needs Devank): where the laptop's browser enters it.
- [ ] **Run the real-contract account and the three other accounts** (Rishi). Answer nothing, approve nothing. Don't
      run Peak Bar: its run starts at 0:00, so its question is the newest one Dana's text answers.
- [ ] **Look at Ridgefire's trace.** Its unsaleables clause asks because the readers disagreed on a live run; every
      run is read live, so in Q&A claim a disagreement only if this run's trace shows one.
- [ ] **Tablet** on Peak Bar's Northmart portal, signed in as nobody, for the Q&A opener. Printed deal
      (`data/accounts/peak-bar/deals/`) with §3.1, §3.2 and §5.4 visible.
- [ ] **Dana's phone** (Devank): WhatsApp open on the Twilio sandbox chat, clawback.biz signed in as the owner as the
      fallback. Send any message to the sandbox on Sunday morning: WhatsApp only lets a business send a free-form
      message to someone who wrote in the last 24 hours (check in Twilio's console).
- [ ] **Sam's phone** (Manasv): clawback.biz signed in as the controller, on Approvals. WhatsApp open as well.
- [ ] **Laptop tabs** (Rishi): Peak Bar's payment, the real-contract account, Fernwell, Ridgefire, Birchbank,
      `/results`, `/scenario`, `/upload` with the sample remittance.
- [ ] **Backup video** open in a tab, cued to the Peak Bar beats.

## What to click (the presenter's list)

1. 0:00 **Northmart pays** on Peak Bar.
2. Peak Bar's payment screen and feed.
3. C1 → its evidence (sentence, math line). C3 → the broker's email.
4. Dana's phone: reply to the question.
5. C4 → **How Clawback decided**.
6. Sam's phone: **Approve**. The QuickBooks post on the laptop.
7. Real-contract account → the charge citing KeHE's policy.
8. ✂ Fernwell → Ridgefire → Birchbank.
9. `/results`.

## Q&A plan (2 minutes)

- **Devank answers** in two sentences, then points. **Rishi puts on screen** what the answer points at. **Manasv
  hands** the judge the tablet or `/scenario` when the answer is "try it."
- **Opener, if no question comes in five seconds:** hand over the tablet. "You're Northmart. Argue with our dispute."
  The judge types (or taps **There was no cap**); Clawback answers with §3.2 and the weekly sales: 1,200 + 980 +
  2,820 = 5,000 before week 4. Then tap **Attach signed amendment**: it concedes $1,000 and keeps $540 disputed.
- **The ones we expect** (full answers in [judge-qa.md](judge-qa.md)):

| Question | Point at |
| --- | --- |
| "Is this real data?" | `data/contracts/README.md` (SEC links) · sources.md · then "our brands, our numbers" |
| "You graded your own homework." | `/scenario`: the judge's own clause, both models live |
| "Real remittances aren't CSVs." | `/upload`: the sample remittance, each line's quote highlighted, the totals check |
| "Two models? The eval shows Claude twice." | How Clawback decided: the Gemini row; then the one-line truth about the recorded score |
| "Who can move money?" | Sam's phone: only the controller's sign-in approves |
| "What does a run cost?" | The trace summary: about $0.38 of Claude, 65–73 seconds |

- **Don't know a number?** "We haven't measured that." Never guess, never round a demo number, never say what a real
  company would have won.
- **At 4:30**, Devank says "last question." End on `/results`.

## Numbers to have in your head

- Peak Bar ← Northmart: INV-3102 **$48,200** · paid **$41,350** · taken **$6,850** (6 charges) · **$4,120 disputed**,
  **$2,730 accepted**, **1 question**. Credit memo $2,730 = C1 $1,200 + C3 $330 + C6 $1,200.
- C1 $1,800 → $600 disputed + $1,200 accepted · C2 $980 disputed · C3 $330 accepted · C4 $1,540 disputed ·
  C5 $1,000 disputed · C6 $1,200 asked → accepted.
- After the amendment: C4 → $540 disputed, $1,000 conceded; totals $3,120 disputed and $3,730 accepted.
- Fernwell ← Tidemark: $1,878.60 disputed, $6,480.20 accepted, 1 question (a $5,487.50 excess over the $5,000
  limit). Ridgefire ← Corbel: $1,918.00 disputed, $655.00 accepted, 1 question. Birchbank ← Greenfold: all 4 fair,
  $2,881.52 accepted.
- A live Peak Bar run: 65–73 s, 13–14 Claude calls, about $0.38 of Claude. Eval: 30 of 30, 0 wrong automatic actions.
- The cases: Omaha v. UNFI $268,816.94 of ~$326,780 (~82%); Saks ~$34M not owed, ~$48M repaid with interest; Walmart
  OTIF 3% of cost of goods, 98% target from Sept 15, 2020; Coles $10M penalty, more than $12M refunds ordered;
  TeaSquares $32,000 invoiced, $21,000 paid.

## If something goes wrong

| Problem | Do | Say |
| --- | --- | --- |
| The feed is slow before 1:00 | Keep narrating; open C1 the moment it lands | "Every line here is a live call: Claude, Gemini, then code." |
| No card by 1:00 | Plan B: the backup video | "Same run, recorded this morning; the live one finishes behind it." |
| "Too many runs" | Make sure the admin token is set; otherwise a judge's phone at clawback.biz has its own 3 runs | "The public site limits each visitor's runs, so a link can't drain our credits." |
| Dana's WhatsApp doesn't arrive | Answer on the charge's card, signed in as the owner | "Same question, in the app." |
| Sam's Approve fails | Sam replies `YES` on WhatsApp (only the controller's number counts) | "Same approval, from the controller's phone." |
| The controller says no | Show "held by controller" with the note | "That's the point: if the controller refuses, nothing posts." |
| A portal reply is held for Dana | Tap a preset instead | "Anything it can't back with evidence goes to the owner, never out the door." |
| Over time | Skip ✂ rows | — |

## Video version

The 2:30 video follows the shot list in docs/design.md ("Video, live pitch and Devpost"), opening on the Omaha case
instead of the portal.
