// PROTOTYPE DATA. Stands in for GET /charges/{id} and GET /evidence/{id} until the API lands.
// Amounts are copied from the scenario table in docs/design.md; wording follows the team prototype.
// Deal wording must be swapped for Manasv's data/deals/spring-promo.md text (with offsets) when it exists.

import type { ChargeDetail, Evidence } from "../types";

const deal31: Evidence = {
  id: "deal-3.1",
  kind: "deal",
  label: "Spring promo deal, §3.1",
  segments: [
    "§3.1 Supplier will fund a promotional allowance of ",
    { mark: "rate", text: "$1.00 per unit" },
    " on ",
    { mark: "products", text: "Peak Bar Original and Peak Bar Chocolate" },
    " sold between ",
    { mark: "dates", text: "March 1 and March 31, 2026" },
    ".",
  ],
};

const deal32: Evidence = {
  id: "deal-3.2",
  kind: "deal",
  label: "Spring promo deal, §3.2",
  segments: ["§3.2 The promotional allowance applies to a ", { mark: "cap", text: "maximum of 5,000 units" }, " in total."],
};

const deal54: Evidence = {
  id: "deal-5.4",
  kind: "deal",
  label: "Spring promo deal, §5.4",
  segments: [
    "§5.4 Northmart may charge a display fee of ",
    { mark: "max", text: "up to $1,500 per month" },
    " ",
    { mark: "discretion", text: "at its discretion, with written notice" },
    " to Supplier.",
  ],
};

const brokerEmail: Evidence = {
  id: "email-0328",
  kind: "email",
  label: "Broker email, Mar 28",
  from: "jordan@peakbar-broker.example (approved sender)",
  segments: [
    "Northmart asked to extend Spring Promo ",
    { mark: "dates", text: "through April 7, same terms" },
    ", ",
    { mark: "extra", text: "up to 500 additional units" },
    ". Approved.",
  ],
};

const plan4: Evidence = {
  id: "plan-4",
  kind: "row",
  label: "Your promo plan, row 4",
  table: "Promo plan",
  fields: [
    ["Products", "Original, Chocolate"],
    ["Rate", "$1.00 per bar"],
    ["Dates", "Mar 1 – Mar 31"],
    ["Cap", "5,000 bars"],
  ],
};

export const CHARGES: Record<string, ChargeDetail> = {
  C1: {
    id: "C1",
    title: "Week 1 promo",
    detail: "1,200 bars × $1.50",
    headline: "They charged $1.50 a bar. The deal says $1.00, so $1,200 is fair and $600 is not.",
    quoteRef: "deal-3.1",
    math: [
      {
        label: "Northmart took",
        tokens: [{ value: "1,200 bars", ref: "charge-C1" }, " × ", { value: "$1.50", ref: "charge-C1" }, " = ", { value: "$1,800", ref: "charge-C1" }],
      },
      {
        label: "Deal allows",
        tone: "accept",
        tokens: [{ value: "1,200 bars", ref: "sales-w1" }, " × ", { value: "$1.00", ref: "deal-3.1#rate" }, " = ", { value: "$1,200", ref: "calc-C1" }],
      },
      { label: "Took too much", tone: "dispute", tokens: [{ value: "$600", ref: "calc-C1" }] },
    ],
    checks: [
      "The deal, your promo plan and store sales all say $1.00 a bar",
      "Two separate sources back the rate",
      "We have an answer ready for their likely pushback",
    ],
    gateNote: "Split under your policy: accept the part the deal allows, dispute the rest.",
    comeback: {
      pushback: "“The rate was raised to $1.50 later.”",
      answer: "No amendment in the deal file, no email changing the rate, and your promo plan still shows $1.00.",
    },
    evidence: [
      deal31,
      {
        id: "charge-C1",
        kind: "row",
        label: "Northmart's charge on this payment",
        table: "Charges taken, March payment",
        fields: [
          ["Charge", "C1, week 1 promo"],
          ["Bars", "1,200"],
          ["Rate charged", "$1.50"],
          ["Amount taken", "$1,800"],
        ],
      },
      {
        id: "sales-w1",
        kind: "row",
        label: "Store sales, week 1",
        table: "Store sales",
        fields: [
          ["Week", "Mar 1 – Mar 7"],
          ["Promoted bars", "1,200"],
        ],
      },
      plan4,
      { id: "calc-C1", kind: "calc", label: "Worked out in code", text: "Covered bars × the deal's rate. Calculated by Clawback's math engine, not by AI." },
    ],
  },
  C2: {
    id: "C2",
    title: "Week 2 promo",
    detail: "Ref NM-2231",
    headline: "Week 2 was already paid on the Mar 14 payment. This is the same charge twice.",
    quoteRef: "deal-3.1",
    math: [
      { label: "Already taken Mar 14", tokens: ["Ref NM-2178 · ", { value: "980 bars", ref: "paid-2178" }, " · ", { value: "$980", ref: "paid-2178" }] },
      { label: "Taken again", tokens: ["Ref NM-2231 · ", { value: "$980", ref: "charge-C2" }] },
      { label: "Charged twice", tone: "dispute", tokens: [{ value: "$980", ref: "calc-C2" }] },
    ],
    checks: ["Same week, same bars, same amount as ref NM-2178", "Store sales confirm 980 bars that week", "Comeback answered"],
    gateNote: "Disputed in full under your policy.",
    comeback: {
      pushback: "“Different reference numbers, so different charges.”",
      answer: "Both cover Mar 8–14 and 980 bars, matching store sales of 980 for that week.",
    },
    evidence: [
      deal31,
      {
        id: "paid-2178",
        kind: "row",
        label: "Earlier payment, Mar 14",
        table: "Prior payments",
        fields: [
          ["Ref", "NM-2178"],
          ["Paid on", "Mar 14"],
          ["Week", "Mar 8 – Mar 14"],
          ["Bars", "980"],
          ["Amount", "$980"],
        ],
      },
      {
        id: "charge-C2",
        kind: "row",
        label: "Northmart's charge on this payment",
        table: "Charges taken, March payment",
        fields: [
          ["Charge", "C2, week 2 promo"],
          ["Ref", "NM-2231"],
          ["Amount taken", "$980"],
        ],
      },
      { id: "sales-w2", kind: "row", label: "Store sales, week 2", table: "Store sales", fields: [["Week", "Mar 8 – Mar 14"], ["Promoted bars", "980"]] },
      { id: "calc-C2", kind: "calc", label: "Worked out in code", text: "A prior payment covers the same promo, product and week, so nothing more is owed." },
    ],
  },
  C3: {
    id: "C3",
    title: "Apr 1–7 promo",
    detail: "330 bars × $1.00",
    headline: "After the deal's end date, but your broker extended the promo by email. Fair charge.",
    quoteRef: "email-0328",
    math: [
      { label: "Extension allows", tokens: ["up to ", { value: "500 bars", ref: "email-0328#extra" }, " at ", { value: "$1.00", ref: "deal-3.1#rate" }] },
      { label: "Northmart took", tone: "accept", tokens: [{ value: "330 bars", ref: "sales-apr" }, " × ", { value: "$1.00", ref: "charge-C3" }, " = ", { value: "$330", ref: "charge-C3" }] },
    ],
    checks: ["Email is from your approved broker", "330 bars is within the 500 extra allowed", "Store sales confirm 330 bars"],
    gateNote: "Accepted: the charge matches what the deal allows.",
    comeback: { none: "Nothing to rehearse. Clawback doesn't fight fair charges." },
    evidence: [
      brokerEmail,
      deal31,
      { id: "sales-apr", kind: "row", label: "Store sales, Apr 1–7", table: "Store sales", fields: [["Week", "Apr 1 – Apr 7"], ["Promoted bars", "330"]] },
      {
        id: "charge-C3",
        kind: "row",
        label: "Northmart's charge on this payment",
        table: "Charges taken, March payment",
        fields: [
          ["Charge", "C3, Apr 1–7 promo"],
          ["Bars", "330"],
          ["Rate charged", "$1.00"],
          ["Amount taken", "$330"],
        ],
      },
    ],
  },
  C4: {
    id: "C4",
    title: "Week 4 promo",
    detail: "1,540 bars × $1.00",
    headline: "The deal covers 5,000 bars in total. That cap was reached in week 3.",
    quoteRef: "deal-3.2",
    math: [
      {
        label: "Weeks 1–3",
        tokens: [{ value: "1,200", ref: "sales-w1" }, " + ", { value: "980", ref: "sales-w2" }, " + ", { value: "2,820", ref: "sales-w3" }, " = ", { value: "5,000 bars", ref: "deal-3.2#cap" }],
      },
      { label: "Week 4 took", tokens: [{ value: "1,540 bars", ref: "charge-C4" }, " × ", { value: "$1.00", ref: "charge-C4" }] },
      { label: "Over the cap", tone: "dispute", tokens: [{ value: "$1,540", ref: "calc-C4" }] },
    ],
    checks: ["Store sales show the cap was hit Mar 21", "The only written change adds bars for Apr 1–7, not March", "Comeback answered"],
    gateNote: "Disputed in full under your policy.",
    comeback: {
      pushback: "“The cap was raised by phone.”",
      answer: "No written change exists. The only email adds 500 bars for Apr 1–7.",
    },
    evidence: [
      deal32,
      { id: "sales-w1", kind: "row", label: "Store sales, week 1", table: "Store sales", fields: [["Week", "Mar 1 – Mar 7"], ["Promoted bars", "1,200"]] },
      { id: "sales-w2", kind: "row", label: "Store sales, week 2", table: "Store sales", fields: [["Week", "Mar 8 – Mar 14"], ["Promoted bars", "980"]] },
      { id: "sales-w3", kind: "row", label: "Store sales, week 3", table: "Store sales", fields: [["Week", "Mar 15 – Mar 21"], ["Promoted bars", "2,820"]] },
      {
        id: "charge-C4",
        kind: "row",
        label: "Northmart's charge on this payment",
        table: "Charges taken, March payment",
        fields: [
          ["Charge", "C4, week 4 promo"],
          ["Bars", "1,540"],
          ["Rate charged", "$1.00"],
          ["Amount taken", "$1,540"],
        ],
      },
      { id: "calc-C4", kind: "calc", label: "Worked out in code", text: "Promoted bars added week by week in date order; bars after the cap are not covered." },
    ],
  },
  C5: {
    id: "C5",
    title: "Mint promo",
    detail: "1,000 bars × $1.00",
    headline: "The deal names Original and Chocolate only. Mint isn't covered.",
    quoteRef: "deal-3.1",
    math: [
      { label: "Covered", tokens: [{ value: "Original, Chocolate", ref: "deal-3.1#products" }] },
      { label: "Northmart took", tokens: ["Mint · ", { value: "1,000 bars", ref: "sales-mint" }, " × ", { value: "$1.00", ref: "charge-C5" }] },
      { label: "Not covered", tone: "dispute", tokens: [{ value: "$1,000", ref: "calc-C5" }] },
    ],
    checks: ["§3.1 lists the products by name", "Your promo plan has no Mint row", "Comeback answered"],
    gateNote: "Disputed in full under your policy.",
    comeback: {
      pushback: "“Mint is part of the Peak Bar line.”",
      answer: "§3.1 names Original and Chocolate only.",
    },
    evidence: [
      deal31,
      plan4,
      { id: "sales-mint", kind: "row", label: "Store sales, Mint", table: "Store sales", fields: [["Product", "Peak Bar Mint"], ["Promoted bars", "1,000"]] },
      {
        id: "charge-C5",
        kind: "row",
        label: "Northmart's charge on this payment",
        table: "Charges taken, March payment",
        fields: [
          ["Charge", "C5, Mint promo"],
          ["Bars", "1,000"],
          ["Rate charged", "$1.00"],
          ["Amount taken", "$1,000"],
        ],
      },
      { id: "calc-C5", kind: "calc", label: "Worked out in code", text: "Product not in the deal's product list, so nothing is owed." },
    ],
  },
  C6: {
    id: "C6",
    title: "Display fee",
    detail: "Notice dated Mar 11 (20 days)",
    headline: "The deal allows this fee “at its discretion,” but sets no notice period. That's your call.",
    quoteRef: "deal-5.4",
    math: [
      { label: "Fee taken", tokens: [{ value: "$1,200", ref: "notice-0311" }, " of up to ", { value: "$1,500", ref: "deal-5.4#max" }] },
      { label: "Notice given", tokens: [{ value: "20 days", ref: "notice-0311" }, " ahead"] },
    ],
    checks: ["The fee is within the $1,500 limit", "Written notice was sent Mar 11", "The deal sets no minimum notice, so it needs your judgment"],
    gateNote: "Discretion wording: Clawback asks you once, then remembers your answer.",
    comeback: { none: "Not rehearsed. Discretion fees go to you first." },
    evidence: [
      deal54,
      {
        id: "notice-0311",
        kind: "row",
        label: "Northmart's display fee notice",
        table: "Notices",
        fields: [
          ["Dated", "Mar 11"],
          ["Notice", "20 days ahead"],
          ["Fee", "$1,200"],
        ],
      },
    ],
  },
};

export const RULE_1: Evidence = {
  id: "rule-1",
  kind: "rule",
  label: "Rule #1",
  text: "Accept Northmart display fees with at least 14 days' notice. Dispute them otherwise.",
  meta: "Learned Oct 24 from your answer, approved by Dana",
};
