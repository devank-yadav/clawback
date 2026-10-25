"use client";

// Every run of the agents for this distributor, newest first. Each row is a fact sheet of that run (what the
// distributor kept, what was disputed, what was fair, questions) and opens its own result. Empty until the agents
// have run: no totals are shown that no run produced.

import Link from "next/link";
import { useCallback } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar, { DistributorMark } from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { useFetched } from "@/lib/useFetched";

const STATUS = { started: "Agents working", waiting: "Waiting on you", finished: "Finished", failed: "Stopped" } as const;
const TONE = { started: "is-live", waiting: "is-amber", finished: "is-green", failed: "is-red" } as const;
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
      <main className="fl-main bp bp-hs">
        <PageHeader title="History" line={`Every payment from ${cast.distributor} the agents checked. Open a run to see what each agent did.`} />
        {runs.error && <div className="fl-problem" role="alert">{runs.error}</div>}

        {runs.data && list.length === 0 ? (
          <EmptyState
            title={`The agents haven’t run for ${cast.distributor} yet.`}
            line="Results appear here once a payment has been checked."
            action={<Link className="cx-btn" href={withAccount("/", account?.id)}>Go to the agents</Link>}
          />
        ) : (
          <div className="bw-stage">
            <section className="bp-frame" aria-label="Runs of the agents">
              <div className="bp-frame-bar"><span className="bp-tab">Runs <b>{runs.data ? list.length : "–"}</b></span></div>
              <div className="bp-thead" aria-hidden="true"><span>Date</span><span>Distributor</span><span>Result</span><span>Status</span><span /></div>
              {!runs.data && !runs.error && [0, 1, 2].map((i) => <div key={i} className="bp-skel" aria-hidden="true"><i /><i /><i /><i /><i /></div>)}
              <ol className="bp-rows">
                {list.map((r, i) => (
                  <li key={r.run_id}>
                    <Link className={`bp-row ${r.replaced ? "is-replaced" : ""}`} href={withAccount("/", account?.id, { run: r.run_id })}>
                      <span className="bp-when"><strong>{when(r.started_at)}</strong><small>{r.kind} payment{r.invoice_id ? ` · ${r.invoice_id}` : ""}</small></span>
                      <span className="bp-who">
                        <DistributorMark name={cast.distributor} color={account?.distributor.colors.primary} size={26} />
                        <span><strong>{cast.distributor}</strong></span>
                      </span>
                      <span className="bp-cell bp-result">
                        {r.taken !== null && <span>Kept <b className="is-amber">{money(r.taken)}</b></span>}
                        {r.disputed !== null && r.disputed > 0 && <span>Disputed <b className="is-dispute">{money(r.disputed)}</b></span>}
                        {r.accepted !== null && r.accepted > 0 && <span>Fair <b className="is-fair">{money(r.accepted)}</b></span>}
                        {r.questions > 0 && <span>{r.questions} question{r.questions === 1 ? "" : "s"}</span>}
                        {r.taken === null && !r.disputed && !r.accepted && r.questions === 0 && <span className="is-none">No totals yet</span>}
                      </span>
                      <span className="bp-status">
                        <span className={`bp-chip ${r.replaced ? "is-swap" : TONE[r.status]}`}>{r.replaced ? "Replaced by a newer run" : i === 0 && r.status === "waiting" ? "Waiting on you" : STATUS[r.status]}</span>
                      </span>
                      <span className="bp-go">Open →</span>
                    </Link>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        )}

        {score.data?.status === "done" && (
          <p className="bp-score">
            <span>How accurate are the agents? On a 30-case test set with a key written first: <strong>{score.data.correct} of {score.data.cases} correct</strong>, <strong>{score.data.wrong_automatic} wrong automatic actions</strong>. <Link className="bp-link" href={withAccount("/results", account?.id)}>Details</Link></span>
          </p>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
