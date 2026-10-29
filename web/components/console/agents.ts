// The six agents behind one charge, in the order they work, built only from what the run has streamed so far.
// A step is "done" when its event has arrived (a finding, a decision, a rehearsal); until then it is "waiting".
// Wording only: every number shown is text the API already sent (finding.math, decision.reason).

import type { ChargeDetail, Evidence } from "@/lib/types";
import type { RunState } from "@/lib/useRunEvents";

export type AgentKind = "AI" | "CODE" | "RULE";
export type StepState = "done" | "waiting" | "person";

export type AgentStep = {
  agent: string;
  kind: AgentKind;
  state: StepState;
  /** One plain sentence: what this agent concluded. */
  result: string;
  /** Short labels of the sources this step relied on. */
  evidence: string[];
  /** Time the step's event arrived, when the stream carries one. */
  at: string | null;
  /** Extra lines (the calculator's arithmetic). */
  detail?: string[];
};

const label = (e: Evidence) => e.label;

/** The clause a charge's decision rests on: the one its dispute line names (a cap charge cites §3.2, not the rate's
 * §3.1), else the first the finding cites, else the first in the evidence. The others stay listed as evidence. */
export function mainClause(chargeId: string, state: Pick<RunState, "dispute" | "findings">, evidence: Evidence[]): Evidence | null {
  const clauses = evidence.filter((e) => e.kind === "clause");
  const ref = state.dispute?.lines.find((l) => l.charge_id === chargeId)?.clause_ref;
  const cited = state.findings[chargeId]?.evidence_ids ?? [];
  return (ref ? clauses.find((c) => c.label.includes(ref)) : undefined)
    ?? clauses.find((c) => cited.includes(c.id))
    ?? clauses[0] ?? null;
}

export function agentSteps(chargeId: string, state: RunState, detail: ChargeDetail | null): AgentStep[] {
  const finding = state.findings[chargeId] ?? null;
  const decision = state.decisions[chargeId] ?? null;
  const rehearsal = state.rehearsals[chargeId] ?? null;
  const question = Object.values(state.questions).find((q) => q.charge_id === chargeId) ?? null;
  const rule = decision?.rule_id ? (state.rules[decision.rule_id] ?? null) : null;
  const evidence = detail?.evidence ?? [];
  const main = mainClause(chargeId, state, evidence);
  const clauses = [...(main ? [main] : []), ...evidence.filter((e) => e.kind === "clause" && e !== main)];
  const sources = evidence.filter((e) => e.kind !== "clause" && e.kind !== "charge");
  const lines = state.feed.filter((l) => l.charge_id === chargeId);
  const readerLine = state.feed.find((l) => l.actor === "reader") ?? null;
  const at = (actor: string) => lines.find((l) => l.actor === actor)?.at ?? null;
  const read = !!finding;

  const steps: AgentStep[] = [
    {
      agent: "Contract reader",
      kind: "AI",
      state: read ? "done" : "waiting",
      result: read
        ? clauses[0]
          ? `Found the clause that governs this charge: ${clauses[0].label}.`
          : "Read the signed deal for the terms behind this charge."
        : "Reading the signed deal…",
      evidence: clauses.map(label),
      at: readerLine?.at ?? null,
    },
    {
      agent: "Second reader",
      kind: "AI",
      state: read ? "done" : "waiting",
      result: !read
        ? "Reading the same deal on its own…"
        : finding.readers_agree
          ? "Read the deal independently and agrees with the first reader."
          : "Read the clause differently from the first reader, so no agent decides alone.",
      evidence: clauses.slice(0, 1).map(label),
      at: readerLine?.at ?? null,
    },
    {
      agent: "Investigator",
      kind: "AI",
      state: read ? "done" : "waiting",
      result: finding?.finding ?? "Matching sales, emails and past payments to this charge…",
      evidence: sources.map(label),
      at: at("investigator"),
    },
    {
      agent: "Calculator",
      kind: "CODE",
      state: read ? "done" : "waiting",
      result: !read
        ? "Waiting for the facts before doing any math."
        : finding.math.length
          ? "Ran the arithmetic in tested code. No AI does math."
          : "No arithmetic needed for this charge.",
      evidence: [],
      at: at("investigator"),
      // The parts are fragments of sentences; where one sentence ends and the next starts ("period.Cap"), add the
      // space. A period after a letter only, so "$1.00" stays as it is.
      detail: finding?.math.length ? [finding.math.map((m) => m.text).join("").replace(/(?<=[a-z)\]])\.(?=[A-Z0-9])/g, ". ")] : undefined,
    },
    {
      agent: "Policy check",
      kind: "RULE",
      state: decision ? "done" : question && !question.answer ? "person" : "waiting",
      result: decision
        ? rule
          ? (decision.reason.includes(rule.label) ? decision.reason : `${decision.reason} (${rule.label})`)
          : decision.reason
        : question && !question.answer
          ? "The deal leaves this to judgment, so the owner decides. One question, asked once."
          : "Waiting for the investigation.",
      evidence: rule ? [rule.label] : [],
      at: decision?.decided_at ?? question?.sent_at ?? null,
    },
    {
      agent: "Negotiator",
      kind: "AI",
      state: rehearsal ? "done" : decision ? "done" : "waiting",
      result: rehearsal
        ? `Expects the distributor to say: “${rehearsal.predicted_rebuttal}” Answer ready: ${rehearsal.answer}`
        : decision?.decision === "accept"
          ? "Nothing to dispute. Clawback doesn’t fight a fair charge."
          : decision?.decision === "ask"
            ? "Holds any dispute until the owner answers."
            : decision
              ? "Prepares the dispute line with the clause and data attached."
              : "Waiting for a decision.",
      evidence: rehearsal ? evidence.filter((e) => rehearsal.answer_evidence_ids.includes(e.id)).map(label) : [],
      at: at("negotiator"),
    },
  ];
  return steps;
}

export const doneCount = (steps: AgentStep[]) => steps.filter((s) => s.state === "done").length;
