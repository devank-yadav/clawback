"use client";

// The contract library: the signed deal (locked: nobody edits it, agents included) and what changes it (amendments,
// emails from approved senders, notices), with every term the agents read highlighted where it sits in the text.
// The next deal's draft is where changes belong: the Deal coach proposes redlines there for you to accept or not.

import Link from "next/link";
import { useCallback, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { LibraryDocument } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

function Highlighted({ doc, active, onPick }: { doc: LibraryDocument; active: number | null; onPick: (i: number) => void }) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  doc.terms.forEach((t, i) => {
    if (t.char_start < at) return; // overlapping terms: the first one is drawn
    parts.push(doc.text.slice(at, t.char_start));
    parts.push(
      <mark key={i} className={`ct-mark is-${t.status} ${t.discretion ? "is-discretion" : ""} ${active === i ? "is-active" : ""}`} onClick={() => onPick(i)} title={t.label}>
        {doc.text.slice(t.char_start, t.char_end)}
      </mark>,
    );
    at = t.char_end;
  });
  parts.push(doc.text.slice(at));
  return <pre className="ct-text">{parts}</pre>;
}

export default function Contracts() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchContract(account!.id), [account]);
  const lib = useFetched(account ? load : null, account?.id ?? "");
  const [pick, setPick] = useState<string | null>(null);
  const [term, setTerm] = useState<number | null>(null);
  const docs = lib.data?.documents ?? [];
  const doc = docs.find((d) => d.id === pick) ?? docs[0] ?? null;

  return (
    <div className="fl">
      <TopBar account={account} active="contracts" />
      <main className="fl-main">
        <header className="ds-head">
          <span className="cx-eyebrow">{account ? `${account.brand.name} · ${cast.distributor}` : " "}</span>
          <h1>The deal with {cast.distributor}</h1>
          <p>{lib.data?.read_in_run ? "Highlighted: every term the two deal readers agreed on, found word for word. Click one to see what the agents took from it." : "The terms light up here once the agents have read the deal (run them from Agents)."}</p>
        </header>
        {lib.error && <div className="fl-problem" role="alert">{lib.error}</div>}
        <div className="ct">
          <aside className="ct-list">
            {docs.map((d) => (
              <button key={d.id} className={`ct-doc ${doc?.id === d.id ? "is-on" : ""}`} onClick={() => { setPick(d.id); setTerm(null); }}>
                <strong>{d.title}</strong>
                <small>
                  {d.locked ? "Locked" : d.kind === "draft" ? "Draft · editable through the Deal coach" : d.sender ? `from ${d.sender}${d.approved_sender ? " · approved sender" : " · a claim, can’t change the deal"}` : d.kind}
                  {d.terms.length ? ` · ${d.terms.length} term${d.terms.length === 1 ? "" : "s"}` : ""}
                </small>
              </button>
            ))}
          </aside>
          {doc && (
            <section className="ct-view">
              <header>
                <strong>{doc.title}</strong>
                {doc.locked && <em className="sv-lock">Locked · nobody edits it, agents included</em>}
                {doc.kind === "draft" && <Link className="cx-btn" href={withAccount("/coach", account?.id)}>Get redlines from the Deal coach</Link>}
              </header>
              {doc.terms.length > 0 && (
                <div className="ct-terms">
                  {doc.terms.map((t, i) => (
                    <button key={i} className={`ct-term is-${t.status} ${term === i ? "is-on" : ""}`} onClick={() => setTerm(i)}>
                      <b>{t.type.replace(/_/g, " ")}</b>{t.label}{t.discretion ? " · left to judgment" : ""}
                    </button>
                  ))}
                </div>
              )}
              <Highlighted doc={doc} active={term} onPick={setTerm} />
            </section>
          )}
        </div>
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
