"use client";

// The distributors the supplier sells through, as one table: each one's plain status, its last payment (from its
// overview), and what the latest check found (taken, disputed, waiting on you), as the API reports them. A row opens
// that distributor's agents view. Stopping tracking sits behind a row menu and asks once more; distributors not
// tracked are listed below, to track again.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar, { DistributorMark, STATUS_TONE } from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader, SectionHead } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { DistributorItem, Overview, RunSummary, SupplierItem } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

type Facts = { overview: Overview | null; run: RunSummary | null };
const day = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const none = <span className="db-none">–</span>;

/** Each tracked distributor's last payment and latest check; one that fails to load shows dashes. */
async function loadFacts(ids: string[]): Promise<Record<string, Facts>> {
  const pairs = await Promise.all(ids.map(async (id) => {
    const [overview, runs] = await Promise.all([
      api.fetchOverview(id).catch(() => null),
      api.fetchRuns(id).catch(() => [] as RunSummary[]),
    ]);
    return [id, { overview, run: runs.find((r) => !r.replaced) ?? null }] as const;
  }));
  return Object.fromEntries(pairs);
}

/** The facts for a comma-joined list of account ids, reloaded when the list changes. */
function useFacts(ids: string) {
  const load = useCallback(() => loadFacts(ids ? ids.split(",") : []), [ids]);
  return useFetched(ids ? load : null, ids);
}

/** "…" on a row: Stop tracking, which asks once more before it stops. */
function RowMenu({ d, busy, onStop }: { d: DistributorItem; busy: boolean; onStop: () => void }) {
  const [open, setOpen] = useState(false);
  const [sure, setSure] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setSure(false); } };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); setSure(false); } };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="ds-menu" ref={ref}>
      <button className="ds-menu-btn" aria-haspopup="menu" aria-expanded={open} aria-label={`More for ${d.distributor.name}`} onClick={() => setOpen((v) => !v)}><MoreHorizontal /></button>
      {open && (
        <div className="tb-menu ds-menu-list" role="menu">
          <Link role="menuitem" className="tb-row" href={withAccount("/contracts", d.account_id)}><span><strong>Signed deal</strong></span></Link>
          <button role="menuitem" className="tb-row is-danger" disabled={busy} onClick={() => (sure ? onStop() : setSure(true))}>
            <span><strong>{sure ? `Stop tracking ${d.distributor.name}?` : "Stop tracking"}</strong>{sure && <small>Click again to stop. Its payments won’t be checked.</small>}</span>
          </button>
        </div>
      )}
    </div>
  );
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
  const ids = tracked.map((d) => d.account_id).join(",");
  const facts = useFacts(ids);

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
        <PageHeader title="Distributors" line={supplier ? `${tracked.length} tracked. Open one to see its payments and the agents’ work.` : undefined} />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <section className="bp-frame" aria-label="Distributors you track">
          <div className="bp-thead" aria-hidden="true"><span>Distributor</span><span>Status</span><span>Last payment</span><span className="num">Taken</span><span className="num">Disputed</span><span className="num">Waits on you</span><span /></div>
          {!supplier && !fetched.error && [0, 1, 2].map((i) => <div key={i} className="bp-skel" aria-hidden="true"><i /><i /><i /><i /><i /></div>)}
          {supplier && tracked.length === 0 && <EmptyState title="No distributors tracked yet." line="Track one below and the agents start checking its payments." />}
          <ul className="bp-rows">
            {tracked.map((d) => {
              const f = facts.data?.[d.account_id];
              const last = f?.overview?.recent_remittances?.[0] ?? null;
              return (
                <li key={d.account_id}>
                  <div className={`bp-row ${d.account_id === account?.id ? "is-current" : ""}`}>
                    <Link className="bp-row-open" href={withAccount("/", d.account_id)} aria-label={`Open ${d.distributor.name}`} />
                    <span className="bp-who">
                      <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={30} />
                      <span><strong>{d.distributor.name}</strong></span>
                    </span>
                    <span className="bp-cell" data-label="Status"><span className={`bp-chip ${STATUS_TONE[d.status]}`}>{d.status_label}</span></span>
                    <span className="bp-cell" data-label="Last payment">{last ? <><strong>{money(last.paid)}</strong><small>{day(last.date)}</small></> : none}</span>
                    <span className="bp-cell num" data-label="Taken">{f?.run?.taken != null ? money(f.run.taken) : none}</span>
                    <span className="bp-cell num" data-label="Disputed">{f?.run?.disputed ? money(f.run.disputed) : none}</span>
                    <span className="bp-cell num" data-label="Waits on you">{f?.run?.waiting ? money(f.run.waiting) : none}</span>
                    <span className="bp-row-end bp-over"><RowMenu d={d} busy={busy === d.account_id} onStop={() => void toggle(d)} /></span>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        {others.length > 0 && (
          <section id="add" className="bp-section">
            <SectionHead title="Not tracked" muted="Track one and the agents check its payments too." />
            <ul className="bp-add-list">
              {others.map((d) => (
                <li key={d.account_id} className="bp-add-row">
                  <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={32} />
                  <strong>{d.distributor.name}</strong>
                  <button className="cx-btn is-ghost" disabled={busy === d.account_id} onClick={() => void toggle(d)}>Track</button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
