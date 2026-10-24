"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { money } from "@/lib/format";
import { CHARGES } from "@/lib/prototype/charges";
import { OWNER_ANSWER, REMITTANCE } from "@/lib/prototype/run";
import type { DecisionData } from "@/lib/types";
import type { RunState } from "@/lib/useRunEvents";
import { Glyph, type Status } from "./parts";

const drop = {
  initial: { opacity: 0, y: -10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, height: 0, marginTop: 0 },
  transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const },
};

type Props = {
  state: RunState;
  selected: string | null;
  onSelect: (id: string) => void;
  onAnswer: (questionId: string) => void;
  onController: (approve: boolean) => void;
};

export function statusOf(d: DecisionData | undefined): Status {
  return d ? d.decision : "checking";
}

export function ChargeList({ state, selected, onSelect, onAnswer, onController }: Props) {
  const openQuestion = Object.values(state.questions).find((q) => !q.answer);
  const ids = state.order;
  const disputing = ids.filter((id) => ["dispute", "split"].includes(state.decisions[id]?.decision));
  const fair = ids.filter((id) => state.decisions[id]?.decision === "accept");
  const skipped = ids.filter((id) => state.decisions[id]?.decision === "skip");
  const checking = ids.filter((id) => !state.decisions[id]);
  // An unanswered charge lives in its question card until the question arrives.
  const asking = ids.filter((id) => state.decisions[id]?.decision === "ask" && openQuestion?.charge_id !== id);

  return (
    <div className="flex flex-col gap-6">
      <AnimatePresence initial={false}>
        {openQuestion && (
          <motion.div key="question" {...drop} className="overflow-hidden">
            <OwnerQuestion
              text={openQuestion.text}
              selected={selected === openQuestion.charge_id}
              onAnswer={() => onAnswer(openQuestion.id)}
              onOpen={() => onSelect(openQuestion.charge_id)}
            />
          </motion.div>
        )}
        {state.approval && (
          <motion.div key="approval" {...drop} className="overflow-hidden">
            <ControllerApproval state={state} onDecide={onController} />
          </motion.div>
        )}
      </AnimatePresence>

      <Group title="Disputing" count={disputing.length}>
        {disputing.map((id) => (
          <Row key={id} id={id} state={state} selected={selected === id} onSelect={onSelect} />
        ))}
      </Group>
      <Group title="Accepted as fair" count={fair.length}>
        {fair.map((id) => (
          <Row key={id} id={id} state={state} selected={selected === id} onSelect={onSelect} />
        ))}
      </Group>
      {asking.length + skipped.length > 0 && (
        <Group title="On hold" count={asking.length + skipped.length}>
          {[...asking, ...skipped].map((id) => (
            <Row key={id} id={id} state={state} selected={selected === id} onSelect={onSelect} />
          ))}
        </Group>
      )}
      {checking.length > 0 && (
        <Group title="Checking" count={checking.length}>
          {checking.map((id) => (
            <Row key={id} id={id} state={state} selected={selected === id} onSelect={onSelect} />
          ))}
        </Group>
      )}
    </div>
  );
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <h2 className="flex items-baseline gap-2 px-1 font-display text-[15px] font-semibold text-ink">
        {title}
        <span className="num text-[13px] font-normal text-muted">{count}</span>
      </h2>
      {count === 0 ? (
        <p className="mt-2 rounded-xl border border-dashed border-line px-4 py-3 text-[15px] text-muted">None yet</p>
      ) : (
        <ul className="mt-2 overflow-hidden rounded-xl border border-line bg-panel">
          <AnimatePresence initial={false}>{children}</AnimatePresence>
        </ul>
      )}
    </section>
  );
}

function Outcome({ d }: { d: DecisionData | undefined }) {
  if (!d) return <span className="text-muted">Checking</span>;
  switch (d.decision) {
    case "split":
      return (
        <>
          <span className="text-dispute">
            <span className="num">{money(d.disputed)}</span> disputed
          </span>
          <span className="text-muted">
            , <span className="num">{money(d.accepted)}</span> fair
          </span>
        </>
      );
    case "dispute":
      return (
        <span className="text-dispute">
          Disputing <span className="num">{money(d.disputed)}</span>
        </span>
      );
    case "accept":
      return <span className="text-muted">{d.rule_id ? "Fair by Rule #1" : "Fair"}</span>;
    case "ask":
      return <span className="text-ask">Needs your answer</span>;
    case "skip":
      return <span className="text-muted">Can&apos;t verify the deal</span>;
  }
}

function Row({ id, state, selected, onSelect }: { id: string; state: RunState; selected: boolean; onSelect: (id: string) => void }) {
  const c = CHARGES[id];
  const f = state.findings[id];
  const d = state.decisions[id];
  return (
    <motion.li layout="position" {...drop} className="border-b border-line-soft last:border-b-0">
      <button
        type="button"
        onClick={() => onSelect(id)}
        aria-current={selected ? "true" : undefined}
        className={`group relative flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors focus-visible:-outline-offset-2 ${
          selected ? "bg-sunk" : "hover:bg-sunk/70"
        }`}
      >
        {selected && <span className="absolute inset-y-2 left-0 w-[3px] rounded-r bg-accent" aria-hidden />}
        <Glyph status={statusOf(d)} className="mt-[5px]" />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="num text-[13px] text-muted">{id}</span>
              <span className="text-[17px] font-semibold">{c.title}</span>
            </span>
            <span className="num shrink-0 text-[17px]">{f ? money(f.taken) : ""}</span>
          </span>
          <span className="flex flex-wrap items-baseline justify-between gap-x-3">
            <span className="text-[15px] text-muted">{c.detail}</span>
            <span className="ml-auto text-[14px] whitespace-nowrap">
              <Outcome d={d} />
            </span>
          </span>
        </span>
      </button>
    </motion.li>
  );
}

function OwnerQuestion({ text, selected, onAnswer, onOpen }: { text: string; selected: boolean; onAnswer: () => void; onOpen: () => void }) {
  return (
    <section aria-labelledby="q-heading" className="rounded-xl border border-ask/45 bg-ask-soft p-4 sm:p-5">
      <h2 id="q-heading" className="flex items-center gap-2 font-display text-[15px] font-semibold text-ask">
        <Glyph status="ask" />
        One question for you
      </h2>
      <p className="mt-2 text-[17px] leading-snug text-ink">{text}</p>
      <p className="mt-2 text-[15px] text-muted">Clawback saves your answer as a rule, so it won&apos;t ask about this again.</p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onAnswer}
          className="rounded-lg bg-accent px-4 py-2.5 text-[16px] font-semibold text-white shadow-sm transition-[filter] hover:brightness-110 dark:text-[#0f151c]"
        >
          {OWNER_ANSWER}
        </button>
        <button
          type="button"
          onClick={onOpen}
          aria-pressed={selected}
          className="rounded-lg px-3 py-2.5 text-[16px] font-semibold text-ink underline-offset-4 hover:underline"
        >
          See the evidence
        </button>
      </div>
      <p className="mt-3 text-[14px] text-muted">We also texted you this question. You can reply there instead.</p>
    </section>
  );
}

function ControllerApproval({ state, onDecide }: { state: RunState; onDecide: (approve: boolean) => void }) {
  const a = state.approval!;
  const who = REMITTANCE.controller;
  const memo = state.ledger.find((p) => p.entity === "Credit memo");
  const open = state.ledger.find((p) => p.status === "open");

  if (a.status === "approved") {
    return (
      <section aria-label="Controller approval" className="rounded-xl border border-line bg-panel p-4 sm:p-5">
        <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold text-good">
          <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden>
            <circle cx="8" cy="8" r="6.5" fill="var(--good)" />
            <path d="M5.2 8.2 7.1 10l3.6-3.9" fill="none" stroke="var(--panel)" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {who} approved
        </h2>
        <p className="mt-2 text-[17px]">
          {memo ? (
            <>
              Credit memo for <span className="num">{money(memo.amount)}</span> posted to QuickBooks.
            </>
          ) : (
            "Posting the credit memo to QuickBooks…"
          )}
        </p>
        {open && (
          <p className="mt-1 text-[15px] text-muted">
            <span className="num">{money(open.amount)}</span> stays open on {REMITTANCE.invoice} while dispute D-0417 is decided.
          </p>
        )}
      </section>
    );
  }

  if (a.status === "refused") {
    return (
      <section aria-label="Controller approval" className="rounded-xl border border-line bg-panel p-4 sm:p-5">
        <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold text-ink">
          <ClockIcon />
          Held by {who}
        </h2>
        <p className="mt-2 text-[17px]">Nothing was posted to QuickBooks. The credit memo is back with you.</p>
        {a.note && <blockquote className="mt-3 border-l-2 border-line pl-3 text-[16px] text-muted">“{a.note}”</blockquote>}
      </section>
    );
  }

  return (
    <section aria-label="Controller approval" className="rounded-xl border border-dashed border-muted/60 bg-panel p-4 sm:p-5">
      <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold text-ink">
        <ClockIcon />
        Waiting on {who} to approve
      </h2>
      <p className="mt-2 text-[17px]">
        Credit memo for <span className="num">{money(a.amount)}</span>, {a.lines} lines.
      </p>
      <p className="mt-1 text-[15px] text-muted">{who} keeps your books. Nothing goes into QuickBooks until they say yes.</p>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-dashed border-line pt-3">
        <span className="mr-1 text-[14px] text-muted">Prototype: play {who}&apos;s reply</span>
        <button type="button" onClick={() => onDecide(true)} className="rounded-lg border border-line bg-panel px-3 py-1.5 text-[15px] font-semibold hover:bg-sunk">
          Approve
        </button>
        <button type="button" onClick={() => onDecide(false)} className="rounded-lg border border-line bg-panel px-3 py-1.5 text-[15px] font-semibold hover:bg-sunk">
          Refuse
        </button>
      </div>
    </section>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden>
      <circle cx="8" cy="8" r="6" fill="none" stroke="var(--muted)" strokeWidth="1.6" strokeDasharray="2.4 1.6" />
      <path d="M8 5v3.2l2 1.3" fill="none" stroke="var(--ink)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
