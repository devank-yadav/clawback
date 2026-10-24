// Thin client for the FastAPI service (api/routes/). Request and response shapes follow api/contracts.py and the
// account contracts; nothing here computes money. The app always talks to the API: for local work without it,
// `npm run dev:mock` serves the same shapes from web/mock/.

import type {
  Account, Approval, Lookback, AuditEntry, AuditVerify, ChargeDetail, CoachResponse, Dispute, EvalReport, Evidence, LedgerPost,
  Overview, PortalMessage, RunEvent, ScenarioExample, ScenarioRequest, ScenarioResponse, SupplierItem, RunSummary, SavedOverview, DocumentText, TraceStep, TraceSummary,
} from "./types";
import { adminToken } from "./tokens";

/** `/api` behind Caddy on the deployed domain (set at build time by web/Dockerfile); the local API in dev. */
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

export const apiUrl = (path: string) => (/^https?:/.test(path) ? path : `${API_BASE}${path}`);

const TIMEOUT_MS = 15_000;

/** An HTTP answer other than 2xx, with its status (401, 404, 429…) and the API's own `detail` text. */
export class ApiError extends Error {
  constructor(readonly status: number, message: string, readonly detail: string = "") {
    super(message);
  }
}

type CallInit = {
  method?: string;
  body?: unknown;
  timeoutMs?: number;
  /** Send the presenter's admin token if this tab holds one (resets, and the calls limited per visitor). */
  admin?: boolean;
  /** The signed-in role's access code, for the owner's answer and the controller's approval. */
  roleCode?: string | null;
};

async function call<T>(path: string, init?: CallInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (init?.body !== undefined) headers["Content-Type"] = "application/json";
  const admin = init?.admin ? adminToken() : null;
  if (admin) headers.Authorization = `Bearer ${admin}`;
  if (init?.roleCode) headers["X-Clawback-Role-Token"] = init.roleCode;
  const method = init?.method ?? "GET";
  const res = await fetch(apiUrl(path), {
    method,
    headers,
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    signal: AbortSignal.timeout(init?.timeoutMs ?? TIMEOUT_MS),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* no JSON body */
    }
    throw new ApiError(res.status, `${method} ${path.split("?")[0]} answered ${res.status}`, detail);
  }
  return (await res.json()) as T;
}

const q = encodeURIComponent;

/** What every screen says when the API can't be reached. */
export const unreachable = (e: Error) => `Can't reach Clawback right now (${e.message}). Try again in a moment.`;

// ---- Accounts
export const fetchAccounts = () => call<Account[]>("/accounts");
export const fetchSuppliers = () => call<SupplierItem[]>("/suppliers");
export const fetchRuns = (account: string) => call<RunSummary[]>(`/accounts/${q(account)}/runs`);
export const fetchSaved = (account: string) => call<SavedOverview>(`/accounts/${q(account)}/saved`);
export const fetchDocument = (account: string, doc: string) => call<DocumentText>(`/accounts/${q(account)}/documents/${q(doc)}`);
export const setTracked = (supplier: string, accountId: string, tracked: boolean) =>
  call<SupplierItem>(`/suppliers/${q(supplier)}/tracking`, { method: "POST", body: { account_id: accountId, tracked } });
export const fetchOverview = (account: string) => call<Overview>(`/accounts/${q(account)}/overview`);

/** GET /accounts/{id}/lookback, or null when this API doesn't have it yet (404), so the card can hide. */
export async function fetchLookback(account: string): Promise<Lookback | null> {
  try {
    return await call<Lookback>(`/accounts/${q(account)}/lookback`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

// ---- Runs
export type StartedRun = { run_id: string; events_url: string };
export type PaymentStarted = { via: "nessie" | "direct"; deposit_id: string | null; run_id: string | null; message: string };

/** GET /runs/latest?account=: the account's run in progress, or null when none has started (the API answers 404). */
export async function latestRun(account: string): Promise<StartedRun | null> {
  try {
    return await call<StartedRun>(`/runs/latest?account=${q(account)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/** POST /payments/{account}: the "<Distributor> pays" button, the only thing that starts a run. run_id is null until Nessie's deposit is seen. */
export const accountPays = (account: string) => call<PaymentStarted>(`/payments/${q(account)}`, { method: "POST", timeoutMs: 20_000, admin: true });

/** The stream for a run the page already knows the id of. */
export const runRef = (runId: string): StartedRun => ({ run_id: runId, events_url: `/runs/${q(runId)}/events` });

/** Every event a run has so far, read once (no live follow). For screens that need one fact from a run, like its dispute id. */
export async function runEventsOnce(runId: string): Promise<RunEvent[]> {
  const res = await fetch(apiUrl(`/runs/${q(runId)}/events?keepalive=false&delay_ms=0`), { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new ApiError(res.status, `GET /runs/${runId}/events answered ${res.status}`);
  const events: RunEvent[] = [];
  for (const line of (await res.text()).split("\n")) {
    if (!line.startsWith("data:")) continue;
    try {
      events.push(JSON.parse(line.slice(5)) as RunEvent);
    } catch {
      /* skip a malformed frame */
    }
  }
  return events;
}

/** POST /questions/{id}/answer: the owner's reply (owner's access code); the rule and new decisions arrive as events. */
export const answerQuestion = (questionId: string, text: string, roleCode: string | null) =>
  call<unknown>(`/questions/${q(questionId)}/answer`, { method: "POST", body: { text, from_role: "owner" }, roleCode });

/** POST /approvals/{id}: the controller's yes or no (controller's access code). Refusing posts nothing and keeps the note. */
export const decideApproval = (approvalId: string, approve: boolean, note: string | null, roleCode: string | null) =>
  call<{ approval: Approval; ledger_post: LedgerPost | null }>(`/approvals/${q(approvalId)}`, { method: "POST", body: { approve, note }, roleCode });

/** POST /demo/reset. On the deployed site it needs the admin token; a 401 surfaces as ApiError(401) so the screen can ask for it. */
export const resetWorkspace = () => call<unknown>("/demo/reset", { method: "POST", admin: true, timeoutMs: 30_000 });

// ---- Evidence and the decision trace
/** GET /charges/{id}: the evidence behind one row. */
export const fetchChargeDetail = (chargeId: string, runId: string) => call<ChargeDetail>(`/charges/${q(chargeId)}?run_id=${q(runId)}`);

/** GET /evidence/{id}: the sentence, data row, email, rule or person behind one number. */
export const fetchEvidence = (evidenceId: string, runId?: string) =>
  call<Evidence>(`/evidence/${q(evidenceId)}${runId ? `?run_id=${q(runId)}` : ""}`);

/** GET /runs/{id}/trace?charge_id=: every AI call behind one charge, in order. */
export const fetchTrace = (runId: string, chargeId?: string) =>
  call<TraceStep[]>(`/runs/${q(runId)}/trace${chargeId ? `?charge_id=${q(chargeId)}` : ""}`);

/** GET /runs/{id}/trace/summary: calls, tokens, AI time, wall time and cost (when priced) for the whole run. */
export const fetchTraceSummary = (runId: string) => call<TraceSummary>(`/runs/${q(runId)}/trace/summary`);

// ---- The distributor's portal (by dispute id)
export type PortalPreset = { id: string; label: string; text: string; attachment_doc_id: string | null; expect: string; charge_ids: string[] };
/** The dispute's printable packet: every line, its quote, its rows and its math, as one PDF. A plain link, opened in a new tab. */
export const disputePacketUrl = (id: string) => apiUrl(`/portal/disputes/${q(id)}/packet.pdf`);
export const fetchPortalPresets = (account: string, disputeId: string) =>
  call<PortalPreset[]>(`/portal/presets?account=${q(account)}&dispute_id=${q(disputeId)}`);
export const fetchDispute = (id: string) => call<Dispute>(`/portal/disputes/${q(id)}`);
export const fetchPortalMessages = (id: string) => call<PortalMessage[]>(`/portal/disputes/${q(id)}/messages`);
/** Returns the distributor's message and Clawback's reply (only theirs when the reply is held for the owner). */
export const postPortalMessage = (id: string, text: string, attachmentDocId: string | null) =>
  call<PortalMessage[]>(`/portal/disputes/${q(id)}/messages`, { method: "POST", body: { text, attachment_doc_id: attachmentDocId }, timeoutMs: 40_000, admin: true });

// ---- Next month, coach, scenario, accuracy, audit
/** POST /replay/april: next month's charges under the rules saved so far. */
export const replayNextMonth = (account: string) => call<StartedRun>(`/replay/april?account=${q(account)}`, { method: "POST", admin: true });
export const fetchEval = () => call<EvalReport>("/eval/latest");
/** POST /coach: redlines on next season's draft. The model may take a while. */
export const fetchCoach = (account: string) => call<CoachResponse>(`/coach?account=${q(account)}`, { method: "POST", timeoutMs: 40_000, admin: true });
export const fetchScenarioExamples = () => call<ScenarioExample[]>("/scenario/examples");
/** POST /scenario: a pasted clause and charge. Allow up to 30 seconds. */
export const postScenario = (req: ScenarioRequest) => call<ScenarioResponse>("/scenario", { method: "POST", body: req, timeoutMs: 35_000, admin: true });
export const fetchAudit = (account: string) => call<AuditEntry[]>(`/audit?account=${q(account)}`);
export const verifyAudit = () => call<AuditVerify>("/audit/verify");
