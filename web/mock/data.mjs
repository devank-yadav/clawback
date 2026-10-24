// Mock data for `npm run dev:mock`: four invented brands, each selling through an invented distributor, in exactly the
// shapes the API contracts give. Dev-only; nothing in the app imports this. Peak Bar Co. replays the recorded run in
// web/fixtures/; the other three are generated runs with shortage, pricing and spoilage charges.

const months = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"];

/** Six months of history ending with the current invoice: [invoiced, deducted, recovered] per month. */
function history(rows) {
  return months.map((month, i) => {
    const [invoiced, deducted, recovered] = rows[i];
    return { month, invoiced, paid: invoiced - deducted, deducted, recovered };
  });
}

export const ACCOUNTS = [
  {
    id: "peak-bar",
    brand: {
      name: "Peak Bar Co.", kind: "Snack bars", city: "Portland, OR", initials: "PB",
      colors: { primary: "#3f5a3c", accent: "#d9c27a" },
      owner: { name: "Dana Okafor", email: "dana@peakbar.example" },
    },
    distributor: { name: "Northmart", desk_email: "deductions@northmart.example", portal_name: "Northmart Supplier Portal", colors: { primary: "#0b4f9e", accent: "#f2b134" } },
    invoice: { id: "INV-3102", expected: 48200, received: 41350, month: "2026-03", period_start: "2026-03-01", period_end: "2026-03-31" },
    fixture: true,
    months: history([[44100, 3920, 1650], [45800, 4410, 2210], [52300, 5120, 2480], [39900, 3280, 1970], [43600, 4050, 2140], [48200, 6850, 0]]),
    remittances: [["2026-03-28", "INV-3102", 41350, 6850], ["2026-02-27", "INV-3047", 39550, 4050], ["2026-01-30", "INV-2988", 36620, 3280], ["2025-12-29", "INV-2931", 47180, 5120], ["2025-11-28", "INV-2874", 41390, 4410]],
    types: [["PA", "Promo allowance", 21, 18740], ["DF", "Display fee", 6, 6420], ["SH", "Shortage claim", 3, 1470]],
  },
  {
    id: "fernway",
    brand: {
      name: "Fernway Kombucha", kind: "Bottled kombucha", city: "Oakland, CA", initials: "FK",
      colors: { primary: "#c4532d", accent: "#f3d9c4" },
      owner: { name: "Maya Lindqvist", email: "maya@fernway.example" },
    },
    distributor: { name: "Larkfield Foods", desk_email: "supplier-deductions@larkfield.example", portal_name: "Larkfield Supplier Hub", colors: { primary: "#2f6b4f", accent: "#e2b33c" } },
    invoice: { id: "INV-7741", expected: 36480, received: 33077, month: "2026-03", period_start: "2026-03-01", period_end: "2026-03-31" },
    months: history([[31200, 2410, 980], [33950, 2870, 1320], [35100, 3090, 1460], [29800, 2240, 1110], [32400, 2660, 1290], [36480, 3403, 0]]),
    remittances: [["2026-03-30", "INV-7741", 33077, 3403], ["2026-02-27", "INV-7688", 29740, 2660], ["2026-01-29", "INV-7630", 27560, 2240], ["2025-12-30", "INV-7571", 32010, 3090], ["2025-11-27", "INV-7519", 31080, 2870]],
    types: [["SH", "Shortage claim", 9, 4120], ["PR", "Pricing deduction", 7, 3880], ["SP", "Spoilage", 5, 2210], ["PA", "Promo allowance", 4, 6463]],
    deal: { doc: "larkfield-supply-2026", title: "Larkfield Supply Agreement 2026" },
    charges: [
      {
        id: "C1", ref: "LF-90412", code: "SH", description: "Short shipment, PO 55102 line 3", product: "Ginger Kombucha 12oz", units: 96, rate: 3.25, amount: 312,
        decision: "dispute", disputed: 312, accepted: 0, gate_row: 7, type: "short_shipped_disproved", confidence: 0.96,
        reason: "Larkfield signed for all 480 bottles, so nothing was short: dispute $312.",
        finding: "Larkfield claims 96 bottles short, but its own receiver signed for all 480 on Mar 6.",
        math: [["480 shipped", "ev-pod-55102"], [" · ", null], ["480 received", "ev-pod-55102"], [" → 0 short · took ", null], ["$312", "ev-charge-C1"], [" → $312 not owed", null]],
        evidence: [
          { id: "ev-pod-55102", kind: "delivery", label: "Proof of delivery, PO 55102", summary: "Larkfield's receiver signed for 480 of 480 bottles on Mar 6.", rows: [{ line_ref: "PO 55102-3", product: "Ginger Kombucha 12oz", shipped_units: 480, received_units: 480, unit_price: 3.25, received_by: "R. Ortiz", received_at: "2026-03-06" }] },
          { id: "ev-policy-4.2", kind: "policy", label: "§4.2 shortages", summary: "Shortages must be noted on the delivery receipt at signing.", quote: "Any shortage must be noted on the delivery receipt at the time of signing; a receipt signed without exception confirms full delivery.", before: "4.2 Shortages. " },
        ],
        rehearsal: { predicted_rebuttal: "Our warehouse count found 96 bottles missing after receipt.", answer: "Under §4.2 a shortage must be noted at signing. R. Ortiz signed for 480 of 480 on Mar 6 with no exception.", ids: ["ev-policy-4.2", "ev-pod-55102"] },
      },
      {
        id: "C2", ref: "LF-90415", code: "PR", description: "Price difference, Hibiscus 12oz", product: "Hibiscus Kombucha 12oz", units: 1200, rate: 0.4, amount: 480,
        decision: "dispute", disputed: 480, accepted: 0, gate_row: 7, type: "price_mismatch", confidence: 0.95,
        reason: "The agreed price is $2.85 from Mar 1; Larkfield paid at the old $2.45: dispute $480.",
        finding: "Larkfield paid $2.45 a bottle, but the signed price list sets $2.85 from March 1.",
        math: [["1,200 bottles", "ev-charge-C2"], [" × ($2.85 agreed − $2.45 paid) = $480 short-paid · the price list sets ", null], ["$2.85", "ev-price-hibiscus"]],
        evidence: [
          { id: "ev-price-hibiscus", kind: "price", label: "Price list, Hibiscus 12oz", summary: "Signed price list: $2.85 a bottle from Mar 1, 2026.", rows: [{ product: "Hibiscus Kombucha 12oz", agreed_price: 2.45, effective_from: "2025-07-01", effective_to: "2026-02-28" }, { product: "Hibiscus Kombucha 12oz", agreed_price: 2.85, effective_from: "2026-03-01", effective_to: null }] },
          { id: "ev-clause-3.1", kind: "clause", label: "§3.1 prices", summary: "Prices follow the signed price list in effect on the ship date.", quote: "Prices are those on the signed price list in effect on the date of shipment.", before: "3.1 Price. " },
        ],
        rehearsal: { predicted_rebuttal: "We never received the March price increase.", answer: "The price list effective Mar 1 is signed by both sides (Exhibit B). §3.1 applies the list in effect on the ship date.", ids: ["ev-price-hibiscus", "ev-clause-3.1"] },
      },
      {
        id: "C3", ref: "LF-90420", code: "SP", description: "Spoiled product, Mar 18 store returns", product: "Original Kombucha 12oz", units: 160, rate: 2.85, amount: 456,
        decision: "accept", disputed: 0, accepted: 456, gate_row: 5, type: "matches_deal", confidence: 0.94,
        reason: "160 bottles is under the 2% spoilage allowance, with store photos: accept $456.",
        finding: "160 spoiled bottles is within the 2% allowance (192 of 9,600 shipped), and photos are attached.",
        math: [["9,600 shipped", "ev-ship-march"], [" × 2% = 192 allowed · claimed ", null], ["160", "ev-charge-C3"], [" → within the allowance", null]],
        evidence: [
          { id: "ev-policy-7.2", kind: "policy", label: "§7.2 spoilage", summary: "Spoilage up to 2% of shipped units, with store photos.", quote: "Distributor may deduct for product that spoils before its printed date, up to 2% of the month's shipped units, when store photos are provided.", before: "7.2 Spoilage. " },
          { id: "ev-ship-march", kind: "delivery", label: "March shipments", summary: "9,600 bottles shipped in March.", rows: [{ line_ref: "March total", product: "All flavors", shipped_units: 9600, received_units: 9600, unit_price: null, received_by: "Larkfield DC 2", received_at: "2026-03-31" }] },
        ],
      },
      {
        id: "C4", ref: "LF-90433", code: "PA", description: "Spring promo, 2,155 bottles", product: "All flavors", units: 2155, rate: 1, amount: 2155,
        decision: "accept", disputed: 0, accepted: 2155, gate_row: 5, type: "matches_deal", confidence: 0.98,
        reason: "$1.00 a bottle on 2,155 promoted bottles matches the deal: accept $2,155.",
        finding: "Rate and units match the deal and store sales.",
        math: [["2,155 bottles", "ev-sales-spring"], [" × ", null], ["$1.00", "ev-clause-5.1"], [" = $2,155 allowed · took $2,155", null]],
        evidence: [
          { id: "ev-clause-5.1", kind: "clause", label: "§5.1 spring promo", summary: "$1.00 a bottle on promoted bottles sold in March.", quote: "Supplier will fund $1.00 per bottle on promoted bottles sold March 1 to March 31, 2026.", before: "5.1 Spring promotion. " },
          { id: "ev-sales-spring", kind: "sales", label: "March promoted sales", summary: "2,155 promoted bottles sold.", rows: [{ week_start: "2026-03-01", week_end: "2026-03-31", product: "All flavors", promo_units: 2155, total_units: 8810 }] },
        ],
      },
    ],
    nextMonth: [
      { id: "A1", ref: "LF-91002", code: "SH", description: "Short shipment, PO 55240", product: "Ginger Kombucha 12oz", units: 48, rate: 3.25, amount: 156, decision: "accept", disputed: 0, accepted: 156, gate_row: 5, type: "matches_deal", confidence: 0.95, reason: "The receipt notes 48 short at signing: accept $156.", finding: "Shortage noted on the receipt at signing, as §4.2 requires.", math: [["48 short", "ev-pod-55240"], [" × $3.25 = $156", null]], evidence: [{ id: "ev-pod-55240", kind: "delivery", label: "Proof of delivery, PO 55240", summary: "Signed with exception: 48 short.", rows: [{ line_ref: "PO 55240-1", product: "Ginger Kombucha 12oz", shipped_units: 480, received_units: 432, unit_price: 3.25, received_by: "R. Ortiz", received_at: "2026-04-03" }] }] },
    ],
  },
  {
    id: "little-ember",
    brand: {
      name: "Little Ember Hot Sauce", kind: "Small-batch hot sauce", city: "Austin, TX", initials: "LE",
      colors: { primary: "#b8321f", accent: "#f7c873" },
      owner: { name: "Rosa Delgado", email: "rosa@littleember.example" },
    },
    distributor: { name: "Tallgrass Wholesale", desk_email: "vendor-claims@tallgrass.example", portal_name: "Tallgrass Vendor Desk", colors: { primary: "#5b2d82", accent: "#f0c419" } },
    invoice: { id: "INV-2290", expected: 22750, received: 19822, month: "2026-03", period_start: "2026-03-01", period_end: "2026-03-31" },
    months: history([[18400, 1610, 720], [21950, 2080, 940], [26300, 2950, 1310], [17200, 1490, 820], [19800, 1870, 1010], [22750, 2928, 0]]),
    remittances: [["2026-03-27", "INV-2290", 19822, 2928], ["2026-02-26", "INV-2241", 17930, 1870], ["2026-01-29", "INV-2198", 15710, 1490], ["2025-12-30", "INV-2152", 23350, 2950], ["2025-11-26", "INV-2107", 19870, 2080]],
    types: [["PR", "Pricing deduction", 8, 4310], ["SH", "Shortage claim", 6, 2240], ["PA", "Promo allowance", 5, 6380]],
    deal: { doc: "tallgrass-vendor-2026", title: "Tallgrass Vendor Agreement" },
    charges: [
      {
        id: "C1", ref: "TG-4471", code: "PR", description: "Price variance, Smoked Habanero 5oz", product: "Smoked Habanero 5oz", units: 2400, rate: 0.35, amount: 840,
        decision: "dispute", disputed: 840, accepted: 0, gate_row: 7, type: "price_mismatch", confidence: 0.96,
        reason: "The signed price is $4.10 through Mar 31; Tallgrass paid $3.75: dispute $840.",
        finding: "Tallgrass paid $3.75 a bottle; the signed price list holds $4.10 through March 31.",
        math: [["2,400 bottles", "ev-charge-C1"], [" × ($4.10 − $3.75) = $840 · agreed price ", null], ["$4.10", "ev-price-habanero"]],
        evidence: [
          { id: "ev-price-habanero", kind: "price", label: "Price list, Smoked Habanero 5oz", summary: "$4.10 a bottle from Jan 1 through Mar 31, 2026.", rows: [{ product: "Smoked Habanero 5oz", agreed_price: 4.1, effective_from: "2026-01-01", effective_to: "2026-03-31" }, { product: "Smoked Habanero 5oz", agreed_price: 3.75, effective_from: "2026-04-01", effective_to: null }] },
          { id: "ev-policy-2.4", kind: "policy", label: "§2.4 price changes", summary: "New prices apply only from their effective date.", quote: "A price change applies to orders shipped on or after its effective date and never to earlier shipments.", before: "2.4 Price changes. " },
        ],
        rehearsal: { predicted_rebuttal: "The new $3.75 price was agreed in February.", answer: "It was agreed for shipments from Apr 1 (§2.4). These shipped in March at $4.10.", ids: ["ev-policy-2.4", "ev-price-habanero"] },
      },
      {
        id: "C2", ref: "TG-4473", code: "SH", description: "Short-shipped, PO 8812", product: "Ghost Pepper 5oz", units: 60, rate: 4.1, amount: 246,
        decision: "accept", disputed: 0, accepted: 246, gate_row: 5, type: "matches_deal", confidence: 0.97,
        reason: "The receipt notes 60 bottles short at signing: accept $246.",
        finding: "Receiver noted 540 of 600 at signing; the shortage is real.",
        math: [["600 shipped", "ev-pod-8812"], [" − ", null], ["540 received", "ev-pod-8812"], [" = 60 short × $4.10 = $246", null]],
        evidence: [{ id: "ev-pod-8812", kind: "delivery", label: "Proof of delivery, PO 8812", summary: "Signed with exception: 540 of 600 received.", rows: [{ line_ref: "PO 8812-2", product: "Ghost Pepper 5oz", shipped_units: 600, received_units: 540, unit_price: 4.1, received_by: "J. Abara", received_at: "2026-03-12" }] }],
      },
      {
        id: "C3", ref: "TG-4480", code: "PA", description: "Holiday promo, 1,800 bottles", product: "All sauces", units: 1800, rate: 0.75, amount: 1350,
        decision: "split", disputed: 450, accepted: 900, gate_row: 7, type: "rate_over", confidence: 0.97,
        reason: "The deal pays $0.50 a bottle, not $0.75: accept $900, dispute $450.",
        finding: "Charged $0.75 a bottle; §6.1 sets $0.50. 1,800 bottles sold, so $900 is owed.",
        math: [["1,800 bottles", "ev-sales-holiday"], [" × ", null], ["$0.50", "ev-clause-6.1"], [" = $900 allowed · took $1,350 → $450 too much", null]],
        evidence: [
          { id: "ev-clause-6.1", kind: "clause", label: "§6.1 promo rate", summary: "$0.50 a bottle on promoted bottles.", quote: "Supplier will fund a promotional allowance of $0.50 per bottle sold during an agreed promotion.", before: "6.1 Promotions. " },
          { id: "ev-sales-holiday", kind: "sales", label: "Promo sales", summary: "1,800 promoted bottles sold.", rows: [{ week_start: "2026-03-01", week_end: "2026-03-14", product: "All sauces", promo_units: 1800, total_units: 4120 }] },
        ],
        rehearsal: { predicted_rebuttal: "Our promo calendar lists $0.75.", answer: "The signed agreement (§6.1) sets $0.50; a calendar can't change it.", ids: ["ev-clause-6.1"] },
      },
      {
        id: "C4", ref: "TG-4486", code: "SH", description: "Short-shipped, PO 8830", product: "Smoked Habanero 5oz", units: 120, rate: 4.1, amount: 492,
        decision: "dispute", disputed: 492, accepted: 0, gate_row: 7, type: "short_shipped_disproved", confidence: 0.95,
        reason: "Signed for 720 of 720 with no exception: dispute $492.",
        finding: "Receipt for PO 8830 shows all 720 bottles received and signed without exception.",
        math: [["720 shipped", "ev-pod-8830"], [" · ", null], ["720 received", "ev-pod-8830"], [" → nothing short · took $492", null]],
        evidence: [{ id: "ev-pod-8830", kind: "delivery", label: "Proof of delivery, PO 8830", summary: "720 of 720 received, signed without exception.", rows: [{ line_ref: "PO 8830-1", product: "Smoked Habanero 5oz", shipped_units: 720, received_units: 720, unit_price: 4.1, received_by: "J. Abara", received_at: "2026-03-20" }] }],
        rehearsal: { predicted_rebuttal: "Cases were damaged and unsellable.", answer: "Damage must be noted at signing; the receipt for PO 8830 has no exception.", ids: ["ev-pod-8830"] },
      },
    ],
    nextMonth: [
      { id: "A1", ref: "TG-4602", code: "PR", description: "Price variance, Smoked Habanero 5oz", product: "Smoked Habanero 5oz", units: 1800, rate: 0.35, amount: 630, decision: "accept", disputed: 0, accepted: 630, gate_row: 5, type: "matches_deal", confidence: 0.97, reason: "April ships at the new $3.75 price: accept $630.", finding: "From Apr 1 the agreed price is $3.75, so the deduction matches.", math: [["1,800 bottles", null], [" × $0.35 = $630", null]], evidence: [] },
    ],
  },
  {
    id: "brightfold",
    brand: {
      name: "Brightfold Oat Milk", kind: "Oat milk", city: "Minneapolis, MN", initials: "BO",
      colors: { primary: "#e0a526", accent: "#213547" },
      owner: { name: "Hannah Osei", email: "hannah@brightfold.example" },
    },
    distributor: { name: "Orchard & Pine Distributors", desk_email: "deductions@orchardpine.example", portal_name: "Orchard & Pine Partner Portal", colors: { primary: "#1f4e79", accent: "#8cc63f" } },
    invoice: { id: "INV-5108", expected: 58900, received: 53498, month: "2026-03", period_start: "2026-03-01", period_end: "2026-03-31" },
    months: history([[51200, 4380, 1930], [54800, 4960, 2410], [61500, 5730, 2650], [49900, 4120, 2030], [55300, 4840, 2330], [58900, 5402, 0]]),
    remittances: [["2026-03-31", "INV-5108", 53498, 5402], ["2026-02-27", "INV-5051", 50460, 4840], ["2026-01-30", "INV-4993", 45780, 4120], ["2025-12-30", "INV-4936", 55770, 5730], ["2025-11-28", "INV-4880", 49840, 4960]],
    types: [["SP", "Spoilage", 11, 7240], ["DF", "Display fee", 6, 8400], ["PR", "Pricing deduction", 4, 2980], ["PA", "Promo allowance", 6, 10812]],
    deal: { doc: "orchard-pine-2026", title: "Orchard & Pine Distribution Agreement" },
    charges: [
      {
        id: "C1", ref: "OP-23310", code: "SP", description: "Spoiled cartons, Mar 9 cold-chain break", product: "Original 64oz", units: 420, rate: 3.1, amount: 1302,
        decision: "ask", disputed: 0, accepted: 0, waiting: 1302, gate_row: 4, type: "discretionary_fee", confidence: 0.82,
        reason: "The deal accepts spoilage with “reasonable documentation”: that's your call.",
        finding: "Store photos came with the claim, but no temperature log. §6.3 asks only for reasonable documentation.",
        math: [["420 cartons", "ev-charge-C1"], [" × $3.10 = $1,302 · documentation: ", null], ["photos, no log", "ev-claim-photos"]],
        question: "Orchard & Pine sent store photos but no temperature log for 420 spoiled cartons ($1,302). Accept spoilage claims backed by photos?",
        rule: { label: "Rule #1", summary: "Accept Orchard & Pine spoilage claims with store photos when under 3% of shipped units.", condition: "photos && units_pct < 3", term_type: "fee_discretion" },
        evidence: [
          { id: "ev-policy-6.3", kind: "policy", label: "§6.3 spoilage", summary: "Spoilage deductions need reasonable documentation.", quote: "Distributor may deduct for spoiled product upon reasonable documentation of the loss.", before: "6.3 Spoilage. " },
          { id: "ev-claim-photos", kind: "claim", label: "Orchard & Pine claim, Mar 11", summary: "Twelve store photos of swollen cartons; no temperature log.", sender: "deductions@orchardpine.example", approved: false },
        ],
      },
      {
        id: "C2", ref: "OP-23318", code: "DF", description: "End-cap display, March", product: null, units: 1, rate: 1500, amount: 1500,
        decision: "accept", disputed: 0, accepted: 1500, gate_row: 5, type: "matches_deal", confidence: 0.96,
        reason: "The deal sets a $1,500 March end-cap with 30 days' notice, given Jan 28: accept.",
        finding: "Fee and notice match §5.1: $1,500, notice 32 days ahead.",
        math: [["$1,500", "ev-clause-5.1b"], [" allowed · took $1,500 · notice Jan 28, 32 days ahead", null]],
        evidence: [{ id: "ev-clause-5.1b", kind: "clause", label: "§5.1 display fee", summary: "$1,500 a month for an end-cap with 30 days' notice.", quote: "Supplier will pay $1,500 per month for an end-cap display, with at least 30 days' written notice.", before: "5.1 Displays. " }],
      },
      {
        id: "C3", ref: "OP-23324", code: "PR", description: "Price protection, Original 64oz", product: "Original 64oz", units: 3000, rate: 0.2, amount: 600,
        decision: "dispute", disputed: 600, accepted: 0, gate_row: 7, type: "price_mismatch", confidence: 0.95,
        reason: "The lower price starts Apr 1, not March: dispute $600.",
        finding: "Price protection claimed for March, but the $2.90 price is effective April 1.",
        math: [["3,000 cartons", "ev-charge-C3"], [" × $0.20 = $600 · new price from ", null], ["Apr 1", "ev-price-original"]],
        evidence: [{ id: "ev-price-original", kind: "price", label: "Price list, Original 64oz", summary: "$3.10 through Mar 31; $2.90 from Apr 1.", rows: [{ product: "Original 64oz", agreed_price: 3.1, effective_from: "2025-09-01", effective_to: "2026-03-31" }, { product: "Original 64oz", agreed_price: 2.9, effective_from: "2026-04-01", effective_to: null }] }],
        rehearsal: { predicted_rebuttal: "Price protection covers inventory on hand when a price drops.", answer: "The agreement has no price-protection clause; the new price starts Apr 1 on the signed list.", ids: ["ev-price-original"] },
      },
      {
        id: "C4", ref: "OP-23331", code: "PA", description: "Promo, 4,000 cartons", product: "All", units: 4000, rate: 0.5, amount: 2000,
        decision: "accept", disputed: 0, accepted: 2000, gate_row: 5, type: "matches_deal", confidence: 0.98,
        reason: "$0.50 a carton on 4,000 promoted cartons matches the deal: accept $2,000.",
        finding: "Rate and promoted units match the deal and store sales.",
        math: [["4,000 cartons", null], [" × $0.50 = $2,000 allowed · took $2,000", null]],
        evidence: [],
      },
    ],
    nextMonth: [
      { id: "A1", ref: "OP-23480", code: "SP", description: "Spoiled cartons, Apr 6", product: "Original 64oz", units: 150, rate: 3.1, amount: 465, decision: "accept", disputed: 0, accepted: 465, gate_row: 3, type: "discretionary_fee", confidence: 0.93, ruleApplied: true, reason: "Photos attached and under 3% of shipped: accepted by Rule #1.", finding: "Same kind of claim as March; Rule #1 covers it.", math: [["150 cartons", null], [" × $3.10 = $465", null]], evidence: [] },
    ],
  },
];

/** GET /accounts shape (the internal fields above stay in the mock). */
export const accountOf = (a, latestRunId) => ({
  id: a.id, brand: a.brand, distributor: a.distributor, invoice: a.invoice, latest_run_id: latestRunId ?? null,
});

// ---- The six-month lookback (GET /accounts/{id}/lookback): the earlier remittances' charges, checked after the fact.
// "Today" for the mock is a week after the March remittance, so a few January lines are close to their window.
const LOOKBACK_AS_OF = "2026-04-08";
const DISPUTE_WINDOW_DAYS = 75;
const DAY = 86400000;
const addDays = (ymd, n) => new Date(Date.parse(`${ymd}T00:00:00Z`) + n * DAY).toISOString().slice(0, 10);
const daysBetween = (from, to) => Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY);

export function lookbackOf(a) {
  const codes = a.types.map(([code, label]) => [code, label]);
  const earlier = a.remittances.slice(1);
  // One older remittance (October) so the chart spans six months.
  const oldest = [`${a.months[0].month}-30`, `INV-${Number(earlier.at(-1)[1].slice(4)) - 57}`, 0, a.months[0].deducted];
  const rows = [];
  [...earlier, oldest].forEach(([date, invoice, , deducted], i) => {
    const parts = [Math.round(deducted * 0.45), Math.round(deducted * 0.35)];
    parts.push(deducted - parts[0] - parts[1]);
    parts.forEach((taken, k) => {
      const [code, label] = codes[(i + k) % codes.length];
      const wrongly = k === 0 ? 0 : k === 1 ? Math.round(taken * 0.6) : taken;
      const fileBy = addDays(date, DISPUTE_WINDOW_DAYS);
      const daysLeft = daysBetween(LOOKBACK_AS_OF, fileBy);
      const notChecked = a.id === "fernway" && i === earlier.length && k === 1;
      const settled = wrongly > 0 && daysLeft < 0 && k === 2 && i % 2 === 0;
      const status = notChecked ? "not_checked" : wrongly === 0 ? "fair" : settled ? "settled" : daysLeft >= 0 ? "claimable" : "past_window";
      rows.push({
        ref: `${invoice.replace("INV-", "")}-${k + 1}`, month: date.slice(0, 7), code, description: `${label}, ${invoice}`,
        taken, allowed: notChecked ? null : taken - wrongly, wrongly_taken: notChecked ? 0 : wrongly,
        outcome: status === "settled" ? "Repaid after a dispute" : status === "fair" ? "Matches the deal" : status === "not_checked" ? "No deal term to check against" : "Never disputed",
        recovered: status === "settled" ? wrongly : 0, deducted_on: date,
        file_by: status === "fair" || status === "not_checked" ? null : fileBy, days_left: status === "claimable" ? daysLeft : null, status,
      });
    });
  });
  rows.sort((x, y) => x.deducted_on.localeCompare(y.deducted_on));
  const sum = (st) => rows.filter((r) => st.includes(r.status)).reduce((t, r) => t + r.wrongly_taken, 0);
  return {
    account_id: a.id, as_of: LOOKBACK_AS_OF, dispute_window_days: DISPUTE_WINDOW_DAYS, rows,
    totals: {
      wrongly_taken: sum(["claimable", "past_window", "settled"]), lost_past_window: sum(["past_window"]), claimable_now: sum(["claimable"]),
      checked: rows.filter((r) => r.status !== "not_checked").length, not_checked: rows.filter((r) => r.status === "not_checked").length,
    },
  };
}

/** Days left to file each dispute line, by its place on the dispute (one under two weeks, so the urgent look shows). */
export function withFileBy(dispute) {
  const left = [9, 23, 41, 58, 67];
  return {
    ...dispute,
    lines: dispute.lines.map((l, i) => (l.days_left !== undefined ? l : { ...l, days_left: left[i % left.length], file_by: addDays(LOOKBACK_AS_OF, left[i % left.length]) })),
  };
}

export function overviewOf(a, run) {
  const sum = (k) => a.months.reduce((s, m) => s + m[k], 0);
  const deducted = sum("deducted");
  const recovered = sum("recovered");
  const disputedEarlier = Math.round(deducted * 0.62);
  const totals = run?.totals ?? null;
  return {
    account: accountOf(a, run?.id),
    kpis: {
      invoiced_6m: sum("invoiced"),
      collected_6m: sum("paid") + recovered,
      deducted_6m: deducted,
      recovered_6m: recovered,
      recovery_rate: Math.round((recovered / disputedEarlier) * 1000) / 1000,
      open_disputes: run?.dispute ? 1 : 0,
      open_balance: totals ? totals.disputed + totals.waiting : 0,
      wrongly_taken_6m: lookbackOf(a).totals.wrongly_taken,
      lost_past_window: lookbackOf(a).totals.lost_past_window,
      claimable_now: lookbackOf(a).totals.claimable_now,
    },
    months: a.months,
    deductions_by_type: a.types.map(([code, label, count, amount]) => ({ code, label, count, amount })),
    recent_remittances: (run ? a.remittances : a.remittances.slice(1)).map(([date, invoice, paid, d]) => ({ date, invoice, paid, deducted: d })),
    current: {
      invoice: a.invoice.id, expected: a.invoice.expected, received: run ? a.invoice.received : 0, deducted: run ? a.invoice.expected - a.invoice.received : 0,
      run_id: run?.id ?? null, status: run ? run.status : "awaiting_payment", value: totals?.value ?? null,
    },
  };
}
