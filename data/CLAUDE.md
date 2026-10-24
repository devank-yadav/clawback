# data/ (owner: Manasv, files written by AI, checked by scripts/check_data.py)

Peak Bar's files below live in data/accounts/peak-bar/ (account.yaml holds the invoice, people and senders; charges
are charges/march.csv and charges/april.csv); other accounts sit next to it (api/accounts.py has the layout).
Every number here must match this file to the cent. Never edit numbers by hand; change the prompt, regenerate,
rerun `python scripts/check_data.py`. All names are fictional; label them fictional in any output.

## Cast (fictional)
- Brand: Peak Bar Co. Owner Dana Okafor (dana@peakbar.example). Controller Sam Reyes (sam@peakbar.example).
- Broker: Jordan Lee (jordan@peakbar-broker.example), an APPROVED amendment sender.
- Distributor: Northmart (deductions desk: deductions@northmart.example), NOT an approved amendment sender.

## Invoice and payment
- Invoice INV-3102 to Northmart for March 2026: $48,200.00
- Remittance received: $41,350.00. Taken: $6,850.00 across 6 charges (C1 to C6).

## deals/spring-promo.md (copy these clauses word for word; add realistic surrounding contract text)
- §3.1 "Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and Peak Bar Chocolate sold between March 1 and March 31, 2026."
- §3.2 "The promotional allowance applies to a maximum of 5,000 units in total."
- §5.4 "Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice to Supplier."

## deals/amendment-1.md
Signed by Dana Okafor (Peak Bar Co.) and a Northmart category manager: raises the §3.2 cap to 6,000 units.
Used ONLY when the judge "attaches" it in the portal. Effect: 1,000 of week 4's 1,540 units become covered,
so C4 becomes $540 disputed + $1,000 accepted.

## deals/summer-draft.md
Next month's draft deal. Must contain the same three weak clauses as spring (discretion fee with no notice
period, cap with no mention of extensions, products named in prose not by item number) so Deal Coach can redline them.

## emails/
- broker-2026-03-28.eml, from jordan@peakbar-broker.example, Mar 28 2026:
  "Northmart asked to extend Spring Promo through April 7, same terms, up to 500 additional units. Approved."
- northmart-2026-03-30.eml, from deductions@northmart.example, Mar 30 2026:
  "Per our call, the Spring Promo rate is $1.50 per unit." (a CLAIM from a non-approved sender; must never be applied)

## notices/display-fee-2026-03-11.md
Northmart notice dated Mar 11 2026 of a $1,200 display fee for the month ending Mar 31 (20 days' notice).

## sales/store-sales.csv (columns: week_start, week_end, product, promo_units, total_units)
Promoted units (split across Original and Chocolate as you like, but each week's sum must match):
- Week 1, Mar 1 to Mar 7: 1,200
- Week 2, Mar 8 to Mar 14: 980
- Week 3, Mar 15 to Mar 21: 2,820  (running total 5,000: cap reached)
- Week 4, Mar 22 to Mar 31: 1,540
- Apr 1 to Apr 7: 330
- Mint (not in the deal), March total: 1,000 (any weekly split)
total_units = promo_units plus any non-promo sales you choose.

## payments/prior.csv (columns: ref, paid_on, promo_id, product, period_start, period_end, units, amount)
- NM-2178, paid 2026-03-14, SPRING-26, Original+Chocolate, Mar 8 to Mar 14, 980 units, $980.00  (week 2)
- NM-2201, paid 2026-03-28, SPRING-26, Original+Chocolate, Mar 15 to Mar 21, 2,820 units, $2,820.00  (week 3)

## charges/northmart-march.csv (columns: charge_id, ref, code, description, product, units, rate, amount, period_start, period_end)
| charge | ref | code | description | units | rate | amount | period |
| C1 | NM-2229 | PA | Spring promo week 1 | 1,200 | 1.50 | 1,800.00 | Mar 1 to Mar 7 |
| C2 | NM-2231 | PA | Spring promo week 2 | 980 | 1.00 | 980.00 | Mar 8 to Mar 14 |
| C3 | NM-2240 | PA | Spring promo Apr 1 to 7 | 330 | 1.00 | 330.00 | Apr 1 to Apr 7 |
| C4 | NM-2236 | PA | Spring promo week 4 | 1,540 | 1.00 | 1,540.00 | Mar 22 to Mar 31 |
| C5 | NM-2237 | PA | Spring promo Mint | 1,000 | 1.00 | 1,000.00 | Mar 1 to Mar 31 |
| C6 | NM-2238 | DF | Display fee (notice Mar 11) | 1 | 1,200.00 | 1,200.00 | Mar 1 to Mar 31 |
Sum = 6,850.00. Product for C1 to C4 = Original+Chocolate; C5 = Mint; C6 = none.

Expected decisions (for check_data.py and Devank's tests):
C1 split: dispute 600, accept 1,200 · C2 dispute 980 · C3 accept 330 (broker email) · C4 dispute 1,540 (cap)
· C5 dispute 1,000 (Mint not covered) · C6 ask → owner rule → accept 1,200.
Disputed total 4,120.00 · accepted total 2,730.00 · 4,120 + 2,730 = 6,850.

## charges/northmart-april.csv
- A1 NM-2301, DF, display fee with 18 days' notice, 1,200.00 → Rule #1 accepts
- A2 NM-2302, DF, display fee with 5 days' notice, 800.00 → Rule #1 disputes
(also add notices for both with the right dates)

## plan/promo-plan.csv (columns: promo_id, product, rate, starts, ends, cap)
SPRING-26, Peak Bar Original; Peak Bar Chocolate, 1.00, 2026-03-01, 2026-03-31, 5000

## eval/ (test set, see docs/design.md "Proof, tests and responsible design")
charges-30.csv + answer-key.csv: 12 dispute (rate over split 3, duplicate 3, over cap 2, product not covered 2,
outside dates no amendment 1, distributor-claimed change not signed 1), 12 accept (exact match 5, approved broker
extension 3, charged less than allowed 1, discretion fee covered by a saved rule 2, within $1 1), 6 ask
(discretion fee no rule 3, readers disagree on vague wording 2, overcharge above $5,000 1).
Answer key columns: case_id, expected_decision, expected_disputed, expected_accepted, reason.
outside-deal.md is written by someone NOT on the team (leave a placeholder).

## fixtures/
Saved AI and QuickBooks responses for DEMO_MODE. Written by the app's record mode, not by hand.
