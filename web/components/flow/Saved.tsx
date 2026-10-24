"use client";

// What Clawback keeps for this distributor: the documents the agents read (the signed deal locked: nobody edits it,
// agents included), the rules you saved by answering once, the records the checks use, and the audit trail.

import Link from "next/link";
import { useCallback, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { DocumentText } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

export default function Saved() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchSaved(account!.id), [account]);
  const saved = useFetched(account ? load : null, account?.id ?? "");
  const auditLoad = useCallback(() => api.fetchAudit(account!.id), [account]);
  const audit = useFetched(account ? auditLoad : null, account?.id ?? "");
  const [doc, setDoc] = useState<DocumentText | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const s = saved.data;

  async function open(id: string) {
    if (!account) return;
    setOpening(id);
    try {
      setDoc(await api.fetchDocument(account.id, id));
    } finally {
      setOpening(null);
    }
  }

  return (
    <div className="fl">
      <TopBar account={account} active="saved" />
      <main className="fl-main sv">
        <header className="ds-head">
          <span className="cx-eyebrow">{account ? `${account.brand.name} · ${cast.distributor}` : " "}</span>
          <h1>What Clawback keeps for {cast.distributor}</h1>
          <p>The documents the agents read, the rules you gave them once, the records they check against, and every step they took.</p>
        </header>
        {saved.error && <div className="fl-problem" role="alert">{saved.error}</div>}

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

          <section className="sv-card">
            <h2>Audit trail <small>{audit.data?.length ?? 0}</small></h2>
            <p className="cx-small cx-muted">Every action, who or what did it, and its evidence, hash-chained so an edit shows.</p>
            <Link className="cx-btn is-ghost" href={withAccount("/audit", account?.id)}>Open the audit trail</Link>
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
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
