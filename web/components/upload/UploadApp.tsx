"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { dollars, rate as perUnit, shortDay, units as count } from "@/lib/format";
import { withAccount } from "@/lib/accounts";
import * as api from "./api";
import RemittanceText from "./RemittanceText";
import type { RemittanceLine, RemittanceRead, RemittanceTotals } from "./types";

const CODE: Record<string, string> = {
  PA: "Promo allowance", DF: "Display fee", SH: "Shortage", PR: "Price mismatch", SP: "Spoilage", UNKNOWN: "Unknown code",
};
const STATUS: Record<RemittanceLine["status"], { label: string; css: string }> = {
  verified: { label: "Found on the page", css: "accepted" },
  needs_person: { label: "A person decides", css: "pending" },
  rejected: { label: "Not on the page: ignored", css: "disputed" },
};

function period(l: RemittanceLine) {
  if (!l.period_start || !l.period_end) return "no dates printed";
  return l.period_start === l.period_end ? shortDay(l.period_start) : `${shortDay(l.period_start)} to ${shortDay(l.period_end)}`;
}

function Line({ l, active, onPick }: { l: RemittanceLine; active: boolean; onPick: (n: number) => void }) {
  const s = STATUS[l.status];
  return (
    <li className={`border-b border-[var(--line)] last:border-0 ${active ? "bg-[var(--violet-soft)]" : ""}`}>
      <button type="button" onClick={() => onPick(l.n)} aria-pressed={active}
        className="flex w-full flex-col gap-2 border-0 bg-transparent px-4 py-3 text-left">
        <span className="flex w-full flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <strong className="min-w-0">{l.charge_id ? `${l.charge_id} · ` : ""}{l.description}</strong>
          <span className="money whitespace-nowrap">{dollars(l.amount)}</span>
        </span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--sub)]">
          <span className={`status ${s.css}`}><i />{s.label}</span>
          <span>{l.ref ?? "no number"} · “{l.code_text}” = {CODE[l.code] ?? l.code}</span>
          {l.units !== null && l.rate !== null && <span>{count(l.units)} × {perUnit(l.rate)}</span>}
          <span>{period(l)}</span>
        </span>
        {l.reasons.length > 0 && (
          <span className="flex flex-col gap-1 text-[12px] text-[var(--amber)]">{l.reasons.map((r) => <span key={r}>{r}</span>)}</span>
        )}
        {/* The printed line with its column padding collapsed so it wraps on a phone; the panel keeps the layout. */}
        <span className="block w-full rounded-[6px] bg-[var(--raised)] px-2 py-1 font-mono text-[11px] leading-[1.6] text-[var(--sub)] [overflow-wrap:anywhere]">
          <mark className={`text-inherit [box-decoration-break:clone] ${l.status === "verified" ? "bg-[var(--amber-bg)]" : l.status === "needs_person" ? "bg-[var(--amber-soft)]" : "bg-transparent line-through"}`}>{l.exact_quote.replace(/\s+/g, " ").trim()}</mark>
        </span>
      </button>
    </li>
  );
}

function Check({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return <small className={ok ? "text-[var(--green)]" : "text-[var(--red)]"}>{ok ? "✓ " : "✗ "}{children}</small>;
}

function Totals({ t, r }: { t: RemittanceTotals; r: RemittanceRead }) {
  return (
    <div className="tool-stats">
      <div><span>The lines add up to</span><strong>{dollars(t.lines)}</strong><small>{r.charges.length} charges</small></div>
      <div>
        <span>{r.distributor} says it took</span><strong>{t.short === null ? "Not printed" : dollars(t.short)}</strong>
        {t.gross !== null && t.paid !== null
          ? <Check ok={t.matches_remittance}>{dollars(t.gross)} invoiced, {dollars(t.paid)} paid</Check>
          : <Check ok={false}>gross and paid aren&apos;t both printed</Check>}
      </div>
      <div>
        <span>Your bank says you&apos;re short</span><strong>{dollars(t.account_short)}</strong>
        <Check ok={t.matches_account}>{r.header?.invoice_id ?? "the invoice"}: {dollars(t.expected)} billed, {dollars(t.received)} arrived</Check>
      </div>
    </div>
  );
}

function Result({ r, onReset }: { r: RemittanceRead; onReset: () => void }) {
  const router = useRouter();
  const [active, setActive] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const kept = r.lines.filter((l) => l.status !== "rejected").length;
  const toPerson = r.lines.filter((l) => l.status === "needs_person").length;

  function pick(n: number) {
    setActive(n);
    document.getElementById(`remit-quote-${n}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  async function confirm() {
    setStarting(true);
    setError(null);
    try {
      await api.runRemittance(r.read_id, r.account);
      router.push(withAccount("/", r.account));
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  }

  const h = r.header;
  return (
    <>
      <section className="surface tool-card" aria-label="What the remittance says">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>{h?.payer ?? r.distributor}{h?.payment_ref ? ` · ${h.payment_ref}` : ""}</h2>
            <p className="muted text-[13px]">
              {h?.payment_date ? `Paid ${shortDay(h.payment_date)} · ` : ""}{h?.invoice_id ? `Invoice ${h.invoice_id} · ` : ""}
              Read from {r.input === "pdf" ? "a PDF" : "text"}{r.source === "fixture" ? " (saved answer, offline)" : ""}
            </p>
          </div>
          <span className={`status ${r.ok ? "accepted" : r.can_run ? "pending" : "disputed"}`}>
            <i />{r.ok ? "Every line checks out" : r.can_run ? "Adds up; some lines need a person" : "Doesn't add up"}
          </span>
        </div>
        {r.totals && <Totals t={r.totals} r={r} />}
      </section>

      {(r.problems.length > 0 || r.unclear.length > 0) && (
        <section className="surface tool-card" aria-label="Problems">
          <h2>{r.problems.length + r.unclear.length} thing{r.problems.length + r.unclear.length === 1 ? "" : "s"} to look at</h2>
          <ul className="m-0 mt-2 flex list-none flex-col gap-2 p-0">
            {r.problems.map((p, i) => (
              <li key={i} className="text-[14px]">
                {p.line !== null ? <button type="button" className="text-button p-0" onClick={() => pick(p.line!)}>Line {p.line}</button> : null}
                {p.line !== null ? " " : ""}{p.text}
              </li>
            ))}
            {r.unclear.map((u) => <li key={u} className="text-[14px]">Couldn&apos;t read: {u}</li>)}
          </ul>
        </section>
      )}

      <div className="grid min-w-0 gap-[18px] lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <section className="surface min-w-0 overflow-hidden" aria-label="Deduction lines">
          <div className="list-heading"><div><h2>{kept} charge{kept === 1 ? "" : "s"} from {r.lines.length} line{r.lines.length === 1 ? "" : "s"}</h2><p>Each one is the exact line printed on the remittance.</p></div></div>
          {r.lines.length === 0
            ? <p className="muted p-4">No deduction lines were read.</p>
            : <ul className="m-0 list-none p-0">{r.lines.map((l) => <Line key={l.n} l={l} active={active === l.n} onPick={pick} />)}</ul>}
        </section>
        <section className="surface tool-card min-w-0 lg:sticky lg:top-[76px] lg:self-start" aria-label="The remittance">
          <div className="section-eyebrow !mt-0">The remittance, as read</div>
          <RemittanceText text={r.text} lines={r.lines} active={active} onPick={pick} />
          <p className="muted mt-2 text-[12px]">Yellow: found word for word. Amber: a person decides. Anything not highlighted isn&apos;t a charge.</p>
        </section>
      </div>

      <section className="surface tool-card" aria-label="Confirm">
        <h2>{r.can_run ? `Check these ${kept} charges against the deal?` : "Clawback won't run on this remittance"}</h2>
        <p className="muted text-[14px]">
          {r.can_run
            ? `Nothing here is edited. Clawback checks each charge against the signed deal, the emails and the sales${toPerson ? `, and asks you about the ${toPerson} line${toPerson === 1 ? "" : "s"} it couldn't check` : ""}.`
            : "The lines don't add up to what the payment is short. Upload the full remittance, or ask the distributor for it."}
        </p>
        <div className="tool-actions mt-3">
          <button type="button" className="primary" disabled={!r.can_run || starting} onClick={confirm}>
            {starting ? "Starting…" : "Confirm and check every charge"}
          </button>
          <button type="button" className="secondary" onClick={onReset} disabled={starting}>Bring in another</button>
        </div>
        {error && <p className="feedback error inline" role="alert">{error}</p>}
      </section>
    </>
  );
}

export default function UploadApp() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<RemittanceRead | null>(null);

  async function read(input: { file: File } | { text: string }, what: string) {
    setBusy(what);
    setError(null);
    setResult(null);
    try {
      setResult(await api.readRemittance(input));
    } catch (e) {
      setError(`${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function sample() {
    setBusy("Northmart's March remittance");
    setError(null);
    try {
      const file = await api.sampleFile();
      await read({ file }, file.name);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  function chosen(files: FileList | null) {
    const file = files?.[0];
    if (file) void read({ file }, file.name);
  }

  if (result) return <Result r={result} onReset={() => { setResult(null); setText(""); }} />;

  return (
    <>
      <section className="surface tool-card tool-form" aria-label="Bring in a remittance">
        <label
          htmlFor="remit-file"
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); chosen(e.dataTransfer.files); }}
          className={`!m-0 flex cursor-pointer flex-col items-center gap-2 rounded-[12px] border-2 border-dashed px-4 py-9 text-center focus-within:outline focus-within:outline-2 focus-within:outline-[var(--violet)] ${dragging ? "border-[var(--violet)] bg-[var(--violet-soft)]" : "border-[var(--line)] bg-[var(--card)]"}`}
        >
          <strong className="text-[17px]">Drop the remittance here</strong>
          <span className="muted text-[13px] font-normal">The PDF or text the distributor sent with the payment, or click to choose it</span>
          <input id="remit-file" type="file" className="sr-only" accept=".pdf,.txt,.csv,application/pdf,text/plain,text/csv"
            disabled={!!busy} onChange={(e) => { chosen(e.target.files); e.target.value = ""; }} />
        </label>
        <label htmlFor="remit-text">Or paste its text</label>
        <textarea id="remit-text" rows={7} value={text} onChange={(e) => setText(e.target.value)} disabled={!!busy}
          className="font-mono text-[12px]" placeholder={"DEDUCTIONS TAKEN AGAINST INV-3102\nNM-2229   PROMO ALLOW   Spring promo week 1 ..."} />
        <div className="tool-actions">
          <button type="button" className="primary" disabled={!text.trim() || !!busy} onClick={() => read({ text }, "the pasted text")}>Read this text</button>
          <button type="button" className="secondary" disabled={!!busy} onClick={sample}>Try Northmart&apos;s March remittance</button>
          <a className="text-button" href={api.sampleUrl()} download>Download it (PDF)</a>
        </div>
        {busy && (
          <p className="muted" role="status"><span className="spinner" aria-hidden /> Reading {busy}. Claude lists every deduction line; then plain code checks each one against the page. Up to a minute.</p>
        )}
      </section>
      {error && <p className="feedback error" role="alert">{error}</p>}
      <p className="muted text-[13px]">Fictional demo: Peak Bar Co. and Northmart are made up. Clawback never edits a line: it reads, checks and asks.</p>
    </>
  );
}
