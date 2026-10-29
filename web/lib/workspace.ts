// Turns the folded event state (useRunEvents) into what the workspace screens show.
// Pure reads and wording: every amount and every decision below arrived in an event, none is computed here.

import { codeLabel } from "./accounts";
import { money } from "./format";
import type { Account, Approval, Charge, ChargeDetail, Decision, Evidence, LedgerPost, Question, Remittance, Rule, RunValue, Totals } from "./types";
import type { RunState } from "./useRunEvents";

export type ChargeStatus = "Reviewing" | "Split decision" | "Disputed" | "Accepted" | "Needs your input" | "Can’t verify";

export type ChargeView = {
  id: string;
  ref: string;
  code: string;
  /** "Shortage claim", "Promo allowance": the code in words. */
  kind: string;
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
  /** From the filed dispute's line for this charge: last day to file, and days left. */
  fileBy: string | null;
  daysLeft: number | null;
};

/** owner: waiting on the admin's policy answer. approval: waiting on the admin's yes to the credit memo. posted /
 * refused: the admin answered (or the memo posted on policy or the admin's auto-post rule). */
export type Stage = "checking" | "owner" | "approval" | "posted" | "refused";

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
  /** What the admin's approval actually produced, in words that never overstate it. */
  postingLabel: string;
  postingProblem: string | null;
  disputeLabel: string;
  disputeId: string | null;
  /** On the final totals event, once every charge is decided. */
  value: RunValue | null;
};

const STATUS: Record<Decision["decision"], ChargeStatus> = {
  split: "Split decision",
  dispute: "Disputed",
  accept: "Accepted",
  ask: "Needs your input",
  skip: "Can’t verify",
};

const CHECKING = "Checking this charge against the deal…";

function chargeView(c: Charge, state: RunState): ChargeView {
  const d = state.decisions[c.id];
  const f = state.findings[c.id];
  return {
    id: c.id,
    ref: c.ref,
    code: c.code,
    kind: codeLabel(c.code),
    title: c.description,
    amount: c.amount,
    status: d ? STATUS[d.decision] : "Reviewing",
    reason: d?.reason ?? CHECKING,
    // A rule-decided charge is explained by the rule, not by the earlier "needs a person" finding.
    finding: (d?.rule_id ? d.reason : f?.finding) ?? d?.reason ?? CHECKING,
    accepted: d ? d.accepted : null,
    disputed: d ? d.disputed : null,
    waiting: d ? d.waiting : null,
    ruleId: d?.rule_id ?? null,
    fileBy: null,
    daysLeft: null,
  };
}

function memoPost(ledger: LedgerPost[]) {
  return ledger.find((p) => p.qbo_entity === "credit_memo");
}

/** A ledger post with a "sim-" id was recorded by Clawback but never reached QuickBooks (no connection). */
export const reachedQuickBooks = (p: LedgerPost) => p.status === "posted" && !!p.qbo_id && !p.qbo_id.startsWith("sim-");

function postingLabel(approval: Approval | null, ledger: LedgerPost[]) {
  if (approval?.status === "refused") return "Refused · Not posted";
  if (approval?.status !== "approved") return "Awaiting approval";
  const post = memoPost(ledger);
  if (post && reachedQuickBooks(post)) return "Posted to QuickBooks";
  if (post?.status === "posted") return "Approved · QuickBooks not connected";
  if (post?.status === "failed") return "Posting failed";
  if (post?.status === "held") return "Posting held";
  if (post?.status === "voided") return "Posting voided";
  return "Approved · posting pending";
}

/** One sentence on where the approved entry stands, never claiming more than the ledger post says. */
export function postingSentence(ws: Pick<WorkspaceView, "postingLabel" | "postingProblem">): string {
  if (ws.postingLabel === "Posted to QuickBooks") return "The credit memo is in QuickBooks.";
  if (ws.postingLabel.includes("not connected")) return "QuickBooks isn’t connected on this server, so the entry was recorded here only.";
  if (ws.postingProblem) return `${ws.postingLabel}: ${ws.postingProblem}`;
  return "Waiting for QuickBooks to confirm the entry.";
}

/** Who said yes to the posted memo: the admin, their auto-post rule, or the policy (small memos post on policy). */
export function approvedBy(ws: Pick<WorkspaceView, "approval">, owner: string): string {
  const a = ws.approval;
  if (a?.posted_by_auto_post) return `Posted by ${owner}’s auto-post rule (memos up to ${money(a.posted_by_auto_post.limit)})`;
  if (a?.note?.startsWith("Within policy")) return "Within policy: no approval needed";
  return `Approved by ${owner}`;
}

/** Why the API did not post the credit memo (its note), when it failed or is held. */
export function postingProblem(ledger: LedgerPost[]): string | null {
  const post = memoPost(ledger);
  return post && (post.status === "failed" || post.status === "held") ? (post.note ?? "QuickBooks did not take the entry.") : null;
}

export function selectWorkspace(state: RunState, account: Account | null): WorkspaceView {
  const lines = Object.fromEntries((state.dispute?.lines ?? []).map((l) => [l.charge_id, l]));
  const charges = state.order.map((id) => {
    const c = chargeView(state.charges[id], state);
    const line = lines[id];
    return line ? { ...c, fileBy: line.file_by ?? null, daysLeft: line.days_left ?? null } : c;
  });
  const question = Object.values(state.questions)[0] ?? null;
  const rule = Object.values(state.rules).find((r) => r.status === "active") ?? null;
  const approval = state.approval;
  const remittance = state.run?.remittance ?? null;
  const distributor = account?.distributor.name ?? remittance?.counterparty ?? "the distributor";

  let stage: Stage = "checking";
  if (approval?.status === "approved") stage = "posted";
  else if (approval?.status === "refused") stage = "refused";
  else if (approval || question?.answer) stage = "approval";
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
      const suffix = c?.ruleId ? " · owner policy" : split(l.charge_id) ? " · accepted part" : "";
      return { chargeId: l.charge_id, label: `${c?.title ?? l.charge_id}${suffix}`, amount: l.amount };
    }),
    postingLabel: postingLabel(approval, state.ledger),
    postingProblem: postingProblem(state.ledger),
    // Where the dispute stands, in words (its code stays out of sight; the Disputes page shows it small).
    disputeLabel:
      dispute?.status === "filed" || dispute?.status === "answered"
        ? `Your ${money(dispute.total)} dispute is with ${distributor}`
        : dispute?.status === "ready_to_send" || dispute?.status === "draft"
          ? `Your ${money(dispute.total)} dispute is ready for you to send`
          : dispute?.status === "resolved"
            ? `Your dispute with ${distributor} is settled`
            : dispute
              ? `Your dispute with ${distributor} is closed`
              : "Disputes are filed once every charge is checked",
    disputeId: dispute?.id ?? null,
    value: state.totals?.value ?? null,
  };
}

/** The evidence behind a charge, the deal's own words first (they are what the panel quotes). */
export function orderedEvidence(detail: ChargeDetail | null): Evidence[] {
  const all = detail?.evidence ?? [];
  const lead = (e: Evidence) => (e.kind === "clause" || e.kind === "policy" ? 0 : e.quote ? 1 : 2);
  return [...all].sort((a, b) => lead(a) - lead(b));
}
