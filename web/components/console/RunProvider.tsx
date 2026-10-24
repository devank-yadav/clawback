"use client";

// One run for every console screen. The provider sits in the (console) layout, so moving between
// /home, /review, /activity and /approval keeps the same replay or live stream instead of restarting it.
// Nothing here computes money: amounts and decisions arrive in events (see lib/workspace.ts).

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useRunEvents } from "@/lib/useRunEvents";
import { selectWorkspace, type WorkspaceView } from "@/lib/workspace";

type Run = ReturnType<typeof useRunEvents> & { view: WorkspaceView };

const RunContext = createContext<Run | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const run = useRunEvents("demo");
  const view = useMemo(() => selectWorkspace(run.state, run.source), [run.state, run.source]);
  const value = useMemo(() => ({ ...run, view }), [run, view]);
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): Run {
  const run = useContext(RunContext);
  if (!run) throw new Error("useRun must be used inside <RunProvider>");
  return run;
}
