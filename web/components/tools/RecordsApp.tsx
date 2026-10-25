"use client";

// Records: what Clawback keeps for this distributor. The documents the agents read (the signed deal locked: nobody
// edits it, agents included), the rules you saved by answering once, the records the checks use, and the audit trail
// with its hash-chain check.

import { useMemo, useState } from "react";
import ToolFrame from "./ToolFrame";
import * as api from "@/lib/api";
import type { Account, AuditVerify, DocumentText } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const RECENT = 10;
const short = (h: string) => (h.length > 12 ? `${h.slice(0, 8)}…${h.slice(-4)}` : h);
const stamp = (at: string) => {
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
};

function Kept({ account }: { account: Account }) {
  const saved = useFetched(useMemo(() => () => api.fetchSaved(account.id), [account.id]));
  const [doc, setDoc] = useState<DocumentText | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const s = saved.data;

  async function open(id: string) {
    setOpening(id);
    try {
      setDoc(await api.fetchDocument(account.id, id));
    } finally {
      setOpening(null);
    }
  }

  return (
    <>
      {saved.error && <p className="feedback error" role="alert">{saved.error}</p>}
      <div className="sv-grid">
        <section className="sv-card">
          <h2>Documents <small>{s?.documents.length ?? 0}</small></h2>
          <ul className="sv-list">
            {s?.documents.map((d) => (
              <li key={d.id}>
                <button onClick={() => void open(d.id)} disabled={opening === d.id}>
                  <span><strong>{d.title}</strong><small>{d.sender ? `from ${d.sender} · ` : ""}{Math.round(d.chars / 100) / 10}k characters</small></span>
                  {d.locked && <em className="sv-lock">Locked</em>}
                </button>
              </li>
            ))}
          </ul>
          <p className="cx-tiny">Signed documents are locked: no person or agent edits them. Changes arrive as amendments from approved senders.</p>
        </section>

        <section className="sv-card">
          <h2>Rules you saved <small>{s?.rules.length ?? 0}</small></h2>
          {s && s.rules.length === 0 && <p className="cx-small cx-muted">None yet. When the deal is unclear the agents ask you once; tick “save as a rule” and they never ask again.</p>}
          <ul className="sv-list">
            {s?.rules.map((r) => (
              <li key={r.id}><div><span><strong>{r.label}</strong><small>{r.summary ?? r.pattern_text}</small></span><em className="sv-tag">{r.status}</em></div></li>
            ))}
          </ul>
        </section>

        <section className="sv-card">
          <h2>Records</h2>
          <ul className="sv-list">
            {s?.records.map((r) => <li key={r.label}><div><span><strong>{r.label}</strong></span><em className="sv-tag">{r.rows} rows</em></div></li>)}
          </ul>
          <p className="cx-tiny">The agents check charges against these. Missing records make a check ask you instead of guessing.</p>
        </section>
      </div>

      {doc && (
        <div className="fl-overlay" onClick={() => setDoc(null)} role="presentation">
          <article className="sv-doc" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={doc.title}>
            <header><strong>{doc.title}</strong>{doc.locked && <em className="sv-lock">Locked · read-only</em>}<button className="cx-btn is-ghost" onClick={() => setDoc(null)}>Close</button></header>
            <pre>{doc.text}</pre>
          </article>
        </div>
      )}
    </>
  );
}

function Audit({ account }: { account: Account }) {
  const log = useFetched(useMemo(() => () => api.fetchAudit(account.id), [account.id]));
  const [all, setAll] = useState(false);
  const entries = log.data;
  // The newest steps first catch the eye; the whole chain is one click away (and Verify always checks all of it).
  const shown = all || !entries ? entries : entries.slice(-RECENT);
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
          {shown?.map((e) => (
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
        {entries && entries.length > RECENT && <button className="text-button" onClick={() => setAll((v) => !v)}>{all ? `Show the latest ${RECENT}` : `Show all ${entries.length} entries`}</button>}
        {entries && entries.length === 0 && <p className="muted">Nothing has been logged yet.</p>}
        {!entries && !log.error && <p className="muted">Loading the log…</p>}
      </section>
    </>
  );
}

export default function RecordsApp() {
  return (
    <ToolFrame place="records" title="Records" lead={(a) => `What Clawback keeps for ${a.distributor.name}: the documents the agents read, the rules you gave them once, the records they check against, and every step they took.`}>
      {(account) => (
        <>
          <Kept account={account} />
          <h2 id="audit" className="records-h">Audit trail</h2>
          <p className="muted">Every action, who or what took it, its evidence, and a hash chain that shows if anything was edited.</p>
          <Audit account={account} />
        </>
      )}
    </ToolFrame>
  );
}
