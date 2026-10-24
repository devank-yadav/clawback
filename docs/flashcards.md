# Judge flashcards

15 likely questions with two-line answers. Facts only from docs/design.md (Judge Q&A, Responsible design and the
scenario). Point at the screen named in brackets. Everyone named is fictional. Fill [QUOTE] before judging; the eval score
is from eval/latest.json and eval/latest-agent.json (see docs/submission/devpost.md).

---

**1. Don't recovery services already do this?**
Yes, and companies pay them, which shows the need. We read each deal's exact wording, accept fair charges,
argue back live, and fix the next deal. [Board → Coach]

**2. What if the AI invents a clause?**
It can't use one: the quote must be found word for word and two different models must agree.
Disagreements go to a person. [Show a rejected term]

**3. Why not just a rules engine?**
The math *is* a rules engine with tests. The hard part is that every deal is worded differently and changes
arrive by email; reading that is the AI's job. [Evidence card: highlighted sentence]

**4. What stops it disputing everything?**
It accepted $2,730 here, including a charge that looked wrong until it found the broker's email.
The policy never lets it ask for more than the deal allows. [C3 card]

**5. Who can move money?**
No agent. Credit memos need the controller, and a refusal holds everything.
[Controller approval + audit log]

**6. What if a distributor emails new terms?**
Only approved senders or a document signed by both parties can change a deal; anything else is shown as a
claim. It's in our eval. [Northmart "$1.50" email shown as a claim]

**7. How accurate is it?**
30 of 30 on 30 planted charges, amounts to the cent, 6 asked, 0 wrong automatic actions, in both eval modes.
The answer key was written before the first run; we wrote the cases ourselves. [Results / scoreboard]

**8. How does this reach production?**
Real portals through browser automation (recovery services already do this), adapters for NetSuite or Xero
beside QuickBooks, and the same approval and audit model.

**9. Who is the customer?**
Founders and bookkeepers at small food and consumer brands that sell through big distributors.
[QUOTE]

**10. What if the AI misreads the deal and disputes a fair charge?**
Two models must agree, quotes are verified word for word, and low confidence goes to a person.
It concedes when shown a valid document. [Attach amendment → $1,000 conceded, $540 kept]

**11. Can an agent make up a dollar amount?**
No. All amounts come from tested code, and an outbound filter blocks any figure that isn't in a finding.
[Evidence card: math line]

**12. What about instructions hidden in documents ("ignore the deal")?**
Documents are data, never instructions; nothing in them can change an agent's tools or policy.
Only approved senders or signed documents change a deal, and we test it in the eval.

**13. Could it overreach: write things off or make promises?**
It cannot post to the books, and credit memos over $1,000 need the controller.
It never offers discounts or deadlines. [Portal reply]

**14. How do I know why money moved?**
Every decision cites a sentence, a data row, a rule or a person.
The audit log is hash-chained, so editing a past row breaks the check. [Audit → Verify chain]

**15. Is any real company data involved?**
No: Peak Bar Co. and Northmart are fictional, and we wrote the deal, emails and sales.
In production: least-privilege QuickBooks access, no training on customer data, per-brand isolation.
