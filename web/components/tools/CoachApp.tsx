"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";
import ToolFrame from "./ToolFrame";
import { dollars, monthLabel } from "@/lib/format";
import * as api from "@/lib/api";
import { askAdminToken, LIMIT_ADMIN_REASON, limitMessage } from "@/lib/session";
import type { Account, CoachResponse } from "@/lib/types";

/** Redlines are suggestions only: there is deliberately no send button. */
function Coach({ account }: { account: Account }) {
  const [coach, setCoach] = useState<CoachResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setLimited(null);
    try {
      setCoach(await api.fetchCoach(account.id));
    } catch (e) {
      const limit = limitMessage(e);
      if (limit) setLimited(limit);
      else setError(`The Deal coach didn't answer (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="tool-actions">
        <button className="primary" onClick={run} disabled={busy}>{busy ? "Reading the draft…" : coach ? "Redline again" : "Redline the next draft"}</button>
        {busy && <span className="muted small"><span className="spinner" aria-hidden /> Reading the draft against this month’s findings. This can take half a minute.</span>}
      </div>
      {limited && <div className="feedback notice" role="status"><span>{limited}</span><button className="text-button" onClick={() => askAdminToken(LIMIT_ADMIN_REASON, () => void run())}><KeyRound /> Use admin token</button></div>}
      {error && <p className="feedback error" role="alert">{error}</p>}
      {coach?.redlines.map((r, i) => (
        <section className="surface tool-card redline" key={`${r.clause_ref}-${i}`} aria-label={`Redline for ${r.clause_ref}`}>
          <div className="tool-row">
            <h2>{r.clause_ref}</h2>
            <strong className="tool-cost">Cost {dollars(r.dollars_at_stake)} in {monthLabel(account.invoice.month)}</strong>
          </div>
          <small className="tool-label">Now says</small>
          <blockquote className="struck"><del>{r.original_quote}</del></blockquote>
          <small className="tool-label">Suggested</small>
          <blockquote className="suggest"><ins>{r.suggested_text}</ins></blockquote>
          <p className="muted">{r.reason}</p>
        </section>
      ))}
      {coach && coach.redlines.length === 0 && <p className="muted">No redlines for this draft.</p>}
      {coach && <p className="muted small">Suggestions only. Clawback never sends a redline to {account.distributor.name}.</p>}
    </>
  );
}

export default function CoachApp() {
  return (
    <ToolFrame href="/coach" title="Deal coach" lead={(a) => `Changes to the next deal with ${a.distributor.name}, each tied to what this month’s wording cost.`}>
      {(account) => <Coach account={account} />}
    </ToolFrame>
  );
}
