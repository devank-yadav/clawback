"use client";

// Every run of the agents for this distributor, newest first. Each row is a fact sheet of that run (what the
// distributor kept, what was disputed, what was fair, questions) and opens its own result. Empty until the agents
// have run: no totals are shown that no run produced.

import Link from "next/link";
import { useCallback } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { useFetched } from "@/lib/useFetched";

const STATUS = { started: "Agents working", waiting: "Waiting on you", finished: "Finished", failed: "Stopped" } as const;
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export default function History() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchRuns(account!.id), [account]);
  const runs = useFetched(account ? load : null, account?.id ?? "");
  const evalLoad = useCallback(() => api.fetchEval(), []);
  const score = useFetched(evalLoad);
  const list = runs.data ?? [];

  return (
    <div className="fl">
      <TopBar account={account} active="history" />
      <main className="fl-main hs">
        <header className="ds-head">
          <span className="cx-eyebrow">{account ? `${account.brand.name} · ${cast.distributor}` : " "}</span>
          <h1>{list.length ? `${list.length} run${list.length === 1 ? "" : "s"} of the agents` : "No runs yet"}</h1>
          <p>Every time a payment from {cast.distributor} arrives, the agents run. Open any run to see what each agent did and what it concluded.</p>
        </header>
        {runs.error && <div className="fl-problem" role="alert">{runs.error}</div>}
        {!runs.data && !runs.error && <p className="cx-small cx-muted">Loading…</p>}
        {runs.data && list.length === 0 && (
          <div className="hs-empty">
            <strong>The agents haven’t run for {cast.distributor} yet.</strong>
            <span>Results appear here once a payment has been checked.</span>
            <Link className="cx-btn" href={withAccount("/", account?.id)}>Go to the agents</Link>
          </div>
        )}
        <ol className="hs-list">
          {list.map((r, i) => (
            <li key={r.run_id}>
              <Link className={`hs-row ${r.replaced ? "is-replaced" : ""}`} href={withAccount("/", account?.id, { run: r.run_id })}>
                <span className="hs-when"><strong>{when(r.started_at)}</strong><small>{r.kind} payment{r.invoice_id ? ` · ${r.invoice_id}` : ""}</small></span>
                <span className="hs-facts">
                  {r.taken !== null && <span>Kept <b className="is-amber">{money(r.taken)}</b></span>}
                  {r.disputed !== null && r.disputed > 0 && <span>Disputed <b className="is-dispute">{money(r.disputed)}</b></span>}
                  {r.accepted !== null && r.accepted > 0 && <span>Fair <b className="is-fair">{money(r.accepted)}</b></span>}
                  {r.questions > 0 && <span>{r.questions} question{r.questions === 1 ? "" : "s"}</span>}
                </span>
                <span className={`hs-status is-${r.replaced ? "replaced" : r.status}`}>{r.replaced ? "Replaced by a newer run" : i === 0 && r.status === "waiting" ? "Waiting on you" : STATUS[r.status]}</span>
                <span className="hs-open">Open →</span>
              </Link>
            </li>
          ))}
        </ol>
        {score.data?.status === "done" && (
          <p className="cx-small cx-muted">How accurate are the agents? On a 30-case test set with a key written first: {score.data.correct} of {score.data.cases} correct, {score.data.wrong_automatic} wrong automatic actions. <Link href={withAccount("/results", account?.id)}>Details</Link></p>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
