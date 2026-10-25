"use client";

// /app: the supplier's home. A compact header (with "Send a test payment" on the right), one row of counts, the
// distributors table (status, last payment, what the latest run found, open disputes), and the latest activity. A row
// opens that distributor's agents view (/app/agents). Every amount comes from the API as it is: the screen adds
// nothing up, so the tiles are counts, not sums.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar, { DistributorMark, STATUS_TONE } from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { DisputeThread, DistributorItem, Overview, RunSummary } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

type Row = { d: DistributorItem; overview: Overview | null; run: RunSummary | null; runs: RunSummary[]; disputes: DisputeThread[] };

const day = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const OPEN = new Set(["ready_to_send", "draft", "filed", "answered"]);
const dash = <span className="db-none">–</span>;

/** Each tracked distributor with its overview, its runs and its disputes; one that fails to load shows dashes. */
async function loadRows(): Promise<Row[]> {
  const suppliers = await api.fetchSuppliers();
  const tracked = suppliers.flatMap((s) => s.distributors.filter((d) => d.tracked));
  return Promise.all(tracked.map(async (d) => {
    const [overview, runs, disputes] = await Promise.all([
      api.fetchOverview(d.account_id).catch(() => null),
      api.fetchRuns(d.account_id).catch(() => [] as RunSummary[]),
      api.fetchDisputes(d.account_id).catch(() => [] as DisputeThread[]),
    ]);
    return { d, overview, run: runs.find((r) => !r.replaced) ?? null, runs, disputes };
  }));
}

export default function Dashboard() {
  const { account, cast, startPayment, starting } = useRun();
  const router = useRouter();
  const load = useCallback(() => loadRows(), []);
  const fetched = useFetched(load);
  const rows = fetched.data ?? [];
  const open = (r: Row) => withAccount("/", r.d.account_id);

  const waiting = rows.filter((r) => r.d.status === "needs_you").length;
  const openDisputes = rows.reduce((n, r) => n + r.disputes.filter((t) => t.run_id === r.run?.run_id && OPEN.has(t.dispute.status)).length, 0);
  const checked = rows.reduce((n, r) => n + r.runs.filter((x) => !x.replaced).length, 0);
  const recent = rows
    .flatMap((r) => r.runs.filter((x) => !x.replaced).map((x) => ({ r, x })))
    .sort((a, b) => b.x.started_at.localeCompare(a.x.started_at))
    .slice(0, 5);

  function pay() {
    if (!account) return;
    void startPayment();
    router.push(withAccount("/", account.id));
  }

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main bp ap">
        <PageHeader
          title="Home"
          line={account ? `${account.brand.name} · every distributor’s payments, checked against its deal` : undefined}
          actions={account && <button className="cx-btn fl-go" onClick={pay} disabled={starting}>{starting ? "Sending…" : `Send a test payment from ${cast.distributor}`}</button>}
        />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <section className="ap-tiles" aria-label="At a glance">
          <div><span>Distributors tracked</span><strong>{fetched.data ? rows.length : "–"}</strong></div>
          <div><span>Waiting on you</span><strong className={waiting ? "is-wait" : ""}>{fetched.data ? waiting : "–"}</strong></div>
          <div><span>Open disputes</span><strong>{fetched.data ? openDisputes : "–"}</strong></div>
          <div><span>Payments checked</span><strong>{fetched.data ? checked : "–"}</strong></div>
        </section>

        <section className="ap-table" aria-label="Distributors">
          <div className="ap-head" aria-hidden="true">
            <span>Distributor</span><span>Status</span><span>Last payment</span><span className="num">Kept</span><span className="num">Disputed</span><span className="num">Waits on you</span><span className="num">Open disputes</span>
          </div>
          {!fetched.data && !fetched.error && [0, 1, 2].map((i) => <div key={i} className="ap-row is-skel" aria-hidden="true"><i /><i /><i /></div>)}
          {fetched.data && rows.length === 0 && <p className="ap-empty">No distributors tracked yet. <Link href={withAccount("/distributors", account?.id)}>Track one</Link>.</p>}
          <ul>
            {rows.map((r) => {
              const last = r.overview?.recent_remittances?.[0] ?? null;
              const opened = r.disputes.filter((t) => t.run_id === r.run?.run_id && OPEN.has(t.dispute.status)).length;
              return (
                <li key={r.d.account_id}>
                  <Link href={open(r)} className={`ap-row ${r.d.account_id === account?.id ? "is-current" : ""}`}>
                    <span className="ap-who"><DistributorMark name={r.d.distributor.name} color={r.d.distributor.colors.primary} size={28} /><strong>{r.d.distributor.name}</strong></span>
                    <span data-label="Status"><span className={`bp-chip ${STATUS_TONE[r.d.status]}`}>{r.d.status_label}</span></span>
                    <span data-label="Last payment">{last ? <><strong>{money(last.paid)}</strong><small>{day(last.date)}</small></> : dash}</span>
                    <span className="num" data-label="Kept">{r.run?.taken != null ? money(r.run.taken) : dash}</span>
                    <span className="num is-dispute" data-label="Disputed">{r.run?.disputed ? money(r.run.disputed) : dash}</span>
                    <span className="num is-wait" data-label="Waits on you">{r.run?.waiting ? money(r.run.waiting) : dash}</span>
                    <span className="num" data-label="Open disputes">{opened || dash}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>

        {recent.length > 0 && (
          <section className="ap-recent" aria-label="Recent activity">
            <h2>Recent activity</h2>
            <ol>
              {recent.map(({ r, x }) => (
                <li key={x.run_id}>
                  <Link href={withAccount("/", r.d.account_id, { run: x.run_id })}>
                    <span><strong>{r.d.distributor.name}</strong> {x.kind} payment checked{x.taken != null ? ` · kept ${money(x.taken)}` : ""}{x.disputed ? ` · ${money(x.disputed)} disputed` : ""}{x.status === "waiting" ? " · waiting on you" : ""}</span>
                    <time dateTime={x.started_at}>{when(x.started_at)}</time>
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
