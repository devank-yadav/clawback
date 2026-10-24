"use client";

// The result, on the same page the run played on: what's being won back, what was fair, how fast and how many AI
// calls, the charges in their piles (each opens how it was decided), and where to go next. The dispute card stays
// live, so a reply from the distributor's portal shows up here with the Negotiator's answer.

import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState, type ReactNode } from "react";
import { fetchOverview } from "@/lib/api";
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

export function DonePanel({ onOpen, onNew, rail }: { onOpen: (id: string) => void; onNew: () => void; rail: ReactNode }) {
  const { view, account, cast, link } = useRun();
  const [claimable, setClaimable] = useState<number | null>(null);
  const t = view.totals;
  const v = view.value;

  useEffect(() => {
    if (!account) return;
    let gone = false;
    fetchOverview(account.id).then((o) => !gone && setClaimable(o.kpis.claimable_now ?? null), () => {});
    return () => {
      gone = true;
    };
  }, [account]);

  const disputed = view.charges.filter((c) => (c.disputed ?? 0) > 0);
  const fair = view.charges.filter((c) => (c.accepted ?? 0) > 0);
  const waiting = view.charges.filter((c) => (c.waiting ?? 0) > 0);
  const facts = [
    t ? `${money(t.accepted)} accepted as fair` : null,
    t ? `${t.questions} question${t.questions === 1 ? "" : "s"} asked` : null,
    v?.seconds_to_decided ? `decided in ${Math.round(v.seconds_to_decided)} s` : null,
    v ? `${v.ai_calls} AI calls${v.ai_cost_usd ? ` (${money(v.ai_cost_usd)})` : ""}` : null,
  ].filter(Boolean);

  return (
    <>
      <section className="fl-done-hero" aria-live="polite">
        <span className="cx-eyebrow">{account ? `${account.brand.name} ← ${account.distributor.name} · invoice ${account.invoice.id}` : ""}</span>
        <h1>
          {t && t.disputed > 0
            ? <>Clawback is winning back <b>{money(t.disputed)}</b></>
            : <>Every charge was fair. Nothing to fight.</>}
        </h1>
        <p>{facts.join(" · ")}</p>
        <p className="cx-small cx-muted">{view.stage === "refused" ? `${cast.owner} held the credit memo: nothing posted.` : view.postingLabel}</p>
      </section>

      {rail}

      <div className="fl-piles">
        <Pile title="Disputing, with proof" tone="dispute" total={t?.disputed ?? 0} charges={disputed} amount={(c) => c.disputed ?? 0} onOpen={onOpen} />
        <Pile title="Fair, accepted" tone="fair" total={t?.accepted ?? 0} charges={fair} amount={(c) => c.accepted ?? 0} onOpen={onOpen} />
        <Pile title={`Waiting on ${cast.owner}`} tone="wait" total={t?.waiting ?? 0} charges={waiting} amount={(c) => c.waiting ?? 0} onOpen={onOpen} />
      </div>

      <DisputeCard />

      <nav className="fl-next" aria-label="What next">
        <a href={link("/portal")} target="_blank" rel="noreferrer">
          <strong>Argue as {cast.distributor}</strong>
          <small>Reply on their portal. The Negotiator answers with the evidence, or concedes to a signed change.</small>
          <em>Open the portal ↗</em>
        </a>
        <a href={link("/april")}>
          <strong>Next month</strong>
          <small>The next charges, decided by the rules {cast.owner} saved. No question asked twice.</small>
          <em>Run next month →</em>
        </a>
        <a href={link("/coach")}>
          <strong>Fix the next deal</strong>
          <small>Redlines for the next contract, each with what its clause cost this month.</small>
          <em>Open the Deal coach →</em>
        </a>
        <a href={link("/workspace")}>
          <strong>Six months back</strong>
          <small>{claimable !== null ? `${money(claimable)} more was wrongly taken and can still be claimed.` : "Past deductions checked the same way."}</small>
          <em>Open the workspace →</em>
        </a>
      </nav>

      <div className="cx-head" style={{ alignItems: "center" }}>
        <span className="cx-small cx-muted">
          Every decision is traceable: <a href={link("/workspace", { view: "payments" })}>every charge</a> · <a href={link("/audit")}>audit trail</a>
        </span>
        <button className="cx-btn is-ghost" onClick={onNew}>New payment</button>
      </div>
    </>
  );
}
