// Event and object shapes from the sketch in web/CLAUDE.md.
// api/contracts.py is the source of truth once it lands; update these to match it.

export type DecisionKind = "dispute" | "accept" | "split" | "ask" | "skip";

export type LogData = { text: string; level: "info" | "ok" | "warn" };

export type FindingData = {
  charge_id: string;
  expected: number | null;
  taken: number;
  delta: number | null;
  type: string;
  finding: string;
  evidence_ids: string[];
  confidence?: number;
};

export type DecisionData = {
  charge_id: string;
  decision: DecisionKind;
  disputed: number;
  accepted: number;
  gate_row: number | null;
  rule_id: string | null;
};

export type QuestionData = { id: string; to_role: "owner" | "controller"; charge_id: string; text: string };
export type AnswerData = { question_id: string; text: string; rule_id: string | null };

export type ApprovalData = {
  id: string;
  kind: "credit_memo";
  amount: number;
  lines: number;
  status: "pending" | "approved" | "refused";
  note: string | null;
};

export type DisputeData = { id: string; lines: { charge_id: string; amount: number }[]; status: "filed" };
export type LedgerPostData = { entity: string; amount: number; status: "posted" | "open"; note: string };
export type TotalsData = { disputed: number; accepted: number; waiting: number };

export type RunEvent =
  | { id: number; type: "log"; at: string; data: LogData }
  | { id: number; type: "finding"; at: string; data: FindingData }
  | { id: number; type: "decision"; at: string; data: DecisionData }
  | { id: number; type: "question"; at: string; data: QuestionData }
  | { id: number; type: "answer"; at: string; data: AnswerData }
  | { id: number; type: "approval"; at: string; data: ApprovalData }
  | { id: number; type: "dispute"; at: string; data: DisputeData }
  | { id: number; type: "ledger_post"; at: string; data: LedgerPostData }
  | { id: number; type: "totals"; at: string; data: TotalsData };

// What GET /charges/{id} and GET /evidence/{id} will return. Text only; every amount is supplied, never computed.

export type QuoteSegment = string | { mark: string; text: string };

export type Evidence =
  | { id: string; kind: "deal"; label: string; segments: QuoteSegment[] }
  | { id: string; kind: "email"; label: string; from: string; segments: QuoteSegment[] }
  | { id: string; kind: "row"; label: string; table: string; fields: [string, string][] }
  | { id: string; kind: "rule"; label: string; text: string; meta: string }
  | { id: string; kind: "calc"; label: string; text: string };

/** A number on the evidence card; `ref` is an evidence id, optionally `#mark` to light up a quoted phrase. */
export type MathToken = string | { value: string; ref: string };
export type MathRow = { label: string; tokens: MathToken[]; tone?: "dispute" | "accept" | "plain" };

export type ChargeDetail = {
  id: string;
  title: string;
  detail: string;
  /** Plain-language reason the charge landed where it did. */
  headline: string;
  quoteRef: string;
  math: MathRow[];
  checks: string[];
  gateNote: string;
  comeback: { pushback: string; answer: string } | { none: string };
  evidence: Evidence[];
};
