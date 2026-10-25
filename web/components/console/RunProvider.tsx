"use client";

// The run on `/` and the distributors page. The provider sits in the (console) layout and follows the account the URL
// names (?account=, else the first account), the same way the other pages do; every link it makes keeps that account.
// Nothing here computes money: amounts and decisions arrive in events (see lib/workspace.ts).

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { firstName, useCurrentAccount, withAccount } from "@/lib/accounts";
import type { Account } from "@/lib/types";
import { useRunEvents } from "@/lib/useRunEvents";
import { selectWorkspace, type WorkspaceView } from "@/lib/workspace";

/** The people and companies of the current account, as the screens name them. */
export type Cast = { brand: string; distributor: string; owner: string; ownerFull: string; controller: string; controllerFull: string };

type Run = ReturnType<typeof useRunEvents> & {
  view: WorkspaceView;
  account: Account | null;
  accounts: Account[] | null;
  accountsError: string | null;
  cast: Cast;
  /** Always "live": the console reads the real API. Kept for the components that label their data source. */
  source: "live";
  /** A console link that keeps the current account: link("/charges", { charge: "C6" }). */
  link: (path: string, extra?: Record<string, string>) => string;
};

const RunContext = createContext<Run | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const { account, accounts, error: accountsError } = useCurrentAccount();
  // ?run=<id> opens that run (a row in the Overview's past runs); otherwise the account's newest run.
  const wanted = useSearchParams().get("run");
  const run = useRunEvents(account?.id ?? null, wanted && wanted !== "latest" ? wanted : "latest");
  const view = useMemo(() => selectWorkspace(run.state, account), [run.state, account]);
  const cast = useMemo<Cast>(() => ({
    brand: account?.brand.name ?? "",
    distributor: account?.distributor.name ?? "the distributor",
    owner: account ? firstName(account.brand.owner.name) : "the owner",
    ownerFull: account?.brand.owner.name ?? "the owner",
    controller: account ? firstName(account.brand.controller.name) : "the controller",
    controllerFull: account?.brand.controller.name ?? "the controller",
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
