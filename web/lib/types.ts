// Mirrors api/contracts.py (the source of truth). Money arrives as a JSON number in dollars; the web app
// only formats it. Keep field names identical to the Pydantic models.

export type Money = number;
export type Actor =
  | "system" | "reader" | "investigator" | "gate" | "negotiator" | "bookkeeper" | "coach"
  | "owner" | "northmart" | "distributor" | "policy";
/** One person decides everything: the admin, the brand's owner (answers the questions, approves the credit memos). */
export type Role = "owner";
export type DecisionKind = "dispute" | "accept" | "split" | "ask" | "skip";
// The engine adds finding types as charge types grow (shortages, pricing, spoilage); unknown ones still render.
export type FindingType =
  | "rate_over" | "duplicate" | "outside_dates" | "amended_by_email" | "over_cap"
  | "product_not_covered" | "discretionary_fee" | "matches_deal"
  | (string & {});
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

/** delivery: proof-of-delivery rows; price: the agreed price list; policy: a quote from a deal document's policy section. */
export type EvidenceKind =
  | "clause" | "email" | "claim" | "notice" | "sales" | "charge" | "prior_payment" | "rule" | "person" | "approval"
  | "delivery" | "price" | "policy";

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
  /** Set when a newer run of the same payment replaced this one; a closed question can't be answered. */
  closed_at?: string | null;
  /** How much the question matters, like a code-review risk flag (branch question-severity). Absent on older runs. */
  risk?: QuestionRisk | null;
  /** The supporting facts the card keeps behind "Show details". */
  details?: { label: string; value: string }[] | null;
};

export type QuestionRisk = {
  level: "high" | "medium" | "low" | (string & {});
  kind: "financial" | "legal" | "deadline" | "relationship" | (string & {});
  reason: string;
};

export type Answer = { question_id: string; from_role: Role; text: string; answered_at: string; rule_id: string | null };

// ---- GET /overview (api/contracts.py SupplierOverview): the signed-in supplier across its distributors. Every amount
// is the API's, computed from engine values; the web shows them as given and adds nothing up.
/** Why an amount counts as recovered: the distributor agreed in a dispute thread, or a later remittance credited it. */
export type RecoveredEvidence = { dispute_id: string | null; message_id: string | null; remittance_ref: string | null; charge_id: string | null; amount: Money };
export type OverviewTotals = {
  taken: Money; disputed: Money; fair: Money; waiting: Money;
  /** Only the part of disputed with evidence (a reply agreeing, or a credit), never more. */
  recovered: Money;
  /** Disputed minus recovered: filed or drafted, no agreement or credit yet. */
  disputed_awaiting_reply: Money;
  evidence: RecoveredEvidence[];
};
export type OverviewLink = { page: "run" | "dispute" | "approval" | "question"; run_id: string | null; dispute_id: string | null };
/** One answer to a needs-you item in one tap: a question's reply (text) and whether it saves a rule, or an approval's yes. */
export type QuickChoice = { label: string; text: string; rule: boolean };
export type NeedsYou = {
  kind: "question" | "dispute_email" | "reply_email" | "approval";
  account_id: string; distributor: string;
  /** One plain sentence: what happened and what's asked. */
  title: string;
  /** The why, or the distributor's own words. */
  detail?: string | null;
  amount: Money | null;
  risk_level: "high" | "medium" | "low"; since: string | null; link: OverviewLink;
  /** The question's or approval's id, and its one-tap answers (empty when it needs reading first). */
  target_id?: string | null; choices?: QuickChoice[];
};
export type OpenDispute = {
  /** amount: what still awaits the distributor's reply; total: the whole dispute; agreed: what they agreed to pay. */
  dispute_id: string; account_id: string; distributor: string; run_id: string; amount: Money; status: string;
  filed_at: string | null; file_by: string | null; days_left: number | null; total?: Money; agreed?: Money;
};
export type RecentItem = { at: string; kind: "run_decided" | "reply" | "sent"; account_id: string; distributor: string; text: string; link: OverviewLink };
export type CompanyOverview = {
  supplier: string | null; distributors: number; totals: OverviewTotals;
  /** Already sorted: highest risk first, then the oldest within a level. */
  needs_you: NeedsYou[]; open_disputes: OpenDispute[]; recent: RecentItem[];
};

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
  /** The admin approved this one and ticked "Post fair charges like these automatically from now on". */
  sets_auto_post?: AutoPost | null;
  /** Posted without asking, by the admin's standing yes. */
  posted_by_auto_post?: AutoPost | null;
};

/** The admin's auto-post limit: fair-charge credit memos up to `limit` post without asking. */
export type AutoPost = { limit: Money; set_by: string; approval_id: string; set_at: string };

export type DisputeLine = {
  charge_id: string;
  ref: string;
  amount: Money;
  reason: string;
  clause_ref: string | null;
  quote: string | null;
  math: string;
  evidence_ids: string[];
  /** Last day to file this line with the distributor (YYYY-MM-DD), and days from today; null when the API doesn't know. */
  file_by?: string | null;
  days_left?: number | null;
};

export type Dispute = {
  id: string;
  remittance_id: string;
  counterparty: string;
  lines: DisputeLine[];
  total: Money;
  /** ready_to_send: drafted, waiting for the admin's "Review and send", which files it; draft: an older run's
   * over-limit dispute (sent the same way); filed: sent to the distributor. */
  status: "ready_to_send" | "draft" | "filed" | "answered" | "resolved" | "withdrawn";
  approved_by: "policy" | "owner";
  filed_at: string | null;
};

export type PortalMessage = {
  id: string;
  dispute_id: string;
  /** "clawback" is the brand's side; anything else is the distributor's desk. */
  from_party: "northmart" | "distributor" | "clawback" | (string & {});
  text: string;
  attachment_doc_id: string | null;
  classification: "new_document" | "claim_without_document" | "agrees" | "other" | null;
  charge_ids: string[];
  evidence_ids: string[];
  created_at: string;
  /** Where it was said: the distributor's portal, or an email. */
  channel?: "portal" | "email";
  email_message_id?: string | null;
};

/** One email about a dispute (api/contracts.py DisputeEmail): the dispute email itself, or a reply to the
 * distributor. held: the checks failed, the admin edits it · ready: waiting to be sent · sent: Mailgun took it ·
 * outbox: kept in the app instead (demo mode, or no mail keys) · failed: sending again retries. */
export type DisputeEmail = {
  id: string;
  kind: "dispute" | "reply";
  run_id: string;
  account_id: string;
  dispute_id: string;
  to: string;
  from_addr: string;
  reply_to: string | null;
  subject: string;
  body: string;
  attachments: string[];
  in_reply_to: string | null;
  status: "held" | "ready" | "sent" | "outbox" | "failed";
  written_by: "claude" | "template" | "admin" | "negotiator" | "code";
  problems: string[];
  message_id: string | null;
  sent_at: string | null;
  detail: string | null;
  portal_url: string | null;
  charge_ids: string[];
  evidence_ids: string[];
  replying_to: string | null;
};

/** GET /disputes/{id}/thread: the dispute as it stands, every message on it (portal and email), and its emails. */
export type DisputeThread = { dispute: Dispute; run_id: string; messages: PortalMessage[]; emails: DisputeEmail[] };

/** GET /notifications: something the supplier should know, e.g. a distributor replied to a dispute. */
export type SupplierNotification = { id: string; account_id: string; run_id: string | null; dispute_id: string | null; text: string; at: string };

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
  /** Only on the run's final totals event, once every charge is decided. */
  value?: RunValue | null;
};

/** What one run was worth: the money in play, how long it took, what the AI cost, and the hand-work estimate. */
export type RunValue = {
  disputed: Money;
  accepted: Money;
  questions: number;
  charges: number;
  seconds_to_decided: number;
  ai_calls: number;
  ai_cost_usd: number | null;
  manual_minutes: number | null;
  manual_minutes_per_charge: number | null;
};

export type RunInfo = {
  run_id: string;
  kind: "march" | "april" | "scenario" | "eval";
  status: "started" | "waiting" | "finished" | "failed";
  remittance: Remittance | null;
  demo_mode: boolean;
};

export type LogLine = { text: string; level: "info" | "good" | "warn" | "error"; actor: Actor; charge_id: string | null };

/** A step the board draws as a progress bar: reading the deal (a tick per document) and checking the charges (a tick
 * per charge). The other steps have their own events (dispute, question, approval, ledger_post). */
export type StageInfo = {
  stage: "read" | "check";
  status: "started" | "progress" | "done";
  done: number;
  total: number;
  label: string;
  charge_id: string | null;
  /** read: the quotes both readers agreed on, found word for word in the document. */
  items: string[];
};

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
  | E<"totals", Totals>
  | E<"stage", StageInfo>;

/** GET /charges/{id}: everything the evidence drawer shows. */
export type ChargeDetail = {
  charge: Charge;
  finding: Finding | null;
  decision: Decision | null;
  rehearsal: Rehearsal | null;
  rule: Rule | null;
  evidence: Evidence[];
};

// ---- Coach, scenario box, eval, audit (api/contracts.py)
export type Redline = {
  clause_ref: string;
  original_quote: string;
  suggested_text: string;
  reason: string;
  dollars_at_stake: Money;
  finding_ids: string[];
  quote: Quote | null;
};
export type CoachResponse = { draft_doc_id: string; redlines: Redline[] };

export type EvalReport = {
  status: "not_run" | "running" | "done";
  mode: "engine" | "agent" | null;
  run_at: string | null;
  cases: number;
  correct: number | null;
  amounts_correct: number | null;
  asked: number | null;
  wrong_automatic: number | null;
  unnecessary_questions: number | null;
};

export type ScenarioCharge = {
  description: string;
  amount: Money;
  code?: string | null;
  product?: string | null;
  units?: number | null;
  rate?: number | null;
  period_start?: string | null;
  period_end?: string | null;
  notice_date?: string | null;
};
export type ScenarioRequest = { clause: string; charge: ScenarioCharge };
export type ScenarioExample = { id: string; label: string; request: ScenarioRequest };
export type Term = {
  id: string;
  reader: "claude" | "gemini" | "claude-b" | "merged";
  status: "pending" | "verified" | "rejected" | "disputed";
  type: string;
  params: Record<string, unknown>;
  exact_quote: string;
  discretion: boolean;
  source_approved: boolean;
  reasons: string[];
};
export type ScenarioResponse = {
  stub: boolean;
  decision: Decision | null;
  finding: Finding | null;
  evidence: Evidence[];
  message: string | null;
  terms: Term[];
  rehearsal: Rehearsal | null;
  rule: Rule | null;
  unclear: string[];
};

export type AuditEntry = {
  id: number;
  at: string;
  actor: string;
  action: string;
  object_ref: string;
  evidence: Record<string, unknown>;
  prev_hash: string;
  hash: string;
};
export type AuditVerify = { ok: boolean; checked: number; broken_at: number | null; reason: string };

// ---- Accounts, overview and the decision trace (GET /accounts, /accounts/{id}/overview, /runs/{id}/trace)
export type Colors = { primary: string; accent: string };

export type Account = {
  id: string;
  brand: {
    name: string;
    kind: string;
    city: string;
    initials: string;
    colors: Colors;
    owner: { name: string; email: string };
    /** Older account files name one; unused (the owner decides everything). */
    controller?: { name: string } | null;
  };
  distributor: { name: string; desk_email: string; portal_name: string; colors: Colors };
  invoice: { id: string; expected: Money; received: Money; month: string; period_start: string; period_end: string };
  latest_run_id: string | null;
  supplier?: string;
};

export type Overview = {
  account: Account;
  kpis: {
    invoiced_6m: Money;
    collected_6m: Money;
    deducted_6m: Money;
    recovered_6m: Money;
    /** A fraction (0.42); a value above 1 is read as a percent. */
    recovery_rate: number;
    /** A count of open disputes. */
    open_disputes: number;
    open_balance: Money;
    /** From the lookback, when the API has it. */
    wrongly_taken_6m?: Money;
    lost_past_window?: Money;
    claimable_now?: Money;
  };
  months: { month: string; invoiced: Money; paid: Money; deducted: Money; recovered: Money }[];
  deductions_by_type: { code: string; label: string; count: number; amount: Money }[];
  recent_remittances: { date: string; invoice: string; paid: Money; deducted: Money }[];
  current: { invoice: string; expected: Money; received: Money; deducted: Money; run_id: string | null; status: string; value?: RunValue | null };
};

export type LookbackStatus = "claimable" | "past_window" | "settled" | "fair" | "not_checked";

/** GET /accounts/{id}/lookback: the last six months' charges checked after the fact, and what can still be claimed. */
export type Lookback = {
  account_id: string;
  as_of: string;
  dispute_window_days: number;
  rows: {
    ref: string;
    month: string;
    code: string;
    description: string;
    taken: Money;
    allowed: Money | null;
    wrongly_taken: Money;
    outcome: string;
    recovered: Money;
    deducted_on: string;
    file_by: string | null;
    days_left: number | null;
    status: LookbackStatus;
  }[];
  totals: { wrongly_taken: Money; lost_past_window: Money; claimable_now: Money; checked: number; not_checked: number };
};

/** One AI call in a run, as GET /runs/{id}/trace returns it. */
export type TraceStep = {
  seq: number;
  at: string;
  agent: string;
  service: string;
  run_id: string;
  charge_id: string | null;
  model: string | null;
  prompt: string | null;
  input: unknown;
  output: unknown;
  latency_ms: number | null;
  status: "live" | "recorded" | "failed";
  attempts: number;
  error: string | null;
  /** Tokens the call used, when the API reports them ({input_tokens, output_tokens} or similar). */
  usage?: Record<string, number | null> | null;
};

/** GET /runs/{id}/trace/summary: totals for a whole run. Field names are read loosely (see lib/trace.ts). */
export type TraceSummary = Record<string, unknown>;

// ---- Suppliers: one brand tracking many distributors (GET /suppliers)
export type RelationshipStatus = "waiting_for_payment" | "checking" | "needs_you" | "dispute_open" | "settled" | "stopped";
export type DistributorItem = {
  account_id: string;
  distributor: Account["distributor"];
  tracked: boolean;
  status: RelationshipStatus;
  /** Plain words, never a money figure. */
  status_label: string;
  latest_run_id: string | null;
};
export type SupplierItem = { id: string; brand: Account["brand"]; distributors: DistributorItem[] };

// ---- History and storage (GET /accounts/{id}/runs, /saved, /documents/{doc})
export type RunSummary = {
  run_id: string; kind: string; status: "started" | "waiting" | "finished" | "failed"; started_at: string; replaced: boolean;
  invoice_id: string | null; taken: Money | null; paid?: Money | null; invoiced?: Money | null; charges: number; disputed: Money | null; accepted: Money | null; waiting: Money | null;
  questions: number;
  /** This payment's own deductions (taken also counts older charges checked with it), and how many older ones. */
  kept?: Money | null; older_charges?: number;
};
export type SavedDocument = { id: string; kind: string; title: string; sender: string | null; locked: boolean; chars: number };
export type SavedOverview = { documents: SavedDocument[]; rules: Rule[]; records: { label: string; rows: number }[] };
export type DocumentText = { id: string; title: string; kind: string; locked: boolean; text: string };

// ---- Connections and the contract library (GET /connections, /accounts/{id}/contract)
export type Connection = {
  id: string; name: string; brings: string; status: "connected" | "not_connected" | "ready" | "coming_soon"; detail: string;
  // What the bank, QuickBooks and the remittance inbox have seen on this server, for the account in view (api/sources.py)
  checked_at?: string | null; problem?: string | null; last_seen?: string | null; last_seen_at?: string | null;
  run_id?: string | null; address?: string | null;
};
export type LibraryTerm = { type: string; quote: string; char_start: number; char_end: number; status: string; discretion: boolean; label: string };
export type LibraryDocument = { id: string; title: string; kind: string; locked: boolean; sender: string | null; approved_sender: boolean; text: string; terms: LibraryTerm[] };
export type ContractLibrary = { read_in_run: string | null; documents: LibraryDocument[] };
