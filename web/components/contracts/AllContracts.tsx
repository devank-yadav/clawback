"use client";

// Every contract the supplier has with every distributor, in one place: the signed contracts (locked: nobody edits
// them, agents included), what changed them (amendments, emails from approved senders), notices, and the draft for
// next time. Each card says in plain words what the agents read from the document; a card opens the document with
// those passages highlighted. Nothing here computes money: the summaries are the agents' own term labels, reworded.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileText, Lock } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { renderDocument } from "@/components/flow/DocRender";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { SlideOver } from "@/components/ui/SlideOver";
import * as api from "@/lib/api";
import type { Account, ContractLibrary, LibraryDocument, LibraryTerm } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

/** The API also sends when Google Drive last changed a document; the shared type doesn't list it yet. */
type Doc = LibraryDocument & { updated_at?: string | null };
type Loaded = { account: Account; lib: ContractLibrary | null; error: string | null };

const EMPTY_TITLE = "No contracts yet.";
const EMPTY_LINE = "Upload a signed agreement and the agents read it before they check a payment.";

// ---- plain words for a document -------------------------------------------------------------------------------

function kindLabel(d: Doc): { word: string; tone: string } {
  if (d.kind === "deal") return { word: "Signed contract", tone: "is-accent" };
  if (d.kind === "amendment") return { word: "Amendment", tone: "is-accent" };
  if (d.kind === "email") return d.approved_sender ? { word: "Email that changed the contract", tone: "is-green" } : { word: "Email claiming a change", tone: "is-amber" };
  if (d.kind === "notice") return { word: "Notice", tone: "" };
  if (d.kind === "draft") return { word: "Draft for next time", tone: "is-fair" };
  return { word: "Document", tone: "" };
}

/** "Name: value" lines near the top (email headers, or **Effective date:** in a contract), first one of each wins. */
function headers(text: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const line of text.split("\n").slice(0, 30)) {
    const m = /^\s*\*{0,2}([A-Za-z][A-Za-z .'-]{0,40}?):\*{0,2}\s+(.+?)\s*$/.exec(line);
    if (!m) continue;
    const key = m[1].trim().toLowerCase();
    if (!out.has(key)) out.set(key, m[2].replace(/\*\*/g, "").trim());
  }
  return out;
}

/** "Jordan Lee <jordan@…>" or "Northmart Deductions (deductions@…)" → the name only. */
const nameOnly = (s: string) => s.replace(/<[^>]*>/g, "").replace(/\([^)]*@[^)]*\)/g, "").replace(/\s+/g, " ").trim() || s;

/** The parties under "Between:", as written in bold. */
function parties(text: string): string[] {
  const at = text.search(/\*{0,2}Between:?\*{0,2}/i);
  if (at < 0) return [];
  const out: string[] = [];
  for (const line of text.slice(at).split("\n").slice(1, 6)) {
    const m = /^\s*-\s*\*\*(.+?)\*\*/.exec(line);
    if (m) out.push(m[1].trim());
    else if (out.length && line.trim()) break;
  }
  return out;
}

const both = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

function shortDay(raw: string): string | null {
  const day = /\b\d{1,2} [A-Z][a-z]{2} \d{4}\b/.exec(raw)?.[0] ?? raw;
  const t = Date.parse(day);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** When the document is from, in the words of the document itself. Nothing when it doesn't say. */
function dateOf(d: Doc, h: Map<string, string>): string | null {
  const pick: [string, string][] = d.kind === "email"
    ? [["date", "Sent"]]
    : [["effective date", "Effective"], ["proposed effective date", "Would start"], ["amendment date", "Dated"], ["notice date", "Dated"], ["date", "Dated"]];
  for (const [key, word] of pick) {
    const v = h.get(key);
    if (v) return `${word} ${shortDay(v) ?? v.slice(0, 40)}`;
  }
  if (d.updated_at) {
    const day = shortDay(d.updated_at);
    if (day) return `Updated ${day}`;
  }
  return null;
}

/** Who signed or sent it. */
function whoOf(d: Doc, h: Map<string, string>): string {
  const from = d.sender ?? h.get("from") ?? null;
  if (d.kind === "email" || d.kind === "notice") return from ? `From ${nameOnly(from)}` : "Sender not named";
  const sides = parties(d.text);
  if (d.kind === "draft") return sides.length ? `Between ${both(sides)} · not signed yet` : "Not signed yet";
  if (sides.length) return `Signed by ${both(sides)}`;
  if (d.locked) return d.kind === "amendment" ? "Signed by both sides" : "Signed";
  return from ? `From ${nameOnly(from)}` : "";
}

function titleOf(d: Doc, h: Map<string, string>): string {
  if (d.kind === "email" && h.get("subject")) return h.get("subject")!;
  const head = /^#\s+(.+)$/m.exec(d.text.split("\n").slice(0, 8).join("\n"))?.[1];
  return head ? head.replace(/^DRAFT:\s*/i, "").replace(/\*\*/g, "").trim() : d.title;
}

// ---- plain words for what the agents read ---------------------------------------------------------------------

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function isoParts(s: string) {
  const [y, m, d] = s.split("-").map(Number);
  return { y, m: MONTHS[m - 1] ?? String(m), d };
}

/** 2026-03-01 to 2026-03-31 → "March 1–31, 2026". */
function range(a: string, b: string): string {
  const x = isoParts(a), y = isoParts(b);
  if (x.y === y.y && x.m === y.m) return `${x.m} ${x.d}–${y.d}, ${y.y}`;
  if (x.y === y.y) return `${x.m} ${x.d} – ${y.m} ${y.d}, ${y.y}`;
  return `${x.m} ${x.d}, ${x.y} – ${y.m} ${y.d}, ${y.y}`;
}

/** The agents' label ("$1.0 per unit", "at most 5,000 units") in everyday words, same numbers. */
function plain(label: string): string {
  return label
    .replace(/\$(\d+(?:\.\d+)?)/g, (_, n: string) => {
      const v = Number(n);
      if (!Number.isFinite(v)) return `$${n}`;
      const cents = v < 100 || v % 1 !== 0;
      return `$${v.toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: 2 })}`;
    })
    .replace(/(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})/g, (_, a: string, b: string) => range(a, b))
    .replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (s: string) => { const p = isoParts(s); return `${p.m} ${p.d}, ${p.y}`; })
    .replace(/^\+([\d,]+) units/, "$1 more units")
    .replace(/\bper unit\b/, "a unit")
    .replace(/^at most /, "up to ")
    .replace(/_/g, " ");
}

const upper = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** One plain sentence for a term, for the list beside the document. */
function sentence(t: LibraryTerm): string {
  if (t.type === "product_scope") return upper(plain(t.label).replace(/^covers /, "Covers ").replace(/, ([^,]+)$/, " and $1"));
  return upper(plain(t.label));
}

const ORDER = ["promo_rate", "product_scope", "date_range", "unit_cap", "amendment", "fee_discretion", "fee_schedule", "quantity_variance", "notice_period", "dispute_window"];

/** The key terms as one line: "$1.00 a unit on Peak Bar Original and Peak Bar Chocolate, March 1–31, 2026, up to 5,000 units". */
function summary(d: Doc): string | null {
  const terms = d.terms.filter((t) => t.status !== "rejected").slice().sort((a, b) => {
    const ia = ORDER.indexOf(a.type), ib = ORDER.indexOf(b.type);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  const parts: string[] = [];
  let last = "";
  for (const t of terms) {
    let p = plain(t.label);
    if (t.type === "product_scope") {
      p = p.replace(/^covers /, "on ").replace(/, ([^,]+)$/, " and $1");
      // "$1.00 a unit" + "on Original and Chocolate" read as one phrase.
      if (last === "promo_rate" && parts.length) { parts[parts.length - 1] += ` ${p}`; last = t.type; continue; }
    }
    if (!parts.includes(p)) parts.push(p);
    last = t.type;
  }
  if (!parts.length) return null;
  const shown = parts.slice(0, 4);
  const more = parts.length - shown.length;
  return upper(shown.join(", ")) + (more > 0 ? `, and ${more} more` : "");
}

/** "§3.2" when the highlighted sentence sits on a numbered line of the document. */
function sectionOf(text: string, t: LibraryTerm): string | null {
  const from = /^\s*(\d+(?:\.\d+)+)\b/.exec(t.quote)?.[1];
  if (from) return `§${from}`;
  const start = text.lastIndexOf("\n", Math.max(0, t.char_start - 1)) + 1;
  const line = text.slice(start, text.indexOf("\n", start) < 0 ? undefined : text.indexOf("\n", start));
  const m = /^[\s>*#|-]*(?:Section\s+)?(\d+(?:\.\d+)+)\b/.exec(line);
  return m ? `§${m[1]}` : null;
}

const TERM_STATE: Record<string, { tone: string; word: string } | undefined> = {
  disputed: { tone: "is-amber", word: "The two readers disagree" },
  rejected: { tone: "is-amber", word: "Not found word for word" },
};

// ---- the page --------------------------------------------------------------------------------------------------

function DocCard({ d, distributor, onOpen }: { d: Doc; distributor: string | null; onOpen: () => void }) {
  const h = headers(d.text);
  const k = kindLabel(d);
  const date = dateOf(d, h);
  const who = whoOf(d, h);
  const sum = summary(d);
  return (
    <li>
      <button type="button" className="cb-card is-lift ct-card" onClick={onOpen}>
        <span className="ct-card-top">
          <span className={`cx-pill ${k.tone}`}>{k.word}</span>
          {d.locked && <span className="ct-locked"><Lock aria-hidden="true" />Locked</span>}
          {distributor && <span className="cx-tag ct-dist">{distributor}</span>}
        </span>
        <strong className="ct-card-title">{titleOf(d, h)}</strong>
        {(date || who) && <span className="ct-card-meta">{[date, who].filter(Boolean).join(" · ")}</span>}
        {sum ? <span className="ct-card-sum">{sum}</span> : <span className="ct-card-sum is-none">Nothing in it the agents check payments against.</span>}
      </button>
    </li>
  );
}

function Reader({ d, distributor }: { d: Doc; distributor: string }) {
  const [term, setTerm] = useState<number | null>(null);
  useEffect(() => {
    if (term === null) return;
    document.querySelector(`.ct-doc [data-term="${term}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [term]);
  // Overlapping highlights: the first is drawn; indexes stay the terms list's own, so the list and the text agree.
  const nodes = useMemo(() => {
    const drawn: LibraryTerm[] = d.terms.map((t) => ({ ...t, char_start: -1, char_end: -1 }));
    let at = 0;
    for (const { t, i } of d.terms.map((t, i) => ({ t, i })).sort((a, b) => a.t.char_start - b.t.char_start)) {
      if (t.char_start < at) continue;
      drawn[i] = t;
      at = t.char_end;
    }
    return renderDocument(d.text, drawn, term, setTerm).nodes;
  }, [d, term]);
  const h = headers(d.text);
  const k = kindLabel(d);
  const meta = [dateOf(d, h), whoOf(d, h)].filter(Boolean).join(" · ");

  return (
    <div className="ct-reader">
      <div className="ct-card-top">
        <span className={`cx-pill ${k.tone}`}>{k.word}</span>
        {distributor && <span className="cx-tag ct-dist">{distributor}</span>}
        {meta && <span className="ct-card-meta">{meta}</span>}
      </div>
      {d.locked && <p className="ct-note is-lock"><Lock aria-hidden="true" />Signed contracts are locked: nobody edits them, the agents included.</p>}
      {d.kind === "email" && !d.approved_sender && <p className="ct-note is-claim">This sender isn’t approved to change the contract, so the agents treat the email as a claim and never apply it.</p>}
      {d.kind === "draft" && <p className="ct-note">Not signed yet. This is where changes belong: the Deal coach suggests edits here for you to accept or not.</p>}

      {d.terms.length > 0 && (
        <section className="ct-read" aria-label="What the agents read">
          <h3>What the agents read <small>{d.terms.length}</small></h3>
          <ul>
            {d.terms.map((t, i) => {
              const s = TERM_STATE[t.status];
              const sec = sectionOf(d.text, t);
              return (
                <li key={i}>
                  <button type="button" className={`ct-term ${term === i ? "is-on" : ""}`} aria-pressed={term === i} onClick={() => setTerm(i)}>
                    <span className="ct-term-line">{sentence(t)}{sec && <small>{sec}</small>}</span>
                    {(s || t.discretion) && (
                      <span className="ct-term-flags">
                        {s && <span className={`cx-pill ${s.tone}`}>{s.word}</span>}
                        {t.discretion && <span className="cx-pill is-amber">Left to their judgment</span>}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="ct-hint">Highlighted below: the exact words each one came from.</p>
        </section>
      )}

      <article className="ct-doc dr">{nodes}</article>
    </div>
  );
}

export default function AllContracts() {
  const { account, accounts, accountsError } = useRun();
  const ids = (accounts ?? []).map((a) => a.id).join(",");
  const load = useCallback(
    () => Promise.allSettled((accounts ?? []).map((a) => api.fetchContract(a.id))).then((rs) =>
      rs.map((r, i): Loaded => ({
        account: accounts![i],
        lib: r.status === "fulfilled" ? r.value : null,
        error: r.status === "rejected" ? api.unreachable(r.reason as Error) : null,
      })),
    ),
    [accounts],
  );
  const all = useFetched(accounts ? load : null, ids);
  // ?distributor=<account> opens on that distributor's contracts (the Distributors page links here).
  const params = useSearchParams();
  const [filter, setFilter] = useState<string>(() => params.get("distributor") ?? "all");
  const [open, setOpen] = useState<{ account: string; doc: string } | null>(null);

  // A distributor's name, with the brand added when two brands sell to the same distributor.
  const names = useMemo(() => {
    const list = accounts ?? [];
    const count = new Map<string, number>();
    list.forEach((a) => count.set(a.distributor.name, (count.get(a.distributor.name) ?? 0) + 1));
    return new Map(list.map((a) => [a.id, (count.get(a.distributor.name) ?? 0) > 1 ? `${a.distributor.name} · ${a.brand.name}` : a.distributor.name]));
  }, [accounts]);

  const rows = all.data ?? [];
  const shown = filter === "all" ? rows : rows.filter((r) => r.account.id === filter);
  const total = shown.reduce((n, r) => n + (r.lib?.documents.length ?? 0), 0);
  const loading = !all.data && !all.error && !accountsError;
  const openDoc = open ? (rows.find((r) => r.account.id === open.account)?.lib?.documents.find((d) => d.id === open.doc) as Doc | undefined) ?? null : null;
  const openName = open ? names.get(open.account) ?? "" : "";

  return (
    <div className="fl">
      <TopBar account={account} active="contracts" />
      <main className="fl-main ct-page">
        <PageHeader title="Contracts" line="Every agreement with your distributors, and what changed it. The agents check every payment against these." />
        {(accountsError || all.error) && <div className="fl-problem" role="alert">{accountsError ?? all.error}</div>}

        {(accounts?.length ?? 0) > 1 && (
          <div className="ct-chips" role="group" aria-label="Show contracts for">
            <button type="button" className="ct-chip" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
            {accounts!.map((a) => (
              <button key={a.id} type="button" className="ct-chip" aria-pressed={filter === a.id} onClick={() => setFilter(a.id)}>
                {names.get(a.id)}
                {all.data && <small>{rows.find((r) => r.account.id === a.id)?.lib?.documents.length ?? 0}</small>}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <ul className="ct-list" aria-hidden="true">
            {[0, 1, 2].map((i) => <li key={i}><div className="cb-card ct-card ct-skel"><i style={{ width: "30%" }} /><i style={{ width: "70%" }} /><i style={{ width: "55%" }} /></div></li>)}
          </ul>
        )}

        {all.data && total === 0 && shown.every((r) => !r.error) && <EmptyState title={EMPTY_TITLE} line={EMPTY_LINE} />}
        {accounts && accounts.length === 0 && <EmptyState title={EMPTY_TITLE} line={EMPTY_LINE} />}

        {all.data && filter === "all" && total > 0 && shown.map((r) => (
          <section key={r.account.id} className="ct-group" aria-labelledby={`ct-g-${r.account.id}`}>
            <h2 id={`ct-g-${r.account.id}`} className="ct-group-h">
              <FileText aria-hidden="true" />{names.get(r.account.id)}
              <small>{r.lib ? `${r.lib.documents.length} document${r.lib.documents.length === 1 ? "" : "s"}` : ""}</small>
            </h2>
            {r.error && <div className="fl-problem" role="alert">Couldn’t load the contracts for {names.get(r.account.id)}: {r.error}</div>}
            {r.lib && r.lib.documents.length === 0 && <p className="ct-none">{EMPTY_TITLE} {EMPTY_LINE}</p>}
            {r.lib && r.lib.documents.length > 0 && (
              <ul className="ct-list">
                {r.lib.documents.map((d) => <DocCard key={d.id} d={d} distributor={null} onOpen={() => setOpen({ account: r.account.id, doc: d.id })} />)}
              </ul>
            )}
          </section>
        ))}

        {all.data && filter !== "all" && shown.map((r) => (
          <div key={r.account.id}>
            {r.error && <div className="fl-problem" role="alert">Couldn’t load the contracts for {names.get(r.account.id)}: {r.error}</div>}
            {r.lib && r.lib.documents.length > 0 && (
              <ul className="ct-list">
                {r.lib.documents.map((d) => <DocCard key={d.id} d={d} distributor={names.get(r.account.id) ?? null} onOpen={() => setOpen({ account: r.account.id, doc: d.id })} />)}
              </ul>
            )}
          </div>
        ))}
      </main>

      <SlideOver open={!!openDoc} onClose={() => setOpen(null)} wide title={openDoc ? titleOf(openDoc, headers(openDoc.text)) : ""}>
        {openDoc && <Reader key={`${open?.account}/${openDoc.id}`} d={openDoc} distributor={openName} />}
      </SlideOver>
      <SessionDialogs account={account} />
    </div>
  );
}
