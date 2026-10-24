// Thin client for the FastAPI service (api/routes/). Only used when NEXT_PUBLIC_DATA_SOURCE=live.
// Request and response shapes follow api/contracts.py; nothing here computes money.

import type { Approval, ChargeDetail, LedgerPost } from "./types";

/** `/api` behind Caddy on the deployed domain (set at build time by web/Dockerfile); the local API in dev. */
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

export const apiUrl = (path: string) => (/^https?:/.test(path) ? path : `${API_BASE}${path}`);

const TIMEOUT_MS = 15_000;

async function call<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: init?.method ?? "GET",
    headers: init?.body === undefined ? undefined : { "Content-Type": "application/json" },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} answered ${res.status}`);
  return (await res.json()) as T;
}

export type StartedRun = { run_id: string; events_url: string };

/** POST /runs: the pipeline decides whether this is a recorded (DEMO_MODE) or a live run. */
export const startRun = () => call<StartedRun>("/runs", { method: "POST", body: { kind: "march" } });

/** POST /questions/{id}/answer: the owner's reply; the rule and the new decisions arrive on the event stream. */
export const answerQuestion = (questionId: string, text: string) =>
  call<unknown>(`/questions/${encodeURIComponent(questionId)}/answer`, { method: "POST", body: { text, from_role: "owner" } });

/** POST /approvals/{id}: the controller's yes or no. Refusing posts nothing and keeps the note. */
export const decideApproval = (approvalId: string, approve: boolean, note: string | null) =>
  call<{ approval: Approval; ledger_post: LedgerPost | null }>(`/approvals/${encodeURIComponent(approvalId)}`, {
    method: "POST",
    body: { approve, note },
  });

/** POST /demo/reset: reseeds the demo between takes. */
export const resetDemo = () => call<unknown>("/demo/reset", { method: "POST" });

/** GET /charges/{id}: the evidence behind one row. */
export const fetchChargeDetail = (chargeId: string, runId: string) =>
  call<ChargeDetail>(`/charges/${encodeURIComponent(chargeId)}?run_id=${encodeURIComponent(runId)}`);
