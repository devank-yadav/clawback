// PROTOTYPE DATA. A local stand-in for web/fixtures/run-events.json, which Devank writes.
// Per-charge amounts are the scenario table in docs/design.md. Running totals are written out by hand
// so the screen never adds anything up; replace this file with the real fixture when it lands.

import type { RunEvent } from "../types";

type Scripted = { delay: number; event: Omit<RunEvent, "id" | "at"> };

const ev = (delay: number, event: Scripted["event"]): Scripted => ({ delay, event });

/** The run itself: payment arrives, six charges decided, one question for the owner. */
export const RUN_SCRIPT: Scripted[] = [
  ev(150, { type: "log", data: { text: "Northmart paid $41,350 against invoice INV-3102 for $48,200", level: "info" } }),
  ev(350, { type: "log", data: { text: "Read the spring promo deal and 3 emails; every quote found word for word", level: "ok" } }),
  ev(350, { type: "log", data: { text: "Both deal readers agree on all 6 terms", level: "ok" } }),
  ev(300, { type: "finding", data: { charge_id: "C1", expected: 1200, taken: 1800, delta: 600, type: "rate_over", finding: "Deal says $1.00 off per bar; $1,200 is fair, $600 is not.", evidence_ids: ["deal-3.1", "sales-w1", "plan-4"] } }),
  ev(250, { type: "decision", data: { charge_id: "C1", decision: "split", disputed: 600, accepted: 1200, gate_row: 7, rule_id: null } }),
  ev(0, { type: "totals", data: { disputed: 600, accepted: 1200, waiting: 0 } }),
  ev(300, { type: "finding", data: { charge_id: "C2", expected: 0, taken: 980, delta: 980, type: "duplicate", finding: "Same week and amount already taken on the Mar 14 payment (ref NM-2178).", evidence_ids: ["paid-2178", "sales-w2"] } }),
  ev(250, { type: "decision", data: { charge_id: "C2", decision: "dispute", disputed: 980, accepted: 0, gate_row: 7, rule_id: null } }),
  ev(0, { type: "totals", data: { disputed: 1580, accepted: 1200, waiting: 0 } }),
  ev(300, { type: "finding", data: { charge_id: "C3", expected: 330, taken: 330, delta: 0, type: "amended_by_email", finding: "After the end date, but the broker extended the promo by email.", evidence_ids: ["email-0328", "sales-apr"] } }),
  ev(250, { type: "decision", data: { charge_id: "C3", decision: "accept", disputed: 0, accepted: 330, gate_row: 5, rule_id: null } }),
  ev(0, { type: "totals", data: { disputed: 1580, accepted: 1530, waiting: 0 } }),
  ev(300, { type: "finding", data: { charge_id: "C4", expected: 0, taken: 1540, delta: 1540, type: "over_cap", finding: "The 5,000-bar cap was reached in week 3.", evidence_ids: ["deal-3.2", "sales-w1", "sales-w2", "sales-w3"] } }),
  ev(250, { type: "decision", data: { charge_id: "C4", decision: "dispute", disputed: 1540, accepted: 0, gate_row: 7, rule_id: null } }),
  ev(0, { type: "totals", data: { disputed: 3120, accepted: 1530, waiting: 0 } }),
  ev(300, { type: "finding", data: { charge_id: "C5", expected: 0, taken: 1000, delta: 1000, type: "product_not_covered", finding: "Mint is not named in the deal.", evidence_ids: ["deal-3.1", "sales-mint"] } }),
  ev(250, { type: "decision", data: { charge_id: "C5", decision: "dispute", disputed: 1000, accepted: 0, gate_row: 7, rule_id: null } }),
  ev(0, { type: "totals", data: { disputed: 4120, accepted: 1530, waiting: 0 } }),
  ev(300, { type: "finding", data: { charge_id: "C6", expected: null, taken: 1200, delta: null, type: "discretionary_fee", finding: "Allowed at its discretion with written notice; the deal sets no notice period.", evidence_ids: ["deal-5.4", "notice-0311"] } }),
  ev(250, { type: "decision", data: { charge_id: "C6", decision: "ask", disputed: 0, accepted: 0, gate_row: 4, rule_id: null } }),
  ev(0, { type: "totals", data: { disputed: 4120, accepted: 1530, waiting: 1200 } }),
  ev(300, {
    type: "dispute",
    data: { id: "D-0417", status: "filed", lines: [{ charge_id: "C1", amount: 600 }, { charge_id: "C2", amount: 980 }, { charge_id: "C4", amount: 1540 }, { charge_id: "C5", amount: 1000 }] },
  }),
  ev(0, { type: "log", data: { text: "Filed dispute D-0417 on Northmart's portal: 4 lines, $4,120", level: "ok" } }),
  ev(300, {
    type: "question",
    data: { id: "Q1", to_role: "owner", charge_id: "C6", text: "Northmart took a $1,200 display fee with 20 days' notice. The deal allows it “at its discretion, with written notice.” Accept it?" },
  }),
  ev(0, { type: "log", data: { text: "Texted Dana one question about the display fee", level: "warn" } }),
];

export const OWNER_ANSWER = "Accept if notice is at least 14 days";

/** Appended when the owner answers. Live: POST the answer, then these arrive on the stream. */
export const ANSWER_SCRIPT: Scripted[] = [
  ev(200, { type: "answer", data: { question_id: "Q1", text: OWNER_ANSWER, rule_id: "R1" } }),
  ev(0, { type: "log", data: { text: "Saved Rule #1: accept display fees with 14+ days' notice", level: "ok" } }),
  ev(350, { type: "decision", data: { charge_id: "C6", decision: "accept", disputed: 0, accepted: 1200, gate_row: 3, rule_id: "R1" } }),
  ev(0, { type: "totals", data: { disputed: 4120, accepted: 2730, waiting: 0 } }),
  ev(350, { type: "approval", data: { id: "A1", kind: "credit_memo", amount: 2730, lines: 3, status: "pending", note: null } }),
  ev(0, { type: "log", data: { text: "Asked Sam to approve a $2,730 credit memo (3 lines)", level: "warn" } }),
];

export const CONTROLLER_APPROVE_SCRIPT: Scripted[] = [
  ev(250, { type: "approval", data: { id: "A1", kind: "credit_memo", amount: 2730, lines: 3, status: "approved", note: null } }),
  ev(350, { type: "ledger_post", data: { entity: "Credit memo", amount: 2730, status: "posted", note: "Applied to INV-3102" } }),
  ev(0, { type: "ledger_post", data: { entity: "Open balance", amount: 4120, status: "open", note: "INV-3102, noted with dispute D-0417" } }),
  ev(0, { type: "log", data: { text: "Posted the $2,730 credit memo to QuickBooks", level: "ok" } }),
];

export const CONTROLLER_REFUSE_SCRIPT: Scripted[] = [
  ev(250, {
    type: "approval",
    data: { id: "A1", kind: "credit_memo", amount: 2730, lines: 3, status: "refused", note: "Hold this until I've checked the display fee notice." },
  }),
  ev(0, { type: "log", data: { text: "Sam held the credit memo. Nothing was posted.", level: "warn" } }),
];

export type { Scripted };

/** Stand-in for the remittance row (GET /runs/{id} once it exists). */
export const REMITTANCE = {
  counterparty: "Northmart",
  brand: "Peak Bar Co.",
  invoice: "INV-3102",
  month: "March",
  expected: 48200,
  received: 41350,
  taken: 6850,
  charges: 6,
  owner: "Dana",
  controller: "Sam",
};
