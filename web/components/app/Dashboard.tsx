"use client";

// /app: the company across all its distributors. First what needs the admin (one queue, highest severity first, each
// row a link straight to its action), then the money at a glance, the open disputes with the days left to file, and
// the latest activity. The distributor list lives on Distributors.
//
// Data: GET /overview (branch supplier-overview). Until the API serves it, the page reads the same facts from the
// endpoints that exist (suppliers, each account's runs, disputes and its latest run's events) and leaves a gap where
// only the API can answer: the screen never adds money up, so a company total shows only when one distributor's run
// is the whole of it, and "recovered" shows only from the API's evidence.

import Link from "next/link";
import { useCallback } from "react";
import { AlertTriangle, ArrowRight, CircleAlert, Clock, MinusCircle } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { CompanyOverview, NeedsYou, OpenDispute, Question, RunEvent, RunSummary } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const OPEN = new Set(["ready_to_send", "draft", "filed", "answered"]);
const STATUS: Record<string, string> = { ready_to_send: "Ready to send", draft: "Ready to send", filed: "Sent, awaiting reply", answered: "Replied" };
const RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };
const KIND_ORDER: Record<string, number> = { answer: 0, send: 1, approve: 2 };
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

type Home = { overview: CompanyOverview; fromApi: boolean; names: Record<string, string> };

/** The same facts from the endpoints that exist today, for while GET /overview isn't served. */
async function fromExisting(): Promise<Home> {
  const suppliers = await api.fetchSuppliers();
  const tracked = suppliers.flatMap((s) => s.distributors.filter((d) => d.tracked));
  const names = Object.fromEntries(tracked.map((d) => [d.account_id, d.distributor.name]));
  const per = await Promise.all(tracked.map(async (d) => {
    const runs = await api.fetchRuns(d.account_id).catch(() => [] as RunSummary[]);
    const run = runs.find((r) => !r.replaced) ?? null;
    const [threads, events] = await Promise.all([
      api.fetchDisputes(d.account_id).catch(() => []),
      run ? api.runEventsOnce(run.run_id).catch(() => [] as RunEvent[]) : Promise.resolve([] as RunEvent[]),
    ]);
    return { d, run, runs, threads: threads.filter((t) => t.run_id === run?.run_id), events };
  }));

  const needs: NeedsYou[] = [];
  const open: OpenDispute[] = [];
  for (const { d, run, threads, events } of per) {
    if (!run) continue;
    const questions = new Map<string, Question>();
    const answered = new Set<string>();
    const titles: Record<string, string> = {};
    let approval: { amount: number; status: string } | null = null;
    for (const e of events) {
      if (e.type === "question") questions.set(e.data.id, e.data);
      if (e.type === "answer") answered.add(e.data.question_id);
      if (e.type === "charge") titles[e.data.id] = e.data.description;
      if (e.type === "approval") approval = e.data;
    }
    for (const q of questions.values()) {
      if (answered.has(q.id) || q.answer || q.closed_at) continue;
      needs.push({ kind: "answer", account_id: d.account_id, run_id: run.run_id, distributor: d.distributor.name, risk: q.risk ?? null, question_id: q.id,
        title: q.charge_id && titles[q.charge_id] ? `Decide ${titles[q.charge_id]}` : "Answer a question about a charge" });
    }
    for (const t of threads) {
      if (t.dispute.status === "ready_to_send" || t.dispute.status === "draft") {
        needs.push({ kind: "send", account_id: d.account_id, run_id: run.run_id, distributor: d.distributor.name, dispute_id: t.dispute.id, amount: t.dispute.total, title: `Review and send ${t.dispute.id}` });
      }
      if (OPEN.has(t.dispute.status)) {
        const days = t.dispute.lines.map((l) => l.days_left).filter((n): n is number => typeof n === "number");
        open.push({ account_id: d.account_id, run_id: run.run_id, dispute_id: t.dispute.id, distributor: d.distributor.name, amount: t.dispute.total, status: t.dispute.status, days_left: days.length ? Math.min(...days) : null });
      }
    }
    if (approval?.status === "pending") needs.push({ kind: "approve", account_id: d.account_id, run_id: run.run_id, distributor: d.distributor.name, amount: approval.amount, title: "Approve the credit memo for the fair charges" });
  }

  // A company total is shown only when a single distributor's latest run is the whole of it: nothing is added up here.
  const withRuns = per.filter((p) => p.run && p.run.taken != null);
  const only = withRuns.length === 1 ? withRuns[0].run! : null;
  const recent = per
    .flatMap((p) => p.runs.filter((r) => !r.replaced).map((r) => ({
      at: r.started_at, account_id: p.d.account_id, run_id: r.run_id,
      text: `${p.d.distributor.name}: ${r.kind} payment checked${r.taken != null ? `, ${money(r.taken)} taken` : ""}${r.questions === 0 && r.kind !== "march" ? ", no questions asked" : ""}`,
    })))
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, 5);

  return {
    fromApi: false,
    names,
    overview: {
      totals: only ? { taken: only.taken, disputed: only.disputed, fair: only.accepted, recovered: null } : null,
      needs_you: needs,
      open_disputes: open,
      recent,
    },
  };
}

async function loadHome(): Promise<Home> {
  const fromApi = await api.fetchCompanyOverview();
  if (fromApi) {
    const suppliers = await api.fetchSuppliers().catch(() => []);
    const names = Object.fromEntries(suppliers.flatMap((s) => s.distributors.map((d) => [d.account_id, d.distributor.name])));
    return { overview: fromApi, fromApi: true, names };
  }
  return fromExisting();
}

function Severity({ item }: { item: NeedsYou }) {
  const level = String(item.risk?.level ?? "").toLowerCase();
  const kind = item.risk?.kind ? String(item.risk.kind) : null;
  return (
    <span className="hm-tags">
      {level === "high" && <span className="dc-level is-high"><AlertTriangle aria-hidden="true" />High</span>}
      {level === "medium" && <span className="dc-level is-medium"><CircleAlert aria-hidden="true" />Medium</span>}
      {level === "low" && <span className="dc-level is-low"><MinusCircle aria-hidden="true" />Low</span>}
      {kind && <span className="dc-kind">{kind.charAt(0).toUpperCase() + kind.slice(1)}</span>}
    </span>
  );
}

const ACTION: Record<string, string> = { answer: "Answer", send: "Review and send", approve: "Approve" };

function actionHref(item: NeedsYou): string {
  if (item.kind === "send" && item.dispute_id) return withAccount("/disputes", item.account_id, { id: item.dispute_id, ...(item.run_id ? { run: item.run_id } : {}) });
  return withAccount("/", item.account_id, item.run_id ? { run: item.run_id } : undefined);
}

function DaysLeft({ days }: { days: number | null | undefined }) {
  if (days == null) return <span className="hm-none">Not known</span>;
  const tone = days <= 7 ? "is-red" : days <= 14 ? "is-amber" : "";
  return <span className={`hm-days ${tone}`}>{tone ? <AlertTriangle aria-hidden="true" /> : <Clock aria-hidden="true" />}{days} day{days === 1 ? "" : "s"}</span>;
}

export default function Dashboard() {
  const { account } = useRun();
  const load = useCallback(() => loadHome(), []);
  const fetched = useFetched(load);
  const home = fetched.data;
  const o = home?.overview;
  const needs = [...(o?.needs_you ?? [])].sort((a, b) =>
    (RANK[String(a.risk?.level ?? "").toLowerCase()] ?? 3) - (RANK[String(b.risk?.level ?? "").toLowerCase()] ?? 3)
    || (KIND_ORDER[a.kind] ?? 9) - (KIND_ORDER[b.kind] ?? 9));
  const t = o?.totals ?? null;
  const fair = t?.fair ?? t?.accepted ?? null;
  const evidence = t?.recovered_evidence ?? [];
  const name = (id: string, fallback?: string | null) => fallback ?? home?.names[id] ?? id;

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main bp ap hm">
        <PageHeader title="Home" line={account ? `${account.brand.name}, across every distributor` : undefined}
          actions={<Link className="cx-btn is-ghost" href={withAccount("/upload", account?.id)}>Add a remittance</Link>} />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <section className="hm-block" aria-labelledby="hm-needs">
          <h2 id="hm-needs">Needs you</h2>
          {!home && !fetched.error && <div className="hm-skel" aria-hidden="true"><i /><i /></div>}
          {home && needs.length === 0 && <p className="hm-empty">Nothing needs you. The agents ask here when a contract leaves a charge to your judgment.</p>}
          {needs.length > 0 && (
            <ol className="hm-queue">
              {needs.map((n, i) => (
                <li key={`${n.kind}-${n.account_id}-${n.question_id ?? n.dispute_id ?? i}`}>
                  <Link href={actionHref(n)} className="hm-item">
                    <Severity item={n} />
                    <span className="hm-what">
                      <strong>{n.title}</strong>
                      <small>{name(n.account_id, n.distributor)}{n.risk?.reason ? ` · ${n.risk.reason}` : ""}</small>
                    </span>
                    {n.amount != null && <span className="hm-amt">{money(n.amount)}</span>}
                    <span className="hm-go">{ACTION[n.kind] ?? "Open"}<ArrowRight aria-hidden="true" /></span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="hm-block" aria-labelledby="hm-money">
          <h2 id="hm-money">Money at a glance</h2>
          <dl className="hm-money">
            <div><dt>Taken from payments</dt><dd>{t?.taken != null ? money(t.taken) : <span className="hm-none">–</span>}</dd></div>
            <div><dt><i className="is-dispute" aria-hidden="true" />Disputed, awaiting reply</dt><dd>{t?.disputed != null ? money(t.disputed) : <span className="hm-none">–</span>}</dd></div>
            <div><dt><i className="is-fair" aria-hidden="true" />Fair, accepted</dt><dd>{fair != null ? money(fair) : <span className="hm-none">–</span>}</dd></div>
            <div>
              <dt>Recovered</dt>
              <dd>{t?.recovered != null && evidence.length > 0 ? money(t.recovered) : <span className="hm-none">None yet</span>}</dd>
              {t?.recovered != null && evidence.length > 0 && (
                <small>{evidence.map((e, i) => e.href ? <a key={i} href={e.href}>{e.label ?? e.kind ?? "evidence"}</a> : <span key={i}>{e.label ?? e.kind}</span>).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, ", ", el] : [el]), [])}</small>
              )}
            </div>
          </dl>
          {home && !home.fromApi && !t && <p className="hm-gap">Company totals need the overview from the server; until then they show for one distributor at a time on its agents page.</p>}
        </section>

        <section className="hm-block" aria-labelledby="hm-disputes">
          <h2 id="hm-disputes">Open disputes</h2>
          {home && (o?.open_disputes ?? []).length === 0 && <p className="hm-empty">No open disputes.</p>}
          {(o?.open_disputes ?? []).length > 0 && (
            <table className="hm-table">
              <thead><tr><th scope="col">Distributor</th><th scope="col">Dispute</th><th scope="col" className="num">Amount</th><th scope="col">Status</th><th scope="col">Days left to file</th></tr></thead>
              <tbody>
                {(o?.open_disputes ?? []).map((d) => (
                  <tr key={`${d.account_id}-${d.dispute_id}`}>
                    <td>{name(d.account_id, d.distributor)}</td>
                    <td><Link href={withAccount("/disputes", d.account_id, { id: d.dispute_id, ...(d.run_id ? { run: d.run_id } : {}) })}>{d.dispute_id}</Link></td>
                    <td className="num">{money(d.amount)}</td>
                    <td>{STATUS[d.status] ?? d.status}</td>
                    <td><DaysLeft days={d.days_left} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {(o?.recent ?? []).length > 0 && (
          <section className="hm-block" aria-labelledby="hm-recent">
            <h2 id="hm-recent">Recent activity</h2>
            <ol className="hm-recent">
              {(o?.recent ?? []).slice(0, 5).map((r, i) => (
                <li key={`${r.at}-${i}`}>
                  {r.account_id ? <Link href={withAccount("/", r.account_id, r.run_id ? { run: r.run_id } : undefined)}>{r.text}</Link> : <span>{r.text}</span>}
                  <time dateTime={r.at}>{when(r.at)}</time>
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
