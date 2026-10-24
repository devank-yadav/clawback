"use client";

// The result, on the same page the run played on. Facts only, never a forecast: what the distributor kept, what the deal
// didn't allow and what was done about it, what was fair, how fast and how many AI calls, the charges in their piles (each opens how it was decided), and where to go next. The dispute card stays
// live, so a reply from the distributor's portal shows up here with the Negotiator's answer.

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { money } from "@/lib/format";
import type { ChargeView } from "@/lib/workspace";
import { useRun } from "@/components/console/RunProvider";
import { Money } from "@/components/console/ui";
import { DisputeCard } from "./Spotlight";

function Pile({ title, tone, total, charges, amount, onOpen }: { title: string; tone: "dispute" | "fair" | "wait"; total: number; charges: ChargeView[]; amount: (c: ChargeView) => number; onOpen: (id: string) => void }) {
  const still = useReducedMotion();
  if (charges.length === 0) return null;
  return (
    <section className={`fl-pile is-${tone}`} aria-label={title}>
      <h3><span>{title}</span><Money value={total} /></h3>
      <ul>
        {charges.map((c, k) => (
          <motion.li key={c.id} initial={still ? false : { opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: k * 0.08 }}>
            <button className="fl-pcard" onClick={() => onOpen(c.id)}>
              <span><strong style={{ fontWeight: 500 }}>{c.id} · {c.title}</strong><span>{money(amount(c))}</span></span>
              <small>{c.ruleId ? `${c.ruleId.replace("rule-", "Rule #")} · ` : ""}{c.reason}</small>
            </button>
          </motion.li>
        ))}
      </ul>
    </section>
  );
}

/** "<$0.01" for tiny costs, so a real number never reads as free. */
const cost = (usd: number) => (usd > 0 && usd < 0.01 ? "<$0.01" : money(usd));

export function DonePanel({ onOpen, onNew, rail, next, failed }: { onOpen: (id: string) => void; onNew: () => void; rail: ReactNode; next: ReactNode; failed: boolean }) {
  const { view, state, cast, link } = useRun();
  const t = view.totals;
  const v = view.value;
  const r = view.remittance;
  const distributor = r?.counterparty ?? cast.distributor;

  const disputed = view.charges.filter((c) => (c.disputed ?? 0) > 0);
  const fair = view.charges.filter((c) => (c.accepted ?? 0) > 0);
  const waiting = view.charges.filter((c) => (c.waiting ?? 0) > 0);
  const held = state.dispute?.status === "draft";
  // Facts about what already happened, never a forecast.
  const facts = [
    t && t.questions ? `${t.questions} question${t.questions === 1 ? "" : "s"} for you` : t ? "no questions needed" : null,
    v && v.seconds_to_decided !== null && v.seconds_to_decided !== undefined ? `decided in ${Math.round(v.seconds_to_decided)} s` : null,
    v ? `${v.ai_calls} AI calls${v.ai_cost_usd ? ` · ${cost(v.ai_cost_usd)}` : ""}` : null,
  ].filter(Boolean) as string[];
  const posting = view.postingProblem ?? (view.approval ? view.postingLabel : (t?.accepted ?? 0) > 0 ? "Fair charges are waiting for your approval before anything posts" : "Nothing to post to QuickBooks");

  return (
    <>
      <section className="fl-sum" aria-live="polite">
        <div className="fl-sum-text">
          {failed ? (
            <h1>The agents stopped before finishing</h1>
          ) : (
            <h1>
              {r ? <>{distributor} kept <b>{money(r.taken)}</b></> : <>{distributor}’s charges</>}
              {t && t.disputed > 0 && <> · <span className="is-dispute">{money(t.disputed)} {held ? "held for you" : "disputed"}</span></>}
              {t && t.accepted > 0 && <> · <span className="is-fair">{money(t.accepted)} fair</span></>}
              {t && t.waiting > 0 && <> · <span className="is-wait">{money(t.waiting)} waits on you</span></>}
            </h1>
          )}
          <div className="fl-facts">
            {failed && <span>{state.feed.filter((l) => l.level === "error").at(-1)?.text ?? "See the activity"}</span>}
            {facts.map((f) => <span key={f}>{f}</span>)}
            <span>{posting}</span>
          </div>
        </div>
        <button className="cx-btn" onClick={onNew}>Check a new payment</button>
      </section>

      {next && <section className="fl-nextstep" aria-label="Your next step"><span className="cx-eyebrow">Your next step</span>{next}</section>}

      {rail}

      {disputed.length + fair.length + waiting.length === 0 ? (
        <p className="cx-small cx-muted">No charge has a decision yet.</p>
      ) : (
        <div className="fl-piles">
          <Pile title="Disputed, with proof" tone="dispute" total={t?.disputed ?? 0} charges={disputed} amount={(c) => c.disputed ?? 0} onOpen={onOpen} />
          <Pile title="Fair, accepted" tone="fair" total={t?.accepted ?? 0} charges={fair} amount={(c) => c.accepted ?? 0} onOpen={onOpen} />
          <Pile title="Waiting on your decision" tone="wait" total={t?.waiting ?? 0} charges={waiting} amount={(c) => c.waiting ?? 0} onOpen={onOpen} />
        </div>
      )}

      <DisputeCard />

      <nav className="fl-next" aria-label="What next">
        {state.dispute && (
          <a href={link("/portal")} target="_blank" rel="noreferrer">
            <strong>Argue as {distributor}</strong>
            <small>Reply on their portal. The Negotiator answers with the evidence, or concedes to a signed change.</small>
            <em>Open the portal ↗</em>
          </a>
        )}
        <a href={link("/april")}>
          <strong>Next month</strong>
          <small>The next charges, decided by the rules you saved. No question asked twice.</small>
          <em>Run next month →</em>
        </a>
        <a href={link("/coach")}>
          <strong>Fix the next deal</strong>
          <small>Redlines for the next contract, each with what its clause cost this month.</small>
          <em>Open the Deal coach →</em>
        </a>
        <a href={link("/workspace")}>
          <strong>Past payments</strong>
          <small>The last six months, checked the same way: what the deal didn’t allow.</small>
          <em>Open the overview →</em>
        </a>
      </nav>

      <div className="cx-head" style={{ alignItems: "center" }}>
        <span className="cx-small cx-muted">
          Every decision is traceable: <a href={link("/workspace", { view: "payments" })}>every charge</a> · <a href={link("/audit")}>audit trail</a>
        </span>
        <button className="cx-btn is-ghost" onClick={onNew}>Check a new payment</button>
      </div>
    </>
  );
}
