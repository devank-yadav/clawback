"use client";

// Every payment from every distributor in one list, newest first, so the owner sees at a glance what came in and what
// needs them. One card per payment (a newer check of the same payment folds the earlier ones under it); a payment with
// an item on the owner's list (GET /overview needs_you) is pinned at the top. Each card opens that payment's page,
// where the agents' work is shown. Read again every 15 seconds so a payment the agents just started shows up as
// "Checking now". Nothing here computes money: every amount is the API's.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Play, Upload } from "lucide-react";
import CheckPayments from "@/components/app/CheckPayments";
import { RECEIVED_EVENT, useReceivedPayments, type Received } from "@/components/app/ReceivedPayments";
import { useRun } from "@/components/console/RunProvider";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { inkOn, withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { Account, NeedsYou, RunSummary } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

type Row = RunSummary & { account: Account };
type Payment = { head: Row; earlier: Row[]; flagged: boolean; asks: NeedsYou[] };
type Filter = { kind: "all" } | { kind: "needs" } | { kind: "account"; id: string };

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const monthName = (kind: string) => kind.charAt(0).toUpperCase() + kind.slice(1);
const initial = (name: string) => name.trim().charAt(0).toUpperCase() || "?";

/** Every distributor's payments, newest first. One distributor that can't be read doesn't hide the others. */
async function loadAll(accounts: Account[]): Promise<Row[]> {
  const settled = await Promise.allSettled(accounts.map(async (a) => (await api.fetchRuns(a.id)).map((r) => ({ ...r, account: a }))));
  const ok = settled.filter((s): s is PromiseFulfilledResult<Row[]> => s.status === "fulfilled");
  if (accounts.length > 0 && ok.length === 0) throw (settled[0] as PromiseRejectedResult).reason;
  return ok.flatMap((s) => s.value).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
}

/** One card per payment: the newest check of it, with any earlier ones folded under it. */
function group(rows: Row[], asksByRun: Map<string, NeedsYou[]>): Payment[] {
  const out: Payment[] = [];
  for (const r of rows) {
    const g = out.find((x) => x.head.account.id === r.account.id && x.head.kind === r.kind && x.head.invoice_id === r.invoice_id);
    if (g) g.earlier.push(r);
    else out.push({ head: r, earlier: [], flagged: false, asks: [] });
  }
  for (const p of out) {
    p.asks = [p.head, ...p.earlier].flatMap((r) => asksByRun.get(r.run_id) ?? []);
    p.flagged = !p.head.replaced && (p.head.status === "waiting" || p.asks.length > 0);
  }
  return out;
}

function Mark({ account }: { account: Account }) {
  const bg = account.distributor.colors.primary;
  return <span className="pm-mark" style={{ background: bg, color: inkOn(bg) }} aria-hidden="true">{initial(account.distributor.name)}</span>;
}

/** What a payment is waiting on you for, in a few words (its first item on your list, then how many more). */
function askLine(asks: NeedsYou[]): string {
  const n = asks[0];
  const amt = n.amount != null ? money(n.amount) : null;
  const first = n.kind === "question" ? `A question for you${amt ? ` about ${amt}` : ""}`
    : n.kind === "approval" ? `Send ${amt ?? "the fair charges"} to QuickBooks?`
      : n.kind === "dispute_email" ? `Your ${amt ? `${amt} ` : ""}dispute is ready to send`
        : `${n.distributor} pushed back on your dispute`;
  return asks.length > 1 ? `${first} · ${asks.length - 1} more` : first;
}

/** The status chip and the plain-words line under it. */
function status(r: Row, flagged: boolean, asks: NeedsYou[] = []): { chip: string; tone: string; line: string | null } {
  if (r.status === "failed") return { chip: "Stopped", tone: "", line: "The agents stopped before they finished. Open it to see where." };
  if (flagged) {
    return { chip: "Needs you", tone: "is-amber", line: asks.length ? askLine(asks) : r.waiting && r.waiting > 0 ? `${money(r.waiting)} waiting on your answer` : "The agents are waiting on you" };
  }
  if (r.status === "started") return { chip: "Checking now", tone: "is-accent is-live", line: "The agents are going through each charge" };
  const parts: string[] = [];
  if (r.disputed && r.disputed > 0) parts.push(`${money(r.disputed)} being disputed`);
  if (r.accepted && r.accepted > 0) parts.push(`${money(r.accepted)} fair`);
  return { chip: "Done", tone: "is-green", line: parts.length ? parts.join(" · ") : "Everything was fair" };
}

/** "Paid $41,350 of $48,200 · kept $6,850": the payment's own numbers (the API's summary), else the account's current
 * invoice when it's this payment's; else what was kept. */
function paidLine(r: Row): string | null {
  const inv = r.account.invoice;
  const kept = r.taken !== null ? `kept ${money(r.taken)}` : null;
  if (r.paid != null && r.invoiced != null) return `Paid ${money(r.paid)} of ${money(r.invoiced)}${kept ? ` · ${kept}` : ""}`;
  if (inv && r.invoice_id && inv.id === r.invoice_id) {
    return `Paid ${money(inv.received)} of ${money(inv.expected)}${kept ? ` · ${kept}` : ""}`;
  }
  return kept ? kept.charAt(0).toUpperCase() + kept.slice(1) : null;
}

function PaymentCard({ r, flagged, asks = [], small = false }: { r: Row; flagged: boolean; asks?: NeedsYou[]; small?: boolean }) {
  const s = r.replaced ? { chip: "Checked again later", tone: "", line: null } : status(r, flagged, asks);
  const paid = paidLine(r);
  return (
    <Link className={`pm-card cb-card ${flagged ? "is-flagged" : ""} ${small ? "is-small" : ""}`} href={withAccount("/", r.account.id, { run: r.run_id })}>
      <span className="pm-who">
        <Mark account={r.account} />
        <span className="pm-who-text">
          <strong>{r.account.distributor.name}</strong>
          <small>{monthName(r.kind)} payment · {when(r.started_at)}</small>
        </span>
      </span>
      <span className="pm-body">
        {paid && <span className="pm-paid">{paid}</span>}
        {s.line && <span className="pm-line">{s.line}</span>}
      </span>
      <span className="pm-end">
        <span className={`cx-pill ${s.tone}`}>{s.chip}</span>
        <ArrowRight className="pm-go" aria-hidden="true" />
      </span>
    </Link>
  );
}

function PaymentItem({ p }: { p: Payment }) {
  return (
    <li className="pm-item">
      <PaymentCard r={p.head} flagged={p.flagged} asks={p.asks} />
      {p.earlier.length > 0 && (
        <details className="pm-earlier">
          <summary>Checked {p.earlier.length} time{p.earlier.length === 1 ? "" : "s"} before</summary>
          <ol className="pm-list">
            {p.earlier.map((r) => <li key={r.run_id}><PaymentCard r={r} flagged={false} small /></li>)}
          </ol>
        </details>
      )}
    </li>
  );
}

/** Payments that arrived but the agents haven't started on (autopilot usually starts them on its own). */
function Arrived({ received, accounts, filter }: { received: Received; accounts: Account[]; filter: Filter }) {
  const list = received.pending.filter((p) => filter.kind !== "account" || p.account_id === filter.id);
  if (filter.kind === "needs" || (!list.length && !received.problem)) return null;
  return (
    <section className="pm-section" aria-label="Payments that just arrived">
      <h2 className="pm-h">Just arrived</h2>
      <ol className="pm-list">
        {list.map((p) => {
          const acc = accounts.find((a) => a.id === p.account_id);
          return (
            <li key={p.id} className="pm-item">
              <div className="pm-card cb-card is-arrived">
                <span className="pm-who">
                  {acc ? <Mark account={acc} /> : <span className="pm-mark" aria-hidden="true">{initial(p.distributor)}</span>}
                  <span className="pm-who-text">
                    <strong>{p.distributor}</strong>
                    <small>{p.source === "bank" ? "Deposited in the bank" : "Sent from their portal"} · {when(p.received_at)}</small>
                  </span>
                </span>
                <span className="pm-body">
                  <span className="pm-paid">Paid {money(p.received)} of {money(p.expected)}</span>
                  <span className="pm-line">The agents haven’t started on it yet</span>
                </span>
                <span className="pm-end">
                  <button className="cx-btn is-blue is-small" onClick={() => void received.run(p)} disabled={!!received.runningId}>
                    <Play aria-hidden="true" />{received.runningId === p.id ? "Starting…" : "Start the agents"}
                  </button>
                </span>
              </div>
            </li>
          );
        })}
      </ol>
      {received.problem && <div className="fl-problem" role="alert">{received.problem}</div>}
    </section>
  );
}

export default function Payments() {
  const { account, accounts, accountsError } = useRun();
  const [tick, setTick] = useState(0);
  // ?distributor=<account> opens on one distributor's payments (the Distributors page links here).
  const params = useSearchParams();
  const [filter, setFilter] = useState<Filter>(() => {
    const id = params.get("distributor");
    return id ? { kind: "account", id } : { kind: "all" };
  });
  // Look again every 15 seconds, so a payment the agents just started appears, and a finished one says so; and at
  // once when "Check for new payments" found some.
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 15_000);
    const now = () => setTick((n) => n + 1);
    window.addEventListener(RECEIVED_EVENT, now);
    return () => { window.clearInterval(id); window.removeEventListener(RECEIVED_EVENT, now); };
  }, []);

  const ids = accounts?.map((a) => a.id).join(",") ?? "";
  const loadRows = useCallback(() => loadAll(accounts ?? []), [accounts]);
  const rows = useFetched(accounts ? loadRows : null, `${ids}:${tick}`);
  const loadOverview = useCallback(() => api.fetchCompanyOverview().catch(() => null), []);
  const overview = useFetched(loadOverview, String(tick));
  const received = useReceivedPayments();

  const payments = useMemo(() => {
    const asksByRun = new Map<string, NeedsYou[]>();
    for (const n of overview.data?.needs_you ?? []) if (n.link.run_id) asksByRun.set(n.link.run_id, [...(asksByRun.get(n.link.run_id) ?? []), n]);
    return group(rows.data ?? [], asksByRun);
  }, [rows.data, overview.data]);

  const needs = payments.filter((p) => p.flagged);
  const shown = filter.kind === "account" ? payments.filter((p) => p.head.account.id === filter.id) : payments;
  const pinned = filter.kind === "needs" ? needs : shown.filter((p) => p.flagged);
  const rest = filter.kind === "needs" ? [] : shown.filter((p) => !p.flagged);
  const loading = !rows.data && !rows.error && !accountsError;
  const error = accountsError ?? rows.error;
  const empty = !!rows.data && payments.length === 0 && received.pending.length === 0;
  const isOn = (f: Filter) => f.kind === filter.kind && (f.kind !== "account" || (filter.kind === "account" && filter.id === f.id));

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main pm">
        <PageHeader
          title="Payments"
          line="Every payment from your distributors. New ones start the agents on their own."
          actions={<>
            <CheckPayments account={account?.id} />
            <Link className="cx-btn is-ghost" href={withAccount("/upload", account?.id)}><Upload aria-hidden="true" />Upload a payment slip</Link>
          </>}
        />
        {error && <div className="fl-problem" role="alert">{error}</div>}

        {!empty && (
          <div className="pm-filters" role="group" aria-label="Show payments">
            <button className="pm-chip" aria-pressed={isOn({ kind: "all" })} onClick={() => setFilter({ kind: "all" })}>All</button>
            <button className="pm-chip is-needs" aria-pressed={isOn({ kind: "needs" })} onClick={() => setFilter({ kind: "needs" })}>
              Needs you<span className="pm-count">{needs.length}</span>
            </button>
            {(accounts ?? []).map((a) => (
              <button key={a.id} className="pm-chip" aria-pressed={isOn({ kind: "account", id: a.id })} onClick={() => setFilter({ kind: "account", id: a.id })}>
                <Mark account={a} />{a.distributor.name}
              </button>
            ))}
          </div>
        )}

        <Arrived received={received} accounts={accounts ?? []} filter={filter} />

        {loading && (
          <ol className="pm-list" aria-hidden="true">
            {[0, 1, 2].map((i) => <li key={i} className="pm-item"><div className="pm-card cb-card is-skel"><i /><i /><i /></div></li>)}
          </ol>
        )}

        {empty ? (
          <EmptyState title="No payments yet." line="When a distributor pays, it shows up here and the agents start on their own." />
        ) : (
          <>
            {pinned.length > 0 && (
              <section className="pm-section is-needs" aria-label="Needs you">
                <h2 className="pm-h">Needs you <span className="pm-count">{pinned.length}</span></h2>
                <ol className="pm-list">{pinned.map((p) => <PaymentItem key={p.head.run_id} p={p} />)}</ol>
              </section>
            )}
            {rest.length > 0 && (
              <section className="pm-section" aria-label={pinned.length ? "Everything else" : "All payments"}>
                {pinned.length > 0 && <h2 className="pm-h">Everything else</h2>}
                <ol className="pm-list">{rest.map((p) => <PaymentItem key={p.head.run_id} p={p} />)}</ol>
              </section>
            )}
            {rows.data && filter.kind === "needs" && pinned.length === 0 && (
              <p className="pm-calm">Nothing needs you right now. The agents will ask if a deal is unclear.</p>
            )}
            {rows.data && filter.kind === "account" && shown.length === 0 && (
              <p className="pm-calm">No payments from this distributor yet.</p>
            )}
          </>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
