"use client";

// The run's seven stages, left to right (top to bottom on a phone): each with who does it, a progress bar and one
// plain line. Built by stages.ts from the events; nothing here decides anything.

import { CHECK } from "./parts";
import type { Stage } from "./stages";

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

export function StageRail({ stages, compact = false }: { stages: Stage[]; compact?: boolean }) {
  return (
    <ol className={`fl-rail ${compact ? "is-compact" : ""}`} aria-label="What the agents are doing">
      {stages.map((s) => (
        <li key={s.key} className={`fl-stage is-${s.state}`} aria-current={s.state === "active" || s.state === "waiting" ? "step" : undefined}>
          <div className="fl-stage-head">
            <span className="fl-mark" aria-hidden="true">{s.state === "done" ? CHECK : s.state === "skipped" ? "–" : s.state === "failed" ? "!" : s.state === "waiting" ? "?" : null}</span>
            <strong>{s.name}</strong>
            {s.total ? <span className="fl-count">{s.state === "done" ? s.total : s.done ?? 0}/{s.total}</span> : null}
          </div>
          <span className="fl-who">{WHO[s.who]} · {s.agent}</span>
          <span className="fl-line">{s.line}</span>
          <Bar stage={s} />
          <span className="sr-only"> · {s.state}</span>
        </li>
      ))}
    </ol>
  );
}
