"use client";

import { useMemo, useState } from "react";
import { KeyRound } from "lucide-react";
import ToolFrame from "./ToolFrame";
import { dollars } from "@/lib/format";
import * as api from "@/lib/api";
import { askAdminToken, LIMIT_ADMIN_REASON, limitMessage } from "@/lib/session";
import type { Account } from "@/lib/types";
import { useRunEvents } from "@/lib/useRunEvents";
import { selectWorkspace } from "@/lib/workspace";
import { ChargeList } from "@/components/workspace/charge-workspace";

/** Follows one next-month run, started by POST /replay/april. */
function NextMonthRun({ account, runId }: { account: Account; runId: string }) {
  const { state, error } = useRunEvents(account.id, runId);
  const view = useMemo(() => selectWorkspace(state, account), [state, account]);
  const rules = Object.values(state.rules).filter((r) => r.status === "active");
  const asked = state.totals?.questions ?? Object.keys(state.questions).length;
  const open = Object.values(state.questions).find((q) => !q.answer);

  return (
    <>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {open && (
        <section className="surface tool-card" aria-label="Question for the owner">
          <h2>No saved rule covers this yet</h2>
          <p>{open.text}</p>
          <p className="muted">{account.brand.owner.name} answers it once on this month’s payment; next month uses the answer.</p>
        </section>
      )}
      <section className="surface tool-card" aria-label="Next month totals">
        <div className="tool-stats big">
          <div><span>Accepted</span><strong>{dollars(view.totals?.accepted ?? 0)}</strong></div>
          <div><span>Disputing</span><strong>{dollars(view.totals?.disputed ?? 0)}</strong></div>
          <div><span>Questions asked</span><strong>{asked}</strong></div>
        </div>
        {rules.map((r) => <p key={r.id} className="muted">{r.label} applied: {r.summary}</p>)}
      </section>
      <section className="surface preview-section">
        <div className="list-heading"><div><h2>Next month’s charges</h2><p>Decided by the rules {account.brand.owner.name} already set, without asking again.</p></div></div>
        <ChargeList charges={view.charges} onSelect={() => undefined} preview pending={view.remittance ? view.remittance.charge_count - view.charges.length : 0} />
      </section>
      {view.reviewed && !open && <p className="tool-closing">{asked === 0 ? "No questions asked." : `${asked} ${asked === 1 ? "question" : "questions"} asked.`}</p>}
    </>
  );
}

function NextMonth({ account }: { account: Account }) {
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    setLimited(null);
    try {
      setRunId((await api.replayNextMonth(account.id)).run_id);
    } catch (e) {
      const limit = limitMessage(e);
      if (limit) setLimited(limit);
      else setError(`Couldn't start next month (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="tool-actions">
        <button className="primary" onClick={start} disabled={busy}>{busy ? "Starting…" : runId ? "Run next month again" : "Run next month"}</button>
      </div>
      {limited && <div className="feedback notice" role="status"><span>{limited}</span><button className="text-button" onClick={() => askAdminToken(LIMIT_ADMIN_REASON, () => void start())}><KeyRound /> Use admin token</button></div>}
      {error && <p className="feedback error" role="alert">{error}</p>}
      {!runId && !busy && <p className="muted">Next month’s charges from {account.distributor.name}, checked with the rules saved so far.</p>}
      {runId && <NextMonthRun key={runId} account={account} runId={runId} />}
    </>
  );
}

export default function AprilApp() {
  return (
    <ToolFrame href="/april" title="Next month" lead={(a) => `${a.distributor.name}’s next charges, decided by the rules ${a.brand.owner.name} saved.`}>
      {(account) => <NextMonth account={account} />}
    </ToolFrame>
  );
}
