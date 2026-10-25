"use client";

// Payments a distributor sent from its portal, waiting for "Run the agents" (GET /payments/pending, read again every
// 4 seconds). The Agents tab and Home show them in place of "Check for new payments"; "Run the agents" starts the
// payment's run (POST /payments/pending/{id}/run) and opens it. Nothing here computes money.

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Play } from "lucide-react";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import { useFetched } from "@/lib/useFetched";

const ago = (iso: string) => {
  const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  return s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
};

export type Received = {
  pending: api.PendingPayment[];
  runningId: string | null;
  problem: string | null;
  run: (p: api.PendingPayment) => Promise<void>;
};

/** The payments waiting for "Run the agents", and starting one. */
export function useReceivedPayments(): Received {
  const router = useRouter();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setTick((n) => n + 1), 4_000);
    return () => window.clearInterval(t);
  }, []);
  const load = useCallback(() => api.fetchPendingPayments().catch(() => [] as api.PendingPayment[]), []);
  const pending = useFetched(load, String(tick)).data ?? [];
  const [runningId, setRunningId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function run(p: api.PendingPayment) {
    if (runningId) return;
    setRunningId(p.id);
    setProblem(null);
    try {
      const r = await api.runPendingPayment(p.id);
      router.push(withAccount("/", p.account_id, r.run_id ? { run: r.run_id } : undefined));
    } catch (e) {
      setProblem(`The agents couldn’t start on ${p.distributor}’s payment (${(e as Error).message}).`);
      setRunningId(null);
    }
  }

  return { pending, runningId, problem, run };
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
  const { pending, runningId, problem, run } = received;
  if (!pending.length && !problem) return null;
  return (
    <>
      {pending.length > 0 && (
        <ul className="fl-received" aria-label="Payments received">
          {pending.map((p, i) => (
            <li key={p.id}>
              <span className="fl-received-chip">Payment received</span>
              <span className="fl-received-text">
                <strong>{p.distributor} paid {money(p.received)} of {money(p.expected)} on {p.invoice_id}</strong>
                <small>Sent from {p.distributor}’s portal · {ago(p.received_at)} · the agents haven’t started</small>
              </span>
              {i > 0 && <button className="cx-btn is-ghost" onClick={() => void run(p)} disabled={!!runningId}>{runningId === p.id ? "Starting…" : "Run the agents"}</button>}
            </li>
          ))}
        </ul>
      )}
      {problem && <div className="fl-problem" role="alert">{problem}</div>}
    </>
  );
}
