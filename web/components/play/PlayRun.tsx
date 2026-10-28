"use client";

// The run, one thing at a time (the design system's ClawRun screen) on the live run's events: the payment line, the
// Scoreboard, ONE stage (the charge being checked or just stamped, the one question, then the approval and the
// dispute email), and the row of all the charges. The spotlight moves to the next charge only after the current one
// has shown its stamp, so a fast run still reads card by card. Amounts and decisions come from the run's events.

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useRun } from "@/components/console/RunProvider";
import { choicesFor } from "@/components/console/Review";
import { DisputeThread, ReviewAndSend } from "@/components/disputes/DisputeMail";
import { Money } from "@/components/console/ui";
import { ACTOR } from "@/components/flow/parts";
import type { Stage } from "@/components/flow/stages";
import { money } from "@/lib/format";
import { useChargeDetail } from "@/lib/useChargeDetail";
import type { ChargeView } from "@/lib/workspace";
import { CardQueue, DeductionCard, DecisionCard, Scoreboard, VerdictStamp, type Verdict } from "./PlayKit";

const HOLD_MS = 1500; // how long a stamped card stays before the next one is dealt

const VERDICT_OF: Record<string, Verdict | null> = {
  "Reviewing": null, "Split decision": "split", "Disputed": "dispute", "Accepted": "fair", "Needs your input": "ask", "Can’t verify": "skip",
};

const verdictOf = (c: ChargeView) => VERDICT_OF[c.status] ?? null;

/** The charge in the spotlight: it waits on each stamped card for HOLD_MS, then deals the next. */
function useSpotlight(charges: ChargeView[], runKey: string) {
  const [spot, setSpot] = useState(0);
  const [key, setKey] = useState(runKey);
  if (key !== runKey) { setKey(runKey); setSpot(0); } // a new run or a replay starts from the first card
  const current = charges[spot];
  const decided = !!current && verdictOf(current) !== null;
  useEffect(() => {
    if (!decided || spot >= charges.length - 1) return;
    const t = window.setTimeout(() => setSpot((s) => Math.min(s + 1, charges.length - 1)), HOLD_MS);
    return () => window.clearTimeout(t);
  }, [decided, spot, charges.length]);
  return { spot: Math.min(spot, Math.max(charges.length - 1, 0)), atEnd: spot >= charges.length - 1 };
}

/** The admin's one question as a DecisionCard, wired to the same answer the old card sent. */
function PlayQuestion({ charge }: { charge: ChargeView }) {
  const { state, view, source, answerQuestion, cast } = useRun();
  const detail = useChargeDetail(charge.id, state.run?.run_id, source);
  const [busy, setBusy] = useState(false);
  const q = view.question!;
  const clause = detail?.evidence.find((e) => e.kind === "clause") ?? null;
  const level = q.risk?.level ? (String(q.risk.level).charAt(0).toUpperCase() + String(q.risk.level).slice(1).toLowerCase()) as "High" | "Medium" | "Low" : null;
  const choices = choicesFor(charge.code).map((c) => ({
    value: c.id,
    label: c.label,
    consequence: c.id === "dispute" ? `${money(charge.amount)} goes in the dispute` : c.id === "accept" ? `${money(charge.amount)} counts as fair` : "The agents check the notice and decide",
  }));
  const why = q.risk?.reason ?? "The contract leaves this to judgment, so the agents won’t guess your policy.";
  return (
    <DecisionCard
      level={level}
      amount={charge.amount}
      question={<>{cast.distributor} kept {money(charge.amount)} for “{charge.title}”. Is that fair?</>}
      why={why}
      quote={clause ? (clause.quote?.text ?? clause.summary) : undefined}
      quoteSource={clause?.label}
      choices={choices}
      busy={busy}
      goLabel="Decide"
      onDecide={(value, remember) => {
        const pick = choicesFor(charge.code).find((c) => c.id === value);
        if (!pick) return;
        setBusy(true);
        answerQuestion(q.id, pick.text, remember);
      }}
    />
  );
}

/** The admin's yes to the credit memo for the fair charges, in the design system's ApprovalCard. */
function PlayApproval() {
  const { view, decideApproval, cast } = useRun();
  const [autoPost, setAutoPost] = useState(false);
  const [busy, setBusy] = useState(false);
  const a = view.approval;
  if (!a || a.status !== "pending") return null;
  return (
    <section className="cb-approval cb-fair-memo" aria-label="Your approval">
      <span className="cb-approval-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" aria-hidden="true"><path d="M12 6v7M12 17.5v.5" /></svg>
        Needs your OK
      </span>
      <h3>Post the fair charges to QuickBooks?</h3>
      <p>A credit memo for what the contract allows. The disputed money stays open with {cast.distributor}.</p>
      <ul>{view.proposalLines.map((l) => <li key={l.chargeId}><span>{l.label}</span><Money value={l.amount} /></li>)}</ul>
      <div className="cb-approval-total"><span>Total</span><Money value={a.amount} className="cx-big" /></div>
      <label className="cb-check">
        <input type="checkbox" checked={autoPost} onChange={(e) => setAutoPost(e.target.checked)} />
        <span className="cb-check-box" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
        <span className="cb-check-text"><span>Post fair charges like these automatically from now on</span><small>Memos up to {money(a.amount)} post without asking</small></span>
      </label>
      <div className="cb-approval-actions">
        <button type="button" className="cx-btn is-blue" disabled={busy} onClick={() => { setBusy(true); decideApproval(true, null, autoPost); }}>{busy ? "Posting…" : `Approve ${money(a.amount)}`}</button>
        <button type="button" className="cx-btn is-ghost" disabled={busy} onClick={() => { setBusy(true); decideApproval(false, `Held by ${cast.owner}`); }}>Not yet</button>
      </div>
    </section>
  );
}

/** The dispute: a stamp, one sentence, one blue button (the real composer); once sent, the thread with the replies. */
function PlayDispute() {
  const { state, account, cast, link } = useRun();
  const d = state.dispute;
  if (!d) return null;
  const runId = state.run?.run_id ?? null;
  const unsent = d.status === "ready_to_send" || d.status === "draft";
  const replies = state.portal.filter((m) => m.dispute_id === d.id).length;
  return (
    <section className="cb-card cb-play-dispute" aria-label={`Dispute ${d.id}`}>
      <div className="cb-play-dispute-head">
        <VerdictStamp verdict="dispute" amount={d.total} still />
        <div>
          <h2>{unsent ? `Dispute ${d.id} is ready for ${cast.distributor}.` : `Dispute ${d.id} is with ${cast.distributor}.`}</h2>
          <p>{d.lines.length} charge{d.lines.length === 1 ? "" : "s"}, each with the contract sentence, the data and the math. {unsent ? `Nothing goes to ${cast.distributor} until you send it.` : "Their reply lands here the moment it comes in."}</p>
        </div>
      </div>
      {unsent
        ? <ReviewAndSend disputeId={d.id} runId={runId} distributor={cast.distributor} />
        : <DisputeThread disputeId={d.id} runId={runId} distributor={cast.distributor} refreshKey={`${d.status}:${replies}`} limit={4} />}
      <div className="cb-run-next">
        <Link className="cx-btn is-ghost is-small" href={link("/disputes", { id: d.id, ...(runId ? { run: runId } : {}) })}>Open the thread</Link>
        <a className="cx-btn is-ghost is-small" href={link("/portal")} target="_blank" rel="noreferrer">{account?.distributor.portal_name ?? `${cast.distributor}’s portal`}<ArrowUpRight aria-hidden="true" /></a>
      </div>
    </section>
  );
}

export function PlayRun({ pending, done, onOpen, head }: { pending: Stage[]; done: boolean; onOpen: (chargeId: string) => void; head?: ReactNode }) {
  const { state, view, cast } = useRun();
  const charges = view.charges;
  const runKey = state.run?.run_id ?? "none";
  const { spot, atEnd } = useSpotlight(charges, runKey);
  const t = view.totals;
  const r = view.remittance;
  const current = charges[spot] ?? null;
  const allDecided = charges.length > 0 && charges.every((c) => verdictOf(c) !== null);
  const questions = charges.filter((c) => c.status === "Needs your input").length;
  const people = pending.filter((s) => s.key === "approval" || s.key === "file");
  // The agent at work, in its own words: the newest line in the run's feed.
  const last = state.feed.at(-1);
  const agentLine = last ? `${ACTOR[last.actor] ?? last.actor}: ${last.text}` : undefined;

  const cards = useMemo(() => charges.map((c) => ({ id: c.id, title: c.title, amount: c.amount, verdict: verdictOf(c) })), [charges]);
  // until every charge has arrived, the pips count the payment's charges, not just the ones read so far
  const showDone = done && !people.length && allDecided;

  let stage: ReactNode;
  if (!charges.length) {
    stage = (
      <DeductionCard title={`${cast.distributor}’s charges`} amount={r?.taken ?? 0} state="checking" agent={agentLine ?? "The Payment reader is listing every deduction"} />
    );
  } else if (current && current.status === "Needs your input" && view.question && !view.question.answer) {
    stage = <PlayQuestion key={view.question.id} charge={current} />;
  } else if (allDecided && atEnd && people.length) {
    stage = people[0].key === "approval"
      ? <PlayApproval />
      : <PlayDispute />;
  } else if (showDone) {
    stage = state.dispute ? <PlayDispute /> : (
      <section className="cb-card cb-play-done">
        <span className="cx-pill is-green">Done</span>
        <h2>Every charge is decided.</h2>
        <p>{view.disputeLabel}{view.postingLabel ? ` ${view.postingLabel}` : ""}</p>
      </section>
    );
  } else if (current) {
    const v = verdictOf(current);
    stage = (
      <DeductionCard
        key={current.id}
        code={current.code}
        meta={`${current.kind} · ref ${current.ref}`}
        title={current.title}
        amount={current.amount}
        verdict={v}
        back={current.disputed}
        state={v ? undefined : "checking"}
        agent={agentLine}
        reason={v ? current.finding : undefined}
        onOpen={v && v !== "ask" ? () => onOpen(current.id) : undefined}
      />
    );
  }

  return (
    <div className="cb-run">
      <header className="cb-run-head">
        <p className="cb-run-pay">
          {r ? <>{r.counterparty} paid {money(r.received)} and kept <b>{money(r.taken)}</b>.</> : <>Waiting for {cast.distributor}’s payment…</>}
        </p>
        <div className="cb-run-meta">
          <span className="cb-run-sub">{cast.brand}{r ? ` · invoice ${r.invoice_id ?? ""} · ${r.charge_count} charges` : ""}</span>
          {head}
        </div>
      </header>
      <Scoreboard
        back={t?.disputed ?? 0}
        fair={t?.accepted ?? 0}
        questions={questions}
        pips={[...charges.map(verdictOf), ...Array<Verdict | null>(Math.max(0, (r?.charge_count ?? 0) - charges.length)).fill(null)]}
        current={current && !verdictOf(current) ? spot : undefined}
        label={showDone ? "Disputed with proof" : "Clawing back"}
        line={r ? `of the ${money(r.taken)} ${r.counterparty} kept` : undefined}
      />
      <div className="cb-run-stage">{stage}</div>
      {charges.length > 0 && <CardQueue cards={cards} current={current && !showDone ? current.id : undefined} onPick={onOpen} label="Charges in this payment: open a decided one to see its proof" />}
    </div>
  );
}
