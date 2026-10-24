# Judge Q&A: short, honest answers

> Two or three lines each, then point at the screen in brackets. Facts come from `main` (commit 53571d2, Sat Oct 24),
> `DECISIONS.md`, `eval/published/` and the Devpost draft ([devpost.md](devpost.md)), plus what's being finished
> today: four accounts, new charge types, "How Clawback decided", the remittance upload, and the owner and
> controller sign-ins. Check each new screen once on clawback.biz before judging.
>
> - **`TBD (measured)`** is a number we haven't measured. Say "we haven't measured that yet," never a guess.
> - **TODO (needs Devank)** is a fact to fill in, or a line to delete, before judging.
> - All four brands and distributors are invented. The app doesn't say so, so we do.

## The hard ones

**"You graded your own homework."**
Fair. We wrote the 30 test charges and the answer key (the key before the first run). So grade it yourself: type a
clause and a charge here, both models read it live, and you see the decision with its evidence.
[`/scenario`: the judge types; open the decision's sentence and its trace]
- It decides against Peak Bar's March sales and earlier payments, so suggest a promo or fee clause. TODO (needs
  Devank): what else the box accepts today (a shortage, a price, spoilage?).
- Still missing, say so if asked: a deal written by someone outside the team, run cold (`data/eval/outside-deal.md`
  is a placeholder), and the 30 cases cover promo allowances and fees only. TODO (needs Devank): update this if eval
  cases for shortages, prices or spoilage land.

**"Real remittances aren't CSVs."**
Agreed. Drop the distributor's payment slip as a PDF: Claude reads it into charges, and code checks every line and
the totals before they're used.
[The upload screen: drop the sample PDF, open the charges it found] TODO (needs Devank): what the screen shows when a
line or the total doesn't add up, so we can say it in one line.

**"Two models? The eval shows Claude twice."**
You're right about the score. The 30-of-30 agent-mode run was recorded at 3 AM Saturday, before Gemini answered on
our key, so Reader B was a second Claude call with its own prompt, and the score file says `two_models: false`.
Since then, Gemini has read live: it agreed with Claude on every term of the demo deal, both emails and the
amendment, and on one vague test clause it read the products differently, so Clawback asked the owner instead of
guessing. The live site uses Gemini as Reader B, and the trace names the model on every read.
[How Clawback decided: the Gemini row · `docs/proof/gemini-vs-claude.md`]
- If Gemini doesn't answer, Reader B falls back to a second Claude read and the trace says so.
- TODO (needs Devank): if the agent eval is re-run with Gemini on all 30 cases, replace this answer with that score.

**"What does Moss add?"**
Memory by meaning. Each owner answer becomes a rule stored in Moss, and a new judgment-call clause is matched to the
saved rules by meaning, so a reworded display-fee clause still finds Rule #1, with the score on the card.
[April card: "matched by Moss, similarity 1.00" · `/scenario` with a reworded clause]
- Honest limits: the gate also requires the same kind of clause and the same distributor, and with only one saved
  rule that check alone reaches the same rule. And Moss scores any similar fee (a slotting fee, a circular-ad fee)
  at 1.00, so it can't yet tell those apart. Measured: reworded display fee 1.00, late-delivery penalty 0.79,
  spoilage fee 0.67, promo rate 0.35; the gate needs 0.85.

**"What does a run cost, and how long does it take?"**
A live run of the Peak Bar payment takes `TBD (measured)` seconds from deposit to a decided board and costs about
`TBD (measured)` in AI calls (`TBD (measured)` calls, every one listed in the trace). Replaying recorded answers
offline, the board was decided 5.9 seconds after the deposit in rehearsal.
[How Clawback decided: count the rows]
- Checking the same six charges by hand: `TBD (measured)`.
- Each visitor gets 3 live runs per 10 minutes (and the whole site 30 an hour), so the public link can't run up the
  bill.

**"Recovery services and deduction software already exist."**
Yes, and brands pay for them, which shows the need. What we built for: every decision traced to a sentence in that
brand's own deal, fair charges accepted, the distributor's comeback rehearsed before filing, the owner asked only
when the deal is unclear, once, and next month's deal fixed so the fight doesn't repeat.
[C3 accepted with the email · `/coach`]
- Don't name or compare vendors. If pushed: "We can't speak for their products. Here's ours, live."

**"What's the path to production without portal logins?"**
Start from what a brand already has: the payment slip (the upload), the signed deal and its emails, and QuickBooks
through Intuit's official API. None of that needs a distributor login. Today the dispute goes to our mock portal. In
production the same lines (clause, rows, math) go out by email or a person pastes them into the portal. Automating
portals comes later, behind the same approvals.
[Upload screen · D-0417's lines on the portal]

**"Who can move money?"**
No agent. Only the controller's sign-in can approve the credit memo, never the owner's sign-in or an agent. If the
controller says no, nothing is written and the note shows on the card. Disputes over $5,000 wait for the owner.
[Sam's phone, signed in as controller · audit log]
- By text, only a reply from the controller's number counts, and Twilio's signature is checked.

**"What if the AI is wrong?"**
Then the worst case is a question, not a payment. A term counts only if both models read it the same way and its
sentence is found word for word. Code does all the math. A dispute needs confidence of at least 0.9, two kinds of
evidence and an answer to the comeback, or the owner decides. Nothing reaches the books without the controller.
And when the distributor shows a valid document, it backs down.
[Tablet: **Attach signed amendment** → $1,000 conceded, $540 still disputed]

**"What if the distributor sends instructions in an email?"**
Emails are data, never instructions. Only the owner, the approved broker or a document both sides signed can change
a deal. Northmart's own email saying the rate is $1.50 is shown as a claim and never applied.
[Peak Bar: the Mar 30 email on C1's card · the tough distributor's emailed rate claim] One eval case tests it.

**"Why not just a rules engine?"**
The money part is a rules engine: plain Python with tests and a fixed nine-row decision table. The AI does what rules
can't: every deal is worded differently, and changes arrive by email.
[How Clawback decided: AI rows read and explain; the math and the decision are code]

**"Is the code open?"**
Yes: github.com/devank-yadav/clawback, with the eval runnable in one command (`make eval`).
TODO (needs Devank): make it public after the secrets scan (Sun before 8 AM). Until it is, say "It goes public this
morning, right after our secrets scan."

## The product

**Are these real companies?**
No. All four accounts are invented and styled to look like real businesses so the screens feel real. None of them is
a customer. The AI, the math, the phones and the QuickBooks sandbox books are real.

**What are the four accounts?**
Peak Bar Co. and Northmart, the full story. A drinks brand: a shortage the delivery records disprove, a price that's
partly wrong, spoilage over the allowance, and an overcharge over $5,000 that waits for the owner. A clean month:
every charge fair, all accepted. A tough distributor: an emailed rate claim, a repeat charge, a charge outside the
dates, and a vague clause it asks about. [Account switcher]

**How does it check a shortage, a price or spoilage?**
Same pattern as a promo: the charge is compared with a second source (the delivery records, the agreed price, the
deal's spoilage allowance), and code works out the difference. [Drinks brand: the shortage card]

**Can I try it on my phone?**
Yes, at clawback.biz. Each visitor gets 3 live runs per 10 minutes and 20 other AI requests (the scenario box, the
portal, the Deal Coach), so a public link can't drain our credits. Approving money still needs the controller's
sign-in.

**Who is the customer?**
Founders and bookkeepers at small food and drink brands that sell through big distributors.
TODO (needs Devank): one real quote with the person's role and permission, or delete this line.

**Is this a real problem?**
Distributors pay short and keep money for promos, fees, shortages and spoilage. Suppliers have sued over it (the
UNFI class action reported by Grocery Dive). Each charge takes hours to check, so most never are.

## How it decides (Peak Bar)

**Why was C3 accepted when it's outside the promo dates?**
The approved broker extended the promo through April 7 by email on March 28, and the deal (§6.1) lets an approved
rep change terms in writing. [C3's card → the email]

**Why ask about C6 at all?**
§5.4 lets Northmart charge the fee "at its discretion." That's a judgment call, so it belongs to the owner. Clawback
asks once and saves the answer as Rule #1. [Rule #1 card · `/april`]

**What if the two readers disagree?**
The term is marked disputed and every charge that depends on it goes to the owner. Nothing is filed or booked.
Recorded example: on "its core bars", Claude left the products out and Gemini read "core bars", so it asked.
[`docs/proof/gemini-vs-claude.md`]

**What if the AI invents a clause?**
It can't use one. The quote must be found in the document word for word, and every number in the term must appear
in that quote. Otherwise the term is rejected. [C1's card: the highlighted §3.1 sentence]

**What stops it disputing everything?**
It accepted $2,730 here, including a charge that looked wrong until it found the email. It accepts undercharges and
never asks for more than the deal allows. A whole account of fair charges is accepted. [Clean month]

**What's the dollar limit?**
Disputes up to $5,000 in total file on the owner's standing policy. Over $5,000 waits for the owner. The limit is
checked per charge and again on the whole dispute. D-0417 is $4,120. [Drinks brand: the charge waiting on the owner]

**What gets written to QuickBooks?**
A $2,730 credit memo, one line per accepted charge, applied to INV-3102. The disputed $4,120 stays open with a note
listing D-0417's lines. Checked live in the sandbox, and `make reset` deletes those writes again.
[QuickBooks post on the board]

**Can I see why a decision was made, later?**
Every decision cites a sentence, a data row, a rule or a person. Every AI call is in the trace, and every action is
in a hash-chained audit log, so editing a past row breaks the check. [How Clawback decided · `/audit` → Verify chain]

## Proof

**How accurate is it?**
30 of 30 on 30 planted charges, amounts right to the cent, 6 asked, 0 wrong automatic actions, both with the math
and gate alone and with the AI in the loop. We wrote the cases ourselves, and the agent run used Claude for both
readers (see "two models" above). [`/results`]

**What's a "wrong automatic action"?**
Acting where the key says ask, disputing a fair charge, or accepting a wrong one. Our target is zero.

**What if the Wi-Fi dies?**
The backup laptop runs `make demo`: recorded AI answers and a labeled QuickBooks stand-in, same logic, same numbers.

## Safety

**Can it make promises to the distributor?**
No. A filter checks every outgoing message: any dollar figure or quote not in a finding or a verified term, and any
promise, discount or deadline the owner's policy didn't set, is blocked. Twice blocked, the message waits for the
owner.

**What about real customer data?**
The demo uses only invented data. In production: least-privilege access to the books, no training on customer data,
and each brand's data kept separate.

**What would you build next?**
Rules and the audit chain stored in the database (runs already are), more distributors and charge types, and the
Deal Coach's edits going into the next negotiation.
