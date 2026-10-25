"use client";

// /app: the company across all its distributors (GET /overview). First what needs the admin, one queue already ranked
// by the API (highest risk, then the oldest), each row a link straight to its action; then the money at a glance; the
// open disputes with the days left to file; and the latest activity. The distributor list lives on Distributors.
// Every amount is the API's: "recovered" counts only what evidence shows came back, and each piece links to it.

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
import type { NeedsYou, OverviewLink } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const STATUS: Record<string, string> = { ready_to_send: "Ready to send", draft: "Ready to send", filed: "Sent, awaiting reply", answered: "Replied" };
const ACTION: Record<NeedsYou["kind"], string> = { question: "Answer", dispute_email: "Review and send", reply_email: "Send the reply", approval: "Approve" };
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Where a link from the overview lands: a dispute's thread, or the run (its question or approval is on its result). */
function hrefOf(account: string, link: OverviewLink): string {
  if (link.page === "dispute" && link.dispute_id) return withAccount("/disputes", account, { id: link.dispute_id, ...(link.run_id ? { run: link.run_id } : {}) });
  return withAccount("/", account, link.run_id ? { run: link.run_id } : undefined);
}

function Level({ level }: { level: NeedsYou["risk_level"] }) {
  if (level === "high") return <span className="dc-level is-high"><AlertTriangle aria-hidden="true" />High</span>;
  if (level === "medium") return <span className="dc-level is-medium"><CircleAlert aria-hidden="true" />Medium</span>;
  return <span className="dc-level is-low"><MinusCircle aria-hidden="true" />Low</span>;
}

/** Days left in the dispute window: amber at 14 or fewer, red at 7 or fewer, always with the number and an icon. */
function DaysLeft({ days }: { days: number | null }) {
  if (days == null) return <span className="hm-none">Not known</span>;
  const tone = days <= 7 ? "is-red" : days <= 14 ? "is-amber" : "";
  return <span className={`hm-days ${tone}`}>{tone ? <AlertTriangle aria-hidden="true" /> : <Clock aria-hidden="true" />}{days} day{days === 1 ? "" : "s"}</span>;
}

export default function Dashboard() {
  const { account } = useRun();
  const load = useCallback(() => api.fetchCompanyOverview(), []);
  const fetched = useFetched(load);
  const o = fetched.data;
  const t = o?.totals;
  const evidence = t?.evidence ?? [];
  const dash = <span className="hm-none">–</span>;

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main bp ap hm">
        <PageHeader title="Home" line={o ? `${account?.brand.name ?? "Your company"} across ${o.distributors} distributor${o.distributors === 1 ? "" : "s"}` : undefined}
          actions={<Link className="cx-btn is-ghost" href={withAccount("/upload", account?.id)}>Add a remittance</Link>} />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <section className="hm-block" aria-labelledby="hm-needs">
          <h2 id="hm-needs">Needs you</h2>
          {!o && !fetched.error && <div className="hm-skel" aria-hidden="true"><i /><i /></div>}
          {o && o.needs_you.length === 0 && <p className="hm-empty">Nothing needs you. When a contract leaves a charge to your judgment, the question lands here.</p>}
          {o && o.needs_you.length > 0 && (
            <ol className="hm-queue">
              {o.needs_you.map((n, i) => (
                <li key={`${n.kind}-${n.account_id}-${n.link.run_id ?? ""}-${n.link.dispute_id ?? i}`}>
                  <Link href={hrefOf(n.account_id, n.link)} className="hm-item">
                    <Level level={n.risk_level} />
                    <span className="hm-what"><strong>{n.title}</strong><small>{n.distributor}{n.since ? ` · waiting since ${when(n.since)}` : ""}</small></span>
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
            <div><dt>Taken from payments</dt><dd>{t ? money(t.taken) : dash}</dd></div>
            <div><dt><i className="is-dispute" aria-hidden="true" />Disputed, awaiting reply</dt><dd>{t ? money(t.disputed_awaiting_reply) : dash}</dd></div>
            <div><dt><i className="is-fair" aria-hidden="true" />Fair, accepted</dt><dd>{t ? money(t.fair) : dash}</dd></div>
            <div>
              <dt>Recovered</dt>
              <dd>{t ? money(t.recovered) : dash}</dd>
              {t && (evidence.length === 0
                ? <small>No reply or credit yet</small>
                : <small>
                    {evidence.length} piece{evidence.length === 1 ? "" : "s"} of evidence:{" "}
                    {evidence.map((e, i) => (
                      <span key={`${e.dispute_id ?? e.remittance_ref}-${i}`}>
                        {i > 0 && ", "}
                        {e.dispute_id
                          ? <Link href={withAccount("/disputes", account?.id, { id: e.dispute_id })}>{e.message_id ? "reply" : "credit"} on {e.dispute_id}</Link>
                          : <span>credit {e.remittance_ref}</span>}
                      </span>
                    ))}
                  </small>)}
            </div>
          </dl>
        </section>

        <section className="hm-block" aria-labelledby="hm-disputes">
          <h2 id="hm-disputes">Open disputes</h2>
          {o && o.open_disputes.length === 0 && <p className="hm-empty">No open disputes.</p>}
          {o && o.open_disputes.length > 0 && (
            <table className="hm-table">
              <thead><tr><th scope="col">Distributor</th><th scope="col">Dispute</th><th scope="col" className="num">Amount</th><th scope="col">Status</th><th scope="col">Days left to file</th></tr></thead>
              <tbody>
                {o.open_disputes.map((d) => (
                  <tr key={`${d.run_id}-${d.dispute_id}`}>
                    <td data-label="Distributor">{d.distributor}</td>
                    <td data-label="Dispute"><Link href={withAccount("/disputes", d.account_id, { id: d.dispute_id, run: d.run_id })}>{d.dispute_id}</Link></td>
                    <td data-label="Amount" className="num">{money(d.amount)}</td>
                    <td data-label="Status">{STATUS[d.status] ?? d.status}</td>
                    <td data-label="Days left to file"><DaysLeft days={d.days_left} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {o && o.recent.length > 0 && (
          <section className="hm-block" aria-labelledby="hm-recent">
            <h2 id="hm-recent">Recent activity</h2>
            <ol className="hm-recent">
              {o.recent.slice(0, 6).map((r, i) => (
                <li key={`${r.at}-${i}`}>
                  <Link href={hrefOf(r.account_id, r.link)}>{r.text}</Link>
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
