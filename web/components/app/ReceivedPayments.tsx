"use client";

// Payments a distributor sent from its portal, waiting for "Run the agents" (GET /payments/pending, read again every
// 4 seconds). The Agents tab and Home show them in place of "Check for new payments"; "Run the agents" starts the
// payment's run (POST /payments/pending/{id}/run) in the background: it shows on Payments and opens only when
// clicked. Nothing here computes money.

import { useCallback, useEffect, useState } from "react";
import { Play } from "lucide-react";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { useFetched } from "@/lib/useFetched";

const ago = (iso: string) => {
  const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  return s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
};

/** Fired when "Check for new payments" leaves a payment received, so it shows at once (not on the next look). */
export const RECEIVED_EVENT = "clawback:payment-received";

export type Received = {
  pending: api.PendingPayment[];
  runningId: string | null;
  problem: string | null;
  /** What just started, in a sentence ("The agents are checking Northmart’s payment."). */
  started: string | null;
  run: (p: api.PendingPayment) => Promise<void>;
};

/** The payments waiting for "Run the agents", and starting one. */
export function useReceivedPayments(): Received {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    const t = window.setInterval(bump, 4_000);
    window.addEventListener(RECEIVED_EVENT, bump);
    return () => { window.clearInterval(t); window.removeEventListener(RECEIVED_EVENT, bump); };
  }, []);
  const load = useCallback(() => api.fetchPendingPayments().catch(() => [] as api.PendingPayment[]), []);
  const pending = useFetched(load, String(tick)).data ?? [];
  const [runningId, setRunningId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [started, setStarted] = useState<string | null>(null);

  async function run(p: api.PendingPayment) {
    if (runningId) return;
    setRunningId(p.id);
    setProblem(null);
    setStarted(null);
    try {
      await api.runPendingPayment(p.id);
      setStarted(`The agents are checking ${p.distributor}’s payment.`);
      window.dispatchEvent(new Event(RECEIVED_EVENT));  // the payment leaves "received" and shows on Payments
    } catch (e) {
      setProblem(`The agents couldn’t start on ${p.distributor}’s payment (${(e as Error).message}).`);
    } finally {
      setRunningId(null);
    }
  }

  return { pending, runningId, problem, started, run };
}

/** The blue button that takes "Check for new payments"' place while a payment waits: it runs the oldest. */
export function RunAgentsButton({ received }: { received: Received }) {
  const first = received.pending[0];
  if (!first) return null;
  return (
    <button className="cx-btn is-blue fl-runbtn" onClick={() => void received.run(first)} disabled={!!received.runningId}>
      <Play aria-hidden="true" />{received.runningId === first.id ? "Starting…" : "Run the agents"}
    </button>
  );
}

/** Each payment received: who paid, how much of the invoice, when; a later one has its own "Run the agents". */
export function ReceivedList({ received }: { received: Received }) {
  const { pending, runningId, problem, started, run } = received;
  if (!pending.length && !problem && !started) return null;
  return (
    <>
      {pending.length > 0 && (
        <ul className="fl-received" aria-label="Payments received">
          {pending.map((p, i) => (
            <li key={p.id}>
              <span className="fl-received-chip">New payment received</span>
              <span className="fl-received-text">
                <strong>{p.distributor} paid {money(p.received)} of {money(p.expected)} on {p.invoice_id}</strong>
                <small>{p.source === "bank" ? "Deposited in the bank" : `Sent from ${p.distributor}’s portal`} · {ago(p.received_at)} · the agents haven’t started</small>
              </span>
              {i > 0 && <button className="cx-btn is-ghost" onClick={() => void run(p)} disabled={!!runningId}>{runningId === p.id ? "Starting…" : "Run the agents"}</button>}
            </li>
          ))}
        </ul>
      )}
      {problem && <div className="fl-problem" role="alert">{problem}</div>}
      {started && !pending.length && <p className="ck-note" role="status">{started} It’s on Payments.</p>}
    </>
  );
}
