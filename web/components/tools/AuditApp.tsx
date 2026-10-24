"use client";

import { useMemo, useState } from "react";
import { FIXTURE_AUDIT } from "@/lib/fixture";
import * as api from "@/lib/live";
import type { AuditVerify } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { DATA_SOURCE } from "@/lib/useRunEvents";

const short = (h: string) => (h.length > 12 ? `${h.slice(0, 8)}…${h.slice(-4)}` : h);
const stamp = (at: string) => {
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
};

export default function AuditApp() {
  const log = useFetched(useMemo(() => (DATA_SOURCE === "live" ? api.fetchAudit : null), []));
  const entries = DATA_SOURCE === "live" ? log.data : FIXTURE_AUDIT;
  const [check, setCheck] = useState<AuditVerify | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      if (DATA_SOURCE === "live") setCheck(await api.verifyAudit());
      else setError("The chain check runs on the API; it isn't part of the recorded fixtures.");
    } catch (e) {
      setError(`The check didn't run (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="tool-actions">
        <button className="primary" onClick={verify} disabled={busy}>{busy ? "Checking…" : "Verify chain"}</button>
        {check && (
          <span className={`status ${check.ok ? "accepted" : "disputed"}`} role="status">
            <i />{check.ok ? `Chain intact · ${check.checked} rows checked` : `Broken at row ${check.broken_at ?? "?"}${check.reason ? ` · ${check.reason}` : ""}`}
          </span>
        )}
      </div>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {log.error && <p className="feedback error" role="alert">{log.error}</p>}
      <section className="surface tool-card audit">
        <ol>
          {entries?.map((e) => (
            <li key={e.id} className={check && !check.ok && check.broken_at === e.id ? "broken" : ""}>
              <div className="tool-row">
                <div><strong>{e.action.replace(/_/g, " ")}</strong> · {e.object_ref}<small>{e.actor} · {stamp(e.at)}</small></div>
                <code title={e.hash}>{short(e.hash)}</code>
              </div>
              {Object.keys(e.evidence).length > 0 && (
                <details className="source-detail"><summary><span>Evidence<small>{Object.keys(e.evidence).join(", ")}</small></span></summary><div className="source-preview"><pre>{JSON.stringify(e.evidence, null, 2)}</pre><small>Previous hash {short(e.prev_hash)}</small></div></details>
              )}
            </li>
          ))}
        </ol>
        {entries && entries.length === 0 && <p className="muted">Nothing has been logged yet.</p>}
        {!entries && !log.error && <p className="muted">Loading the log…</p>}
      </section>
    </>
  );
}
