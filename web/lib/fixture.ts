// Replays Devank's recorded runs from web/fixtures/ until the live stream (card R7) is wired up.
// Approve and refuse share every event up to the controller's reply, then branch.

import refusalJson from "@/fixtures/refusal-events.json";
import runJson from "@/fixtures/run-events.json";
import type { ChargeDetail, Evidence, RunEvent, RunFixture } from "./types";

const RUN = runJson as unknown as RunFixture;
const REFUSAL = refusalJson as unknown as RunFixture;

export const FIXTURE_RUN_ID = RUN.run_id;

/** Events after `lastId` in the branch the controller chose. */
export function eventsAfter(lastId: number, branch: "approved" | "refused" = "approved"): RunEvent[] {
  const src = branch === "refused" ? REFUSAL : RUN;
  return src.events.filter((e) => e.id > lastId);
}

/**
 * Where the recorded run stops to wait for a person: the owner's answer, or the controller's reply.
 * Live, the stream simply goes quiet at these points until someone acts.
 */
export function waitsForPerson(e: RunEvent): boolean {
  return e.type === "answer" || (e.type === "approval" && e.data.status !== "pending");
}

/** The owner's recorded reply, offered as the one-tap answer in the prototype. */
export function recordedAnswer(questionId: string): string | null {
  const e = RUN.events.find((x) => x.type === "answer" && x.data.question_id === questionId);
  return e && e.type === "answer" ? e.data.text : null;
}

/** Stand-in for GET /charges/{id}. */
export function chargeDetail(id: string): ChargeDetail | null {
  return RUN.charges[id] ?? null;
}

/** Stand-in for GET /evidence/{id}. */
export function evidence(id: string): Evidence | null {
  return RUN.evidence[id] ?? null;
}

/** Replay delay: the recorded gap, sped up so the board fills in a few seconds. */
export function replayDelay(prev: RunEvent | undefined, next: RunEvent): number {
  if (!prev) return 120;
  const gap = Date.parse(next.at) - Date.parse(prev.at);
  return Math.min(Math.max(gap * 0.1, 40), 420);
}
