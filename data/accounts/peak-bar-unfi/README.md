# Peak Bar Co. <- UNFI

## Where each file comes from

| File | What it is | Source |
| --- | --- | --- |
| `data/contracts/unfi-clearvue-supplier-agreement-2010-peak-bar.txt` | UNFI's ClearVue Supplier Agreement, word for word, with its `[***]` redactions | SEC filing (see `data/contracts/README.md`); in `contracts`, so it's in the contract library |
| `deals/peak-bar-unfi-mcb-promotion-2026-03.md` | Our MCB deal sheet under §2.A of the agreement, signed by UNFI | Our side |
| `emails/peak-bar-unfi-deductions-2026-03-24.eml` | UNFI's deductions desk claiming a $1.50 rate | UNFI. It's a claim from a sender who can't change the deal, so it's shown and never applied |
| `notices/peak-bar-unfi-clearvue-fee-2026-q1.md` | UNFI's ClearVue program invoice, under Exhibit B | UNFI |
| `notices/peak-bar-unfi-mcb-backup-2026-03.md` | UNFI's weekly MCB backup | UNFI |
| `remittances/peak-bar-unfi-remittance-7781234-2026-04-20.txt` | The remittance advice | UNFI. It passes `api/remittance.check()` and reads into exactly `charges/march.csv` |
| `charges/march.csv` | The remittance's deduction lines, in the engine's columns | The remittance advice |
| `sales/store-sales.csv` | Weekly cases sold to retailers on the deal | Distributor portal export (UNFI's MCB backup and velocity report) |
| `payments/prior.csv` | Week 2, already billed on the Mar 20 remittance | Distributor portal export (the prior remittance) |
| `plan/`, `terms/ops-terms.csv`, `pricing/` | The promo, its clauses and the case costs, each quoted from the deal sheet | Our side; `scripts/check_accounts.py` checks each quote |
| `deliveries/pod.csv` | The March receipts | Our side (signed receiving records) |
| `history/` | Six months of invoices, remittances and deductions | Our books |
| `expected.csv` | The answer key | Worked out by hand; `scripts/check_accounts.py` recomputes it |

## The charges

- U1 split: a rate over the deal, billed on UNFI's own email claim.
- U2 dispute: a duplicate of a week already billed.
- U3 accept: matches the deal.
- U4 split: over the 4,000-unit cap.
- U5 dispute: a product the deal doesn't cover.
- U6 ask: the ClearVue program fee rests on Exhibit B, whose amount is blacked out (`[***]`). Nothing states the
  amount, so Clawback can't verify the deal and asks the owner. It never guesses the redacted number.

Disputed $2,320.00, accepted $2,950.00, asked $1,250.00. Total $6,520.00 = $124,800.00 − $118,280.00.
