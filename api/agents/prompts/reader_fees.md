This document can also set fees, a deadline for disputing deductions, and a notice period for changes. Besides the term types above, report these three (they replace "ignore dispute windows" above):
- fee_schedule: how one fee is priced. params:
  - fee_code: the fee's name as the document writes it: the abbreviation it defines for the fee if it defines one (e.g. "MCB" for Manufacturer Charge Backs), else the heading of the section that sets the fee, as written.
  - basis: "percent" (a % of an amount), "per_unit", "per_carton", "per_po" (once per purchase order) or "flat".
  - rate: a decimal string; for percent, the percent itself ("5" for 5%), else dollars ("0.29").
  - min and max: the fee's minimum and maximum in dollars as decimal strings, or null when none is stated.
  - per: what the minimum or maximum applies to: "invoice", "po", "incident" (each charge) or "month"; "incident" when nothing is stated.
  - tiers: only when the rate changes with a number of days (e.g. 5% if 0 to 7 days late, 10% if 8 to 14): one {from_days, to_days, rate} per band, to_days null for "and over"; rate null then. Otherwise null.
  - requires_proof: true when the document says backup, proof or documentation comes with the fee; else false. When that is said in the sentence right after the fee's, exact_quote is both sentences, as written.
  A fee charged on top of a cost (landed cost plus a processing fee) is a fee_schedule for the fee part only.
- dispute_window: how long the supplier has to dispute a deduction. params.days, and params.from: "deduction" or "invoice", whichever the deadline counts from.
- notice_period: the notice the distributor must give before changing these terms. params.days.
Rules for these as for every term: the exact sentence as exact_quote, every number in params written in that sentence, fields the type doesn't use null. A number written in words and digits ("thirty (30)") counts as written. A notice that changes a fee returns that fee's fee_schedule with the new values, and effective_from the date the notice says the change starts. discretion is true when whether the fee applies, or its amount, depends on someone's judgment or on a relationship nobody writes down ("depending on retailer relationship"). A choice between two stated rates that a record settles (which program a retailer is on) is not discretion: report the rate the document states in digits.
