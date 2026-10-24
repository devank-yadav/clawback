# Clawback Assistant

Chat with Clawback, the finance agent that checks what a distributor takes out of a small brand's payment.
Built for Cal Hacks 13.0. Every company and person here is fictional: Peak Bar Co. (a snack brand), Northmart
(its distributor), Dana (the owner) and Sam (the bookkeeper).

## What it does

- **Tells you what the distributor took.** "What did Northmart take this month?" gets the amount Northmart
  kept from Peak Bar Co.'s latest payment, how much Clawback is disputing because Northmart took too much,
  how much it accepted as fair under the signed promo deal, and what is still waiting on a person.
- **Shows open disputes.** Each one with its charges, amounts and the plain reason (wrong rate, already paid,
  over the deal's limit, product not in the deal).
- **Passes on Clawback's one question.** When the deal leaves a charge to judgment, Clawback asks the owner
  once. Answer here: a rule like "accept if notice is at least 14 days", ACCEPT or DISPUTE for that charge
  only, or UNDO to cancel the rule. Clawback remembers the rule and never asks twice.
- **Shows what waits on the bookkeeper.** Money only moves when Sam says yes.

## What it won't do

It never approves or moves money, never changes the books and never works out amounts itself: every number
comes straight from Clawback.

## Try

- What did Northmart take this month?
- Which charges are you disputing?
- Is anything waiting on me?
- accept if notice is at least 14 days
- UNDO

Keywords: distributor deductions, promo deal, short payment, dispute charges, small brand finance, bookkeeping,
QuickBooks, snack brand, Cal Hacks.
