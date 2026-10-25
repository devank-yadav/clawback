"use client";

// Who is signed in: GET /auth/me, read once per page load and shared by every component. The session itself is the
// API's HttpOnly cookie (POST /auth/login sets it, POST /auth/logout ends it); this code never sees a password or a
// code. Signing in happens on /signin only: any call the API answers 401 sends the visitor there and back
// (lib/api.ts). Also the one prompt left in the app, the presenter's admin token (demo reset, per-visitor limits).

import { useSyncExternalStore } from "react";
import * as api from "./api";
import { ApiError } from "./api";
import { setAdminToken } from "./tokens";

/** The one role in the app: the supplier's admin, who answers the questions and approves the credit memos. */
export type Role = "owner";

export type Prompt ={ kind: "admin"; reason: string; then: (() => void) | null };

export type Session = {
  /** loading: not asked yet · in: a user is signed in · out: signed out on a site that needs sign-in ·
   * open: a laptop with no passwords, where nobody needs to sign in · unknown: the API couldn't be reached. */
  status: "loading" | "in" | "out" | "open" | "unknown";
  user: api.SessionUser | null;
  supplier: api.SessionSupplier | null;
  prompt: Prompt | null;
};

const SERVER: Session = { status: "loading", user: null, supplier: null, prompt: null };
let state: Session = SERVER;
let asked = false;
const listeners = new Set<() => void>();

function emit(next: Partial<Session>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

/** Asks the API who is signed in (again, after a sign-in or sign-out). */
export function refreshSession(): Promise<void> {
  asked = true;
  return api.me().then(
    (me) => {
      if (!me) emit({ status: "out", user: null, supplier: null });
      else if (me.user) emit({ status: "in", user: me.user, supplier: me.supplier });
      else emit({ status: me.auth_required ? "out" : "open", user: null, supplier: null });
    },
    () => emit({ status: "unknown" }),
  );
}

export function useSession(): Session {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      if (!asked) void refreshSession();
      return () => listeners.delete(cb);
    },
    () => state,
    () => SERVER,
  );
}

/** Signs in with an email and password; the API sets the cookie. Throws ApiError (401, 429, 503) for the form. */
export async function signIn(email: string, password: string) {
  const r = await api.login(email, password);
  emit({ status: "in", user: r.user, supplier: r.supplier });
}

/** Ends the session on the API; the caller then leaves the app (the landing page). */
export async function signOut() {
  try {
    await api.logout();
  } catch {
    /* the cookie may already be gone; leave anyway */
  }
  emit({ status: "out", user: null, supplier: null });
}

export const askAdminToken = (reason: string, then: (() => void) | null = null) => emit({ prompt: { kind: "admin", reason, then } });
export const closePrompt = () => emit({ prompt: null });

/** The presenter typed the admin token: keep it for the tab and carry on with what needed it. */
export function submitAdminToken(token: string) {
  const then = state.prompt?.then ?? null;
  setAdminToken(token);
  emit({ prompt: null });
  then?.();
}

/**
 * Runs an action only the signed-in admin may take (an answer, an approval). Signed out, the API answers 401 and the
 * visitor goes to /signin and back (lib/api.ts); any other failure goes to onError.
 */
export function asAdmin(action: () => Promise<unknown>, onError: (e: Error) => void) {
  action().catch((e: Error) => {
    if (!(e instanceof ApiError && e.status === 401)) onError(e);
  });
}

/** The friendly words for a 429 from the site's per-visitor limit, or null for any other error. */
export function limitMessage(e: unknown): string | null {
  if (!(e instanceof ApiError) || e.status !== 429) return null;
  return e.detail || "That’s the limit for now: each analysis runs live AI. Try again in a few minutes.";
}

export const LIMIT_ADMIN_REASON = "Presenting? The admin token lifts the per-visitor limit for this browser tab.";
