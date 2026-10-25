"use client";

// One charge, decided: the agents' steps as they stream in (ChargeDrawer), and the owner's policy question when the
// deal leaves the charge to judgment (OwnerDecision). Opened from the run on `/`.

import Link from "next/link";
import { useState } from "react";
import { useChargeDetail } from "@/lib/useChargeDetail";
import type { ChargeView } from "@/lib/workspace";
import { agentSteps, doneCount } from "./agents";
import { useRun } from "./RunProvider";
import { KindTag, Money, Pill, StatusPill, StepDot } from "./ui";

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
          <Link className="cx-btn" href={link("/charges", { charge: charge.id })}>Open with every charge</Link>
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
      <label className="cx-check">
        <input type="checkbox" checked={saveRule} onChange={(e) => setSaveRule(e.target.checked)} />
        <span>Save as a rule for next time</span>
      </label>
      <p className="cx-small cx-muted">{saveRule
        ? "Saved as a rule for this distributor, so you’re never asked twice. This guides your agents; it doesn’t change the contract."
        : "Settles this charge only. Nothing is saved, so the next charge like it asks you again."}</p>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <button className="cx-btn" disabled={!picked} onClick={() => picked && answerQuestion(q.id, picked.text, saveRule)}>{saveRule ? "Save policy" : "Decide this charge"}</button>
        {!picked && <span className="cx-tiny">Choose an option first</span>}
      </div>
      <p className="cx-tiny">For {CAST.ownerFull}, admin. This is not the accounting approval: the charge stays open until it’s decided under your policy.</p>
    </aside>
  );
}
