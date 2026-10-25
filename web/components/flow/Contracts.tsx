"use client";

// The contract library: the signed deal (locked: nobody edits it, agents included) and what changes it (amendments,
// emails from approved senders, notices), with every term the agents read highlighted where it sits in the text.
// The next deal's draft is where changes belong: the Deal coach proposes redlines there for you to accept or not.

import { useCallback, useEffect, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import * as api from "@/lib/api";
import type { LibraryDocument, LibraryTerm } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { renderDocument } from "./DocRender";

const TERM_STATE: Record<string, { tone: string; word: string }> = {
  verified: { tone: "is-green", word: "Found word for word" },
  disputed: { tone: "is-amber", word: "Readers disagree" },
  rejected: { tone: "is-red", word: "Quote not found" },
};
const termState = (t: LibraryTerm) => TERM_STATE[t.status] ?? { tone: "is-idle", word: t.status };

/** Where a document comes from: the words under its title in the stack. */
function source(d: LibraryDocument) {
  if (d.locked) return d.kind === "amendment" ? "Signed by both sides" : "Signed";
  if (d.kind === "draft") return "Draft · editable through the Deal coach";
  if (d.sender) return `from ${d.sender}${d.approved_sender ? " · approved sender" : " · a claim, can’t change the deal"}`;
  return d.kind;
}

/** The document as a document: rendered headings, lists and tables, the readers' terms marked at their offsets. */
function Rendered({ doc, active, onPick }: { doc: LibraryDocument; active: number | null; onPick: (i: number) => void }) {
  const terms = [...doc.terms].map((t, i) => ({ t, i })).sort((a, b) => a.t.char_start - b.t.char_start);
  // Overlapping terms: the first one is drawn, as before. Indexes stay the terms list's own, for the side cards.
  const drawn: LibraryTerm[] = doc.terms.map((t) => ({ ...t, char_start: -1, char_end: -1 }));
  let at = 0;
  for (const { t, i } of terms) {
    if (t.char_start < at) continue;
    drawn[i] = t;
    at = t.char_end;
  }
  const { nodes } = renderDocument(doc.text, drawn, active, onPick);
  return <div className="dr">{nodes}</div>;
}

/** The sections of the document, for the outline beside it. */
const outlineOf = (doc: LibraryDocument) => renderDocument(doc.text, [], null, () => undefined).outline;

export default function Contracts() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchContract(account!.id), [account]);
  const lib = useFetched(account ? load : null, account?.id ?? "");
  const [pick, setPick] = useState<string | null>(null);
  const [term, setTerm] = useState<number | null>(null);
  const docs = lib.data?.documents ?? [];
  const doc = docs.find((d) => d.id === pick) ?? docs[0] ?? null;
  const outline = doc ? outlineOf(doc) : [];
  // A term picked on the side scrolls its sentence into view.
  useEffect(() => {
    if (term === null) return;
    document.querySelector(`[data-term="${term}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [term]);
  const groups = [
    { key: "base", title: "The signed deal", docs: docs.filter((d) => d.kind === "deal") },
    { key: "changes", title: "What changes it, with its source", docs: docs.filter((d) => d.kind !== "deal" && d.kind !== "draft") },
    { key: "next", title: "The next deal", docs: docs.filter((d) => d.kind === "draft") },
  ].filter((g) => g.docs.length > 0);

  return (
    <div className="fl">
      <TopBar account={account} active="contracts" />
      <main className="fl-main bp bp-ct">
        <PageHeader
          title="Contracts"
          line={lib.data?.read_in_run ? `The deal with ${cast.distributor} and what changes it. Highlighted: the terms both deal readers agreed on, word for word.` : `The deal with ${cast.distributor}. Terms are highlighted once the agents have read it.`}
        />
        {lib.error && <div className="fl-problem" role="alert">{lib.error}</div>}

        {lib.data && docs.length === 0 && <EmptyState title={`No contract on file for ${cast.distributor} yet.`} line="Once the signed deal is uploaded, the agents read it before they check a payment." />}

        {!lib.data && !lib.error && (
          <div className="bp-ct-grid" aria-hidden="true">
            <div className="bp-stack">{[0, 1, 2].map((i) => <div key={i} className="bp-doc"><i className="bp-skel-block" style={{ width: "70%" }} /><i className="bp-skel-block" style={{ width: "50%" }} /></div>)}</div>
            <div className="bp-paper"><div className="bp-paper-skel">{Array.from({ length: 9 }, (_, i) => <i key={i} className="bp-skel-block" />)}</div></div>
          </div>
        )}

        {doc && (
          <div className="bp-ct-grid">
            <nav className="bp-stack" aria-label="Documents">
              {groups.map((g) => (
                <div key={g.key} className={`bp-stack-group is-${g.key}`}>
                  <h2>{g.title}</h2>
                  {g.docs.map((d) => (
                    <button key={d.id} className={`bp-doc ${doc.id === d.id ? "is-on" : ""}`} aria-current={doc.id === d.id ? "true" : undefined} onClick={() => { setPick(d.id); setTerm(null); }}>
                      <strong>{d.title}</strong>
                      <small>{source(d)}{d.terms.length ? ` · ${d.terms.length} term${d.terms.length === 1 ? "" : "s"}` : ""}</small>
                      {d.locked && <span className="bp-chip is-lock">Locked</span>}
                    </button>
                  ))}
                </div>
              ))}
            </nav>

            <article className="bp-paper">
              <header>
                <h2>{doc.title}</h2>
                <div>
                  {doc.locked && <span className="bp-chip is-lock">Locked · nobody edits it, agents included</span>}
                  {!doc.locked && doc.kind !== "draft" && <span className={`bp-chip ${doc.approved_sender ? "is-green" : "is-amber"}`}>{source(doc)}</span>}

                </div>
              </header>
              <Rendered doc={doc} active={term} onPick={setTerm} />
            </article>

            <aside className="bp-terms" aria-label="Terms the agents read">
              {outline.length > 1 && (
                <details className="dr-outline" open>
                  <summary>On this page</summary>
                  {outline.map((o) => <a key={o.id} href={`#${o.id}`} className={`is-l${o.level}`}>{o.label}</a>)}
                </details>
              )}
              <h2>Terms the agents read <small>{doc.terms.length}</small></h2>
              {doc.terms.length === 0 && <p>{lib.data?.read_in_run ? "No terms highlighted in this document." : "None yet: the agents haven’t read the deal."}</p>}
              {doc.terms.map((t, i) => (
                <button key={i} className={`bp-term is-${t.status} ${term === i ? "is-on" : ""}`} onClick={() => setTerm(i)}>
                  <span className="bp-term-type">{t.type.replace(/_/g, " ")}</span>
                  <strong>{t.label}</strong>
                  <q>{t.quote}</q>
                  <span className="bp-meta">
                    <span className={`bp-chip ${termState(t).tone}`}>{termState(t).word}</span>
                    {t.discretion && <span className="bp-chip is-ask">Left to judgment</span>}
                  </span>
                </button>
              ))}
            </aside>
          </div>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
