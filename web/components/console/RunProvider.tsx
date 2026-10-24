"use client";

// One run for every console screen. The provider sits in the (console) layout, so moving between /home, /review,
// /activity and /approval keeps the same live stream instead of restarting it. It follows the account the URL names
// (?account=, else the first account), the same way the workspace does, and every console link keeps that account.
// Nothing here computes money: amounts and decisions arrive in events (see lib/workspace.ts).

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { firstName, useCurrentAccount, withAccount } from "@/lib/accounts";
import type { Account } from "@/lib/types";
import { useRunEvents } from "@/lib/useRunEvents";
import { selectWorkspace, type WorkspaceView } from "@/lib/workspace";

/** The people and companies of the current account, as the screens name them. The owner is the admin: the one person
 * who answers the questions and approves the credit memos. */
export type Cast = { brand: string; distributor: string; owner: string; ownerFull: string };

type Run = ReturnType<typeof useRunEvents> & {
  view: WorkspaceView;
  account: Account | null;
  accounts: Account[] | null;
  accountsError: string | null;
  cast: Cast;
  /** Always "live": the console reads the real API. Kept for the components that label their data source. */
  source: "live";
  /** A console link that keeps the current account: link("/review", { charge: "C6" }). */
  link: (path: string, extra?: Record<string, string>) => string;
};

const RunContext = createContext<Run | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const { account, accounts, error: accountsError } = useCurrentAccount();
  // ?run=<id> opens that run (a row on History); otherwise the account's newest run.
  const wanted = useSearchParams().get("run");
  const run = useRunEvents(account?.id ?? null, wanted && wanted !== "latest" ? wanted : "latest");
  const view = useMemo(() => selectWorkspace(run.state, account), [run.state, account]);
  const cast = useMemo<Cast>(() => ({
    brand: account?.brand.name ?? "",
    distributor: account?.distributor.name ?? "the distributor",
    owner: account ? firstName(account.brand.owner.name) : "the owner",
    ownerFull: account?.brand.owner.name ?? "the owner",
  }), [account]);
  const link = useCallback((path: string, extra?: Record<string, string>) => withAccount(path, account?.id, extra), [account?.id]);
  const value = useMemo(
    () => ({ ...run, view, account, accounts, accountsError, cast, source: "live" as const, link }),
    [run, view, account, accounts, accountsError, cast, link],
  );
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): Run {
  const run = useContext(RunContext);
  if (!run) throw new Error("useRun must be used inside <RunProvider>");
  return run;
}
