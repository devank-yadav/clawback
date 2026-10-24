"use client";

// The brand accounts (GET /accounts) and which one the URL names (?account=). Every screen reads its account here,
// so names, initials and colors always come from the API, never from the code.

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import * as api from "./api";
import type { Account } from "./types";

let cache: Promise<Account[]> | null = null;

function load(force = false): Promise<Account[]> {
  if (!cache || force) {
    cache = api.fetchAccounts();
    cache.catch(() => (cache = null)); // a failed load is retried on the next mount
  }
  return cache;
}

export type AccountsState = { accounts: Account[] | null; error: string | null; reload: () => void };

/** All accounts, fetched once per page load and shared by every component. */
export function useAccounts(): AccountsState {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load(n > 0).then(
      (list) => {
        if (cancelled) return;
        setAccounts(list);
        setError(null);
      },
      (e: Error) => !cancelled && setError(api.unreachable(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [n]);

  const reload = useCallback(() => setN((v) => v + 1), []);
  return { accounts, error, reload };
}

/** The account the URL names; the first account when the URL names none (or one that doesn't exist). */
export function useCurrentAccount(): AccountsState & { account: Account | null; requested: string | null } {
  const state = useAccounts();
  const requested = useSearchParams().get("account");
  const account = state.accounts?.find((a) => a.id === requested) ?? state.accounts?.[0] ?? null;
  return { ...state, account, requested };
}

/** A link that keeps the account: withAccount("/results", "peak-bar") → "/results?account=peak-bar". */
export function withAccount(path: string, accountId: string | null | undefined, extra?: Record<string, string>): string {
  const params = new URLSearchParams();
  if (accountId) params.set("account", accountId);
  for (const [k, v] of Object.entries(extra ?? {})) params.set(k, v);
  const s = params.toString();
  return s ? `${path}?${s}` : path;
}

/** Readable names for the remittance codes a distributor uses. Unknown codes show as they arrive. */
export const CODE_LABEL: Record<string, string> = {
  PA: "Promo allowance",
  DF: "Display fee",
  SH: "Shortage claim",
  PR: "Pricing deduction",
  SP: "Spoilage",
};

export const codeLabel = (code: string | null | undefined) => (code ? (CODE_LABEL[code] ?? code) : "Deduction");

/** Black or white text, whichever reads on a brand color. Presentation only. */
export function inkOn(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return "#fff";
  const n = parseInt(m[1], 16);
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const l = 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  return l > 0.4 ? "#1f1f23" : "#fff";
}

/** First name, for short copy ("Only Dana can approve"). */
export const firstName = (full: string) => full.split(" ")[0] ?? full;
