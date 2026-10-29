# Live showcase: 3 minutes on clawback.biz

The story: a small chocolate maker, **Cocoa Ridge Chocolate Co.**, invoiced its grocery distributor **Brightway Grocers**
$20,000. Brightway paid $17,300 and kept $2,700 in four deductions. Clawback checks each one against the signed deal
and its amendment, disputes the wrong ones with proof, accepts the fair ones, asks the owner only when the deal leaves
it to judgment, and books the result. Everything below is live: real AI reads, real math, the real distributor portal.

## The numbers (check them in your head)

The deal (one page): **$1.00 a bar** on Dark and Milk bars, March 1-28; **up to 1,000 bars**; a display fee **up to $500**
"at Brightway's discretion". The amendment (the "new contract", Mar 20): **up to 1,500 bars**.

| Deduction | Brightway took | Deal allows | Clawback |
| --- | --- | --- | --- |
| BW-101 promo Mar 1-14, 600 bars × $2.00 | $1,200 | 600 × $1.00 = $600 | **Split: $600 back** (wrong rate) |
| BW-102 promo Mar 15-28, 800 bars × $1.00 | $800 | $800 (1,400 bars ≤ 1,500) | **Fair**, only because of the amendment (the old cap allowed $400) |
| BW-103 Mint Bar, 300 × $1.00 | $300 | $0 | **Dispute**: Mint isn't in the deal |
| BW-104 display fee | $400 | up to $500, at their discretion | **One question** to Ava (21 days' notice) |

Result: **$900 disputed, $1,400 fair, $400 to decide** (→ fair after "accept when notice is at least 14 days").

## Before the judges arrive (5 minutes)

1. One browser, two tabs, signed in as **Cocoa Ridge** (ID `cocoaridge`, password in
   `~/.config/clawback/live-signin.txt`):
   - **Tab A, the brand:** `https://clawback.biz/app`
   - **Tab B, the distributor:** `https://clawback.biz/portal?account=cocoaridge` (Brightway's portal)
2. Company menu (bottom left) → **Presenter mode…** → paste the admin token from the same file. This tab skips the
   visitor rate limits and shows the presenter menu.
3. Company menu → **Reset the demo**. It says when every distributor is ready, then reloads.
4. Settings: both "without asking" limits unticked (so the approval and "Review and send" moments show).

## The 3 minutes

1. **Home (15 s).** "This is Cocoa Ridge's owner, Ava. One chocolate maker, one distributor."
2. **Contracts (20 s).** Open the one-page deal and the amendment: "$1 a bar, up to 1,000 bars; the amendment raises it
   to 1,500."
3. **Tab B, Brightway pays (20 s).** "Now I'm Brightway." The invoice: $20,000, four deductions, $17,300 paid. Optionally
   change a number live (the total updates as you type). **Send payment.**
4. **Tab A (10 s).** Stay on Home; a note pops up when the check is done. **See it.**
5. **The payment (60 s).** Walk the table above: the $2.00 rate (quote highlighted), the amendment that makes BW-102 fair,
   Mint not in the deal, and the one question: pick **Accept when notice is at least 14 days** → saved as a rule, "it
   never asks twice".
6. **Books (10 s).** Approve the memo for the fair charges ("Simulated" books: QuickBooks is a sandbox). "Money only
   moves when the owner says yes."
7. **Dispute + the judge as Brightway (35 s).** Disputes → **Review and send**. Hand Tab B to the judge: a quick reply
   ("The rate was $2.00", "Mint was in the promo", "Agree on Mint") or their own words. Clawback answers with the deal
   and the data.
8. **Close (10 s).** Home → **Done for you**. "Every dollar traced to a sentence, a row or a person."

For a deeper second example, sign in as Peak Bar (ID `testuser`): six distributors, including real Walmart and Five
Below agreements.

## If something goes wrong

- **The check is slow**: keep talking through the table above; the second run of the same payment answers from its
  recording in seconds.
- **"Too many runs"**: the presenter token isn't loaded in that tab (step 2 above).
- **Numbers look odd after many takes**: Reset the demo, start again.
- **A judge wants their own numbers**: Tab B → change any bars, rate or fee, or remove a line, then Send payment. Start
  over puts the invoice back.
