"use client";

import { useMemo, useState } from "react";
import ToolFrame from "./ToolFrame";
import * as api from "@/lib/api";
import type { Account, AuditVerify } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const short = (h: string) => (h.length > 12 ? `${h.slice(0, 8)}…${h.slice(-4)}` : h);
const stamp = (at: string) => {
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
};

function Audit({ account }: { account: Account }) {
  const log = useFetched(useMemo(() => () => api.fetchAudit(account.id), [account.id]));
  const entries = log.data;
  const [check, setCheck] = useState<AuditVerify | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      setCheck(await api.verifyAudit());
    } catch (e) {
      setError(`The check didn't run (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="tool-actions">
        <button className="primary" onClick={verify} disabled={busy}>{busy ? "Checking…" : "Verify the chain"}</button>
        {check && (
          <span className={`status ${check.ok ? "accepted" : "disputed"}`} role="status">
            <i />{check.ok ? `Chain intact · ${check.checked} entries checked` : `Broken at entry ${check.broken_at ?? "?"}${check.reason ? ` · ${check.reason}` : ""}`}
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

export default function AuditApp() {
  return (
    <ToolFrame href="/audit" title="Audit log" lead={() => "Every action, who or what took it, its evidence, and a hash chain that shows if anything was edited."}>
      {(account) => <Audit account={account} />}
    </ToolFrame>
  );
}
