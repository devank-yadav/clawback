// Mirrors the read that POST /accounts/{account}/remittance returns (api/remittance.py, RemittanceRead).
// Money arrives as a JSON number in dollars; this screen only formats it.

import type { Charge, Money } from "@/lib/types";

export type LineStatus = "verified" | "needs_person" | "rejected";

export type RemittanceLine = {
  n: number;
  charge_id: string | null;
  status: LineStatus;
  reasons: string[];
  ref: string | null;
  line_ref: string | null;
  code_text: string;
  code: string;
  description: string;
  product: string | null;
  units: number | null;
  rate: number | null;
  amount: Money;
  period_start: string | null;
  period_end: string | null;
  exact_quote: string;
  char_start: number | null;
  char_end: number | null;
};

export type Problem = {
  kind: "read" | "quote" | "numbers" | "code" | "dates" | "notice" | "header" | "totals";
  text: string;
  line: number | null;
};

export type RemittanceTotals = {
  lines: Money;
  gross: Money | null;
  paid: Money | null;
  short: Money | null;
  expected: Money;
  received: Money;
  account_short: Money;
  matches_remittance: boolean;
  matches_account: boolean;
};

export type RemittanceRead = {
  read_id: string;
  account: string;
  brand: string;
  distributor: string;
  input: "text" | "pdf";
  source: "live" | "fixture";
  ok: boolean;
  can_run: boolean;
  header: { payer: string | null; payment_ref: string | null; payment_date: string | null; invoice_id: string | null } | null;
  lines: RemittanceLine[];
  charges: Charge[];
  problems: Problem[];
  totals: RemittanceTotals | null;
  unclear: string[];
  text: string;
};
