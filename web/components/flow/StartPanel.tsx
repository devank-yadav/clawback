"use client";

// The first screen: one place to drop the payment advice the distributor sent (PDF, CSV or pasted text), or the
// sample payment. A dropped file is read by the Payment reader (POST /accounts/{id}/remittance); if its lines add up,
// the run starts on its own (POST …/remittance/run). Nothing here computes money.

import { useState, type DragEvent } from "react";
import { useRun } from "@/components/console/RunProvider";
import { readRemittance, runRemittance } from "@/components/upload/api";
import { money } from "@/lib/format";
import { PageHero } from "@/components/ui/kit";

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
  const waitingOnYou = view.stage === "owner" || view.approval?.status === "pending";

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
      <section className="fl-start" aria-label="Start a payment check">
        <PageHero
          title={<>Your agents are watching <em>{cast.distributor}’s payments.</em></>}
          sub={<>When a payment lands, they read the deal, check every deduction, <mark>dispute the wrong ones with proof</mark> and accept the fair ones. You’re asked only when the deal is unclear.</>}
        >
          <div className="bw-actions">
            {reading ? (
              <div className="fl-drop is-busy">
                <span className="fl-reading" aria-live="polite">
                  <span className="cx-pill is-live">Payment reader · AI</span>
                  <strong>Reading {reading}…</strong>
                  <small>Listing every deduction line, then checking each one is printed word for word and that they add up.</small>
                  <span className="fl-bar is-indeterminate"><i /></span>
                </span>
              </div>
            ) : (
              <>
                <button className="cx-btn is-blue fl-go" onClick={pay} disabled={busy || !account}>
                  {starting ? "The payment is landing…" : `Send a test payment from ${cast.distributor}`}
                </button>
                <span className="bw-fine">or <button onClick={() => setPasting((v) => !v)} disabled={busy} aria-expanded={pasting}>upload the remittance they sent</button></span>
              </>
            )}
          </div>
        </PageHero>

        {pasting && !reading && (
          <div className="fl-paste">
            <label
              className={`fl-drop ${over ? "is-over" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }}
              onDragLeave={() => setOver(false)}
              onDrop={drop}
            >
              <span className="fl-plus" aria-hidden="true">+</span>
              <strong>Drop {cast.distributor}’s payment advice</strong>
              <small>PDF, CSV or text · or click to choose a file</small>
              <input type="file" accept=".pdf,.csv,.txt,application/pdf,text/csv,text/plain" disabled={busy || !account}
                aria-label="Choose the payment advice file"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void read({ file: f }, f.name); e.target.value = ""; }} />
            </label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} aria-label="Remittance text" placeholder={`Or paste the remittance ${cast.distributor} sent`} />
            <div><button className="cx-btn" disabled={busy || !text.trim()} onClick={() => void read({ text }, "the pasted text")}>Read it</button></div>
          </div>
        )}

        {problem && <div className="fl-problem" role="alert">{problem}</div>}
        {limited && <div className="fl-problem" role="status">{limited}</div>}
        {error && <div className="fl-problem" role="alert">{error}</div>}

        {state.run && (waitingOnYou ? (
          <div className="fl-last is-waiting">
            <span><strong>Your previous payment is waiting on your decision.</strong> Starting a new one replaces it, and its open question closes.</span>
            <button className="cx-btn" onClick={onOpenLast}>Open it</button>
          </div>
        ) : last ? (
          <div className="fl-last">
            <span>
              Last payment: {state.run.status === "failed" ? "the agents stopped" : `${money(last.disputed)} disputed · ${money(last.accepted)} fair${last.questions ? ` · ${last.questions} question${last.questions === 1 ? "" : "s"}` : ""}`}
            </span>
            <button className="cx-btn is-ghost" onClick={onOpenLast}>See the result</button>
          </div>
        ) : null)}

        <div className="bw-stage">
          <div className="bw-frame">
            <div className="fl-watch" aria-label="What the agents are watching">
              {[["Bank", "Deposits from " + cast.distributor], ["QuickBooks", "Invoices and payments"], ["Remittance inbox", "Payment advice and broker emails"]].map(([n, d]) => (
                <span key={n} className="fl-watch-item"><i className="tb-dot is-live" /><span><strong>{n}</strong><small>{d}</small></span></span>
              ))}
            </div>
            <div className="fl-crew" aria-label="The agents">
              {CREW.map((c) => <span key={c.name} className={`fl-chip ${c.tag === "CODE" ? "is-code" : ""}`}><i>{c.tag === "CODE" ? "CODE" : "AI"}</i>{c.name}</span>)}
              <span className="fl-chip is-person"><i>YOU</i>{cast.owner}</span>
            </div>
            <p className="cx-tiny">AI reads and writes. Tested code does every calculation. You decide only what the deal leaves open.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
