"use client";

// Payment review (Figma: "Clawback · Payment review" and "Clawback · Owner policy decision").
// Left: the deductions queue. Right: the selected charge, with the six agents' steps as they stream in.
// When the selected charge is the one waiting on the owner, the drawer becomes the owner's policy question.

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { CAST, OWNER_RULE_REPLY } from "@/lib/cast";
import { shortDate } from "@/lib/format";
import { useChargeDetail } from "@/lib/useChargeDetail";
import type { ChargeView } from "@/lib/workspace";
import { agentSteps, doneCount } from "./agents";
import { useRun } from "./RunProvider";
import { Shell } from "./Shell";
import { KindTag, Money, Pill, StatusPill, StepDot } from "./ui";

const noop = () => () => {};
/** ?charge=C6 from a link on Home or Agent activity, read without forcing the page to render dynamically. */
function useQueryCharge() {
  return useSyncExternalStore(noop, () => new URLSearchParams(window.location.search).get("charge"), () => null);
}

export default function Review() {
  const { view, state, source, awaitingPayment, startPayment, starting } = useRun();
  const fromQuery = useQueryCharge();
  const [picked, setPicked] = useState<string | null>(null);
  const r = view.remittance;
  const selectedId = picked ?? (fromQuery && view.charges.some((c) => c.id === fromQuery) ? fromQuery : view.charges[0]?.id) ?? null;
  const selected = view.charges.find((c) => c.id === selectedId) ?? null;
  const totals = view.totals;

  return (
    <Shell crumbs={["Payments", r?.invoice_id ?? "Waiting for payment"]} right={view.reviewed ? <Pill tone="accent">Review ready</Pill> : r ? <Pill live>Agents checking</Pill> : undefined}>
      <div className="cx-head">
        <div>
          <h1 className="cx-h1">{r?.counterparty ?? "Northmart"}</h1>
          <p className="cx-meta">
            {r ? `Invoice ${r.invoice_id ?? "—"}${r.received_at ? ` · Paid ${shortDate(r.received_at)}` : ""} · ${r.charge_count} charges taken` : "No payment has arrived yet."}
          </p>
        </div>
        {awaitingPayment && (
          <button className="cx-btn" disabled={starting} onClick={() => void startPayment()}>
            {starting ? "Starting…" : "Northmart pays"}
          </button>
        )}
      </div>

      {r && (
        <div className="cx-stats">
          <div className="cx-stat">
            <span className="cx-stat-label">Invoice billed</span>
            <Money value={r.expected} />
            <span className="cx-tiny">Original amount requested</span>
          </div>
          <div className="cx-stat is-green">
            <span className="cx-stat-label">Cash received</span>
            <Money value={r.received} />
            <span className="cx-tiny">Already in your account</span>
          </div>
          <div className="cx-stat is-amber">
            <span className="cx-stat-label">Deductions withheld</span>
            <Money value={r.taken} />
            <span className="cx-tiny">{r.charge_count} charges taken from this payment</span>
          </div>
        </div>
      )}

      <div className="cx-review">
        <section aria-labelledby="ded-h" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="cx-head" style={{ alignItems: "baseline" }}>
            <h2 id="ded-h" style={{ fontSize: 15, fontWeight: 400 }}>Deductions</h2>
            <span className="cx-small cx-muted">{view.charges.length} charges</span>
          </div>
          <div className="cx-list">
            {view.charges.map((c) => (
              <button key={c.id} className="cx-charge" aria-pressed={c.id === selectedId} onClick={() => setPicked(c.id)}>
                <span className="cx-charge-title">{c.title}</span>
                <span className="cx-charge-amt">
                  <Money value={c.amount} />
                </span>
                <span className="cx-charge-why">{c.reason}</span>
                <StatusPill status={c.status} />
              </button>
            ))}
            {view.charges.length === 0 && <div className="cx-card cx-muted">{awaitingPayment ? "Waiting for Northmart’s payment. Nothing is checked until it arrives." : "Loading the run…"}</div>}
          </div>

          {totals && (
            <div className="cx-card">
              <h3 style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Where the deductions stand</h3>
              <div className="cx-rows">
                <div><span>Confirmed fair</span><Money value={totals.accepted} /></div>
                <div><span>Recommended dispute</span><Money value={totals.disputed} /></div>
                <div><span>Needs owner policy</span><Money value={totals.waiting} /></div>
              </div>
              <p className="cx-tiny" style={{ marginTop: 8 }}>Proposed outcomes, not recovered cash. Fair charges still need {CAST.controller}’s accounting approval.</p>
            </div>
          )}
          <Link href={`/activity${selectedId ? `?charge=${selectedId}` : ""}`} className="cx-small">View full agent activity →</Link>
          <p className="cx-tiny">{CAST.owner} · Owner: policy and disputes / {CAST.controller} · Bookkeeper: accounting approval</p>
        </section>

        {selected && (
          view.question && !view.question.answer && view.question.charge_id === selected.id
            ? <OwnerDecision charge={selected} />
            : <ChargeDrawer charge={selected} onClose={() => setPicked(null)} key={selected.id} source={source} runId={state.run?.run_id} />
        )}
      </div>
    </Shell>
  );
}

function ChargeDrawer({ charge, onClose, source, runId }: { charge: ChargeView; onClose: () => void; source: "fixture" | "live"; runId: string | undefined }) {
  const { state, view } = useRun();
  const detail = useChargeDetail(charge.id, runId, source);
  const steps = agentSteps(charge.id, state, detail);
  const clause = detail?.evidence.find((e) => e.kind === "clause") ?? null;
  const decided = charge.accepted !== null;

  return (
    <aside className="cx-drawer" aria-label={`${charge.title} detail`}>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <span className="cx-eyebrow">Deduction detail · {charge.ref}</span>
        <button className="cx-drawer-close" onClick={onClose} aria-label="Back to the first charge">✕</button>
      </div>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <h2>{charge.title}</h2>
        <StatusPill status={charge.status} />
      </div>
      <p className="cx-muted" style={{ fontSize: 13 }}>{charge.finding}</p>

      <div className="cx-split">
        <span className="cx-small">How the {<Money value={charge.amount} />} deduction splits</span>
        <div className="cx-split-row">
          <div><small>Taken</small><Money value={charge.amount} /><small>By the distributor</small></div>
          <div className="is-green"><small>Fair</small>{decided ? <Money value={charge.accepted ?? 0} /> : <span>…</span>}<small>Keep as a charge</small></div>
          <div className="is-accent"><small>{charge.waiting ? "Waiting on owner" : "To dispute"}</small>{decided ? <Money value={(charge.waiting || charge.disputed) ?? 0} /> : <span>…</span>}<small>{charge.waiting ? "Not decided" : "Proposed"}</small></div>
        </div>
      </div>

      {clause && (
        <div className="cx-quote">
          <div className="cx-head"><span className="cx-tiny">Signed deal</span><span className="cx-tiny" style={{ color: "var(--accent)" }}>{clause.label}</span></div>
          <blockquote>“{clause.quote?.text ?? clause.summary}”</blockquote>
        </div>
      )}

      <section aria-labelledby="how-h">
        <div className="cx-head" style={{ marginBottom: 12 }}>
          <h3 id="how-h" style={{ fontSize: 13, fontWeight: 500 }}>How we got here</h3>
          <span className="cx-tiny">{doneCount(steps)} of {steps.length} checks complete</span>
        </div>
        <ol className="cx-steps">
          {steps.map((s) => (
            <li key={s.agent} className={`cx-step is-${s.state}`}>
              <span className="cx-step-rail"><StepDot state={s.state} /><span className="cx-step-line" /></span>
              <div className="cx-step-body">
                <span className="cx-step-name">{s.agent} <KindTag kind={s.kind} /></span>
                <span className="cx-step-result">{s.result}</span>
                {s.detail?.map((d) => <span key={d} className="cx-step-math">{d}</span>)}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <div className="cx-next">
        <strong style={{ fontSize: 13, fontWeight: 500 }}>{nextTitle(charge)}</strong>
        <p className="cx-small cx-muted">{nextLine(charge, view.disputeLabel)}</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="cx-btn" href={`/activity?charge=${charge.id}`}>See every agent step</Link>
          {charge.accepted ? <Link className="cx-btn is-ghost" href="/approval">Accounting approval</Link> : null}
        </div>
      </div>
    </aside>
  );
}

function nextTitle(c: ChargeView) {
  if (c.status === "Reviewing") return "Agents are still checking";
  if (c.status === "Accepted") return "Fair charge: nothing to fight";
  if (c.status === "Needs your input") return "Decided by your rule";
  return "Dispute prepared with proof";
}
function nextLine(c: ChargeView, disputeLabel: string) {
  if (c.status === "Reviewing") return "Each step fills in as its agent finishes.";
  if (c.status === "Accepted") return `Goes into the bookkeeper’s approval. Nothing posts until ${CAST.controller} says yes.`;
  return `${disputeLabel}. Fair parts go to ${CAST.controller}’s accounting approval separately.`;
}

const CHOICES = [
  { id: "rule", label: "Accept when notice is at least 14 days", text: OWNER_RULE_REPLY, recorded: true },
  { id: "always", label: "Always dispute these fees", text: "always dispute", recorded: false },
  { id: "each", label: "Ask me each time", text: "ask me each time", recorded: false },
];

function OwnerDecision({ charge }: { charge: ChargeView }) {
  const { state, view, source, answerQuestion } = useRun();
  const detail = useChargeDetail(charge.id, state.run?.run_id, source);
  const [choice, setChoice] = useState<string | null>(null);
  const finding = state.findings[charge.id];
  const clause = detail?.evidence.find((e) => e.kind === "clause") ?? null;
  const picked = CHOICES.find((c) => c.id === choice) ?? null;
  const q = view.question!;

  return (
    <aside className="cx-drawer" aria-label="Owner policy needed">
      <span className="cx-eyebrow">Owner policy needed</span>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <h2>{charge.title}</h2>
        <Pill tone="amber">Ask owner</Pill>
      </div>
      <div className="cx-head" style={{ alignItems: "flex-end" }}>
        <div><span className="cx-tiny">Entire charge unresolved</span><br /><Money value={charge.amount} className="cx-big" /></div>
        <span className="cx-tiny">Excluded from posting</span>
      </div>
      {clause && (
        <div className="cx-quote is-marked">
          <div className="cx-head"><span className="cx-tiny">Signed deal</span><span className="cx-tiny" style={{ color: "var(--accent)" }}>{clause.label}</span></div>
          <blockquote>“{clause.quote?.text ?? clause.summary}”</blockquote>
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong style={{ fontWeight: 500, fontSize: 13 }}>{finding && !finding.readers_agree ? "Two readers. Different interpretations." : "The deal leaves this to judgment."}</strong>
        <p className="cx-small cx-muted">{finding?.finding ?? charge.finding}</p>
        <p className="cx-small" style={{ color: "var(--accent-ink)" }}>The agents won’t guess your policy. You decide once, and it becomes a rule.</p>
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        <legend style={{ fontSize: 17, marginBottom: 10 }}>How should Clawback handle charges like this?</legend>
        {CHOICES.map((c) => {
          const off = !c.recorded;
          return (
            <span key={c.id} role="radio" tabIndex={off ? -1 : 0} className="cx-choice" aria-checked={choice === c.id} aria-disabled={off}
              onClick={() => !off && setChoice(c.id)}
              onKeyDown={(e) => { if (!off && (e.key === " " || e.key === "Enter")) { e.preventDefault(); setChoice(c.id); } }}>
              <span className="cx-radio" />
              {c.label}
              {off && <span className="cx-tiny" style={{ marginLeft: "auto" }}>Not in this demo</span>}
            </span>
          );
        })}
      </fieldset>
      <p className="cx-small cx-muted">Saved as a rule for this distributor, so you’re never asked twice. This guides your agents; it doesn’t change the contract.</p>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <button className="cx-btn" disabled={!picked} onClick={() => picked && answerQuestion(q.id, picked.text)}>Save policy</button>
        {!picked && <span className="cx-tiny">Choose an option first</span>}
      </div>
      <p className="cx-tiny">For {CAST.ownerFull}, owner. This is not accounting approval: the charge stays open until it’s decided under your policy.</p>
    </aside>
  );
}
