"use client";

// /app/disputes: every dispute this distributor's runs filed, and one open at a time: its lines, its email (Review and
// send, until it's sent) and its thread (portal and email messages, the Negotiator's reply drafts with Send).
// ?id=D-0417&run=<run id> opens one; otherwise the newest.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHero } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { Dispute, DisputeThread as Thread } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { DisputeThread, ReviewAndSend } from "./DisputeMail";

const STATUS: Record<Dispute["status"], { label: string; tone: string }> = {
  ready_to_send: { label: "Ready to send", tone: "is-amber" },
  draft: { label: "Waiting for you", tone: "is-amber" },
  filed: { label: "Sent", tone: "is-live" },
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

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main bp dm-page">
        <PageHero
          align="left"
          title={<>Disputes<em>{open ? `with ${cast.distributor}.` : "and their replies."}</em></>}
          sub={`What was sent to ${cast.distributor}, every reply from their portal or by email, and the answers waiting for you.`}
        />
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
              {threads.map((t, i) => (
                <Link key={`${t.run_id}:${t.dispute.id}`} href={href(t)} className="dm-list-item" aria-current={open === t ? "page" : undefined}>
                  <span><strong>{t.dispute.id}</strong><small>{threads.slice(0, i).some((o) => o.dispute.id === t.dispute.id) ? "An earlier run · " : ""}{t.dispute.lines.length} line{t.dispute.lines.length === 1 ? "" : "s"} · {t.messages.length} message{t.messages.length === 1 ? "" : "s"}</small></span>
                  <span className="dm-list-right"><b>{money(t.dispute.total)}</b><span className={`bp-chip ${STATUS[t.dispute.status].tone}`}>{STATUS[t.dispute.status].label}</span></span>
                </Link>
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
                {unsent(open.dispute) && (
                  <section className="dm-section" aria-label="Review and send">
                    <h3>Review and send</h3>
                    <ReviewAndSend key={`${open.run_id}:${open.dispute.id}`} disputeId={open.dispute.id} runId={open.run_id} onSent={list.reload} />
                  </section>
                )}
                <section className="dm-section" aria-label="The thread">
                  <h3>Thread</h3>
                  <DisputeThread key={`${open.run_id}:${open.dispute.id}`} disputeId={open.dispute.id} runId={open.run_id} distributor={cast.distributor} refreshKey={`${open.dispute.status}:${replies}`} />
                </section>
                <a className="cx-btn is-ghost" href={withAccount("/portal", account?.id, { dispute: open.dispute.id })} target="_blank" rel="noreferrer">Open {account?.distributor.portal_name ?? `${cast.distributor}’s portal`} ↗</a>
              </article>
            )}
          </div>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
