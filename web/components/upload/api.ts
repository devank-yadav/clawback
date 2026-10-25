// The remittance routes (api/routes/remittance.py). Nothing here computes money.

import { apiUrl, type StartedRun } from "@/lib/api";
import type { RemittanceRead } from "./types";

/** The account whose sample remittance ships with the app (data/samples/remittances). */
export const ACCOUNT = "peak-bar";
export const SAMPLE_PDF = "northmart-march-2026.pdf";

const base = (account: string) => `/accounts/${encodeURIComponent(account)}/remittance`;

/** The API's own words when it refuses (FastAPI's `detail`), else the status. */
async function failure(res: Response, what: string): Promise<Error> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return new Error(body.detail);
  } catch {
    // not JSON
  }
  return new Error(`${what} answered ${res.status}`);
}

/** POST the remittance: a file (PDF, .txt, .csv) or pasted text. One Claude read plus its checks: allow a minute. */
export async function readRemittance(input: { file: File } | { text: string }, account = ACCOUNT): Promise<RemittanceRead> {
  const init: RequestInit =
    "file" in input
      ? { method: "POST", body: (() => { const f = new FormData(); f.append("file", input.file); return f; })() }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: input.text }) };
  const res = await fetch(apiUrl(base(account)), { ...init, credentials: "include", signal: AbortSignal.timeout(90_000) });
  if (!res.ok) throw await failure(res, "Reading the remittance");
  return (await res.json()) as RemittanceRead;
}

/** POST /run: starts a run on exactly the charges this read checked. */
export async function runRemittance(readId: string, account = ACCOUNT): Promise<StartedRun> {
  const res = await fetch(apiUrl(`${base(account)}/run`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ read_id: readId }),
    signal: AbortSignal.timeout(15_000),
  });
  if (!res.ok) throw await failure(res, "Starting the run");
  return (await res.json()) as StartedRun;
}

/** The sample remittance Northmart sent with the March payment (data/samples/remittances/). */
export const sampleUrl = (name = SAMPLE_PDF, account = ACCOUNT) => apiUrl(`${base(account)}/samples/${encodeURIComponent(name)}`);

export async function sampleFile(name = SAMPLE_PDF, account = ACCOUNT): Promise<File> {
  const res = await fetch(sampleUrl(name, account), { credentials: "include", signal: AbortSignal.timeout(15_000) });
  if (!res.ok) throw await failure(res, "The sample");
  return new File([await res.blob()], name, { type: res.headers.get("content-type") ?? "application/pdf" });
}
