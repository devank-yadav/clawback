"use client";

// The first screen: one place to drop the payment advice the distributor sent (PDF, CSV or pasted text), or the
// sample payment. A dropped file is read by the Payment reader (POST /accounts/{id}/remittance); if its lines add up,
// the run starts on its own (POST …/remittance/run). Nothing here computes money.

import { useState, type DragEvent } from "react";
import { DotWave } from "@/components/console/DotWave";
import { useRun } from "@/components/console/RunProvider";
import { readRemittance, runRemittance } from "@/components/upload/api";
import { money } from "@/lib/format";

const CREW: { name: string; tag: "AI" | "CODE" | "PERSON" }[] = [
  { name: "Payment reader", tag: "AI" },
  { name: "Deal reader · Claude", tag: "AI" },
  { name: "Deal reader · Gemini", tag: "AI" },
  { name: "Calculator", tag: "CODE" },
  { name: "Investigator", tag: "AI" },
  { name: "Negotiator", tag: "AI" },
  { name: "Rules", tag: "CODE" },
  { name: "Bookkeeper", tag: "CODE" },
];

export function StartPanel({ onStart, onOpenLast }: { onStart: () => void; onOpenLast: () => void }) {
  const { account, cast, state, view, startPayment, starting, limited, follow, error } = useRun();
  const [over, setOver] = useState(false);
  const [reading, setReading] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const [text, setText] = useState("");
  const busy = !!reading || starting;
  const last = state.run && view.totals ? view.totals : null;

  async function read(input: { file: File } | { text: string }, name: string) {
    if (!account || busy) return;
    setReading(name);
    setProblem(null);
    try {
      const r = await readRemittance(input, account.id);
      if (!r.can_run) {
        setProblem(r.problems[0]?.text ?? "The lines don’t add up to what was taken, so no run can start from this read. Check the file, or try the sample payment.");
        return;
      }
      const started = await runRemittance(r.read_id, account.id);
      onStart();
      follow(started.run_id);
    } catch (e) {
      setProblem(`The Payment reader couldn’t use that (${(e as Error).message}).`);
    } finally {
      setReading(null);
    }
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void read({ file }, file.name);
  }

  function pay() {
    onStart();
    void startPayment();
  }

  return (
    <div className="fl-hero">
      <DotWave />
      <section className="fl-start" aria-labelledby="fl-start-h">
        <span className="cx-eyebrow">{account ? `${account.brand.name} ← ${account.distributor.name}` : "Clawback"}</span>
        <h1 id="fl-start-h">Drop in the payment. The agents take it from there.</h1>
        <p className="fl-lead">They read the deal, check every charge, dispute the wrong ones with proof and accept the fair ones. You’re asked only when the deal is unclear.</p>

        <label
          className={`fl-drop ${over ? "is-over" : ""} ${busy ? "is-busy" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
        >
          {reading ? (
            <span className="fl-reading" aria-live="polite">
              <span className="cx-pill is-live">Payment reader · AI</span>
              <strong>Reading {reading}…</strong>
              <small>Listing every deduction line, then checking each one is printed word for word and that they add up.</small>
              <span className="fl-bar is-indeterminate"><i /></span>
            </span>
          ) : (
            <>
              <span className="fl-plus" aria-hidden="true">+</span>
              <strong>Drop {cast.distributor}’s payment advice</strong>
              <small>PDF, CSV or text · or click to choose a file</small>
              <input type="file" accept=".pdf,.csv,.txt,application/pdf,text/csv,text/plain" disabled={busy || !account}
                aria-label="Choose the payment advice file"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void read({ file: f }, f.name); e.target.value = ""; }} />
            </>
          )}
        </label>

        <div className="fl-or">
          <span>No file?</span>
          <button className="cx-btn" onClick={pay} disabled={busy || !account}>
            {starting ? "Starting…" : account ? `${cast.distributor} pays ${money(account.invoice.received)}` : "Loading…"}
          </button>
          <span className="cx-tiny">watch a short payment arrive</span>
          <button className="cx-btn is-ghost" onClick={() => setPasting((v) => !v)} disabled={busy}>Paste text</button>
        </div>
        {pasting && (
          <div className="fl-paste">
            <textarea value={text} onChange={(e) => setText(e.target.value)} aria-label="Remittance text" placeholder={`Paste the remittance ${cast.distributor} sent`} />
            <div><button className="cx-btn" disabled={busy || !text.trim()} onClick={() => void read({ text }, "the pasted text")}>Read it</button></div>
          </div>
        )}

        {problem && <div className="fl-problem" role="alert">{problem}</div>}
        {limited && <div className="fl-problem" role="status">{limited}</div>}
        {error && <div className="fl-problem" role="alert">{error}</div>}

        <div className="fl-crew" aria-label="The agents">
          {CREW.map((c) => <span key={c.name} className={`fl-chip ${c.tag === "CODE" ? "is-code" : ""}`}><i>{c.tag === "CODE" ? "CODE" : "AI"}</i>{c.name}</span>)}
          <span className="fl-chip is-person"><i>ADMIN</i>{cast.owner}</span>
        </div>
        <p className="cx-tiny">AI reads and writes. Tested code does every calculation. People approve money.</p>

        {last && state.run && (
          <div className="fl-last">
            <span>
              Last payment: {state.run.status === "failed" ? "the run stopped" : `${money(last.disputed)} disputed · ${money(last.accepted)} fair${last.questions ? ` · ${last.questions} question${last.questions === 1 ? "" : "s"}` : ""}`}
            </span>
            <button className="cx-btn is-ghost" onClick={onOpenLast}>Open</button>
          </div>
        )}
      </section>
    </div>
  );
}
