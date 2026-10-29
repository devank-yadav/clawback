# Live showcase: 3 minutes on clawback.biz

The story: a small snack brand (Peak Bar Co.) invoiced Northmart $48,200. Northmart pays short and keeps deductions.
Clawback checks every deduction against the signed deal, disputes the wrong ones with proof, accepts the fair ones, asks
the owner only when the deal leaves it to judgment, and books the result. Everything below is live: real AI reads, real
math, the real distributor portal.

## Before the judges arrive (5 minutes)

1. One browser, two tabs, both signed in as Peak Bar (ID `testuser`, password in `~/.config/clawback/live-signin.txt`):
   - **Tab A, the brand:** `https://clawback.biz/app`
   - **Tab B, the distributor:** `https://clawback.biz/portal?account=peak-bar` (Northmart's portal; also linked from
     Settings → Everything else)
2. Company menu (bottom left) → **Presenter mode…** → paste the admin token from the same file. This tab now skips the
   visitor rate limits and shows the presenter menu.
3. Company menu → **Reset the demo**. Wait about 10 seconds for Home to fill.
4. Settings: both "without asking" limits unticked (so the approval and "Review and send" moments show). An email
   address is optional; Gmail isn't connected on the server, so nothing is sent.

## The 3 minutes

1. **Home (15 s).** "This is Peak Bar's owner. Getting back, won back, fair charges, and the one thing that needs them."
2. **Tab B, Northmart pays (30 s).** "Now I'm Northmart." Show the invoice: $48,200, six deductions, $41,350 paid.
   Change one number live, e.g. Mint promo **1000 → 1500 units**: the total updates as you type. **Send payment.**
   "Northmart just kept $7,350 from a $48,200 invoice."
3. **Tab A, the agents work in the background (20 s).** You stay on Home; a note pops up when the check is done,
   and the sidebar counts what needs you. Open it from **See it** (or Payments → Northmart).
4. **The payment (60 s).** Disputed vs fair vs your call.
   - Week 1 charged **$1.50 a bar; the deal says $1.00**: the quote is highlighted, the math is one line.
   - **Apr 1-7 looks out of dates but is fair**: the broker's Mar 28 email extended the deal. "It reads email too, and
     only trusts approved senders."
   - **Mint isn't a covered product**: disputed in full.
   - **Display fee "at its discretion"**: the one question. Pick **Accept when notice is at least 14 days** → saved as
     Rule #1, "it never asks twice".
5. **Books (15 s).** Approve the credit memo for the fair charges ("Simulated" books on this server: QuickBooks is a
   sandbox). "Money only moves when the owner says yes."
6. **Dispute + the judge as Northmart (40 s).** Disputes → **Review and send** → send. Hand Tab B to the judge: they push
   back in the reply box (or tick **Attach Amendment 1**). Clawback answers with the deal and the data, or concedes when
   shown the signed amendment.
7. **Close (10 s).** Home → **Done for you**: what went without asking, and why. "Every dollar traced to a sentence, a
   row or a person."

## If something goes wrong

- **The check is slow** (live AI on a small free server can take 1-2 minutes): keep talking through Tab B's lines;
  if it passes 2 minutes, open the previous payment from Payments.
- **"Too many runs"**: the presenter token isn't loaded in that tab (step 2 above).
- **Numbers look odd after many takes**: Reset the demo, wait 10 s, start again.
- **A judge wants their own numbers**: Tab B → change any units, rate or fee, or remove a line, then Send payment. Start
  over puts the invoice back.
