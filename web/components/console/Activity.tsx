"use client";

// Agent activity (Figma: "Clawback · Agent activity"): every agent's step on one charge, with its sources and result.

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { money } from "@/lib/format";
import { useChargeDetail } from "@/lib/useChargeDetail";
import { agentSteps, doneCount } from "./agents";
import { useRun } from "./RunProvider";
import { Shell } from "./Shell";
import { clock, KindTag, Money, StatusPill, StepDot } from "./ui";

const noop = () => () => {};
function useQueryCharge() {
  return useSyncExternalStore(noop, () => new URLSearchParams(window.location.search).get("charge"), () => null);
}

export default function Activity() {
  const { view, state, source, cast: CAST, link } = useRun();
  const q = useQueryCharge();
  const charge = view.charges.find((c) => c.id === q) ?? view.charges[0] ?? null;
  const detail = useChargeDetail(charge?.id ?? "", state.run?.run_id, source);
  const steps = charge ? agentSteps(charge.id, state, detail) : [];
  const r = view.remittance;
  const headline = !charge
    ? "Agent activity"
    : charge.status === "Reviewing"
      ? `Checking ${charge.title.toLowerCase()}…`
      : charge.disputed
        ? `Why we recommend disputing ${money(charge.disputed)}`
        : charge.waiting
          ? "Why this one needs the owner"
          : "Why this charge is fair";

  return (
    <Shell crumbs={["Payments", r?.invoice_id ?? "—", "Agent activity"]}>
      <div className="cx-head">
        <div>
          <h1 className="cx-h1">{headline}</h1>
          <p className="cx-meta">{r ? `${r.counterparty} · ${r.invoice_id ?? ""}` : "Waiting for a payment"}</p>
        </div>
        <Link className="cx-btn is-ghost" href={charge ? link("/review", { charge: charge.id }) : link("/review")}>Back to payment</Link>
      </div>

      <nav className="cx-picker" aria-label="Choose a charge">
        {view.charges.map((c) => (
          <a key={c.id} href={link("/activity", { charge: c.id })} aria-current={c.id === charge?.id ? "true" : undefined}>{c.title}</a>
        ))}
      </nav>

      {charge && (
        <>
          <div className="cx-card cx-head" style={{ alignItems: "center" }}>
            <div>
              <span className="cx-eyebrow">Selected charge · {charge.ref}</span>
              <h2 style={{ fontSize: 17, fontWeight: 400, marginTop: 4 }}>{charge.title}</h2>
              <p className="cx-tiny" style={{ marginTop: 4 }}>{doneCount(steps)} of {steps.length} agents finished · {state.playing ? "run in progress" : "run paused or complete"}</p>
            </div>
            <StatusPill status={charge.status} />
          </div>

          <div className="cx-activity">
            <ol className="cx-timeline">
              {steps.map((s) => (
                <li key={s.agent} className={`cx-tl cx-step is-${s.state}`}>
                  <time>{clock(s.at)}</time>
                  <StepDot state={s.state} />
                  <div className="cx-tl-card">
                    <h3>
                      {s.agent} <KindTag kind={s.kind} />
                      {s.state === "done" ? <span className="cx-ok">✓ Complete</span> : s.state === "person" ? <span className="cx-wait" style={{ color: "var(--amber)" }}>Waiting on {CAST.owner}</span> : <span className="cx-wait">Waiting</span>}
                    </h3>
                    {s.evidence.length > 0 && <p className="cx-tiny">Evidence · {s.evidence.join(" · ")}</p>}
                    <p className="cx-small">Result · {s.result}</p>
                    {s.detail?.map((d) => <p key={d} className="cx-step-math">{d}</p>)}
                    {s.kind === "CODE" && s.state === "done" && <p className="cx-tiny" style={{ color: "var(--accent)" }}>Deterministic: all arithmetic runs in tested code, never in an AI model.</p>}
                  </div>
                </li>
              ))}
            </ol>

            <aside className="cx-card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <h3 style={{ fontSize: 15, fontWeight: 400 }}>{charge.status === "Reviewing" ? "Still checking" : "Ready, not sent"}</h3>
              <span className="cx-tiny">{charge.waiting ? "Waiting on the owner" : charge.disputed ? "Proposed dispute" : "Fair amount"}</span>
              <Money value={(charge.waiting || charge.disputed || charge.accepted) ?? 0} className="cx-big" />
              <p className="cx-small cx-muted">{CAST.owner} decides policy, then approves the accounting entry as a separate step.</p>
              {(detail?.evidence ?? []).slice(0, 3).map((e) => <span key={e.id} className="cx-small">↗ {e.label}</span>)}
              <Link className="cx-btn" href={link("/review", { charge: charge.id })}>Open in payment review</Link>
              <p className="cx-tiny">{view.disputeLabel}. No accounting entry posted from this screen.</p>
            </aside>
          </div>
        </>
      )}
    </Shell>
  );
}
