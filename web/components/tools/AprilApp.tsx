"use client";

import { useMemo, useState } from "react";
import { APRIL_EVENTS } from "@/lib/fixture";
import { dollars } from "@/lib/format";
import * as api from "@/lib/live";
import { DATA_SOURCE, useRunEvents } from "@/lib/useRunEvents";
import { selectWorkspace } from "@/lib/workspace";
import { ChargeList } from "@/components/workspace/charge-workspace";

/** Follows one April run. Mounted with a run id from POST /replay/april (live) or on its own from the recording (fixture). */
function AprilRun({ runId }: { runId: string }) {
  const { state, source, error } = useRunEvents(runId, DATA_SOURCE, DATA_SOURCE === "fixture" ? APRIL_EVENTS : undefined);
  const view = useMemo(() => selectWorkspace(state, source), [state, source]);
  const rule = Object.values(state.rules).find((r) => r.status === "active");
  const asked = state.totals?.questions ?? Object.keys(state.questions).length;
  const open = Object.values(state.questions).find((q) => !q.answer);

  return (
    <>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {open && (
        <section className="surface tool-card" aria-label="Question for the owner">
          <h2>Rule #1 isn&apos;t saved yet</h2>
          <p>{open.text}</p>
          <p className="muted">Answer it on the workspace first (March), then replay April.</p>
        </section>
      )}
      <section className="surface tool-card" aria-label="April totals">
        <div className="tool-stats big">
          <div><span>Accepted</span><strong>{dollars(view.totals?.accepted ?? 0)}</strong></div>
          <div><span>Disputed</span><strong>{dollars(view.totals?.disputed ?? 0)}</strong></div>
          <div><span>Questions asked</span><strong>{asked}</strong></div>
        </div>
        {rule && <p className="muted">{rule.label} applied: {rule.summary}</p>}
      </section>
      <section className="surface preview-section">
        <div className="list-heading"><div><h2>April fees</h2><p>Decided by the owner&apos;s saved rule, not by asking again.</p></div></div>
        <ChargeList charges={view.charges} onSelect={() => undefined} preview />
      </section>
      {view.reviewed && !open && <p className="tool-closing">{asked === 0 ? "0 questions asked." : `${asked} ${asked === 1 ? "question" : "questions"} asked.`}</p>}
    </>
  );
}

export default function AprilApp() {
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      setRunId((await api.replayApril()).run_id);
    } catch (e) {
      setError(`Couldn't start April (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  if (DATA_SOURCE === "fixture") return <AprilRun runId="april" />;
  return (
    <>
      <div className="tool-actions">
        <button className="primary" onClick={start} disabled={busy}>{busy ? "Starting…" : runId ? "Replay April again" : "Replay April"}</button>
      </div>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {runId && <AprilRun key={runId} runId={runId} />}
    </>
  );
}
