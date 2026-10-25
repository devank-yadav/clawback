"use client";

// /app/disputes: every dispute this distributor's runs filed, and one open at a time: its lines, its email (Review and
// send, until it's sent) and its thread (portal and email messages, the Negotiator's reply drafts with Send).
// ?id=D-0417&run=<run id> opens one; otherwise the newest.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { ArrowUpRight } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { Dispute, DisputeThread as Thread } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { DisputeThread, ReviewAndSend } from "./DisputeMail";

const STATUS: Record<Dispute["status"], { label: string; tone: string }> = {
  ready_to_send: { label: "Ready to send", tone: "is-amber" },
  draft: { label: "Waiting for you", tone: "is-amber" },
  filed: { label: "Filed", tone: "is-live" },
  answered: { label: "Answered", tone: "is-live" },
  resolved: { label: "Resolved", tone: "is-green" },
  withdrawn: { label: "Withdrawn", tone: "is-swap" },
};

const unsent = (d: Dispute) => d.status === "ready_to_send" || d.status === "draft";

export default function Disputes() {
  const { account, cast, state } = useRun();
  const params = useSearchParams();
  const load = useCallback(() => api.fetchDisputes(account!.id), [account]);
  const replies = state.portal.length;
  const list = useFetched(account ? load : null, `${account?.id ?? ""}:${state.dispute?.status ?? ""}:${replies}`);
  const threads = list.data ?? [];
  const wantId = params.get("id");
  const wantRun = params.get("run");
  const open: Thread | null =
    threads.find((t) => t.dispute.id === wantId && (!wantRun || t.run_id === wantRun)) ?? threads.find((t) => t.dispute.id === wantId) ?? threads[0] ?? null;
  const href = (t: Thread) => withAccount("/disputes", account?.id, { id: t.dispute.id, run: t.run_id });
  // One entry per dispute: the newest run's (the API lists newest first), with the runs it replaced folded under it.
  // Only the newest can be sent; an earlier run's is shown for the record.
  const groups: { head: Thread; earlier: Thread[] }[] = [];
  for (const t of threads) {
    const g = groups.find((x) => x.head.dispute.id === t.dispute.id);
    if (g) g.earlier.push(t);
    else groups.push({ head: t, earlier: [] });
  }
  const isHead = (t: Thread | null) => !!t && groups.some((g) => g.head === t);
  const ListItem = ({ t, current }: { t: Thread; current: boolean }) => (
    <Link href={href(t)} className="dm-list-item" aria-current={current ? "page" : undefined}>
      <span><strong>{t.dispute.id}</strong><small>{t.dispute.lines.length} line{t.dispute.lines.length === 1 ? "" : "s"} · {t.messages.length} message{t.messages.length === 1 ? "" : "s"}</small></span>
      <span className="dm-list-right"><b>{money(t.dispute.total)}</b><span className={`bp-chip ${isHead(t) ? STATUS[t.dispute.status].tone : "is-swap"}`}>{isHead(t) ? STATUS[t.dispute.status].label : "Replaced"}</span></span>
    </Link>
  );

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main bp dm-page">
        <PageHeader title="Disputes" line={`What was sent to ${cast.distributor}, and every reply from their portal or by email.`} />
        {list.error && <div className="fl-problem" role="alert">{list.error}</div>}
        {list.data && threads.length === 0 ? (
          <EmptyState
            title={`No disputes with ${cast.distributor} yet.`}
            line="A dispute appears here when the agents find a charge the deal doesn’t allow."
            action={<Link className="cx-btn" href={withAccount("/", account?.id)}>Go to the agents</Link>}
          />
        ) : (
          <div className="dm-layout">
            <nav className="dm-list" aria-label="Disputes">
              {!list.data && !list.error && <div className="bp-skel" aria-hidden="true"><i /><i /></div>}
              {groups.map(({ head, earlier }) => (
                <div key={`${head.run_id}:${head.dispute.id}`} className="dm-group">
                  <ListItem t={head} current={open === head} />
                  {earlier.length > 0 && (
                    <details className="dm-earlier" open={earlier.includes(open as Thread)}>
                      <summary>{earlier.length} earlier run{earlier.length === 1 ? "" : "s"}, replaced</summary>
                      {earlier.map((t) => <ListItem key={`${t.run_id}:${t.dispute.id}`} t={t} current={open === t} />)}
                    </details>
                  )}
                </div>
              ))}
            </nav>
            {open && (
              <article className="fl-card dm-detail" aria-label={`Dispute ${open.dispute.id}`}>
                <header className="cx-head" style={{ alignItems: "center" }}>
                  <h2>{open.dispute.id} · {money(open.dispute.total)}</h2>
                  <span className={`bp-chip ${STATUS[open.dispute.status].tone}`}>{STATUS[open.dispute.status].label}</span>
                </header>
                <ul className="dm-lines" aria-label="What it disputes">
                  {open.dispute.lines.map((l) => (
                    <li key={l.charge_id}>
                      <span><strong>{l.ref}</strong> {l.reason}{l.clause_ref ? <small> · {l.clause_ref}</small> : null}</span>
                      <b>{money(l.amount)}</b>
                    </li>
                  ))}
                </ul>
                {unsent(open.dispute) && isHead(open) && (
                  <section className="dm-section" aria-label="Review and send">
                    <h3>Review and send</h3>
                    <ReviewAndSend key={`${open.run_id}:${open.dispute.id}`} disputeId={open.dispute.id} runId={open.run_id} distributor={cast.distributor} onSent={list.reload} />
                  </section>
                )}
                <section className="dm-section" aria-label="The thread">
                  <h3>Thread</h3>
                  <DisputeThread key={`${open.run_id}:${open.dispute.id}`} disputeId={open.dispute.id} runId={open.run_id} distributor={cast.distributor} refreshKey={`${open.dispute.status}:${replies}`} />
                </section>
                <a className="cx-btn is-ghost" href={withAccount("/portal", account?.id, { dispute: open.dispute.id })} target="_blank" rel="noreferrer">Open {account?.distributor.portal_name ?? `${cast.distributor}’s portal`}<ArrowUpRight aria-hidden="true" /></a>
              </article>
            )}
          </div>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
