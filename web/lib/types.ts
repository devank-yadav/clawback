// Mirrors api/contracts.py (the source of truth). Money arrives as a JSON number in dollars; the web app
// only formats it. Keep field names identical to the Pydantic models.

export type Money = number;
export type Actor =
  | "system" | "reader" | "investigator" | "gate" | "negotiator" | "bookkeeper" | "coach"
  | "owner" | "controller" | "northmart" | "policy";
export type Role = "owner" | "controller";
export type DecisionKind = "dispute" | "accept" | "split" | "ask" | "skip";
export type FindingType =
  | "rate_over" | "duplicate" | "outside_dates" | "amended_by_email" | "over_cap"
  | "product_not_covered" | "discretionary_fee" | "matches_deal";
export type TermType = "promo_rate" | "product_scope" | "unit_cap" | "date_range" | "fee_discretion" | "amendment";

export type Remittance = {
  id: string;
  counterparty: string;
  invoice_id: string | null;
  expected: Money;
  received: Money;
  taken: Money;
  charge_count: number;
  received_at: string | null;
  nessie_tx_id: string | null;
};

export type Charge = {
  id: string;
  remittance_id: string | null;
  ref: string;
  code: string;
  description: string;
  product: string | null;
  units: number;
  rate: number;
  amount: Money;
  period_start: string;
  period_end: string;
  notice_date: string | null;
};

export type EvidenceKind = "clause" | "email" | "claim" | "notice" | "sales" | "charge" | "prior_payment" | "rule" | "person" | "approval";

export type Quote = {
  doc_id: string;
  text: string;
  char_start: number;
  char_end: number;
  context_before: string;
  context_after: string;
};

export type Evidence = {
  id: string;
  kind: EvidenceKind;
  label: string;
  summary: string;
  quote: Quote | null;
  rows: Record<string, string | number | null>[];
  sender: string | null;
  approved_sender: boolean | null;
  sent_at: string | null;
  rule_id: string | null;
  approval_id: string | null;
  person: string | null;
};

export type MathPart = { text: string; evidence_id: string | null };

export type Finding = {
  id: string;
  charge_id: string;
  finding: string;
  type: FindingType;
  evidence_ids: string[];
  confidence: number;
  open_questions: string[];
  expected: Money;
  taken: Money;
  delta: Money;
  readers_agree: boolean;
  math: MathPart[];
};

export type Rehearsal = {
  charge_id: string;
  predicted_rebuttal: string;
  answer: string;
  answer_evidence_ids: string[];
  answered: boolean;
};

export type Decision = {
  charge_id: string;
  decision: DecisionKind;
  disputed: Money;
  accepted: Money;
  waiting: Money;
  gate_row: number;
  rule_id: string | null;
  decided_by: Actor;
  decided_at: string;
  reason: string;
};

export type Question = {
  id: string;
  to_role: Role;
  charge_id: string | null;
  text: string;
  channel: "sms" | "inbox";
  sent_at: string;
  answer: string | null;
  answered_at: string | null;
  rule_id: string | null;
};

export type Answer = { question_id: string; from_role: Role; text: string; answered_at: string; rule_id: string | null };

export type Rule = {
  id: string;
  label: string;
  pattern_text: string;
  term_type: TermType;
  counterparty: string;
  condition: string;
  decision: "accept" | "dispute" | "ask";
  else_decision: "accept" | "dispute" | "ask";
  summary: string;
  approver: string;
  approver_role: Role;
  learned_at: string;
  source_question_id: string | null;
  status: "pending" | "active" | "undone";
};

export type Approval = {
  id: string;
  kind: "credit_memo" | "dispute_over_limit" | "closed_period";
  amount: Money;
  lines: { charge_id: string; amount: Money }[];
  proposed_by: Actor;
  approver_role: Role;
  status: "pending" | "approved" | "refused";
  text: string;
  note: string | null;
  requested_at: string;
  decided_at: string | null;
};

export type DisputeLine = {
  charge_id: string;
  ref: string;
  amount: Money;
  reason: string;
  clause_ref: string | null;
  quote: string | null;
  math: string;
  evidence_ids: string[];
};

export type Dispute = {
  id: string;
  remittance_id: string;
  counterparty: string;
  lines: DisputeLine[];
  total: Money;
  status: "draft" | "filed" | "answered" | "resolved" | "withdrawn";
  approved_by: "policy" | "owner";
  filed_at: string | null;
};

export type PortalMessage = {
  id: string;
  dispute_id: string;
  from_party: "northmart" | "clawback";
  text: string;
  attachment_doc_id: string | null;
  classification: "new_document" | "claim_without_document" | "agrees" | "other" | null;
  charge_ids: string[];
  evidence_ids: string[];
  created_at: string;
};

export type LedgerPost = {
  id: string;
  qbo_entity: "customer" | "item" | "invoice" | "payment" | "credit_memo" | "invoice_note";
  qbo_id: string | null;
  qbo_url: string | null;
  amount: Money;
  lines: { charge_id: string | null; description: string; amount: Money }[];
  status: "pending" | "posted" | "held" | "failed" | "voided";
  approval_id: string | null;
  note: string | null;
  posted_at: string | null;
};

export type Totals = {
  taken: Money;
  disputed: Money;
  accepted: Money;
  waiting: Money;
  undecided: Money;
  questions: number;
  skipped: number;
};

export type RunInfo = {
  run_id: string;
  kind: "march" | "april" | "scenario" | "eval";
  status: "started" | "waiting" | "finished" | "failed";
  remittance: Remittance | null;
  demo_mode: boolean;
};

export type LogLine = { text: string; level: "info" | "good" | "warn" | "error"; actor: Actor; charge_id: string | null };

type E<T extends string, D> = { id: number; run_id: string; at: string; type: T; data: D };

export type RunEvent =
  | E<"run", RunInfo>
  | E<"log", LogLine>
  | E<"charge", Charge>
  | E<"finding", Finding>
  | E<"rehearsal", Rehearsal>
  | E<"decision", Decision>
  | E<"question", Question>
  | E<"answer", Answer>
  | E<"rule", Rule>
  | E<"approval", Approval>
  | E<"dispute", Dispute>
  | E<"portal_message", PortalMessage>
  | E<"ledger_post", LedgerPost>
  | E<"totals", Totals>;

/** GET /charges/{id}: everything the evidence drawer shows. */
export type ChargeDetail = {
  charge: Charge;
  finding: Finding | null;
  decision: Decision | null;
  rehearsal: Rehearsal | null;
  rule: Rule | null;
  evidence: Evidence[];
};

/** web/fixtures/run-events.json and friends. */
export type RunFixture = {
  run_id: string;
  events: RunEvent[];
  charges: Record<string, ChargeDetail>;
  evidence: Record<string, Evidence>;
};
