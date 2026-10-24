# Real contracts

Text copied from public SEC filings, unedited (OCR typos included), so the readers face real legal wording. The
`.txt` filings are byte for byte as served; the HTML ones are converted to text (tags dropped, table cells joined by
" | "), words untouched.
Anything we add for a demo lives in its own document written by our side (a brand's promotion submission, a
broker email, a notice), never inside these files.

| File | Source | Checked |
| --- | --- | --- |
| `kehe-vendor-policies-2015.txt` | KeHE Distributors Vendor Policies & Procedures, effective May 31, 2015. Exhibit 10.31 to Rocky Mountain High Brands' S-1, filed 2018-07-06: https://www.sec.gov/Archives/edgar/data/1670869/000166357718000305/ex10_31.htm | 2026-10-24: 5,775 words, identical word for word to the page text on sec.gov (whitespace aside) |
| `walmart-supplier-agreement-2003.txt` | Wal-Mart Supplier Agreement, effective 01/23/2003. EX-10.57 to Rockford Corp's 10-K, filed 2004-03-30: https://www.sec.gov/Archives/edgar/data/828064/000095015304000722/p68961exv10w57.txt | 2026-10-24: fetched as served |
| `walmart-supplier-agreement-2013.txt` | Wal-Mart Supplier Agreement, effective 04/18/2013. EX-10.32, EveryWare Global, filed 2013-05-28: https://www.sec.gov/Archives/edgar/data/1532543/000119312513236424/d516622dex1032.htm | 2026-10-24: HTML converted to text |
| `five-below-vendor-agreement-2023.txt` | Five Below Vendor Agreement (Legal Aug 2023, Compliance June 2023, Supply Chain Aug 2023). EX-10.5 to JM Group's F-1/A, filed 2025-09-12: https://www.sec.gov/Archives/edgar/data/2049717/000121390025087032/ea022619509ex10-5_jmgroup.htm | 2026-10-24: HTML converted to text |
| `five-below-vendor-agreement-2025.txt` | Five Below Vendor Agreement, 2025 version. EX-4.4 to JM Group's 20-F, filed 2026-02-10: https://www.sec.gov/Archives/edgar/data/2049717/000121390026014380/ea027551401ex4-4_jmgroup.htm | 2026-10-24: HTML converted to text |
| `five-below-vendor-agreement-2023-excerpt.txt` | Excerpt of `five-below-vendor-agreement-2023.txt`, lines 1-13 (title), 584-591 (§11 Cancellation by Vendor: the ±5% variance), 4926-5142 (E. Violation Summary: the fee table, the $100 admin fee, the 90-day dispute window) and 5734-5794 (Document Instructions and their chargebacks). Read by the Fizzwick Toys account (named in `data/accounts/fizzwick/account.yaml` `contracts`; the ranges are in its `fees/fees.yaml` `excerpts`) | 2026-10-24: the source's lines joined by a `[...]` line, nothing reworded; `scripts/check_accounts.py` rebuilds it from the ranges |
| `five-below-vendor-agreement-2025-excerpt.txt` | Excerpt of `five-below-vendor-agreement-2025.txt`, lines 1-4 (title), 653-664 (§11), 5367-5626 (Violation Summary) and 6190-6246 (Document Instructions) | 2026-10-24: as above |

Accounts on these filings: `data/accounts/copperline/` (Copperline Home Co. <- Walmart, on the full 2013 agreement) and
`data/accounts/fizzwick/` (Fizzwick Toys Co. <- Five Below, on both excerpts: which version governs a purchase order is
set by the date it was issued, in our signed acceptance). The 2003 Walmart agreement is saved but not used by an account.
