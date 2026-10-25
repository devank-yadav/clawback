"use client";

// The run's centerpiece: the stage the agents are on right now, big. Its step, who is working (pulsing while they
// work), what they're doing this second, their own last lines streaming in, and how far along they are. The rail of
// all seven stages sits under it as context. Wording only: every line and count arrived in an event.

import type { FeedLine } from "@/lib/useRunEvents";
import type { Stage, StageKey } from "./stages";

const ACTORS: Record<StageKey, string[]> = {
  payment: ["system"], read: ["reader"], check: ["investigator", "negotiator", "gate", "policy"], file: ["negotiator"],
  owner: ["owner", "gate", "policy"], approval: ["owner", "bookkeeper"], books: ["bookkeeper"],
};

const VERB: Partial<Record<StageKey, string>> = {
  payment: "Receiving the payment", read: "Reading the deal", check: "Checking every charge", file: "Filing the dispute",
  books: "Posting to QuickBooks",
};

export function StageHero({ stage, stages, feed, done }: { stage: Stage | null; stages: Stage[]; feed: FeedLine[]; done: boolean }) {
  if (!stage) {
    return (
      <section className="sh is-done" aria-live="polite">
        <span className="sh-step">All {stages.length} stages</span>
        <h2>{done ? "The agents are finished" : "The agents are getting ready"}</h2>
        <p className="sh-line">{done ? "Every charge has a decision with its proof. The result is below." : "Starting up…"}</p>
      </section>
    );
  }
  const index = stages.findIndex((s) => s.key === stage.key) + 1;
  const person = stage.who === "PERSON";
  const waiting = stage.state === "waiting";
  const agents = stage.agent.split(/\s[·+]\s/).filter(Boolean);
  const mine = feed.filter((l) => ACTORS[stage.key].includes(l.actor)).slice(-4);
  const pct = stage.total ? Math.max(4, Math.round(((stage.done ?? 0) / stage.total) * 100)) : null;

  return (
    <section className={`sh ${waiting ? "is-waiting" : "is-working"} ${stage.state === "failed" ? "is-failed" : ""}`} aria-live="polite" aria-label="What the agents are doing now">
      <div className="sh-top">
        <span className="sh-step">Step {index} of {stages.length}</span>
        <span className={`sh-badge ${waiting ? "is-amber" : ""}`}>{waiting ? (person ? "Waiting on you" : "Paused") : stage.state === "failed" ? "Stopped" : "Working now"}</span>
      </div>
      <h2>{waiting && person ? "Your call" : VERB[stage.key] ?? stage.name}</h2>
      <div className="sh-agents">
        {agents.map((a) => (
          <span key={a} className={`sh-agent ${stage.who === "CODE" ? "is-code" : person ? "is-person" : ""} ${!waiting && stage.state === "active" ? "is-on" : ""}`}>
            <i aria-hidden="true" />{a}<em>{stage.who === "CODE" ? "code" : person ? "you" : "AI"}</em>
          </span>
        ))}
      </div>
      <p className="sh-line">{stage.line}</p>
      {pct !== null && (
        <div className="sh-progress" role="progressbar" aria-valuemin={0} aria-valuemax={stage.total ?? 0} aria-valuenow={stage.done ?? 0}>
          <div><i style={{ width: `${pct}%` }} /></div>
          <span>{stage.done ?? 0} of {stage.total}</span>
        </div>
      )}
      {pct === null && !waiting && stage.state === "active" && <div className="sh-progress is-indeterminate"><div><i /></div></div>}
      {mine.length > 0 && (
        <ol className="sh-ticker">
          {mine.map((l) => <li key={l.id} className={l.level}>{l.text}</li>)}
        </ol>
      )}
    </section>
  );
}
