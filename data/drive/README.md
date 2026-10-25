# Peak Bar Co.'s Google Drive folder

`Peak Bar Co/` is what we upload to Google Drive for the demo. It is the folder a supplier keeps for its distributors,
with one folder per distributor, each split the way finance teams file the paperwork:

| Folder | What's in it |
| --- | --- |
| `01 Contracts` | The signed agreement (the real SEC filing, word for word, where we have one), our signed setup or acceptance, the agreed price list |
| `02 Promotions` | Promotion submissions and deal sheets, the promotion plan, broker emails that extend a promotion, policy-change notices |
| `03 Remittances` | The remittance advice for the payment (text or PDF, the file Clawback's remittance reader takes), prior remittance lines, the remittance history |
| `04 Deductions & backup` | The distributor's deduction export, its backup and notices for each fee, the deduction history |
| `05 Correspondence` | Emails from the distributor's desk (claims, not deal changes) |
| `06 Sales data` | Weekly sales on promotion, as exported from the distributor's portal |
| `07 Orders & shipping` | Purchase orders, proof of delivery, delivery appointment logs, invoices |

`_Company/` holds the owner's policy (`config/policy.yaml`) and the people whose written approval can change a deal.

Distributors: Northmart, KeHE Distributors, UNFI, Sam's Club, Walmart and Five Below. Those are Peak Bar Co.'s accounts
in `data/accounts/` (`supplier: peak-bar`).

## Rules
- Every file is a copy of a file in `data/accounts/<id>/`, `data/contracts/` or `data/samples/`, renamed so a
  person can read it, dated first where it has a date. Nothing here is edited by hand.
- To rebuild after a data change, run `python scripts/build_drive.py`. It deletes `Peak Bar Co/` and copies
  everything again.
- The folder layout follows the research recommendation (01 Contracts to 07 Orders & shipping). The file names are
  our own convention; no source documents how real teams name their files.
