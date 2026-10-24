# Judge Q&A: short answers

> Two lines per answer, each pointing at something on screen. Built from docs/design.md (Judge Q&A, Risks,
> Responsible design), checked against `main` at commit f55757a (Sat Oct 24 morning) and the canonical Devpost
> draft, docs/submission/devpost.md. **[TODO]** marks a fact to fill in before judging. Everyone named is fictional. Never quote a number that isn't in this file or on the scoreboard.

## The problem and the customer

**Who is the customer?**
Founders and bookkeepers at small food and consumer brands that sell through big distributors. **[TODO: quote
from our interviews, with role.]**

**Is this a real problem?**
Distributors pay short and take money back for promos and fees; suppliers have sued over it (the UNFI class
action, in our Sources). Each charge takes hours to check, so most never are.

**Don't recovery services already do this?**
Yes, and companies pay them, which shows the need. We read each deal's exact wording, accept fair charges,
argue back live, and fix the next deal.

**What job does it replace?**
The deductions analyst and the collections specialist: checking each charge, filing disputes, answering the
distributor, and booking the result.

## How it decides

**What if the AI invents a clause?**
It can't use one. The quote must be found in the source word for word, two different models must agree, and
any disagreement goes to a person. (Show a rejected term.)

**Does the AI compute the amounts?**
No. All money math is plain Python with unit tests (`api/engine/`). The AI finds and quotes terms; code does
the arithmetic; a fixed decision table decides.

**Why not just a rules engine?**
The math is a rules engine with tests. The hard part is that every deal is worded differently and changes
arrive by email; reading that is the AI's job.

**Why did C3 get accepted when it's outside the promo dates?**
The approved broker extended the promo through April 7 by email on March 28. The deal (§6.1) lets an approved
rep change terms in writing. (Open the email from the card.)

**A distributor emails new terms. What happens?**
Only approved senders or a document signed by both sides can change a deal. Northmart's own email saying "the
rate is $1.50" is shown as a claim and never applied. It's in our eval.

**What stops it disputing everything?**
It accepted $2,730 here, including a charge that looked wrong until it found the email. It never asks for
more than the deal allows, and it accepts undercharges.

**Why ask about C6 at all?**
§5.4 says Northmart may charge the fee "at its discretion." That's a judgment call, so it belongs to the owner.
Clawback asks once and saves the answer as Rule #1.

**How does "never asks twice" work with different wording?**
Saved rules are indexed in Moss and matched by meaning: a differently worded display-fee clause still finds Rule #1
(similarity at least 0.85, same kind of clause, same distributor), and the card shows the score. Without Moss it falls
back to matching the kind of clause and the distributor. Show it in the scenario box with a reworded clause.

**What if the two AI readers disagree?**
The term is marked disputed and every charge that depends on it goes to the owner. Nothing is filed or booked.
Real example: on "its core bars", Claude left the products out and Gemini read "core bars", so Clawback asked
(docs/proof/gemini-vs-claude.md).

**What if the distributor is right?**
It concedes. When the judge attaches the signed amendment raising the cap to 6,000, Clawback withdraws $1,000
of C4 and keeps $540 disputed.

## Money and control

**Who can move money?**
No agent. The credit memo needs the controller's yes; if the controller refuses, nothing posts and the note
shows on the card. (Show the approval and the audit log.)

**What's the dollar limit?**
Disputes up to $5,000 in total file on the owner's standing policy; over $5,000 waits for the owner. The limit
is checked per charge and again on the whole dispute. D-0417 is $4,120.

**What actually gets written to QuickBooks?**
A credit memo for the $2,730 accepted, one line per charge, applied to INV-3102; the disputed $4,120 stays open
with a note listing the D-0417 lines. Checked live in the sandbox: INV-3102 dropped to $4,120 open, and
`make reset` puts it back to $6,850.

**Can I see why a decision was made later?**
Every decision cites a sentence, a data row, a rule or a person, and every action is in a hash-chained audit
log; editing a past row breaks the chain check. (Show "Verify chain".)

## Proof

**How accurate is it?**
30 of 30 correct on 30 planted charges, amounts right to the cent, 6 asked, 0 wrong automatic actions, in both engine mode (math and gate alone) and agent mode (readers and agents in the loop). The answer key was written before the first run. We wrote the cases ourselves, so a deal from someone
outside the team is next. (Show the scoreboard.)

**What counts as a "wrong automatic action"?**
Acting where the key says Ask, disputing a fair charge, or accepting a wrong one. Our target is zero.

**What's real and what's simulated?**
Real: the AI reading, the math, the decision rules, the QuickBooks sandbox writes, the SMS, the Nessie deposit,
the eval score. Simulated: Peak Bar Co. and Northmart are fictional; we wrote the deal, emails and sales; the
portal is our mock.

**Can I try my own case?**
Yes: paste a clause and a charge and it decides with evidence (`POST /scenario`, built). **[TODO: the `/scenario`
screen]**

**What if the Wi-Fi dies?**
`DEMO_MODE` replays saved AI and QuickBooks responses with the same logic, so the demo runs offline.

## Safety and responsible design

**What could go wrong?**
A misread deal could dispute a fair charge and hurt the relationship. That's why two models must agree, quotes
are verified, low confidence goes to a person, and it concedes on a valid document.

**What about instructions hidden in documents?**
Documents, emails and portal replies are data, never instructions. Nothing in them can change an agent's tools
or the policy.

**Can it make promises to the distributor?**
No. An outbound filter blocks any dollar figure or quote not in a finding or verified term, and any promise,
discount or deadline the policy didn't set.

**What about real customer data?**
The demo uses only fictional data. In production: least-privilege QuickBooks access, no training on customer
data, and per-brand isolation.

## What's next

**How does this reach production?**
Real portals through browser automation (recovery services already do this), adapters for NetSuite or Xero
beside QuickBooks, and the same approval and audit model.

**What would you build next?**
More distributors and deal types, and the Deal Coach
feeding redlines into the next negotiation.
