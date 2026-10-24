"use client";

// Who is signed in to the workspace: the brand's owner (answers policy questions) or its controller (approves
// accounting entries). On the deployed site each role has an access code (OWNER_TOKEN / CONTROLLER_TOKEN on the API);
// a local API has none, so the code may be left empty. Also the prompts that ask for a code or the admin token.

import { useSyncExternalStore } from "react";
import { ApiError } from "./api";
import { setAdminToken } from "./tokens";

export type Role = "owner" | "controller";

export type Prompt =
  | { kind: "role"; role: Role; reason: string | null; then: (() => void) | null }
  | { kind: "admin"; reason: string; then: (() => void) | null };

export type Session = { role: Role | null; code: string | null; prompt: Prompt | null };

const KEY = "clawback-session";
const SERVER: Session = { role: null, code: null, prompt: null };
let state: Session = SERVER;
let loaded = false;
const listeners = new Set<() => void>();

function snapshot(): Session {
  if (!loaded && typeof window !== "undefined") {
    loaded = true;
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(KEY) ?? "null");
      if (saved?.role === "owner" || saved?.role === "controller") state = { ...state, role: saved.role, code: typeof saved.code === "string" ? saved.code : null };
    } catch {
      /* nothing saved, or storage blocked */
    }
  }
  return state;
}

function emit(next: Partial<Session>) {
  state = { ...snapshot(), ...next };
  listeners.forEach((l) => l());
}

export function useSession(): Session {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    snapshot,
    () => SERVER,
  );
}

export function signIn(role: Role, code: string | null) {
  const then = state.prompt?.then ?? null;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify({ role, code }));
  } catch {
    /* kept in memory only */
  }
  emit({ role, code: code || null, prompt: null });
  then?.();
}

export function signOut() {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
  emit({ role: null, code: null, prompt: null });
}

export const askSignIn = (role: Role, reason: string | null = null, then: (() => void) | null = null) => emit({ prompt: { kind: "role", role, reason, then } });
export const askAdminToken = (reason: string, then: (() => void) | null = null) => emit({ prompt: { kind: "admin", reason, then } });
export const closePrompt = () => emit({ prompt: null });

/** The presenter typed the admin token: keep it for the tab and carry on with what needed it. */
export function submitAdminToken(token: string) {
  const then = state.prompt?.then ?? null;
  setAdminToken(token);
  emit({ prompt: null });
  then?.();
}

const REFUSED: Record<Role, string> = {
  owner: "Only the owner can answer this. Enter the owner’s access code.",
  controller: "Only the controller can approve this. Enter the controller’s access code.",
};

/**
 * Runs an action that only one role may take: asks that role to sign in first when someone else is signed in,
 * and asks again when the server refuses the code (401).
 */
export function asRole(role: Role, action: (code: string | null) => Promise<unknown>, onError: (e: Error) => void) {
  const run = () => {
    action(snapshot().code).catch((e: Error) => {
      if (e instanceof ApiError && e.status === 401) askSignIn(role, REFUSED[role], run);
      else onError(e);
    });
  };
  if (snapshot().role !== role) askSignIn(role, null, run);
  else run();
}

/** The friendly words for a 429 from the site's per-visitor limit, or null for any other error. */
export function limitMessage(e: unknown): string | null {
  if (!(e instanceof ApiError) || e.status !== 429) return null;
  return e.detail || "That’s the limit for now: each analysis runs live AI. Try again in a few minutes.";
}

export const LIMIT_ADMIN_REASON = "Presenting? The admin token lifts the per-visitor limit for this browser tab.";
