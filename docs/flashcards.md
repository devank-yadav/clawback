# Judge flashcards

21 likely questions with two-line answers, matching [docs/submission/judge-qa.md](submission/judge-qa.md) (the
longer versions and caveats live there). Point at the screen in brackets. Real facts are told the way their source
tells them ([sources.md](submission/sources.md)); never say what Clawback would have won for a real company.
`TBD (measured)` means we haven't measured it: say so, never guess. Fill [QUOTE] before judging or skip the line.

---

**0. Is this real data?**
Real contracts (KeHE, Walmart, Five Below, unedited from SEC filings) and real cases (Omaha v. UNFI, Saks, Walmart's
on-time fines, Coles). Our brands, their charges and every number are ours. [`data/contracts/README.md`]

---

**1. You graded your own homework.**
Fair: we wrote the 30 cases (the answer key came first). So grade it yourself: type a clause and a charge,
and both models read it live. [`/scenario`]

**2. Real remittances aren't CSVs.**
Agreed. Drop the payment slip as a PDF: Claude reads it into charges, and code checks every line and the
totals. [Upload screen]

**3. Two models? The eval shows Claude twice.**
True for the score: it was recorded before Gemini answered on our key, so Reader B was a second Claude call.
Gemini reads live now, and on a vague clause it disagreed, so Clawback asked. [How Clawback decided: Gemini row]

**4. What does Moss add?**
Memory by meaning: a reworded display-fee clause still finds Rule #1, with the score on the card. Limit: it
can't yet tell similar fees apart, so type and distributor must match too. [April card: similarity 1.00]

**5. What does a run cost, and how long?**
Measured on 5 live Peak Bar runs: 65–73 seconds, 13–14 Claude calls, about $0.38 of Claude, same decisions
every time. [Trace summary]

**6. Recovery services and deduction software already exist.**
Yes, and brands pay for them, which shows the need. Ours traces each decision to the brand's own deal, accepts
fair charges, rehearses the comeback, and fixes next month's deal. [C3 card → `/coach`]

**7. Path to production without portal logins?**
It starts from what a brand already has: the payment slip, the deal and its emails, and QuickBooks's API. In
production, disputes go out by email or get pasted into a portal; automating portals comes later. [Upload · D-0417]

**8. Who can move money?**
No agent. Only the owner's sign-in (the admin) approves the memo; a no posts nothing.
[Dana's phone, signed in as the admin · audit log]

**9. What if the AI is wrong?**
The worst case is a question, not a payment: two models must agree, quotes are checked word for word, code does
the math. Shown a valid document, it backs down. [Tablet: Attach signed amendment → $1,000 conceded, $540 kept]

**10. What if the distributor sends instructions in an email?**
Emails are data, never instructions. Only the owner, the approved broker or a document both sides signed can
change a deal; Northmart's "$1.50" email is shown as a claim. [C1 card: the Mar 30 email]

**11. Why not just a rules engine?**
The money part *is* a rules engine with tests and a fixed nine-row gate. The AI reads what rules can't: deals
worded differently and changes by email. [How Clawback decided: AI rows vs code]

**12. Is the code open?**
Yes: github.com/devank-yadav/clawback; `make eval` reruns the score. (Until it's public: "It goes public this
morning, right after our secrets scan.")

**13. Are the brands real?**
No: Peak Bar, Fernwell, Ridgefire, Birchbank and their distributors are ours. KeHE, Walmart and Five Below's
contracts are real text, but those companies didn't take part and the charges are ours.

**14. What do the other accounts show?**
Fernwell (shortage disproved by the proof of delivery, a $5,487.50 excess waiting on the owner), Ridgefire (an
emailed rate, a repeat charge), Birchbank (all fair, $2,881.52 accepted). [Account switcher]

**15. What stops it disputing everything?**
It accepted $2,730 for Peak Bar, including a charge that looked wrong until it found the email, and a whole
clean month. It never asks for more than the deal allows. [Clean month]

**16. Why ask about C6?**
§5.4 says "at its discretion": a judgment call, so the owner decides, once. The answer becomes Rule #1, and
April's fees are decided with zero questions. [`/april`]

**17. How accurate is it?**
30 of 30 on planted charges, amounts to the cent, 6 asked, 0 wrong automatic actions, in both eval modes. We
wrote the cases, and they cover promos and fees only. [`/results`]

**18. Can I try it on my phone?**
Yes: clawback.biz. Each visitor gets 3 live runs per 10 minutes so a public link can't drain our credits;
approving money still needs the admin's sign-in.

**19. How do I know why money moved?**
Every decision cites a sentence, a row, a rule or a person, and every AI call is in the trace. The audit log is
hash-chained, so editing a past row breaks the check. [`/audit` → Verify chain]

**20. Who is the customer?**
Founders and bookkeepers at small food and drink brands that sell through big distributors. Omaha Industries
sued UNFI in 2024, saying UNFI charged back $268,816.94 on about $326,780 of product. [QUOTE]
