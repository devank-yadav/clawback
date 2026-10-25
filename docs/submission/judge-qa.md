# Judge Q&A: short, honest answers

> Two or three lines each, then point at the screen in brackets. Facts come from `main` (Sat Oct 24, after the
> multi-account merge), `DECISIONS.md`, `eval/published/`, the Devpost draft ([devpost.md](devpost.md)) and
> [sources.md](sources.md) for every real case.
>
> - **Real facts are told the way their source tells them** ("Omaha Industries sued UNFI in 2024, saying …"). Never
>   say what Clawback would have won for a real company; say what it would have checked and flagged.
> - **`TBD (measured)`** is a number we haven't measured. Say "we haven't measured that yet," never a guess.
> - **TODO (needs Devank)** is a fact to fill in, or a line to delete, before judging.

## The hard ones

**"Is this real data?"**
The contracts are real: KeHE's 2015 vendor policies and Walmart's and Five Below's supplier agreements, unedited from
public SEC filings. The cases are real: Omaha Industries v. UNFI, Saks's markdown allowances, Walmart's on-time fines,
Coles in Australia. The brands, their charges and every number in our accounts are ours.
[`data/contracts/README.md` with the SEC links · [sources.md](sources.md)]
- None of those companies is a customer or took part. Peak Bar's deal with Northmart is one we wrote.

**"You graded your own homework."**
Fair. We wrote the 30 test charges and the answer key (the key before the first run). So grade it yourself: type a
clause and a charge here, both models read it live, and you see the decision with its evidence.
[`/scenario`: the judge types; open the decision's sentence and its trace]
- It decides against Peak Bar's March sales and earlier payments, so suggest a promo or fee clause. TODO (needs
  Devank): what else the box accepts today (a shortage, a price, spoilage?).
- Still missing, say so if asked: a deal written by someone outside the team, run cold (`data/eval/outside-deal.md`
  is a placeholder), and the 30 cases cover promo allowances and fees only. Shortages, prices and spoilage are checked
  on the three new accounts' live runs instead (13 of 13 matched).

**"Real remittances aren't CSVs."**
Agreed. Drop the remittance as a PDF or paste it: Claude lists its deduction lines, and code checks that each line's
quote is printed on the page word for word, its numbers are in that quote, and the lines add up to what was short.
A line not on the page is rejected; a read that doesn't add up can't start a run; anything else unclear goes to the
owner. [`/upload`: each line's quote highlighted, the totals check, then confirm to start the run]

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
Measured on 5 live Peak Bar runs: 65 to 73 seconds from the deposit to a decided board, 13 or 14 Claude calls, about
$0.38 of Claude per run, and the same decisions every time. Gemini's calls show tokens but no cost, because we
couldn't open Google's price page to copy the prices. [The trace summary: calls, tokens, time and cost per run]
- Checking the same six charges by hand: `TBD (measured)`.
- Each visitor gets 3 live runs per 10 minutes (the whole site 30 an hour), so the public link can't run up the bill.

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
No agent. Only the owner, signed in as the admin, can approve the credit memo. If she says no, nothing is written and
the note shows on the card. If she ticked "post fair charges like these automatically", later memos up to that amount
post on her rule, and the audit log says so. Disputes over $5,000 wait for her too.
[Dana's phone, signed in as the admin · audit log]
- By text, only a reply from the owner's number counts, and Twilio's signature is checked.

**"What if the AI is wrong?"**
Then the worst case is a question, not a payment. A term counts only if both models read it the same way and its
sentence is found word for word. Code does all the math. A dispute needs confidence of at least 0.9, two kinds of
evidence and an answer to the comeback, or the owner decides. Nothing reaches the books without the owner's yes.
And when the distributor shows a valid document, it backs down.
[Tablet: **Attach signed amendment** → $1,000 conceded, $540 still disputed]

**"What if the distributor sends instructions in an email?"**
Emails are data, never instructions. Only the owner, the approved broker or a document both sides signed can change
a deal. Northmart's own email saying the rate is $1.50 is shown as a claim and never applied.
[Peak Bar: the Mar 30 email on C1's card · Ridgefire: R1, Corbel's emailed rate] One eval case tests it.

**"Why not just a rules engine?"**
The money part is a rules engine: plain Python with tests and a fixed nine-row decision table. The AI does what rules
can't: every deal is worded differently, and changes arrive by email.
[How Clawback decided: AI rows read and explain; the math and the decision are code]

**"Is the code open?"**
Yes: github.com/devank-yadav/clawback, with the eval runnable in one command (`make eval`).
TODO (needs Devank): make it public after the secrets scan (Sun before 8 AM). Until it is, say "It goes public this
morning, right after our secrets scan."

## The product

**Are the brands real?**
No: Peak Bar, Fernwell, Ridgefire and Birchbank and their numbers are ours, and so is Northmart. The contracts in the
real-contract accounts (KeHE, Walmart, Five Below) are real text from SEC filings, but those companies didn't take
part, and the charges against our brands are ours.

**What are the accounts?**
Peak Bar ← Northmart, the full story. Fernwell Sparkling Tea ← Tidemark: a shortage the proof of delivery disproves,
a price claim and spoilage that are partly right, and a $5,487.50 excess over the $5,000 limit that waits for the
owner. Ridgefire Salsa ← Corbel: a rate from Corbel's own email, a repeat charge, a charge after the feature ended,
and a clause worded two ways, so it asks. Birchbank Kitchen ← Greenfold: every charge fair, $2,881.52 accepted.
Plus the accounts on real contracts. TODO (needs Devank): their names once merged. [Account switcher]

**How does it check a shortage, a price or spoilage?**
Same pattern as a promo: the charge is compared with a second source (the proof of delivery, the agreed price list,
the deal's spoilage terms), and code works out the difference. No delivery row or agreed price means it asks.
[Fernwell: F3, 180 of 180 cases signed for]

**Can I try it on my phone?**
Yes, at clawback.biz. Each visitor gets 3 live runs per 10 minutes and 20 other AI requests (the scenario box, the
portal, the Deal Coach), so a public link can't drain our credits. Approving money still needs the admin's
sign-in.

**Who is the customer?**
Founders and bookkeepers at small food and drink brands that sell through big distributors and retailers. TODO
(needs Devank): one real quote with the person's role and permission, or delete this line.

**Is this a real problem?**
Omaha Industries sued UNFI in 2024, saying UNFI charged back $268,816.94 on about $326,780 of product sold to Giant
Food. TeaSquares' founder said the company invoiced KeHE $32,000 in 2019 and was paid $21,000. In the UK Groceries
Code Adjudicator's 2026 survey of more than 2,600 suppliers, 20% said retailers were slow to resolve invoice
discrepancies, the most common issue. [sources.md]

**What would Clawback have done for Omaha?**
Checked each chargeback for proof of the product's condition and what happened to it, and flagged the ones with
none, and flagged chargebacks taking most of an invoice. We don't say what it would have won.

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
checked per charge and again on the whole dispute. D-0417 is $4,120. [Fernwell: F2, the $5,487.50 excess waiting on the owner]

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
readers (see "two models" above). Five live Peak Bar runs decided the same way every time, and one live run per new
account matched every expected decision. [`/results`]

**What's a "wrong automatic action"?**
Acting where the key says ask, disputing a fair charge, or accepting a wrong one. Our target is zero.

**What if the Wi-Fi dies?**
Clawback always runs live now, so we play the backup video of a recorded run; the live site keeps running for Q&A.

## Safety

**Can it make promises to the distributor?**
No. A filter checks every outgoing message: any dollar figure or quote not in a finding or a verified term, and any
promise, discount or deadline the owner's policy didn't set, is blocked. Twice blocked, the message waits for the
owner.

**What about real customer data?**
Our accounts hold only our own brands and numbers, and the contracts are public SEC filings. In production: least-privilege access to the books, no training on customer data,
and each brand's data kept separate.

**What would you build next?**
Walmart's on-time-in-full fines checked against the delivery appointment log, more real distributor policies,
and the Deal Coach's edits going into the next negotiation.
