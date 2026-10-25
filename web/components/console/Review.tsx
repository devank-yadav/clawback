"use client";

// Payment review (Figma: "Clawback · Payment review" and "Clawback · Owner policy decision").
// Left: the deductions queue. Right: the selected charge, with the six agents' steps as they stream in.
// When the selected charge is the one waiting on the owner, the drawer becomes the owner's policy question.

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { money, shortDate } from "@/lib/format";
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
  const { view, state, source, awaitingPayment, startPayment, starting, limited, cast: CAST, link } = useRun();
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
          <h1 className="cx-h1">{r?.counterparty ?? CAST.distributor}</h1>
          <p className="cx-meta">
            {r ? `Invoice ${r.invoice_id ?? "—"}${r.received_at ? ` · Paid ${shortDate(r.received_at)}` : ""} · ${r.charge_count} charges taken` : "No payment has arrived yet."}
          </p>
        </div>
        {awaitingPayment && (
          <button className="cx-btn" disabled={starting} onClick={() => void startPayment()}>
            {starting ? "Starting…" : `${CAST.distributor} pays`}
          </button>
        )}
      </div>
      {limited && <div className="cx-card" role="status">{limited}</div>}

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
            {view.charges.length === 0 && <div className="cx-card cx-muted">{awaitingPayment ? `Waiting for ${CAST.distributor}’s payment. Nothing is checked until it arrives.` : "Loading the run…"}</div>}
          </div>

          {totals && (
            <div className="cx-card">
              <h3 style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Where the deductions stand</h3>
              <div className="cx-rows">
                <div><span>Confirmed fair</span><Money value={totals.accepted} /></div>
                <div><span>Recommended dispute</span><Money value={totals.disputed} /></div>
                <div><span>Needs owner policy</span><Money value={totals.waiting} /></div>
              </div>
              <p className="cx-tiny" style={{ marginTop: 8 }}>Proposed outcomes, not recovered cash. Fair charges still need your accounting approval.</p>
            </div>
          )}
          <Link href={selectedId ? link("/activity", { charge: selectedId }) : link("/activity")} className="cx-small">View full agent activity →</Link>
          <p className="cx-tiny">{CAST.ownerFull} · Admin: policy, disputes and accounting approval</p>
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

export function ChargeDrawer({ charge, onClose, source, runId }: { charge: ChargeView; onClose: () => void; source: "fixture" | "live"; runId: string | undefined }) {
  const { state, view, link } = useRun();
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
          <div className="is-fair"><small>Fair</small>{decided ? <Money value={charge.accepted ?? 0} /> : <span>…</span>}<small>Keep as a charge</small></div>
          <div className="is-dispute"><small>{charge.waiting ? "Waiting on owner" : "To dispute"}</small>{decided ? <Money value={(charge.waiting || charge.disputed) ?? 0} /> : <span>…</span>}<small>{charge.waiting ? "Not decided" : "Proposed"}</small></div>
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
          <Link className="cx-btn" href={link("/activity", { charge: charge.id })}>See every agent step</Link>
          {charge.accepted ? <Link className="cx-btn is-ghost" href={link("/approval")}>Accounting approval</Link> : null}
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
  if (c.status === "Accepted") return "Goes into your accounting approval. Nothing posts until you say yes.";
  return `${disputeLabel}. Fair parts go to your accounting approval separately.`;
}

/** The owner's choices: the replies the API reads (api/replies.py). A rule is saved and remembered; "this one" settles
 * only this charge. The display-fee rule is the wording the recorded demo expects, word for word. */
function choicesFor(code: string) {
  const rule = code === "DF"
    ? [{ id: "rule", label: "Accept when notice is at least 14 days", text: "accept if notice is at least 14 days" }]
    : [];
  return [...rule,
    { id: "accept", label: "Accept this one", text: code === "DF" ? "accept" : "accept it this time" },
    { id: "dispute", label: "Dispute this one", text: "dispute it" }];
}

export function OwnerDecision({ charge }: { charge: ChargeView }) {
  const { state, view, source, answerQuestion, cast: CAST } = useRun();
  const detail = useChargeDetail(charge.id, state.run?.run_id, source);
  const [choice, setChoice] = useState<string | null>(null);
  const finding = state.findings[charge.id];
  const clause = detail?.evidence.find((e) => e.kind === "clause") ?? null;
  const choices = choicesFor(charge.code);
  const [own, setOwn] = useState("");
  const [saveRule, setSaveRule] = useState(true);
  const picked = choice === "own" ? (own.trim() ? { id: "own", label: own, text: own.trim() } : null) : choices.find((c) => c.id === choice) ?? null;
  const q = view.question!;
  const risk = q.risk ?? null;
  const level = risk ? LEVEL[String(risk.level).toLowerCase()] ?? null : null;
  const kind = risk ? KIND[String(risk.kind).toLowerCase()] ?? String(risk.kind) : null;
  const disagree = !!finding && !finding.readers_agree;
  // One sentence of why: the risk's reason, else what the agents concluded.
  const reason = risk?.reason ?? (disagree ? "Two readers read this term differently, so the agents won’t pick one." : "The deal leaves this to judgment, so the agents won’t guess your policy.");
  // Everything else waits behind "Show details": the API's own details when it sends them, else what the card used to say.
  const details: { label: string; value: string }[] = [
    { label: "Charge", value: `${charge.title} · ${money(charge.amount)}, held out of posting until you decide` },
    ...(q.details ?? []),
    ...(!q.details?.length ? [{ label: "What the agents found", value: finding?.finding ?? charge.finding ?? "" }] : []),
    ...(clause ? [{ label: `Signed deal ${clause.label}`, value: `“${clause.quote?.text ?? clause.summary}”` }] : []),
    { label: "Your answer", value: saveRule ? "Saved as a rule for this distributor, so you’re never asked twice. It guides the agents; it doesn’t change the contract." : "Settles this charge only; the next one like it asks again." },
    { label: "Who decides", value: `${CAST.ownerFull}, admin. This isn’t the accounting approval, which comes after.` },
  ].filter((d) => d.value);

  return (
    <aside className={`dc ${level ? `is-${level.tone}` : ""}`} aria-label="A decision for you">
      <div className="dc-top">
        {level && <span className={`dc-level is-${level.tone}`}>{level.icon}{level.word}</span>}
        {kind && <span className="dc-kind">{kind}</span>}
        {!level && <span className="dc-kind">Your decision</span>}
        <span className="dc-charge">{charge.title} · <Money value={charge.amount} /></span>
      </div>
      <p className="dc-reason">{reason}</p>
      <fieldset className="dc-choices">
        <legend>How should Clawback handle charges like this?</legend>
        {choices.map((c) => (
          <span key={c.id} role="radio" tabIndex={0} className="cx-choice" aria-checked={choice === c.id}
            onClick={() => setChoice(c.id)}
            onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); setChoice(c.id); } }}>
            <span className="cx-radio" />
            {c.label}
          </span>
        ))}
        <span role="radio" tabIndex={0} className="cx-choice" aria-checked={choice === "own"} onClick={() => setChoice("own")}
          onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); setChoice("own"); } }}>
          <span className="cx-radio" />
          <input className="cx-note" style={{ flex: 1, minHeight: 0 }} placeholder="Or write your own rule" value={own}
            onFocus={() => setChoice("own")} onChange={(e) => setOwn(e.target.value)} aria-label="Your own rule" />
        </span>
      </fieldset>
      <div className="dc-actions">
        <label className="cx-check">
          <input type="checkbox" checked={saveRule} onChange={(e) => setSaveRule(e.target.checked)} />
          <span>Save as a rule</span>
        </label>
        <button className="cx-btn" disabled={!picked} title={picked ? undefined : "Choose an option first"} onClick={() => picked && answerQuestion(q.id, picked.text, saveRule)}>{saveRule ? "Save policy" : "Decide this charge"}</button>
      </div>
      <details className="dc-details">
        <summary>Show details</summary>
        <dl>
          {details.map((d) => <div key={d.label}><dt>{d.label}</dt><dd>{d.value}</dd></div>)}
        </dl>
      </details>
    </aside>
  );
}

const LEVEL: Record<string, { word: string; tone: "high" | "medium" | "low"; icon: React.ReactNode }> = {
  high: { word: "High", tone: "high", icon: <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 15 14H1z" fill="currentColor" /><path d="M8 6v3.5M8 11.4v.1" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" /></svg> },
  medium: { word: "Medium", tone: "medium", icon: <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="currentColor" /><path d="M8 4.6v4M8 11v.1" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" /></svg> },
  low: { word: "Low", tone: "low", icon: <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M5.3 8h5.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg> },
};
const KIND: Record<string, string> = { financial: "Financial", legal: "Legal", deadline: "Deadline", relationship: "Relationship" };
