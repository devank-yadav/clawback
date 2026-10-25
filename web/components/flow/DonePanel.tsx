"use client";

// A run's result, on the page the run played on. Facts only, never a forecast: what the distributor took and what
// the deal didn't allow, where the money went, the one thing that needs the admin first, the charges in their piles
// (each opens how it was decided), the dispute, and the run's audit trail. Nothing else.

import { motion, useReducedMotion } from "framer-motion";
import { useCallback, useState, type ReactNode } from "react";
import { Play, ScrollText } from "lucide-react";
import { money } from "@/lib/format";
import type { ChargeView } from "@/lib/workspace";
import { useRun } from "@/components/console/RunProvider";
import { DisputeCard } from "./Spotlight";
import { MoneyBar } from "@/components/ui/kit";
import { AuditDrawer } from "./AuditDrawer";
import { Claw, landPulse } from "@/components/ui/Claw";

// The claw pulls the disputed money back once per run in this tab, and again after Replay.
const clawed = new Set<string>();

function Pile({ title, tone, total, charges, amount, onOpen }: { title: string; tone: "dispute" | "fair" | "wait"; total: number; charges: ChargeView[]; amount: (c: ChargeView) => number; onOpen: (id: string) => void }) {
  const still = useReducedMotion();
  if (charges.length === 0) return null;
  return (
    <section className={`fl-pile is-${tone}`} aria-label={title}>
      <h3><span>{title}</span><span className="fl-pile-total">{money(total)}</span></h3>
      <ul>
        {charges.map((c, k) => (
          <motion.li key={c.id} initial={still ? false : { opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: k * 0.08 }}>
            <button className="fl-pcard" onClick={() => onOpen(c.id)}>
              <span><strong style={{ fontWeight: 500 }}>{c.id} · {c.title}</strong><span>{money(amount(c))}</span></span>
              <small>{(c.disputed ?? 0) > 0 && (c.accepted ?? 0) > 0 ? `Split: ${money(c.disputed ?? 0)} disputed, ${money(c.accepted ?? 0)} fair · ` : ""}{c.ruleId ? `${c.ruleId.replace("rule-", "Rule #")} · ` : ""}{c.reason}</small>
            </button>
          </motion.li>
        ))}
      </ul>
    </section>
  );
}

export function DonePanel({ onOpen, onNew, onReplay, next, disputeInNext = false, failed }: { onOpen: (id: string) => void; onNew: () => void; onReplay?: () => void; rail?: ReactNode; next: ReactNode; disputeInNext?: boolean; failed: boolean }) {
  const { view, state, cast } = useRun();
  const [audit, setAudit] = useState(false);
  const [sum, setSum] = useState<HTMLElement | null>(null);
  const [clawDone, setClawDone] = useState(false);
  const closeAudit = useCallback(() => setAudit(false), []);
  const t = view.totals;
  const v = view.value;
  const r = view.remittance;
  const distributor = r?.counterparty ?? cast.distributor;

  const disputed = view.charges.filter((c) => (c.disputed ?? 0) > 0);
  const fair = view.charges.filter((c) => (c.accepted ?? 0) > 0);
  const waiting = view.charges.filter((c) => (c.waiting ?? 0) > 0);
  const unsent = state.dispute?.status === "draft" || state.dispute?.status === "ready_to_send";
  const seconds = v && v.seconds_to_decided != null ? Math.round(v.seconds_to_decided) : null;
  // The headline's second line: the one fact that matters most, already decided.
  const second = !t ? null
    : t.disputed > 0 ? `${money(t.disputed)} of it isn’t allowed by the deal.`
    : t.waiting > 0 ? `${money(t.waiting)} of it waits on your call.`
    : "Every charge matches the deal.";
  const disputedLabel = unsent ? "To dispute, ready to send" : `Disputed, awaiting ${distributor}’s reply`;
  const meta = [
    r ? `${distributor} paid ${money(r.received)} of ${money(r.expected)}` : null,
    view.charges.length ? `${view.charges.length} charges checked${seconds !== null ? ` in ${seconds} s` : ""}` : null,
  ].filter(Boolean).join(" · ");

  const runId = state.run?.run_id;
  const claw = !failed && !!r && !!t && t.disputed > 0 && !!runId && !clawDone && !clawed.has(runId);

  return (
    <>
      <section className="fl-sum cw-host" aria-live="polite" ref={setSum}>
        {claw && (
          <Claw host={sum} from=".fl-sum-taken" to=".bw-bar-track i.is-dispute" label={`${money(t.disputed)} disputed`} delay={0.35}
            onLand={() => landPulse(document.querySelector(".bw-bar-legend li:first-child b"))}
            onDone={() => { clawed.add(runId); setClawDone(true); }} />
        )}
        <div className="fl-sum-text">
          {failed ? (
            <h1>The agents stopped before finishing</h1>
          ) : (
            <h1>
              {r ? <>{distributor} kept <span className="fl-sum-taken">{money(r.taken)}</span>.</> : <>{distributor}’s charges.</>}
              {second && <em>{second}</em>}
            </h1>
          )}
          {failed ? <p className="fl-sum-meta">{state.feed.filter((l) => l.level === "error").at(-1)?.text ?? "See the activity"}</p> : meta && <p className="fl-sum-meta">{meta}</p>}
        </div>
      </section>

      {!failed && t && (
        <MoneyBar
          label={r ? `Where the ${money(r.taken)} went` : "Where the charges went"}
          parts={[
            { tone: "dispute", label: disputedLabel, value: t.disputed },
            { tone: "fair", label: "Fair, accepted", value: t.accepted },
            { tone: "wait", label: "Waits on you", value: t.waiting },
          ]}
        />
      )}

      {next && (
        <section className="fl-nextstep" aria-labelledby="fl-next-h">
          <h2 id="fl-next-h">Needs you</h2>
          {next}
        </section>
      )}

      {disputed.length + fair.length + waiting.length === 0 ? (
        <p className="cx-small cx-muted">No charge has a decision yet.</p>
      ) : (
        <div className="fl-piles">
          <Pile title={disputedLabel} tone="dispute" total={t?.disputed ?? 0} charges={disputed} amount={(c) => c.disputed ?? 0} onOpen={onOpen} />
          <Pile title="Fair, accepted" tone="fair" total={t?.accepted ?? 0} charges={fair} amount={(c) => c.accepted ?? 0} onOpen={onOpen} />
          <Pile title="Waiting on your decision" tone="wait" total={t?.waiting ?? 0} charges={waiting} amount={(c) => c.waiting ?? 0} onOpen={onOpen} />
        </div>
      )}

      {!disputeInNext && <DisputeCard />}

      <div className="fl-foot">
        <span className="fl-foot-left">
          {state.run && onReplay && <button className="cx-btn is-ghost" onClick={() => { if (runId) clawed.delete(runId); setClawDone(false); onReplay(); }}><Play aria-hidden="true" />Replay the run</button>}
          {state.run && <button className="cx-btn is-ghost" onClick={() => setAudit(true)}><ScrollText aria-hidden="true" />Audit trail</button>}
        </span>
        <button className="cx-btn is-ghost" onClick={onNew}>Back to the start</button>
      </div>
      {state.run && <AuditDrawer runId={state.run.run_id} open={audit} onClose={closeAudit} />}
    </>
  );
}
