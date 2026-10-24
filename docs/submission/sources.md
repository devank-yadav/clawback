# Sources

Every real-world fact in the pitch, the judge Q&A and the Devpost text, with the source it comes from. Tell each one
the way its source tells it ("Omaha Industries sued UNFI, saying …"); never say a real company did something the
source doesn't say, and never say what Clawback would have won.

> The sources were opened by our researcher on Sat Oct 24. The session that wrote these docs couldn't reach them
> (its network blocks those sites). TODO (needs Devank): open each link once before submitting, and check the
> figures quoted next to it.

## Real cases

| # | What the source says | What Clawback would have checked and flagged | Source |
| --- | --- | --- | --- |
| 1 | Omaha Industries (Tender & True) sued UNFI in the U.S. District Court for Rhode Island (1:24-cv-00015), filed Jan 9, 2024. It says UNFI charged back $268,816.94 against about $326,780 of product sold to Giant Food (about 82%), as product the contract lets UNFI charge back as "unacceptable"; that UNFI never returned or disposed of the product or accounted for it; and that a Giant category manager knew of no quality problems | A chargeback with no proof of the product's condition or what happened to it; chargebacks that take most of what was invoiced | [Supply Chain Dive](https://www.supplychaindive.com/news/omaha-sues-grocery-distributor-unfi-chargebacks-giant-food/704810/) · [Grocery Dive](https://www.grocerydive.com/news/omaha-sues-grocery-distributor-unfi-chargebacks-giant-food/705044/) |
| 2 | Saks's own SEC filings (8-K, June 2005; 10-K, Sept 2005) say its merchants collected about $34 million of markdown allowances vendors didn't owe, in fiscal 1996–2003, using wrong sales figures, and that Saks repaid about $48 million with interest. SEC Litigation Release 20266 (2007) | Each allowance recomputed from the vendor's own sell-through, not the retailer's figure | [SEC Litigation Release 20266](https://www.sec.gov/litigation/litreleases/lr-20266) |
| 3 | Walmart's on-time-in-full (OTIF) program charges 3% of the cost of goods on cases that arrive late or short; the target rose to 98% from Sept 15, 2020. Talk Business & Politics reports Walmart's own food and consumables OTIF was 40% in March 2019 | A miss that the delivery appointment log puts on the carrier or on Walmart, disputed with that log | [Talk Business & Politics](https://talkbusiness.net/2020/09/walmart-demands-all-suppliers-comply-with-98-on-time-in-full-shipment-rule/) |
| 4 | In Australia (2014), the Federal Court ordered a $10 million penalty against Coles for unconscionable conduct toward suppliers (payments outside its trading terms); an arbiter ordered more than $12 million refunded | A deduction with no clause in the trading terms behind it | [Food & Drink Business](https://www.foodanddrinkbusiness.com.au/news/court-backs-coles-10m-supplier-conduct-penalty) |
| 5 | NYSM Organics sued UNFI (filed Nov 3, 2024, Rhode Island Superior Court) over payment discounts taken after the payment window and constant deductions | A discount taken outside the deal's payment window | [Grocery Dive](https://www.grocerydive.com/news/unfi-class-action-lawsuit-payment-discounts-grocery-natural-foods/732132/) |
| 6 | TeaSquares' founder said the company invoiced KeHE $32,000 in 2019 and was paid $21,000 | Every line of the short pay, against the distributor's own written policy | Foodbevy podcast, episode #98. TODO (needs Devank): the episode link |

## Survey

- UK Groceries Code Adjudicator, 2026 survey of more than 2,600 suppliers: 20% said retailers were slow to resolve
  invoice discrepancies, the most common issue reported.
  [gov.uk](https://www.gov.uk/government/news/high-code-compliance-maintained-as-some-supplier-issues-increase)

## Real contracts the agents read

Unedited text from public SEC filings, listed with links in [data/contracts/README.md](../../data/contracts/README.md):
KeHE Distributors Vendor Policies & Procedures (2015), the Wal-Mart Supplier Agreement (2003 and 2013), and the Five
Below Vendor Agreement (2023 and 2025). These companies are not our customers and didn't take part. The brands
selling to them in our accounts, and every charge and number in those accounts, are ours.

## Our own measurements

| Fact | Source |
| --- | --- |
| 5 live Peak Bar runs: identical decisions, $4,120 disputed, 1 question, 65–73 s, 13–14 Claude calls, about $0.38 of Claude per run | `DECISIONS.md`, Sat Oct 24 10:45, and the run's trace summary (`GET /runs/{id}/trace/summary`) |
| One live run per new account matched its expected decisions (Birchbank 4/4, Fernwell 5/5, Ridgefire 4/4) | `DECISIONS.md`, Sat Oct 24 11:50 |
| Eval: 30 of 30, 0 wrong automatic actions; the recorded agent run used Claude for both readers | `eval/published/agent.json`, `eval/published/engine.json` |
| Gemini and Claude disagreeing on "its core bars" | [docs/proof/gemini-vs-claude.md](../proof/gemini-vs-claude.md) |
