# Live demo script (3 minutes, then 2 minutes of Q&A)

> Spoken walkthrough for the judging table. Numbers are fixed by data/CLAUDE.md; never round or change them.
> Steps marked **[PLANNED]** depend on screens not built yet (checked against `main` at commit f55757a, Sat Oct 24
> morning). The API behind every step is built and tested.
> **In `make demo` (DEMO_MODE) no texts go out and QuickBooks writes are simulated:** answer Dana's question and
> Sam's approval in the app. Phones buzz only in a live run with the Twilio keys set.
> Cut lines are marked ✂ if we're running long. Everyone named is fictional; say so once at the start.

## Before the judge sits down (checklist)

- [ ] `make reset` ran; the board is empty and Rule #1 does not exist yet.
- [ ] Laptop on `/` (Overview, with the **Northmart pays** button). Tablet on `/portal` as Northmart. **[PLANNED: `/portal` screen]**
- [ ] Owner phone (Dana) and controller phone (Sam) on the table, unlocked, volume up (live runs only; SMS or Twilio's WhatsApp Sandbox).
- [ ] Printed deal (`data/deals/spring-promo.md`) with §3.1, §3.2 and §5.4 visible.
- [ ] `DEMO_MODE=true` ready as the fallback (`make demo`); backup video open in a tab.
- [ ] Roles: **Devank** narrates · **Rishi** drives the laptop · **Manasv** holds the controller phone and runs reset.

## The script

| Time | Do | Say |
| --- | --- | --- |
| 0:00–0:15 | Hand the judge the printed deal and the tablet. | "You're Northmart, a big distributor. Everything here is fictional. This is the promo deal you signed with Peak Bar Co., a small snack brand." |
| 0:15–0:30 | Laptop on the Payment screen: expected $48,200, received $41,350, −$6,850 in red. | "Peak Bar invoiced you $48,200 for March. You paid $41,350. You took $6,850 back in six charges. Checking each one by hand takes hours a founder doesn't have." |
| 0:30–0:45 | Click **Northmart pays** (posts the Nessie deposit; without Nessie keys or in DEMO_MODE it starts the run directly). The board starts filling. | "The short payment just landed in the bank. That starts Clawback. It reads the deal, the emails and the store sales, and checks every charge." |
| 0:45–1:05 | Open C1's evidence card. Point at the highlighted §3.1 sentence and the math line. | "Week 1: you charged $1.50 a bar. The deal says $1.00, right here in §3.1. So $600 is disputed and the fair $1,200 is accepted. Every number on this card opens its source." |
| 1:05–1:20 | Point at C3 in the Accept column, open the broker email. | "This one looks wrong: April dates on a March promo. But the broker extended it by email on March 28, and he's an approved sender. So Clawback accepts the $330. It doesn't fight fair charges." |
| ✂ 1:20–1:30 | Point at C2 and C5 in Dispute. | "Week 2 was already paid on March 14, so $980 is disputed. Mint isn't in the deal, so that $1,000 is disputed too." |
| 1:30–1:50 | Owner phone buzzes. Read the SMS aloud, then reply "accept if notice is at least 14 days". Rule #1 card appears. (In DEMO_MODE, answer on the charge's card in the app.) | "The display fee says 'at its discretion.' That's a judgment call, so Clawback asks the owner once. She sets a rule: accept if notice is at least 14 days. This one had 20 days, so it's accepted." |
| 1:50–2:00 | Meters land on $4,120 disputed, $2,730 accepted, 1 question. Controller phone buzzes: "Approve credit memo of $2,730 (3 lines)?" Manasv taps **yes**. | "Only a person moves money. The controller approves the $2,730 credit memo, and it goes into QuickBooks. The disputed $4,120 stays open." |
| 2:00–2:25 | Turn to the judge. "Reply to our dispute on the tablet. Argue." Judge types (likely "there was no cap"). Clawback answers in the thread. | "Before filing, Clawback predicted your comeback and made sure it could answer it. §3.2 caps the promo at 5,000 bars. Weeks 1 to 3 sold 1,200 plus 980 plus 2,820, which is 5,000. Week 4's 1,540 bars aren't covered." |
| 2:25–2:40 | If the judge doesn't, ask them to tap **Attach signed amendment**. C4 changes: $540 disputed, $1,000 accepted. | "Now you've shown a signed amendment raising the cap to 6,000. That's a valid document, so Clawback concedes $1,000 and keeps $540 disputed. It argues with proof, and backs down with proof." |
| 2:40–2:50 | Open `/april`. **[PLANNED: screen; API is `POST /replay/april`]** | "Next month: a $1,200 fee with 18 days' notice is accepted and an $800 fee with 5 days' notice is disputed, both by Rule #1. Zero questions. It asks once and never twice." |
| ✂ 2:50–2:55 | Open `/coach`. **[PLANNED: screen; API is `POST /coach`]** | "And it rewrites next month's deal so this fight doesn't happen again." |
| 2:55–3:00 | Open `/results`. **[PLANNED: screen]** | "$4,120 disputed, $2,730 accepted, one question, and our real score on 30 planted charges: 30 of 30, with zero wrong automatic actions. That's Clawback." |

## Numbers to have in your head

- Invoice INV-3102 **$48,200** · paid **$41,350** · taken **$6,850** (6 charges)
- C1 $1,800 → $600 disputed + $1,200 accepted · C2 $980 disputed · C3 $330 accepted · C4 $1,540 disputed ·
  C5 $1,000 disputed · C6 $1,200 asked → accepted
- Totals: **$4,120 disputed**, **$2,730 accepted**, **1 question**. Credit memo $2,730 = C1 $1,200 + C3 $330 + C6 $1,200.
- After the amendment: C4 → **$540 disputed, $1,000 conceded**; totals become $3,120 disputed and $3,730 accepted.
- Cap math: 1,200 + 980 + 2,820 = 5,000 (cap reached Mar 21). With the 6,000 cap, 1,000 of week 4's 1,540 are covered.
- April: A1 $1,200, 18 days' notice → accept · A2 $800, 5 days' notice → dispute · 0 questions.
- Dispute D-0417 is $4,120, under the $5,000 auto-dispute limit, so it files on the owner's policy.

## If something goes wrong

| Problem | Do | Say |
| --- | --- | --- |
| Wi-Fi drops or a live call fails | Switch to `make demo` (DEMO_MODE replays saved responses) | "We record every outside call, so the demo runs offline. Same logic, same numbers." |
| SMS doesn't arrive | Answer in the app (the charge's card, or Approvals for Sam) | "Same question, in the app instead of a text." |
| Nessie deposit doesn't start the run | Restart the API with `NESSIE_POLL=off` (or use `make demo`); then **Northmart pays** starts the run itself | — |
| Controller says no (on purpose or by mistake) | Show "held by controller" with the note | "That's the point: if the controller refuses, nothing posts." Then reset if time allows. |
| Judge types nonsense in the portal | Let Clawback reply; it asks for the written change or routes to the owner | "It only changes its mind for a signed document." |
| Over time | Skip the ✂ rows | — |

## Video version

The 2:30 video follows the shot list in docs/design.md ("Video, live pitch and Devpost"). It opens on the
portal comeback, not on the payment screen.
