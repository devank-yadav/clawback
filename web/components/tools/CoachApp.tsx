"use client";

import { useState } from "react";
import { FIXTURE_COACH } from "@/lib/fixture";
import { dollars } from "@/lib/format";
import * as api from "@/lib/live";
import type { CoachResponse } from "@/lib/types";
import { DATA_SOURCE } from "@/lib/useRunEvents";

/** Redlines are suggestions only: there is deliberately no send button. */
export default function CoachApp() {
  const [coach, setCoach] = useState<CoachResponse | null>(DATA_SOURCE === "fixture" ? FIXTURE_COACH : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setCoach(await api.fetchCoach());
    } catch (e) {
      setError(`The Deal Coach didn't answer (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="tool-actions">
        {DATA_SOURCE === "live" && <button className="primary" onClick={run} disabled={busy}>{busy ? "Reading the draft…" : coach ? "Redline again" : "Redline the summer draft"}</button>}
        {DATA_SOURCE === "fixture" && <span className="muted">Recorded example · fixture data</span>}
      </div>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {coach?.redlines.map((r, i) => (
        <section className="surface tool-card redline" key={`${r.clause_ref}-${i}`} aria-label={`Redline for ${r.clause_ref}`}>
          <div className="tool-row">
            <h2>{r.clause_ref}</h2>
            <strong className="tool-cost">This clause cost {dollars(r.dollars_at_stake)} in March</strong>
          </div>
          <small className="tool-label">Now says</small>
          <blockquote className="struck"><del>{r.original_quote}</del></blockquote>
          <small className="tool-label">Suggested</small>
          <blockquote className="suggest"><ins>{r.suggested_text}</ins></blockquote>
          <p className="muted">{r.reason}</p>
        </section>
      ))}
      {coach && coach.redlines.length === 0 && <p className="muted">No redlines for this draft.</p>}
      {coach && <p className="muted small">Suggestions only. Clawback never sends a redline to anyone.</p>}
    </>
  );
}
