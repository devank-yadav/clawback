# Live pitch: 3 minutes, then 2 minutes of Q&A

> What we say and click at the judging table on Sunday. Written for the product as it's being finished on Sat Oct 24:
> four accounts on https://clawback.biz, every run generated live, "How Clawback decided", the remittance upload, and
> the owner and controller sign-ins. Walk through it once on the live site Sunday morning and fix any label below
> that doesn't match the screen.
>
> - **The app has no "fictional" labels.** The honesty line is spoken, once, at 0:30. Never skip it.
> - **Peak Bar's numbers are fixed** (data/CLAUDE.md). Never round them. For the other three accounts, say no
>   amounts: read them off the screen if a judge asks.
> - **Roles:** Devank narrates and holds the owner's phone (Dana). Rishi drives the laptop. Manasv holds the
>   controller's phone (Sam) and runs the reset between tables.
> - ✂ marks a line to cut if we're running long.

## The script

Plan A starts a fresh live run at 0:48. Plan B (walk the board of the run made before the judge sat down) is below;
pick it during setup, not mid-pitch. Each "Say" line is timed at about 2.5 words a second.

| Time | Do | Say |
| --- | --- | --- |
| 0:00–0:30 | Hand the judge the tablet, open on dispute D-0417 in the Northmart portal, and the printed deal. "You're the distributor. Push back: tell us there was no cap." The judge types it, or taps **There was no cap**. Clawback's reply lands with §3.2 and the weekly sales. Say the line once it lands. | "You're Northmart, a big distributor, and you just told a small snack brand its promo had no cap. Clawback answered with the sentence you signed: §3.2, 5,000 bars. And the store sales: 1,200, 980 and 2,820. That's 5,000 before week 4 even started." |
| 0:30–0:48 | Laptop on Peak Bar Co.'s payment: $48,200 invoiced, $41,350 received, −$6,850. | "One honest note: these companies are simulated. The AI, the math, the phones and the QuickBooks sandbox books are real. Peak Bar billed $48,200 for March and got $41,350: Northmart kept $6,850 in six charges. Checking them takes hours a founder doesn't have." |
| 0:48–1:00 | Click **Northmart pays**. The feed starts. | "The short payment just landed in the bank, and that starts Clawback. Claude and Gemini each read the deal and the emails. Plain code does all the math." |
| 1:00–1:23 | Open C1: the highlighted §3.1 sentence and the math line. Then C3 and its email. | "Week 1: they charged $1.50 a bar. §3.1 says $1.00. So $600 is disputed and the fair $1,200 is accepted. This one looks wrong: April dates on a March promo. But the approved broker extended it by email. Accepted. It doesn't fight fair charges." |
| 1:23–1:43 | Dana's phone buzzes. Devank reads the question aloud and replies `accept if notice is at least 14 days`. Rule #1 appears; C6 moves to Accept. | "The display fee is 'at its discretion.' That's a judgment call, so it asks the owner, once. She sets a rule: 14 days' notice. This notice came 20 days ahead, so it's accepted. Next month, it won't ask." |
| 1:43–1:54 | Point at the totals: $4,120 disputed, $2,730 accepted, 1 question. The $2,730 credit memo waits on the controller. | "$4,120 disputed, $2,730 accepted, one question. The $2,730 credit memo, the QuickBooks entry for what we accept, now waits for the controller. Back to that in a second." |
| 1:54–2:07 | Switch accounts: the drinks brand, then the tough distributor, then the clean month. | "Three more accounts. A drinks brand: delivery records disprove a shortage. A tough distributor: its emailed rate is never applied. And a clean month: every charge fair, all accepted. It never fights a fair charge." |
| 2:07–2:28 | Back on Peak Bar. Open **How Clawback decided** on C4. If the rows differ from the line, describe the rows on screen instead; add nothing that isn't there. | "This is every AI call behind the charge you argued about. Claude and Gemini each read the cap. Code found the sentence word for word and did the math. Claude wrote the finding, and rehearsed your comeback before filing. Then the gate, plain code, made the call. The AI reads; code decides." |
| 2:28–2:46 | Manasv, signed in as the controller on Sam's phone, taps **Approve**. The QuickBooks post appears: memo written, INV-3102 at $4,120 open. | "Money is the one thing no agent can touch. Only the controller's sign-in approves this. Not the owner's, not an agent. Sam says yes, and QuickBooks gets it: $2,730 credited, $4,120 left open with the dispute lines." |
| ✂ 2:46–2:52 | Open `/april` (start the April replay if it hasn't run). | "Next month: two display fees, decided by Rule #1. Zero questions." |
| 2:52–3:00 | Open `/results`. | "$4,120 disputed, $2,730 accepted, one question. And on 30 planted charges: 30 of 30, zero wrong automatic actions." |

If ✂ was cut, say the April line in a few words before the score.

### Plan B: walk the run made before the judge sat down

Use it when the setup run was too slow for Plan A's timings (C1 decided more than 12 seconds after the deposit, or
the whole board more than 35), or the live site is slow that morning.

- 0:48–1:00: don't click **Northmart pays**. Open the board of the run made in setup and say "This ran two minutes
  ago, when Northmart's short payment landed in the bank."
- 1:23–1:43: Dana's question from that run is still open. Answer it the same way.
- Everything else is the same.

## Before the judge sits down (setup, about 4 minutes)

- [ ] **Reset the live site** (Manasv): `make reset API=https://clawback.biz/api CLAWBACK_ADMIN_TOKEN=<token>`.
      QuickBooks goes back to INV-3102 with $6,850 open, and Rule #1 is gone. Check that it answered `ok: true`.
- [ ] **Presenter's laptop skips the visitor limit** (the admin token). Without it, our own setup runs use up the
      3 live runs per visitor per 10 minutes. TODO (needs Devank): how the laptop's browser carries the admin token.
- [ ] **Run the other three accounts first, Peak Bar last** (Rishi). Answer nothing and approve nothing. Texts
      answer the newest open question, so Peak Bar's has to be the newest one. Time Peak Bar's run from the deposit:
      C1 decided within 12 seconds and the whole board within 35 means Plan A; anything slower means Plan B.
- [ ] **Look at the tough distributor's trace.** Every run is read live, so the two readers may or may not split on
      its vague clause this time. In Q&A, claim a disagreement only if this trace shows one.
- [ ] **Tablet** on `/portal`, dispute D-0417 open, signed in as nobody (it's Northmart). Printed deal
      (`data/deals/spring-promo.md`) on top, §3.1, §3.2 and §5.4 visible.
- [ ] **Dana's phone** (Devank): WhatsApp open on the chat with Twilio's sandbox number, and clawback.biz signed in
      as the owner (the in-app fallback). Send any message from it to the sandbox on Sunday morning: WhatsApp only
      lets a business send a free-form message to someone who wrote in the last 24 hours (check in Twilio's console).
- [ ] **Sam's phone** (Manasv): clawback.biz signed in as the controller, on Approvals. WhatsApp open as well.
- [ ] **Laptop tabs** (Rishi): Peak Bar's payment, the other three accounts, `/april`, `/results`, `/scenario`,
      the upload screen with a sample remittance PDF on the desktop. TODO (needs Devank): which PDF to use.
- [ ] **Backup:** a second laptop running `make demo` (replays recorded answers, works offline) and the backup video
      in a tab. TODO (needs Devank): check that the three new accounts replay in `make demo`. If they don't, skip the
      tour on the backup.

## What to click (the presenter's list)

1. Tablet → judge. Portal reply arrives.
2. Laptop: Peak Bar's payment screen.
3. **Northmart pays** (Plan A only).
4. C1 → its evidence (sentence, math line).
5. C3 → the broker's email.
6. Dana's phone: reply to the question.
7. Totals; Approvals shows the memo waiting.
8. Account switcher: drinks brand → tough distributor → clean month → back to Peak Bar.
9. C4 → **How Clawback decided**.
10. Sam's phone: **Approve**. Then the QuickBooks post on the laptop.
11. ✂ `/april`.
12. `/results`.

## Q&A plan (2 minutes)

- **Devank answers** in two sentences, then points. **Rishi puts on screen** whatever the answer points at.
  **Manasv hands** the judge the laptop on `/scenario` or the tablet when the answer is "try it."
- **No question in the first five seconds?** Offer one: "We wrote our own test cases. Want to try a clause of your
  own?" Open `/scenario`: the judge types a clause and a charge, and both models read it live.
- **The five we expect, and where each answer points** (full answers in [judge-qa.md](judge-qa.md)):

| Question | Point at |
| --- | --- |
| "You graded your own homework." | `/scenario`: the judge's own clause, decided live |
| "Real remittances aren't CSVs." | The upload: drop the sample PDF |
| "Two models? The eval shows Claude twice." | How Clawback decided: the Gemini row; then the one-line truth about the score |
| "Who can move money?" | Sam's phone: the controller's sign-in. The owner's sign-in can't approve |
| "What if the AI is wrong, or the distributor is right?" | Tablet: **Attach signed amendment**. $1,000 is conceded and $540 stays disputed |

- **Don't know a number?** Say "we haven't measured that." Never guess, never round a demo number.
- **At 4:30**, Devank says "last question." End on the scoreboard, still open on `/results`.

## Numbers to have in your head (Peak Bar Co. ← Northmart)

- Invoice INV-3102 **$48,200** · paid **$41,350** · taken **$6,850** (6 charges)
- C1 $1,800 → $600 disputed + $1,200 accepted · C2 $980 disputed · C3 $330 accepted · C4 $1,540 disputed ·
  C5 $1,000 disputed · C6 $1,200 asked → accepted
- Totals: **$4,120 disputed**, **$2,730 accepted**, **1 question**. Credit memo $2,730 = C1 $1,200 + C3 $330 + C6 $1,200.
- After the amendment: C4 → **$540 disputed, $1,000 conceded**; totals become $3,120 disputed and $3,730 accepted.
- Cap math: 1,200 + 980 + 2,820 = 5,000 (cap reached Mar 21). With the 6,000 cap, 1,000 of week 4's 1,540 are covered.
- April: $1,200 fee, 18 days' notice → accept · $800 fee, 5 days' notice → dispute · 0 questions.
- D-0417 is $4,120, under the $5,000 limit, so it files on the owner's standing policy.
- Eval: 30 of 30, amounts right to the cent, 6 asked, 0 wrong automatic actions.

## If something goes wrong

| Problem | Do | Say |
| --- | --- | --- |
| The portal reply is slow in the first 30 seconds | Keep talking through the clause on the printed deal; the reply lands | "It's reading your message and checking every number it sends back." |
| The portal holds the judge's message for Dana | Tap **There was no cap** instead | "Anything it can't back with evidence goes to the owner, never out the door." |
| The board is still filling at 1:00 | Narrate the feed lines as they arrive; open C1 the moment it lands | "Every line here is a real call: Claude, Gemini, then code." |
| "Too many runs" (visitor limit) | Use the run made in setup (Plan B) | "The public site limits each visitor's live runs, so a link can't drain our credits." |
| Dana's WhatsApp doesn't arrive | Answer on the charge's card, signed in as the owner | "Same question, in the app." |
| Sam's sign-in or Approve fails | Sam replies `YES` on WhatsApp (only the controller's number counts) | "Same approval, by text from the controller's phone." |
| The controller says no | Show "held by controller" with the note | "That's the point: if the controller refuses, nothing posts." |
| Wi-Fi or the live site is down | Second laptop, `make demo` | "Every outside call is recorded, so it runs offline. Same logic, same numbers." |
| Over time | Skip ✂ rows | — |

## Video version

The 2:30 video follows the shot list in docs/design.md ("Video, live pitch and Devpost"). It also opens on the portal
comeback.
