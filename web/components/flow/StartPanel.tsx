"use client";

// The first screen, saying what is true right now: payments received and waiting for "Run the agents" (shown by the
// button and the list alone), a run going on for another distributor, or no new payment (then "Check for new payments").
// A small "Upload" opens one place to drop the payment advice the distributor sent (PDF, CSV or pasted text): the Payment reader reads
// it (POST /accounts/{id}/remittance) and, if its lines add up, the run starts (POST …/remittance/run). Nothing here
// computes money.

import Link from "next/link";
import { Upload } from "lucide-react";
import { useCallback, useEffect, useState, type DragEvent } from "react";
import { useRun } from "@/components/console/RunProvider";
import { readRemittance, runRemittance } from "@/components/upload/api";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { useFetched } from "@/lib/useFetched";
import CheckPayments from "@/components/app/CheckPayments";
import { RunAgentsButton, useReceivedPayments } from "@/components/app/ReceivedPayments";
import { AgentRoster } from "./AgentRoster";

/** The supplier's distributors whose payment the agents are checking right now, read again every 4 seconds. */
function useCheckingElsewhere() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setTick((n) => n + 1), 4_000);
    return () => window.clearInterval(t);
  }, []);
  const load = useCallback(() => api.fetchSuppliers().catch(() => []), []);
  return (useFetched(load, String(tick)).data ?? []).flatMap((s) => s.distributors).filter((d) => d.tracked && d.status === "checking");
}

export function StartPanel({ onStart, onOpenLast }: { onStart: () => void; onOpenLast: () => void }) {
  const { account, cast, state, view, starting, limited, follow, error } = useRun();
  const received = useReceivedPayments();
  const { pending, runningId } = received;
  const elsewhere = useCheckingElsewhere().filter((d) => d.account_id !== account?.id);
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
        setProblem(r.problems[0]?.text ?? "The lines don’t add up to what was taken, so no run can start from this read. Check the file and try again.");
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


  const next = pending[0] ?? null;
  // The owner's Settings: with "start the agents when a payment comes in" on (the default), nothing waits for a click.
  const settings = useFetched(useCallback(() => api.fetchAutopilot(), []));
  const auto = settings.data?.run_on_arrival ?? true;
  const upload = (
    <button className="cx-btn is-ghost fl-upload" onClick={() => setPasting((v) => !v)} disabled={busy} aria-expanded={pasting}>
      <Upload aria-hidden="true" />Upload a payment slip
    </button>
  );

  return (
    <div className="cb-run cb-start">
      <header className="cb-run-head">
        <h1 className="cb-run-pay">Payments</h1>
        <p className="cb-run-sub">{cast.brand}{cast.distributor ? ` · ${cast.distributor}` : ""}</p>
      </header>

      {/* One card: the payment that's waiting, the run going on elsewhere, or that nothing has come in yet. */}
      {!reading && (
        <section className="cb-card cb-hero" aria-label="The next payment">
          {next ? (
            <>
              <span className="cx-pill is-accent is-live">New payment received</span>
              <h2>{next.distributor} paid {money(next.received)} of your {money(next.expected)} invoice.</h2>
              <p>The agents check every charge they kept against the signed contract, one at a time.</p>
              <div className="cb-run-next"><RunAgentsButton received={received} />{upload}</div>
              {pending.length > 1 && <small className="cb-hero-more">{pending.length - 1} more payment{pending.length > 2 ? "s" : ""} waiting after this one</small>}
            </>
          ) : elsewhere.length > 0 ? (
            <>
              <span className="cx-pill is-accent is-live">Working</span>
              <h2>The agents are checking {elsewhere.map((d) => `${d.distributor.name}’s`).join(" and ")} payment.</h2>
              <p>You can watch it, or wait here for {cast.distributor}’s next payment.</p>
              <div className="cb-run-next">
                <Link className="cx-btn is-blue" href={withAccount("/", elsewhere[0].account_id, elsewhere[0].latest_run_id ? { run: elsewhere[0].latest_run_id } : undefined)}>Watch it</Link>
                {upload}
              </div>
            </>
          ) : (
            <>
              <span className="cx-pill is-green">Watching</span>
              <h2>No new payment from {cast.distributor} yet.</h2>
              <p>{auto
                ? "When one comes in from the bank or QuickBooks, the agents start on their own. You’re only asked when the contract leaves something to you."
                : "When one comes in from the bank or QuickBooks, it shows up here, ready for you to run the agents."}</p>
              <div className="cb-run-next"><CheckPayments account={account?.id} />{upload}</div>
            </>
          )}
        </section>
      )}

        {reading && (
          <div className="fl-drop is-busy">
            <span className="fl-reading" aria-live="polite">
              <span className="cx-pill is-live">Payment reader · AI</span>
              <strong>Reading {reading}…</strong>
              <small>Listing every deduction line, then checking each one is printed word for word and that they add up.</small>
              <span className="fl-bar is-indeterminate"><i /></span>
            </span>
          </div>
        )}

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

      {state.run && !waitingOnYou && last && (
        <button type="button" className="cb-card cb-last" onClick={onOpenLast}>
          <span>Last payment</span>
          <strong>{state.run.status === "failed" ? "The agents stopped" : `${money(last.disputed)} disputed · ${money(last.accepted)} fair${last.questions ? ` · ${last.questions} question${last.questions === 1 ? "" : "s"}` : ""}`}</strong>
          <em>See the result</em>
        </button>
      )}

      <AgentRoster compact account={account?.id} working={starting || !!reading || !!runningId || elsewhere.length > 0} received={next?.distributor ?? null} />
    </div>
  );
}
