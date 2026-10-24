# Judge flashcards

20 likely questions with two-line answers, matching [docs/submission/judge-qa.md](submission/judge-qa.md) (the
longer versions and caveats live there). Point at the screen in brackets. All four accounts are invented; the app
doesn't say so, so we do. `TBD (measured)` means we haven't measured it: say so, never guess. Fill [QUOTE] before
judging or skip the line.

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
Live: `TBD (measured)` seconds and `TBD (measured)` in AI calls, all listed in the trace. Replayed offline,
the board was decided in 5.9 seconds. [How Clawback decided]

**6. Recovery services and deduction software already exist.**
Yes, and brands pay for them, which shows the need. Ours traces each decision to the brand's own deal, accepts
fair charges, rehearses the comeback, and fixes next month's deal. [C3 card → `/coach`]

**7. Path to production without portal logins?**
It starts from what a brand already has: the payment slip, the deal and its emails, and QuickBooks's API. In
production, disputes go out by email or get pasted into a portal; automating portals comes later. [Upload · D-0417]

**8. Who can move money?**
No agent. Only the controller's sign-in approves the memo, never the owner's or an agent; a no posts nothing.
[Sam's phone, signed in as controller · audit log]

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

**13. Are these real companies?**
No: all four accounts are invented, styled like real businesses; none is a customer. The AI, the math, the
phones and the QuickBooks sandbox books are real.

**14. What do the other accounts show?**
A drinks brand (shortage disproved by delivery records, a charge over $5,000 waiting on the owner), a tough
distributor (emailed rate claim, repeat charge), and a clean month where everything is accepted. [Account switcher]

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
approving money still needs the controller's sign-in.

**19. How do I know why money moved?**
Every decision cites a sentence, a row, a rule or a person, and every AI call is in the trace. The audit log is
hash-chained, so editing a past row breaks the check. [`/audit` → Verify chain]

**20. Who is the customer?**
Founders and bookkeepers at small food and drink brands that sell through big distributors.
[QUOTE]
