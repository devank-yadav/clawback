"use client";

// What Clawback keeps for this distributor: the documents the agents read (the signed deal locked: nobody edits it,
// agents included), the rules you saved by answering once, the records the checks use, and the audit trail.

import Link from "next/link";
import { useCallback, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHero, SectionHead, StatTile } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { shortDate } from "@/lib/format";
import type { DocumentText, Rule } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const RULE_STATE: Record<Rule["status"], { tone: string; word: string }> = {
  active: { tone: "is-green", word: "In use" }, pending: { tone: "is-idle", word: "Pending" }, undone: { tone: "is-off", word: "Undone" },
};

export default function Saved() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchSaved(account!.id), [account]);
  const saved = useFetched(account ? load : null, account?.id ?? "");
  const auditLoad = useCallback(() => api.fetchAudit(account!.id), [account]);
  const audit = useFetched(account ? auditLoad : null, account?.id ?? "");
  const [doc, setDoc] = useState<DocumentText | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const s = saved.data;
  const skeleton = !s && !saved.error;

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
      <main className="fl-main bp bp-sv">
        <PageHero
          title={<>What Clawback keeps<em>for {cast.distributor}.</em></>}
          sub="The documents the agents read, the rules you gave them once, the records they check against, and every step they took."
        />
        {saved.error && <div className="fl-problem" role="alert">{saved.error}</div>}

        <section className="bp-section">
          <SectionHead title={<>Contracts and documents{s && <> · {s.documents.length}</>}</>} muted="Signed ones are locked: no person or agent edits them." />
          <div className="bp-frame bp-docs">
            {skeleton && [0, 1, 2].map((i) => <div key={i} className="bp-skel" aria-hidden="true"><i /><i /></div>)}
            {s && s.documents.length === 0 && <EmptyState title="No documents yet." line="Upload the signed deal and the agents read it before they check a payment." />}
            <ul className="bp-rows">
              {s?.documents.map((d) => (
                <li key={d.id}>
                  <button className="bp-row" onClick={() => void open(d.id)} disabled={opening === d.id}>
                    <span className="bp-who">
                      <i className={`bp-doc-icon ${d.locked ? "is-locked" : ""}`} aria-hidden="true" />
                      <span><strong>{d.title}</strong><small>{d.sender ? `from ${d.sender} · ` : ""}{Math.round(d.chars / 100) / 10}k characters</small></span>
                    </span>
                    {d.locked ? <em className="bp-chip is-lock">Locked</em> : <em className="bp-chip is-plain">{opening === d.id ? "Opening…" : "Read"}</em>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <p className="bp-fine">Signed documents are locked: no person or agent edits them. Changes arrive as amendments from approved senders.</p>
        </section>

        <section className="bp-section">
          <SectionHead title={<>Rules you saved{s && <> · {s.rules.length}</>}</>} muted="Answer once, and the agents never ask again." />
          {skeleton && <div className="bp-rules" aria-hidden="true">{[0, 1].map((i) => <div key={i} className="bp-insight"><i className="bp-skel-block" style={{ width: "30%" }} /><i className="bp-skel-block" /><i className="bp-skel-block" style={{ width: "70%" }} /></div>)}</div>}
          {s && s.rules.length === 0 && (
            <EmptyState title="None yet." line="When the deal is unclear the agents ask you once; tick “save as a rule” and they never ask again." />
          )}
          {s && s.rules.length > 0 && (
            <div className="bp-rules">
              {s.rules.map((r) => (
                <article key={r.id} className={`bp-insight is-${r.status}`}>
                  <div className="bp-insight-top">
                    <span className="bp-tag">{r.label}</span>
                    <span className={`bp-chip ${RULE_STATE[r.status].tone}`}>{RULE_STATE[r.status].word}</span>
                  </div>
                  <h3>{r.summary ?? r.pattern_text}</h3>
                  {r.summary && r.pattern_text && <p>Matches: “{r.pattern_text}”</p>}
                  <div className="bp-meta">
                    <span>Learned {shortDate(r.learned_at)}, approved by {r.approver}</span>
                    <span>{r.counterparty}</span>
                    <span>{r.term_type.replace(/_/g, " ")}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="bp-section bp-records">
          <SectionHead title="Records" muted="The agents check charges against these." />
          {skeleton && <div className="bw-stats" aria-hidden="true">{[0, 1, 2, 3].map((i) => <div key={i} className="bw-stat"><i className="bp-skel-block" style={{ width: "50%" }} /><i className="bp-skel-block" style={{ height: 22 }} /></div>)}</div>}
          {s && s.records.length === 0 && <EmptyState title="No records yet." line="Upload store sales or past payments and the checks use them." />}
          {s && s.records.length > 0 && (
            <div className="bw-stats">
              {s.records.map((r) => <StatTile key={r.label} label={r.label} value={r.rows.toLocaleString("en-US")} hint={r.rows === 1 ? "row" : "rows"} />)}
            </div>
          )}
          <p className="bp-fine">Missing records make a check ask you instead of guessing.</p>
          <div className="bp-audit">
            <span><strong>Audit trail{audit.data && <> · {audit.data.length}</>}</strong><small>Every action, who or what did it, and its evidence, hash-chained so an edit shows.</small></span>
            <Link className="cx-btn is-ghost" href={withAccount("/audit", account?.id)}>Open the audit trail</Link>
          </div>
        </section>

        {doc && (
          <div className="fl-overlay" onClick={() => setDoc(null)} role="presentation">
            <article className="sv-doc" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={doc.title}>
              <header><strong>{doc.title}</strong>{doc.locked && <em className="bp-chip is-lock">Locked · read-only</em>}<button className="cx-btn is-ghost" onClick={() => setDoc(null)}>Close</button></header>
              <pre>{doc.text}</pre>
            </article>
          </div>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
