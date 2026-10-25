"use client";

// Every payment the agents checked for this distributor, newest first, one row per payment: what was taken, disputed
// and fair, and how many questions it took (a later month decided by a saved rule says so: "0 questions · decided by
// Rule #1"). Runs a newer run of the same payment replaced fold under "earlier runs". Each row opens its result.

import Link from "next/link";
import { Fragment, useCallback, useState } from "react";
import { ArrowRight, CalendarClock } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { askAdminToken, LIMIT_ADMIN_REASON, limitMessage } from "@/lib/session";
import type { RunSummary } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const STATUS = { started: "Agents working", waiting: "Waiting on you", finished: "Finished", failed: "Stopped" } as const;
const TONE = { started: "is-live", waiting: "is-amber", finished: "is-green", failed: "is-red" } as const;
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const month = (kind: string) => kind.charAt(0).toUpperCase() + kind.slice(1);

type Row = RunSummary & { rules: string[] };

/** The runs, each with the saved rules that decided it (read from its events, for a run that asked nothing). */
async function loadRuns(account: string): Promise<Row[]> {
  const runs = await api.fetchRuns(account);
  return Promise.all(runs.map(async (r) => {
    if (r.replaced || r.questions > 0 || r.status !== "finished") return { ...r, rules: [] };
    const events = await api.runEventsOnce(r.run_id).catch(() => []);
    const ids = new Set<string>();
    for (const e of events) if (e.type === "decision" && e.data.rule_id) ids.add(e.data.rule_id);
    return { ...r, rules: [...ids].map((id) => id.replace(/^rule-/, "Rule #")) };
  }));
}

function RunRow({ r, account }: { r: Row; account: string | undefined }) {
  return (
    <Link className={`bp-row ${r.replaced ? "is-replaced" : ""}`} href={withAccount("/", account, { run: r.run_id })}>
      <span className="bp-when"><strong>{month(r.kind)} payment</strong><small>{when(r.started_at)}{r.invoice_id ? ` · ${r.invoice_id}` : ""}</small></span>
      <span className="bp-cell bp-result">
        {r.taken !== null && <span>Taken <b>{money(r.taken)}</b></span>}
        {r.disputed !== null && r.disputed > 0 && <span><i className="is-dispute" aria-hidden="true" />Disputed <b>{money(r.disputed)}</b></span>}
        {r.accepted !== null && r.accepted > 0 && <span><i className="is-fair" aria-hidden="true" />Fair <b>{money(r.accepted)}</b></span>}
        {r.taken === null && !r.disputed && !r.accepted && <span className="is-none">No totals yet</span>}
      </span>
      <span className="bp-cell">{r.questions > 0 ? `${r.questions} question${r.questions === 1 ? "" : "s"}` : r.rules.length ? `0 questions · decided by ${r.rules.join(", ")}` : r.status === "finished" ? "0 questions" : ""}</span>
      <span className="bp-status">
        <span className={`bp-chip ${r.replaced ? "is-swap" : TONE[r.status]}`}>{r.replaced ? "Replaced" : STATUS[r.status]}</span>
      </span>
      <span className="bp-go">Open<ArrowRight aria-hidden="true" /></span>
    </Link>
  );
}

export default function History() {
  const { account, cast } = useRun();
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const load = useCallback(() => loadRuns(account!.id), [account]);
  const runs = useFetched(account ? load : null, `${account?.id ?? ""}:${tick}`);
  const evalLoad = useCallback(() => api.fetchEval(), []);
  const score = useFetched(evalLoad);
  const list = runs.data ?? [];
  // One row per payment: the newest run, with any it replaced folded under it.
  const groups: { head: Row; earlier: Row[] }[] = [];
  for (const r of list) {
    const g = groups.find((x) => x.head.kind === r.kind && x.head.invoice_id === r.invoice_id);
    if (g) g.earlier.push(r);
    else groups.push({ head: r, earlier: [] });
  }

  /** Next month's payment, checked with the rules saved so far (POST /replay/april); it shows up as a row here. */
  async function nextMonth() {
    if (!account) return;
    setBusy(true);
    setProblem(null);
    try {
      await api.replayNextMonth(account.id);
      window.setTimeout(() => setTick((n) => n + 1), 4000);
    } catch (e) {
      const limit = limitMessage(e);
      if (limit) askAdminToken(LIMIT_ADMIN_REASON, () => void nextMonth());
      else setProblem(`Couldn’t check next month (${(e as Error).message}).`);
    } finally {
      window.setTimeout(() => setBusy(false), 4000);
    }
  }

  return (
    <div className="fl">
      <TopBar account={account} active="history" />
      <main className="fl-main bp bp-hs">
        <PageHeader title="History" line={`Every payment from ${cast.distributor} the agents checked.`}
          actions={account && <button className="cx-btn is-ghost" onClick={() => void nextMonth()} disabled={busy}><CalendarClock aria-hidden="true" />{busy ? "Checking next month…" : "Check next month with saved rules"}</button>} />
        {(runs.error || problem) && <div className="fl-problem" role="alert">{runs.error ?? problem}</div>}

        {runs.data && list.length === 0 ? (
          <EmptyState
            title={`No payment from ${cast.distributor} checked yet.`}
            line="Each payment the bank, QuickBooks or the remittance inbox brings in is checked and listed here."
          />
        ) : (
          <section className="bp-frame bp-hs-frame" aria-label="Payments checked">
            <div className="bp-thead" aria-hidden="true"><span>Payment</span><span>Result</span><span>Questions</span><span>Status</span><span /></div>
            {!runs.data && !runs.error && [0, 1, 2].map((i) => <div key={i} className="bp-skel" aria-hidden="true"><i /><i /><i /><i /><i /></div>)}
            <ol className="bp-rows">
              {groups.map(({ head, earlier }) => (
                <Fragment key={head.run_id}>
                  <li><RunRow r={head} account={account?.id} /></li>
                  {earlier.length > 0 && (
                    <li>
                      <details className="bp-earlier">
                        <summary>{earlier.length} earlier run{earlier.length === 1 ? "" : "s"} of this payment</summary>
                        <ol className="bp-rows">{earlier.map((r) => <li key={r.run_id}><RunRow r={r} account={account?.id} /></li>)}</ol>
                      </details>
                    </li>
                  )}
                </Fragment>
              ))}
            </ol>
          </section>
        )}

        {score.data?.status === "done" && (
          <p className="bp-score">
            How accurate are the agents? On {score.data.cases} planted charges with an answer key written first: <strong>{score.data.correct} of {score.data.cases} correct</strong>, <strong>{score.data.wrong_automatic} wrong automatic actions</strong>.
          </p>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
