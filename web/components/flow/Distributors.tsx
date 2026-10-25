"use client";

// The supplier's home: the distributors it sells through, each with a plain status (never a money figure). Pick one
// and its whole workflow opens: contract, payments, the agents' run, decisions and the result. Track or untrack any.

import Link from "next/link";
import { useCallback, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar, { DistributorMark, STATUS_TONE } from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, HeroPill, PageHero, SectionHead } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { DistributorItem, SupplierItem } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const ACTION: Record<DistributorItem["status"], string> = {
  waiting_for_payment: "Open", checking: "Watch the agents", needs_you: "Decide now", settled: "See the result", stopped: "See what happened",
};

/** The latest run's payment month, from its id ("run-march-…"); no run yet means no payment checked yet. */
function lastPayment(d: DistributorItem) {
  if (!d.latest_run_id) return "None yet";
  const month = /^run-([a-z]+)-/.exec(d.latest_run_id)?.[1];
  return month ? `${month.charAt(0).toUpperCase()}${month.slice(1)} payment` : "Checked";
}

export default function Distributors() {
  const { account } = useRun();
  const load = useCallback(() => api.fetchSuppliers(), []);
  const fetched = useFetched(load);
  const [changed, setChanged] = useState<SupplierItem | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const all = fetched.data;
  const supplier = changed ?? all?.find((s) => s.distributors.some((d) => d.account_id === account?.id)) ?? all?.[0] ?? null;
  const tracked = supplier?.distributors.filter((d) => d.tracked) ?? [];
  const others = supplier?.distributors.filter((d) => !d.tracked) ?? [];
  const waiting = tracked.filter((d) => d.status === "needs_you");

  async function toggle(d: DistributorItem) {
    if (!supplier) return;
    setBusy(d.account_id);
    try {
      setChanged(await api.setTracked(supplier.id, d.account_id, !d.tracked));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="fl">
      <TopBar account={account} active="distributors" />
      <main className="fl-main bp bp-ds">
        <PageHero
          pill={<HeroPill>{supplier?.brand.name ?? "Your distributors"}</HeroPill>}
          title={supplier ? <>You sell through {tracked.length} distributor{tracked.length === 1 ? "" : "s"}.<em>The agents watch every payment.</em></> : <>Loading your<em>distributors…</em></>}
          sub="The agents watch each one’s payments and check every deduction against its deal. Open one to see its whole workflow."
        />

        {waiting.length > 0 && (
          <Link className="bp-next" href={withAccount("/", waiting[0].account_id)}>
            <DistributorMark name={waiting[0].distributor.name} color={waiting[0].distributor.colors.primary} size={40} />
            <span className="bp-next-text"><span className="bp-chip is-amber">Your next step</span>{waiting[0].distributor.name}: {waiting[0].status_label.toLowerCase()}</span>
            <b>Decide now →</b>
          </Link>
        )}
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <div className="bw-stage">
          <section className="bp-frame" aria-label="Distributors you track">
            <div className="bp-frame-bar">
              <span className="bp-tab">Tracked <b>{supplier ? tracked.length : "–"}</b></span>
              <a className="cx-btn" href="#add">Add a distributor</a>
            </div>
            <div className="bp-thead" aria-hidden="true"><span>Distributor</span><span>Status</span><span>Last payment</span><span>Contract</span><span /></div>
            {!supplier && !fetched.error && [0, 1, 2].map((i) => <div key={i} className="bp-skel" aria-hidden="true"><i /><i /><i /><i /><i /></div>)}
            {supplier && tracked.length === 0 && (
              <EmptyState title="No distributors tracked yet." line="Track one below and the agents start checking its payments." />
            )}
            <ul className="bp-rows">
              {tracked.map((d) => (
                <li key={d.account_id}>
                  <div className={`bp-row ${d.account_id === account?.id ? "is-current" : ""}`}>
                    <Link className="bp-row-open" href={withAccount("/", d.account_id)} aria-label={`Open ${d.distributor.name}`} />
                    <span className="bp-who">
                      <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={34} />
                      <span><strong>{d.distributor.name}</strong>{d.account_id === account?.id && <small>In view now</small>}</span>
                    </span>
                    <span className="bp-cell" data-label="Status"><span className={`bp-chip ${STATUS_TONE[d.status]}`}>{d.status_label}</span></span>
                    <span className="bp-cell" data-label="Last payment"><strong>{lastPayment(d)}</strong></span>
                    <span className="bp-cell" data-label="Contract"><Link className="bp-link bp-over" href={withAccount("/contracts", d.account_id)}>Signed deal</Link></span>
                    <span className="bp-row-end">
                      <span className="bp-go">{ACTION[d.status]} →</span>
                      <button className="bp-untrack bp-over" disabled={busy === d.account_id} onClick={() => void toggle(d)}>Stop tracking</button>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {supplier && (
          <section id="add" className="bp-section">
            <SectionHead title="Add a distributor" muted="Track another and the agents check its payments too." />
            {others.length > 0 ? (
              <ul className="bp-add-list">
                {others.map((d) => (
                  <li key={d.account_id} className="bp-add-row">
                    <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={32} />
                    <strong>{d.distributor.name}</strong>
                    <button className="cx-btn is-ghost" disabled={busy === d.account_id} onClick={() => void toggle(d)}>Track</button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="bp-add-done">Every distributor {supplier.brand.name} sells through is tracked. Stop tracking one above and it shows up here.</p>
            )}
          </section>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
