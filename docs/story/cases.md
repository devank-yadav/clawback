# Real cases behind Clawback

Material for the landing page and Devpost. Every case below is real and sourced. Each quote is under 15 words and
attributed. Labels: **[verified]** means read on the court, regulator or SEC page, or in the original article;
**[reported]** means trade press, a podcast or a vendor guide; **[unverified]** means sources conflict or we could not
confirm it. Figures are as the source states them.

Industry-wide numbers conflict (vendor figures range from 2% to 20% of revenue lost to deductions), so the copy says
"industry sources report" and never quotes one figure as fact.

## NYSM Organics v. United Natural Foods (UNFI), Rhode Island, 2024 [verified]

**What happened.**
- A small natural-foods supplier from Martha's Vineyard filed a putative class action on Nov 3, 2024.
- It alleges that UNFI takes prompt-pay discounts on invoices it pays after the discount window has closed, and holds
  back payment while a supplier's balance is negative.
- The complaint calls them "opaque and constant deductions" (NYSM's complaint, via Grocery Dive).
- The court dismissed the consumer-protection claim on June 5, 2025. The contract claims remain pending, per UNFI's
  10-Q for the quarter ended Nov 1, 2025. Any later status is **[unverified]**.

**Sources:**
- [Grocery Dive](https://www.grocerydive.com/news/unfi-class-action-lawsuit-payment-discounts-grocery-natural-foods/732132/)
- [New Hope](https://www.newhope.com/industry-news/massachusetts-organic-food-supplier-accuses-unfi-deceptive-practices-breach-of-contract)
- [UNFI 10-Q](https://www.sec.gov/Archives/edgar/data/1020859/000102085925000065/unfi-20251101.htm)

**How Clawback catches it.**
- Clawback reads the discount terms from the signed agreement, then checks the payment date against the invoice date.
- A discount taken after the window is disputed for its exact amount, citing the clause, the invoice date and the
  payment date.
- Where the agreement's number is blacked out, as in UNFI's filed supplier agreement, Clawback says it can't verify
  the deal and asks. It never guesses the rate. In the demo, that's Peak Bar's UNFI account, charge U6, the ClearVue
  fee whose amount the filing redacts.
- Not in the demo yet: Clawback's math engine doesn't date a discount by the invoice and payment dates today.

## Omaha Industries v. UNFI, 2024 [verified via trade press; complaint not read]

**What happened.**
- Omaha alleges that UNFI charged back $268,816.94 on more than $326,780 of pet food sold to Giant Food, calling the
  product unacceptable.
- Giant's category manager reportedly knew of no quality problem.
- Omaha says UNFI "has refused to provide a full accounting" (Omaha's complaint, via Grocery Dive).
- The court and docket number are **[unverified]**.

**Sources:**
- [Grocery Dive](https://www.grocerydive.com/news/omaha-sues-grocery-distributor-unfi-chargebacks-giant-food/705044/)
- [Supply Chain Dive](https://www.supplychaindive.com/news/omaha-sues-grocery-distributor-unfi-chargebacks-giant-food/704810)

**How Clawback catches it.**
- A chargeback that rests on a fact, such as "unacceptable product", needs backup.
- With no quality report or retailer claim on file, Clawback asks for the backup instead of accepting the charge.
- Every charge is tied to a sentence in the agreement and a row of evidence, or it goes to a person.

## Founders' KeHE accounts [reported]

**What happened.**
- TeaSquares' founder describes invoicing KeHE about $32,000 and receiving about $21,000. The gap was chargebacks,
  fees and retailer returns (Foodbevy guide and podcast #98).
- A separate case study describes a brand that invoiced $68,267 to KeHE and received $13,345 (The Good Food CFO,
  May 2025). It doesn't itemize the deductions.

**Sources:**
- [Foodbevy guide](https://guide.foodbevy.com/?p=1150)
- [Foodbevy podcast #98](https://podcast.foodbevy.com/1832151/episodes/12408975-98-breaking-down-distributor-deductions-and-chargebacks)
- [The Good Food CFO](https://thegoodfoodcfo.substack.com/p/kehe-uncovered-real-case-study-of-3a6)

**How Clawback catches it.**
- Each line is checked against KeHE's own Vendor Policies, the real 2015 filing: the MCB fee rate and its minimum, the
  spoils terms, and the 180-day dispute window.
- Clawback disputes only what goes over the policy, and accepts the rest.
- In the demo: Peak Bar's KeHE account, charges K1 to K10.

## Tesco and the UK Groceries Code Adjudicator, 2016 [verified via trade press; the report PDF didn't render]

**What happened.**
- The Adjudicator investigated Tesco's conduct from June 2013 to February 2015.
- It found unilateral deductions for short deliveries and service charges, duplicate invoicing, and payments delayed
  on purpose.
- Tesco "seriously breached" the Code (Christine Tacon, Groceries Code Adjudicator).
- Tesco was told to stop unilateral deductions, explain each one, and give suppliers at least 30 days to challenge it.

**Sources:**
- [Bakery and Snacks](https://www.bakeryandsnacks.com/Article/2016/01/26/Tesco-seriously-breached-Groceries-Supply-Code-of-Practice)
- [GCA final report (PDF)](https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/494840/GCA_Tesco_plc_final_report_26012016_-_version_for_download.pdf)

**How Clawback catches it.**
- The duplicate check finds a charge already paid on an earlier remittance.
- A shortage is checked against the signed proof of delivery.
- A deduction with no explanation goes to a backup request, not an accept.
- In the demo: Northmart's C2 and UNFI's U2, each a promo week billed a second time.

## ACCC v Coles, Federal Court of Australia, 2014 [verified via trade press]

**What happened.**
- Coles paid A$10 million in penalties for unconscionable conduct toward suppliers in 2010 and 2011.
- The conduct included rebates for its "Active Retail Collaboration" program, and claims for "profit gap", waste and
  markdowns.
- "Coles withheld money from suppliers it had no right to withhold" (Justice Gordon).

**Source:** [Food & Drink Business](https://www.foodanddrinkbusiness.com.au/news/court-backs-coles-10m-supplier-conduct-penalty)

**How Clawback catches it.**
- A charge that no clause in the deal supports is disputed as "not in the deal".
- Clawback never accepts a charge it can't tie to a verified term.

## Walmart's On-Time In-Full fines (a policy, not a dispute case) [verified]

**What happened.**
- From 2019, Walmart required full-truckload suppliers to arrive on time and in full 87% of the time, up from 85%.
- Misses are fined 3% of the cost of goods (Supply Chain Dive, Mar 8, 2019).

**Source:** [Supply Chain Dive](https://www.supplychaindive.com/news/walmart-on-time-in-full-87-suppliers/550083/)

**How Clawback catches it.**
- A late-delivery fine is checked against the appointment log.
- When Walmart routed the freight and its carrier picked up late, the miss isn't the supplier's, so the fine is
  disputed.
- In the demo: Peak Bar's Walmart account, charge W6.

## Where the demo's contracts come from

- **UNFI:** the ClearVue Supplier Agreement between UNFI and Annie's, with its numbers blacked out as filed. Exhibit
  10.21 to Annie's S-1, 2012:
  https://www.sec.gov/Archives/edgar/data/1431897/000119312512104829/d261388dex1021.htm
- **Sam's Club:** the Grocery Merchandise Agreement with Ittella/Stonegate Foods, effective Feb 3, 2020: a 1% swell
  allowance off each invoice, and payment terms of 2% 30, net 45. Sam's Club charge S5 takes swell at 1.5%, and is
  checked against the 1%. Part of Exhibit 10.14 to Tattooed Chef's 8-K, 2020:
  https://www.sec.gov/Archives/edgar/data/1741231/000121390020032445/ea127797ex10-14_tattooed.htm
- **KeHE, Walmart and Five Below:** the filings listed in `data/contracts/README.md`.
- Peak Bar Co. and its documents (deal sheets, remittances, notices, sales reports) are written by our side, in the
  formats real suppliers receive. The contracts' own words are never edited.
