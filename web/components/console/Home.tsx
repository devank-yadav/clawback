"use client";

// Home (Figma: "Clawback · Home"). Live tiles come from the run; the six-month chart and the other two
// distributors are example data (the API doesn't track history across payments yet) and are labelled that way.

import Link from "next/link";
import { CAST } from "@/lib/cast";
import { useRun } from "./RunProvider";
import { Shell } from "./Shell";
import { Money, Pill } from "./ui";

const MONTHS = ["May", "Jun", "Jul", "Aug", "Sep", "Oct"];
// Example history only (thousands of dollars), drawn as a chart; never used as accounting data.
const TAKEN = [3.6, 4.3, 5.2, 5.4, 5.1, 5.5];
const BACK = [1.9, 2.4, 2.9, 3.7, 3.6, 4.4];

function Chart() {
  const W = 760, H = 200, P = 34, max = 6;
  const x = (i: number) => P + (i * (W - P * 2)) / (MONTHS.length - 1);
  const y = (v: number) => H - 24 - (v / max) * (H - 44);
  const line = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
  return (
    <svg className="cx-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Example chart: money withheld and money recovered by month, May to October">
      {[0, 3, 6].map((v) => (
        <g key={v}>
          <line x1={P} x2={W - P} y1={y(v)} y2={y(v)} stroke="#333542" />
          <text x={0} y={y(v) + 4} fill="#8b8ea3" fontSize="10">${v}k</text>
        </g>
      ))}
      <path d={`${line(BACK)} L${x(5)},${y(0)} L${x(0)},${y(0)} Z`} fill="#777cff" opacity="0.12" />
      <path d={line(TAKEN)} fill="none" stroke="#a1a3b4" strokeWidth="2" />
      <path d={line(BACK)} fill="none" stroke="#777cff" strokeWidth="2" />
      {MONTHS.map((m, i) => (
        <text key={m} x={x(i)} y={H - 4} fill="#8b8ea3" fontSize="10" textAnchor="middle">{m}</text>
      ))}
    </svg>
  );
}

export default function Home() {
  const { view } = useRun();
  const r = view.remittance;
  const asking = view.question && !view.question.answer ? 1 : 0;
  const approving = view.approval?.status === "pending" ? 1 : 0;
  const disputes = view.charges.filter((c) => (c.disputed ?? 0) > 0).length;
  const status = asking ? "Needs your decision" : approving ? "Controller review" : view.reviewed ? "Review ready" : r ? "Agents checking" : "Waiting for payment";

  return (
    <Shell crumbs={["Overview"]} right="Fictional demo data">
      <div className="cx-head">
        <div>
          <h1 className="cx-h1">Good afternoon, {CAST.owner}</h1>
          <p className="cx-meta">Your recovery overview · {CAST.brand}</p>
        </div>
        <Link className="cx-btn" href="/review">Review latest payment</Link>
      </div>

      <section className="cx-card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div className="cx-head">
          <h2 style={{ fontSize: 15, fontWeight: 400 }}>Money withheld and money recovered</h2>
          <Pill>Example data · May–Oct</Pill>
        </div>
        <div className="cx-legend">
          <div><span><i style={{ background: "#a1a3b4" }} />Deducted from payments</span><Money value={28640} /></div>
          <div><span><i style={{ background: "#777cff" }} />Recovered to date</span><Money value={18420} /></div>
        </div>
        <Chart />
        <p className="cx-tiny">Illustrative six-month history. Unrecovered deductions can include fair charges; not all are owed back.</p>
      </section>

      <div className="cx-tiles">
        <Link className="cx-tile" href={view.question ? `/review?charge=${view.question.charge_id}` : "/review"}>
          <span className="cx-tile-top">Needs you · Owner</span>
          <strong>{asking}</strong>
          <span className="cx-small cx-muted">{asking ? "1 policy question from your agents." : "No open questions."}</span>
        </Link>
        <Link className="cx-tile" href="/approval">
          <span className="cx-tile-top">Accounting · {CAST.controller}</span>
          <strong>{approving}</strong>
          <span className="cx-small cx-muted">{approving ? "Fair-charge entry awaiting the bookkeeper." : view.postingLabel}</span>
        </Link>
        <Link className="cx-tile" href="/review">
          <span className="cx-tile-top">Disputes</span>
          <strong>{disputes}</strong>
          <span className="cx-small cx-muted">{view.disputeLabel}</span>
        </Link>
      </div>

      <section>
        <div className="cx-head" style={{ marginBottom: 6 }}>
          <h2 style={{ fontSize: 15, fontWeight: 400 }}>Your distributors</h2>
        </div>
        <div className="cx-dist">
          <Link href="/review">
            <b>{(r?.counterparty ?? "Northmart")[0]}</b>
            <span><span className="cx-dist-name">{r?.counterparty ?? "Northmart"}</span><br /><span className="cx-tiny">{r ? `${r.invoice_id} · ${r.charge_count} deductions` : "Waiting for the next payment"}</span></span>
            <Pill tone={asking ? "amber" : "accent"} live={status === "Agents checking"}>{status}</Pill>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
          </Link>
          {[["Greenline Organics", "Fair charges · example"], ["Harvest Wholesale", "Dispute in progress · example"]].map(([n, s]) => (
            <Link key={n} href="/home" aria-disabled="true">
              <b>{n[0]}</b>
              <span><span className="cx-dist-name">{n}</span><br /><span className="cx-tiny">Example distributor</span></span>
              <Pill>{s}</Pill>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
            </Link>
          ))}
        </div>
      </section>
    </Shell>
  );
}
