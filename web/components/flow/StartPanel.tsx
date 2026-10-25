"use client";

// The first screen, saying what is true right now: payments received and waiting for "Run the agents" (sent from a
// distributor's portal), a run going on for another distributor, or no new payment (then "Check for new payments").
// Also one place to drop the payment advice the distributor sent (PDF, CSV or pasted text): the Payment reader reads
// it (POST /accounts/{id}/remittance) and, if its lines add up, the run starts (POST …/remittance/run). Nothing here
// computes money.

import Link from "next/link";
import { useCallback, useEffect, useState, type DragEvent } from "react";
import { useRun } from "@/components/console/RunProvider";
import { readRemittance, runRemittance } from "@/components/upload/api";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { useFetched } from "@/lib/useFetched";
import { PageHeader } from "@/components/ui/kit";
import CheckPayments from "@/components/app/CheckPayments";
import { ReceivedList, RunAgentsButton, useReceivedPayments } from "@/components/app/ReceivedPayments";
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


  return (
    <div className="fl-hero">
      <section className="fl-start" aria-label="Start a payment check">
        <PageHeader
          title="Agents"
          line={<>
            {pending.length > 0
              ? <>New payment{pending.length === 1 ? "" : "s"} received. Run the agents to check {pending.length === 1 ? "it" : "them"} against the contract.</>
              : elsewhere.length > 0
                ? <>The agents are checking {elsewhere.map((d) => `${d.distributor.name}’s`).join(" and ")} payment now. <Link className="ph-link" href={withAccount("/", elsewhere[0].account_id, elsewhere[0].latest_run_id ? { run: elsewhere[0].latest_run_id } : undefined)}>Watch it</Link></>
                : <>No new payment from {cast.distributor}. New payments show up here; once the bank or QuickBooks is connected, they start the agents on their own.</>}
            {" "}<button className="ph-link" onClick={() => setPasting((v) => !v)} disabled={busy} aria-expanded={pasting}>Upload a remittance manually</button>
          </>}
          actions={!reading && (pending.length > 0
            ? <RunAgentsButton received={received} />
            : <CheckPayments account={account?.id} />)}
        />
        <ReceivedList received={received} />
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
          <div className="fl-last">
            <span>
              Last payment: {state.run.status === "failed" ? "the agents stopped" : `${money(last.disputed)} disputed · ${money(last.accepted)} fair${last.questions ? ` · ${last.questions} question${last.questions === 1 ? "" : "s"}` : ""}`}
            </span>
            <button className="cx-btn is-ghost" onClick={onOpenLast}>See the result</button>
          </div>
        )}

        <AgentRoster account={account?.id} working={starting || !!reading || !!runningId || elsewhere.length > 0} received={pending[0]?.distributor ?? null} />

      </section>
    </div>
  );
}
