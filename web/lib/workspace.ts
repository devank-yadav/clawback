// Turns the folded event state (useRunEvents) into what the workspace screens show.
// Pure reads and wording: every amount and every decision below arrived in an event, none is computed here.

import type { Approval, Charge, ChargeDetail, Decision, Evidence, LedgerPost, Question, Remittance, Rule, Totals } from "./types";
import type { DataSource, RunState } from "./useRunEvents";

export type ChargeStatus = "Reviewing" | "Split decision" | "Disputed" | "Accepted" | "Needs your input" | "Can’t verify";

export type ChargeView = {
  id: string;
  ref: string;
  title: string;
  amount: number;
  status: ChargeStatus;
  /** One line under the charge name: the gate's own reason. */
  reason: string;
  finding: string;
  /** null until the decision arrives; the amounts come straight from the decision event. */
  accepted: number | null;
  disputed: number | null;
  waiting: number | null;
  ruleId: string | null;
};

/** owner: waiting on Dana's policy answer. controller: waiting on Sam. posted / refused: Sam has answered. */
export type Stage = "checking" | "owner" | "controller" | "posted" | "refused";

export type ProposalLine = { chargeId: string; label: string; amount: number };

export type WorkspaceView = {
  remittance: Remittance | null;
  charges: ChargeView[];
  totals: Totals | null;
  /** Every charge has a decision (the stream is past the checking phase). */
  reviewed: boolean;
  stage: Stage;
  question: Question | null;
  rule: Rule | null;
  /** Charges decided by the saved rule, for the Rules screen. */
  ruleCharges: ChargeView[];
  approval: Approval | null;
  proposalLines: ProposalLine[];
  /** What the controller's approval actually produced, in words that never overstate it. */
  postingLabel: string;
  postingProblem: string | null;
  disputeLabel: string;
};

const STATUS: Record<Decision["decision"], ChargeStatus> = {
  split: "Split decision",
  dispute: "Disputed",
  accept: "Accepted",
  ask: "Needs your input",
  skip: "Can’t verify",
};

function chargeView(c: Charge, state: RunState): ChargeView {
  const d = state.decisions[c.id];
  const f = state.findings[c.id];
  return {
    id: c.id,
    ref: c.ref,
    title: c.description,
    amount: c.amount,
    status: d ? STATUS[d.decision] : "Reviewing",
    reason: d?.reason ?? "Checking this charge against the deal…",
    // A rule-decided charge is explained by the rule, not by the earlier "needs a person" finding.
    finding: (d?.rule_id ? d.reason : f?.finding) ?? d?.reason ?? "Checking this charge against the deal…",
    accepted: d ? d.accepted : null,
    disputed: d ? d.disputed : null,
    waiting: d ? d.waiting : null,
    ruleId: d?.rule_id ?? null,
  };
}

function memoPost(ledger: LedgerPost[]) {
  return ledger.find((p) => p.qbo_entity === "credit_memo");
}

function postingLabel(approval: Approval | null, ledger: LedgerPost[], source: DataSource) {
  if (approval?.status === "refused") return "Refused · Unposted";
  if (approval?.status !== "approved") return "Awaiting approval";
  const post = memoPost(ledger);
  if (post?.status === "posted" && source === "live" && post.qbo_id && !post.qbo_id.startsWith("sim-")) return "Posted · QuickBooks sandbox";
  if (post?.status === "posted") return "Simulated posted";
  if (post?.status === "failed") return "Posting failed";
  if (post?.status === "held") return "Posting held";
  if (post?.status === "voided") return "Posting voided";
  return "Approved · posting pending";
}

/** Why the API did not post the credit memo (its note), when it failed or is held. */
export function postingProblem(ledger: LedgerPost[]): string | null {
  const post = memoPost(ledger);
  return post && (post.status === "failed" || post.status === "held") ? (post.note ?? "QuickBooks did not take the entry.") : null;
}

export function selectWorkspace(state: RunState, source: DataSource): WorkspaceView {
  const charges = state.order.map((id) => chargeView(state.charges[id], state));
  const question = Object.values(state.questions)[0] ?? null;
  const rule = Object.values(state.rules).find((r) => r.status === "active") ?? null;
  const approval = state.approval;
  const remittance = state.run?.remittance ?? null;

  let stage: Stage = "checking";
  if (approval?.status === "approved") stage = "posted";
  else if (approval?.status === "refused") stage = "refused";
  else if (approval || question?.answer) stage = "controller";
  else if (question) stage = "owner";

  const byId = Object.fromEntries(charges.map((c) => [c.id, c]));
  const split = (id: string) => byId[id]?.status === "Split decision";
  const dispute = state.dispute;
  return {
    remittance,
    charges,
    totals: state.totals,
    reviewed: !!remittance && charges.length >= remittance.charge_count && charges.every((c) => c.status !== "Reviewing"),
    stage,
    question,
    rule,
    ruleCharges: rule ? charges.filter((c) => c.ruleId === rule.id) : [],
    approval,
    proposalLines: (approval?.lines ?? []).map((l) => {
      const c = byId[l.charge_id];
      const suffix = c?.ruleId ? " · owner-approved policy" : split(l.charge_id) ? " · accepted allocation" : "";
      return { chargeId: l.charge_id, label: `${c?.title ?? l.charge_id}${suffix}`, amount: l.amount };
    }),
    postingLabel: postingLabel(approval, state.ledger, source),
    postingProblem: postingProblem(state.ledger),
    // Filing is the Negotiator's job and happens on the API; a fixture replay never files anything.
    disputeLabel:
      source === "live" && dispute?.status === "filed"
        ? `Dispute ${dispute.id} filed on the mock Northmart portal`
        : "Disputes proposed · Not filed",
  };
}

/** The evidence rows behind a charge, the deal clause first (it is the sentence the drawer quotes). */
export function evidenceRows(detail: ChargeDetail | null): { id: string; label: string; summary: string; text: string; kind: Evidence["kind"] }[] {
  const all = detail?.evidence ?? [];
  const ordered = [...all.filter((e) => e.kind === "clause"), ...all.filter((e) => e.kind !== "clause")];
  return ordered.map((e) => ({
    id: e.id,
    label: e.label,
    summary: e.summary,
    text: e.quote?.text ?? e.summary,
    kind: e.kind,
  }));
}
