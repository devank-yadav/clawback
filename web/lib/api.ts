// Thin client for the FastAPI service (api/routes/). Request and response shapes follow api/contracts.py and the
// account contracts; nothing here computes money. The app always talks to the API: for local work without it,
// `npm run dev:mock` serves the same shapes from web/mock/.

import type {
  Account, Approval, Lookback, AuditEntry, AuditVerify, ChargeDetail, CoachResponse, CompanyOverview, Dispute, DisputeEmail, DisputeThread, SupplierNotification, EvalReport, Evidence, LedgerPost,
  Money, Overview, PortalMessage, Rule, RunEvent, ScenarioExample, ScenarioRequest, ScenarioResponse, SupplierItem, RunSummary, SavedOverview, DocumentText, Connection, ContractLibrary, TraceStep, TraceSummary,
} from "./types";
import { adminToken } from "./tokens";
import { goSignIn } from "./signin-route";

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
};

/** A 401 that means "sign in", not "the presenter's admin token": everything but /auth/* and the demo reset. */
const signInOn401 = (path: string) => !path.startsWith("/auth/") && !path.startsWith("/demo/reset");

async function call<T>(path: string, init?: CallInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (init?.body !== undefined) headers["Content-Type"] = "application/json";
  const admin = init?.admin ? adminToken() : null;
  if (admin) headers.Authorization = `Bearer ${admin}`;
  const method = init?.method ?? "GET";
  // The session is the HttpOnly cookie the API set at sign-in (POST /auth/login); every call carries it.
  const res = await fetch(apiUrl(path), {
    method,
    headers,
    credentials: "include",
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    signal: AbortSignal.timeout(init?.timeoutMs ?? TIMEOUT_MS),
  });
  // Signed out (or the 12-hour session ended): off to /signin, and back here afterwards.
  if (res.status === 401 && signInOn401(path) && !admin) goSignIn("needed");
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

// ---- Sign-in (api/routes/auth.py): an email and password in, the HttpOnly session cookie back
export type SessionUser = { id: string; email: string; name: string; role: string };
export type SessionSupplier = { id: string; name: string; account_ids: string[] };
export type Me = { user: SessionUser | null; supplier: SessionSupplier | null; auth_required: boolean };

/** POST /auth/login: 401 wrong email or password, 429 too many tries, 503 sign-in isn't set up on this server. */
export const login = (email: string, password: string) =>
  call<{ role: string; user: SessionUser; supplier: SessionSupplier }>("/auth/login", { method: "POST", body: { email, password } });

/** POST /auth/logout: always ok; the cookie is gone after it. */
export const logout = () => call<{ ok: boolean }>("/auth/logout", { method: "POST" });

/** GET /auth/me: who is signed in; null when signed out (401). An open laptop answers auth_required false. */
export async function me(): Promise<Me | null> {
  try {
    return await call<Me>("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

// ---- Accounts
export const fetchAccounts = () => call<Account[]>("/accounts");
export const fetchSuppliers = () => call<SupplierItem[]>("/suppliers");
export const fetchConnections = (account?: string) =>
  call<Connection[]>(account ? `/connections?account=${q(account)}` : "/connections");
export const fetchContract = (account: string) => call<ContractLibrary>(`/accounts/${q(account)}/contract`);
export const fetchRuns = (account: string) => call<RunSummary[]>(`/accounts/${q(account)}/runs`);
export const fetchSaved = (account: string) => call<SavedOverview>(`/accounts/${q(account)}/saved`);
/** POST /accounts/{id}/rules/{rule}/undo (admin): the rule stops applying from the next charge on. */
export const undoRule = (account: string, ruleId: string) =>
  call<Rule>(`/accounts/${q(account)}/rules/${q(ruleId)}/undo`, { method: "POST" });
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

/** POST /payments/sync ("Check for new payments", api/contracts.py PaymentSync): one look at the bank and QuickBooks
 * now; each payment found starts its account's run. */
export type FoundPayment = { source: string; account_id: string; distributor: string; amount: Money | null; invoice_id: string | null; run_id: string | null };
export type PaymentSync = { checked: string[]; found: FoundPayment[]; message: string };
export const syncPayments = () => call<PaymentSync>("/payments/sync", { method: "POST", timeoutMs: 30_000 });

/** A payment the distributor sent from its portal, waiting for "Run the agents" (api/contracts.py PendingPayment).
 * The bank's and QuickBooks' pollers start their runs on their own; these wait for the admin. */
export type PendingPayment = { id: string; account_id: string; distributor: string; invoice_id: string; expected: Money; received: Money; source: "portal" | "bank"; received_at: string; run_id?: string | null };
export const fetchPendingPayments = () => call<PendingPayment[]>("/payments/pending");
/** POST /portal/payments/{account}: the distributor's "Send payment" (nothing runs; it waits as received). */
export const sendPortalPayment = (account: string) => call<PendingPayment>(`/portal/payments/${q(account)}`, { method: "POST" });
/** POST /payments/pending/{id}/run: "Run the agents" on a received payment. */
export const runPendingPayment = (id: string) => call<PaymentStarted>(`/payments/pending/${q(id)}/run`, { method: "POST", timeoutMs: 20_000 });

/** POST /payments/{account}: the presenter's deposit; run_id is null until the bank's deposit is seen. */
export const accountPays =(account: string) => call<PaymentStarted>(`/payments/${q(account)}`, { method: "POST", timeoutMs: 20_000, admin: true });

/** The stream for a run the page already knows the id of. */
export const runRef = (runId: string): StartedRun => ({ run_id: runId, events_url: `/runs/${q(runId)}/events` });

/** The HTTP status of one quick read of a run's events (0 when the API can't be reached). The browser's EventSource
 * never says why a stream closed; this tells a run the API no longer has (404) from a restart still in progress. */
export async function runEventsStatus(eventsUrl: string, after: number): Promise<number> {
  try {
    const res = await fetch(apiUrl(`${eventsUrl}${eventsUrl.includes("?") ? "&" : "?"}keepalive=false&delay_ms=0&after=${after}`), { credentials: "include", signal: AbortSignal.timeout(TIMEOUT_MS) });
    void res.body?.cancel().catch(() => undefined);
    return res.status;
  } catch {
    return 0;
  }
}

/** Every event a run has so far, read once (no live follow). For screens that need one fact from a run, like its dispute id. */
export async function runEventsOnce(runId: string): Promise<RunEvent[]> {
  const res = await fetch(apiUrl(`/runs/${q(runId)}/events?keepalive=false&delay_ms=0`), { credentials: "include", signal: AbortSignal.timeout(TIMEOUT_MS) });
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

/** POST /questions/{id}/answer: the admin's reply (the signed-in session); the rule and new decisions arrive as events.
 * saveRule false settles this charge only: no rule is saved, so the next charge like it asks again. */
export const answerQuestion = (questionId: string, text: string, saveRule = true) =>
  call<{ answer: unknown; rule: Rule | null }>(`/questions/${q(questionId)}/answer`, { method: "POST", body: { text, from_role: "owner", save_rule: saveRule } });

/** POST /approvals/{id}: the admin's yes or no (the signed-in session). Refusing posts nothing and keeps the note.
 * autoPost with a yes: fair-charge memos up to this one's amount post without asking from now on. */
export const decideApproval = (approvalId: string, approve: boolean, note: string | null, autoPost = false) =>
  call<{ approval: Approval; ledger_post: LedgerPost | null }>(`/approvals/${q(approvalId)}`, { method: "POST", body: { approve, note, auto_post: autoPost } });

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

// ---- Dispute email (api/routes/dispute_mail.py): review and send, the thread, the Negotiator's reply drafts
const runQ = (runId: string | null | undefined) => (runId ? `?run_id=${q(runId)}` : "");
/** GET /disputes?account=: every dispute this account's runs filed (the newest version of each), newest run first. */
export const fetchDisputes = (account: string) => call<DisputeThread[]>(`/disputes?account=${q(account)}`);
export const fetchDisputeThread = (id: string, runId?: string | null) => call<DisputeThread>(`/disputes/${q(id)}/thread${runQ(runId)}`);
/** GET /disputes/{id}/email: the dispute's email, drafted on the first look. The model may take a while. */
export const fetchDisputeEmail = (id: string, runId?: string | null) => call<DisputeEmail>(`/disputes/${q(id)}/email${runQ(runId)}`, { timeoutMs: 45_000 });
/** PUT /disputes/{id}/email (admin): saved as ready, or held with problems[] when the outbound filter blocks it. */
export const saveDisputeEmail = (id: string, runId: string | null | undefined, subject: string, body: string) =>
  call<DisputeEmail>(`/disputes/${q(id)}/email${runQ(runId)}`, { method: "PUT", body: { subject, body } });
export const redraftDisputeEmail = (id: string, runId?: string | null) =>
  call<DisputeEmail>(`/disputes/${q(id)}/email/redraft${runQ(runId)}`, { method: "POST", timeoutMs: 45_000 });
/** POST /disputes/{id}/send (admin): emails it with its packet and files it. 409 when held or already sent. */
export const sendDispute = (id: string, runId: string | null | undefined, subject: string, body: string) =>
  call<{ dispute: Dispute; email: DisputeEmail }>(`/disputes/${q(id)}/send${runQ(runId)}`, { method: "POST", body: { subject, body }, timeoutMs: 30_000 });
/** POST /disputes/{id}/replies/{email_id}/send (admin): sends the Negotiator's drafted answer, optionally edited. */
export const sendDisputeReply = (id: string, emailId: string, runId: string | null | undefined, subject: string, body: string) =>
  call<DisputeEmail>(`/disputes/${q(id)}/replies/${q(emailId)}/send${runQ(runId)}`, { method: "POST", body: { subject, body }, timeoutMs: 30_000 });
/** POST /disputes/{id}/replies (admin): the admin's own answer when no drafted one waits. Sent if it passes the
 * outbound filter; held with the problems if not (it then shows as a draft to fix and send). */
export const writeDisputeReply = (id: string, runId: string | null | undefined, text: string) =>
  call<DisputeEmail>(`/disputes/${q(id)}/replies${runQ(runId)}`, { method: "POST", body: { text }, timeoutMs: 30_000 });
export const fetchNotifications = () => call<SupplierNotification[]>("/notifications");


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
/** GET /overview: the signed-in supplier across all its distributors (Home). */
export const fetchCompanyOverview = () => call<CompanyOverview>("/overview");
/** GET /audit?run_id=: one run's entries (the run's audit drawer). */
export const fetchRunAudit = (runId: string) => call<AuditEntry[]>(`/audit?run_id=${q(runId)}`);
export const verifyAudit = () => call<AuditVerify>("/audit/verify");

/** The owner's Settings (api/autopilot.py): what the agents may do without asking, and the weekly summary. */
export type Autopilot = {
  run_on_arrival: boolean;
  send_disputes_under: Money | null;
  post_fair_under: Money | null;
  digest_email: string | null;
  digest_weekly: boolean;
  digest_last_sent: string | null;
  updated_by: string | null;
  updated_at: string | null;
};
type Clearable = "send_disputes_under" | "post_fair_under" | "digest_email";
export type AutopilotChange = Partial<Pick<Autopilot, "run_on_arrival" | "send_disputes_under" | "post_fair_under" | "digest_email" | "digest_weekly">> & { clear?: Clearable[] };
export const fetchAutopilot = () => call<Autopilot>("/settings/autopilot");
export const saveAutopilot = (change: AutopilotChange) => call<Autopilot>("/settings/autopilot", { method: "PUT", body: change });

/** The weekly summary (api/digest.py), and sending it now. */
export type DigestItem = { title: string; distributor: string; amount: number | null; level: string; actions: { label: string; url: string }[]; open_url: string };
export type Digest = { to: string | null; subject: string; text: string; html: string; items: DigestItem[] };
export type DigestSent = { status: "sent" | "not_sent"; to: string | null; detail: string; subject: string };
export const previewDigest = () => call<Digest>("/digest/preview");
export const sendDigest = () => call<DigestSent>("/digest/send", { method: "POST" });
