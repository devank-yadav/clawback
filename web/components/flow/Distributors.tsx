"use client";

// The supplier's home: the distributors it sells through, each with a plain status (never a money figure). Pick one
// and its whole workflow opens: contract, payments, the agents' run, decisions and the result. Track or untrack any.

import Link from "next/link";
import { useCallback, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar, { DistributorMark, STATUS_TONE } from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { DistributorItem, SupplierItem } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const ACTION: Record<DistributorItem["status"], string> = {
  waiting_for_payment: "Open", checking: "Watch the agents", needs_you: "Decide now", settled: "See the result", stopped: "See what happened",
};

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
      <TopBar account={account} />
      <main className="fl-main ds">
        <header className="ds-head">
          <span className="cx-eyebrow">{supplier?.brand.name ?? " "}</span>
          <h1>{supplier ? `You sell through ${tracked.length} distributor${tracked.length === 1 ? "" : "s"}` : "Loading your distributors…"}</h1>
          <p>The agents watch each one’s payments and check every deduction against its deal. Open one to see its whole workflow.</p>
        </header>

        {waiting.length > 0 && (
          <Link className="ds-next" href={withAccount("/", waiting[0].account_id)}>
            <i className="tb-dot is-amber" />
            <span><strong>Your next step</strong>{waiting[0].distributor.name}: {waiting[0].status_label.toLowerCase()}</span>
            <b>Decide now →</b>
          </Link>
        )}
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <div className="ds-grid">
          {tracked.map((d) => (
            <article key={d.account_id} className={`ds-card ${d.account_id === account?.id ? "is-current" : ""}`}>
              <Link className="ds-open" href={withAccount("/", d.account_id)} aria-label={`Open ${d.distributor.name}`} />
              <div className="ds-card-top">
                <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={40} />
                <span className={`ds-status ${STATUS_TONE[d.status]}`}><i className={`tb-dot ${STATUS_TONE[d.status]}`} />{d.status_label}</span>
              </div>
              <h2>{d.distributor.name}</h2>
              <div className="ds-card-foot">
                <span>{ACTION[d.status]} →</span>
                <button className="ds-untrack" disabled={busy === d.account_id} onClick={() => void toggle(d)}>Stop tracking</button>
              </div>
            </article>
          ))}
        </div>

        {others.length > 0 && (
          <section className="ds-add">
            <h2>Add a distributor</h2>
            <p className="cx-small cx-muted">Track another distributor and the agents start checking its payments too.</p>
            <div className="ds-add-list">
              {others.map((d) => (
                <div key={d.account_id} className="ds-add-row">
                  <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={30} />
                  <strong>{d.distributor.name}</strong>
                  <button className="cx-btn" disabled={busy === d.account_id} onClick={() => void toggle(d)}>Track</button>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
