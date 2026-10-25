"use client";

// The run's seven steps, left to right: each with the agents who do it, a progress bar and one plain line. With
// `details`, a step opens what its agents did and concluded (AgentStrip.tsx), so this one row is both the progress
// and the agents. On a phone the compact rail is a row of seven marks with the current step spelled out under it.
// Built by stages.ts from the events; nothing here decides anything.

import { useState, type ReactNode } from "react";
import { CHECK } from "./parts";
import { focusStage, type Stage, type StageKey } from "./stages";

const WHO: Record<Stage["who"], string> = { AI: "AI", CODE: "Code", PERSON: "Person" };

function Bar({ stage }: { stage: Stage }) {
  if (stage.state === "done") return <div className="fl-bar"><i style={{ width: "100%" }} /></div>;
  if (stage.state !== "active") return <div className="fl-bar"><i style={{ width: 0 }} /></div>;
  if (stage.total) {
    // A stage at 0 of N still shows it has started.
    const pct = Math.max(6, Math.round(((stage.done ?? 0) / stage.total) * 100));
    return <div className="fl-bar" role="progressbar" aria-valuemin={0} aria-valuemax={stage.total} aria-valuenow={stage.done ?? 0}><i style={{ width: `${pct}%` }} /></div>;
  }
  return <div className="fl-bar is-indeterminate"><i /></div>;
}

function StageBody({ s }: { s: Stage }) {
  return (
    <>
      <div className="fl-stage-head">
        <span className="fl-mark" aria-hidden="true">{s.state === "done" ? CHECK : s.state === "skipped" ? "–" : s.state === "failed" ? "!" : s.state === "waiting" ? "?" : null}</span>
        <strong>{s.name}</strong>
        {s.total ? <span className="fl-count">{s.state === "done" ? s.total : s.done ?? 0}/{s.total}</span> : null}
      </div>
      <span className="fl-who">{WHO[s.who]} · {s.agent}</span>
      <span className="fl-line">{s.line}</span>
      <Bar stage={s} />
      <span className="sr-only"> · {s.state}</span>
    </>
  );
}

export function StageRail({ stages, compact = false, details }: { stages: Stage[]; compact?: boolean; details?: (key: StageKey) => ReactNode }) {
  const [open, setOpen] = useState<StageKey | null>(null);
  const now = compact ? focusStage(stages) : null;
  const shown = details && open ? stages.find((s) => s.key === open) ?? null : null;
  return (
    <>
      <ol className={`fl-rail ${compact ? "is-compact" : ""} ${details ? "is-open-able" : ""}`} aria-label="What the agents are doing">
        {stages.map((s) => (
          <li key={s.key} className={`fl-stage is-${s.state} ${open === s.key ? "is-open" : ""}`} aria-current={s.state === "active" || s.state === "waiting" ? "step" : undefined}>
            {details ? (
              <button className="fl-stage-btn" onClick={() => setOpen(open === s.key ? null : s.key)} aria-expanded={open === s.key} aria-label={`${s.name}: what its agents did`}>
                <StageBody s={s} />
              </button>
            ) : <StageBody s={s} />}
          </li>
        ))}
      </ol>
      {now && (
        <p className={`fl-rail-now is-${now.state}`} aria-hidden="true">
          <b>Step {stages.indexOf(now) + 1} of {stages.length} · {now.name}</b>
          {now.line}
        </p>
      )}
      {shown && details && (
        <div className="as-detail" role="region" aria-label={`${shown.name}: what its agents did`}>
          <div className="as-detail-head">
            <strong>{shown.name}</strong>
            <span>{shown.line}</span>
            <button className="cx-btn is-ghost" onClick={() => setOpen(null)}>Close</button>
          </div>
          {details(shown.key)}
        </div>
      )}
    </>
  );
}
