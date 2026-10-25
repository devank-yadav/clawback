"use client";

// Home (Figma: "Clawback · Home"). The chart and the six-month totals come from GET /accounts/{id}/overview (computed
// by the API from the account's history); the tiles come from the run; the distributors are the real accounts.

import Link from "next/link";
import { useCallback } from "react";
import * as api from "@/lib/api";
import { useFetched } from "@/lib/useFetched";
import type { Overview } from "@/lib/types";
import { useRun } from "./RunProvider";
import { Shell } from "./Shell";
import { Money, Pill } from "./ui";

const monthName = (m: string) => new Date(`${m}-15T12:00:00`).toLocaleString("en-US", { month: "short" });

function Chart({ months }: { months: Overview["months"] }) {
  const W = 760, H = 200, P = 34;
  const taken = months.map((m) => Number(m.deducted));
  const back = months.map((m) => Number(m.recovered));
  const top = Math.max(1, ...taken, ...back);
  const step = 10 ** Math.floor(Math.log10(top));
  const max = Math.ceil(top / step) * step;
  const x = (i: number) => P + (i * (W - P * 2)) / Math.max(1, months.length - 1);
  const y = (v: number) => H - 24 - (v / max) * (H - 44);
  const line = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  const ticks = [0, max / 2, max];
  const k = (v: number) => (v >= 1000 ? `$${Math.round(v / 100) / 10}k` : `$${Math.round(v)}`);
  return (
    <svg className="cx-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Money deducted and money recovered by month, last six months">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={P} x2={W - P} y1={y(v)} y2={y(v)} stroke="#e3e8ee" />
          <text x={0} y={y(v) + 4} fill="#61737f" fontSize="10">{k(v)}</text>
        </g>
      ))}
      <path d={`${line(back)} L${x(months.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill="#1f6fe5" opacity="0.1" />
      <path d={line(taken)} fill="none" stroke="#8a9aa6" strokeWidth="2" />
      <path d={line(back)} fill="none" stroke="#1f6fe5" strokeWidth="2" />
      {months.map((m, i) => (
        <text key={m.month} x={x(i)} y={H - 4} fill="#61737f" fontSize="10" textAnchor="middle">{monthName(m.month)}</text>
      ))}
    </svg>
  );
}

export default function Home() {
  const { view, cast, account, accounts, link, state } = useRun();
  const load = useCallback(() => api.fetchOverview(account!.id), [account]);
  const overview = useFetched(account ? load : null, `${account?.id}:${state.lastEventId > 0 ? state.totals?.disputed : ""}`);
  const o = overview.data;
  const r = view.remittance;
  const asking = view.question && !view.question.answer ? 1 : 0;
  const approving = view.approval?.status === "pending" ? 1 : 0;
  const disputes = view.charges.filter((c) => (c.disputed ?? 0) > 0).length;
  const status = asking ? "Needs your decision" : approving ? "Needs your approval" : view.reviewed ? "Review ready" : r ? "Agents checking" : "Waiting for payment";
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const range = o?.months.length ? `${monthName(o.months[0].month)}–${monthName(o.months[o.months.length - 1].month)}` : "";

  return (
    <Shell crumbs={["Overview"]}>
      <div className="cx-head">
        <div>
          <h1 className="cx-h1">{greeting}, {cast.owner}</h1>
          <p className="cx-meta">Your recovery overview · {cast.brand}</p>
        </div>
        <Link className="cx-btn" href={link("/review")}>Review latest payment</Link>
      </div>

      <section className="cx-card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div className="cx-head">
          <h2 style={{ fontSize: 15, fontWeight: 400 }}>Money withheld and money recovered</h2>
          {range && <Pill>Last six months · {range}</Pill>}
        </div>
        {o ? (
          <>
            <div className="cx-legend">
              <div><span><i style={{ background: "#8a9aa6" }} />Deducted from payments</span><Money value={Number(o.kpis.deducted_6m)} /></div>
              <div><span><i style={{ background: "#1f6fe5" }} />Recovered to date</span><Money value={Number(o.kpis.recovered_6m)} /></div>
              {o.kpis.claimable_now !== undefined && (
                <div><span><i style={{ background: "var(--amber)" }} />Still claimable now</span><Money value={Number(o.kpis.claimable_now)} /></div>
              )}
            </div>
            <Chart months={o.months} />
            <p className="cx-tiny">Unrecovered deductions can include fair charges; not all are owed back.</p>
          </>
        ) : (
          <p className="cx-small cx-muted">{overview.error ?? "Loading the last six months…"}</p>
        )}
      </section>

      <div className="cx-tiles">
        <Link className="cx-tile" href={view.question?.charge_id ? link("/review", { charge: view.question.charge_id }) : link("/review")}>
          <span className="cx-tile-top">Needs you · Owner</span>
          <strong>{asking}</strong>
          <span className="cx-small cx-muted">{asking ? "1 policy question from your agents." : "No open questions."}</span>
        </Link>
        <Link className="cx-tile" href={link("/approval")}>
          <span className="cx-tile-top">Accounting · {cast.owner}</span>
          <strong>{approving}</strong>
          <span className="cx-small cx-muted">{approving ? "Fair-charge entry awaiting your approval." : view.postingLabel}</span>
        </Link>
        <Link className="cx-tile" href={link("/review")}>
          <span className="cx-tile-top">Disputes</span>
          <strong>{disputes}</strong>
          <span className="cx-small cx-muted">{view.disputeLabel}</span>
        </Link>
      </div>

      <section>
        <div className="cx-head" style={{ marginBottom: 6 }}>
          <h2 style={{ fontSize: 15, fontWeight: 400 }}>Your accounts</h2>
        </div>
        <div className="cx-dist">
          {(accounts ?? []).map((a) => {
            const current = a.id === account?.id;
            return (
              <Link key={a.id} href={`/review?account=${encodeURIComponent(a.id)}`}>
                <b>{a.distributor.name[0]}</b>
                <span>
                  <span className="cx-dist-name">{a.distributor.name}</span><br />
                  <span className="cx-tiny">{a.brand.name} · invoice {a.invoice.id}{current && r ? ` · ${r.charge_count} deductions` : ""}</span>
                </span>
                <Pill tone={current && asking ? "amber" : "accent"} live={current && status === "Agents checking"}>
                  {current ? status : a.latest_run_id ? "Checked" : "Waiting for payment"}
                </Pill>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
              </Link>
            );
          })}
        </div>
      </section>
    </Shell>
  );
}
