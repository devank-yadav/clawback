# Peak Bar Co. <- Sam's Club

## Where each file comes from

| File | What it is | Source |
| --- | --- | --- |
| `data/contracts/sams-club-grocery-merchandise-agreement-2020-excerpt-peak-bar.txt` | The Sam's Club Grocery Merchandise Agreement 607499-64-2 (effective 02/03/2020), word for word: its own lines cut from the filed exhibit | SEC filing (see `data/contracts/README.md`); in `contracts`, so it's in the contract library |
| `deals/peak-bar-sams-instant-savings-2026-03.md` | Our Instant Savings event, accepted by Sam's Club | Our side |
| `deals/peak-bar-sams-sampling-program-2026.md` | Our in-club sampling program, accepted by Sam's Club: a fee at Sam's discretion, up to $1,500 a month | Our side |
| `emails/peak-bar-sams-ap-2026-03-20.eml` | Sam's accounts payable claiming $2.50 a unit | Sam's Club. It's a claim from a sender who can't change the deal, so it's shown and never applied |
| `notices/peak-bar-sams-sampling-fee-2026-03-10.md` | Sam's notice of the March sampling fee | Sam's Club |
| `remittances/peak-bar-sams-retail-link-40018266-2026-04-16.txt` | The remittance detail | Sam's Club (Retail Link). It passes `api/remittance.check()` and reads into exactly `charges/march.csv` |
| `charges/march.csv` | The remittance's deduction lines, in the engine's columns | The remittance |
| `sales/store-sales.csv` | Weekly club packs sold to members | Distributor portal export (Retail Link point of sale) |
| `payments/prior.csv` | The week of Mar 16, deducted on the Mar 27 payment | Distributor portal export (the prior remittance) |
| `terms/ops-terms.csv` | The promo clauses, plus the agreement's Swell Allowance (1.0%, off each invoice) for the unsaleables charge | Quoted from the documents; `scripts/check_accounts.py` checks each quote |
| `plan/`, `pricing/` | The event and the item costs | Our side |
| `deliveries/pod.csv` | The March receipts at the distribution center | Our side |
| `history/` | Six months of invoices, payments and deductions | Our books |
| `expected.csv` | The answer key | Worked out by hand; `scripts/check_accounts.py` recomputes it |

## The charges

- S1 accept: matches the event.
- S2 split: a rate over the deal, deducted on Sam's own email claim.
- S3 split: over the 6,000-unit cap.
- S4 dispute: a product the event doesn't cover.
- S5 split: swell taken at 1.5%. The agreement's Swell Allowance is 1.0% of each invoice.
- S6 ask: a sampling fee at Sam's discretion. Clawback asks once, and the answer becomes a rule.

The sampling fee is set in our own program agreement, not in the filed agreement, which has no such clause.

Disputed $2,283.20, accepted $9,966.40, asked $1,200.00. Total $13,449.60 = $116,640.00 − $103,190.40.

The remittance codes are the engine's own (PA, SP, DF), with Sam's wording (code 51, SW) in the description.
