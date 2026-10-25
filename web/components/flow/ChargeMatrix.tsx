"use client";

// Every charge against the four steps it goes through: the Calculator (tested code), the Investigator (AI), the
// Negotiator rehearsing the distributor's comeback (AI) and the Rules (code + the owner's policy). A cell fills when
// its event arrives; the one working right now breathes. Charges not reached yet wait in the queue below.

import { money } from "@/lib/format";
import type { RunState } from "@/lib/useRunEvents";
import type { ChargeView, WorkspaceView } from "@/lib/workspace";
import { Pill } from "@/components/console/ui";
import { CHECK } from "./parts";

type Cell = "todo" | "active" | "done" | "skipped" | "warn" | "person";

const COLS: { name: string; who: string }[] = [
  { name: "Calculator", who: "code" },
  { name: "Investigator", who: "AI" },
  { name: "Negotiator", who: "AI" },
  { name: "Rules", who: "code" },
];

const LABEL: Record<Cell, string> = { todo: "not started", active: "working now", done: "done", skipped: "not needed", warn: "handed to a person", person: "waiting on the owner" };

function cells(id: string, state: RunState, charge: ChargeView | undefined, current: boolean): Cell[] {
  const finding = state.findings[id];
  const decision = state.decisions[id];
  const rehearsal = state.rehearsals[id];
  const negotiating = state.feed.some((l) => l.charge_id === id && l.actor === "negotiator");
  const math: Cell = state.charges[id] ? "done" : "todo";
  const inv: Cell = finding ? "done" : decision ? "warn" : current ? "active" : "todo";
  const neg: Cell = rehearsal ? "done" : negotiating ? (decision ? "warn" : "active") : decision ? "skipped" : "todo";
  const rules: Cell = decision
    ? charge?.status === "Needs your input" ? "person" : "done"
    : current && finding && !(negotiating && !rehearsal) ? "active" : "todo";
  return [math, inv, neg, rules];
}

function Result({ c, owner }: { c: ChargeView | undefined; owner: string }) {
  if (!c || c.status === "Reviewing") return <span className="cx-tiny">…</span>;
  const rule = c.ruleId ? <span className="cx-tag is-rule">{c.ruleId.replace("rule-", "Rule #")}</span> : null;
  switch (c.status) {
    case "Disputed":
      return <><Pill tone="dispute">Dispute</Pill>{money(c.disputed ?? 0)}{rule}</>;
    case "Split decision":
      return <><Pill tone="dispute">Split</Pill>{money(c.disputed ?? 0)} / {money(c.accepted ?? 0)}{rule}</>;
    case "Accepted":
      return <><Pill tone="fair">Fair</Pill>{money(c.accepted ?? 0)}{rule}</>;
    case "Needs your input":
      return <><Pill tone="amber">Ask {owner}</Pill>{money(c.waiting ?? c.amount)}</>;
    default:
      return <Pill>Can’t verify</Pill>;
  }
}

export function ChargeMatrix({ state, view, owner, onOpen }: { state: RunState; view: WorkspaceView; owner: string; onOpen: (id: string) => void }) {
  const check = state.stages.check;
  const total = check?.total ?? view.remittance?.charge_count ?? state.order.length;
  const working = check ? check.status !== "done" : state.run?.status === "started";
  const currentId = check ? (check.status === "done" ? null : check.charge_id) : working ? state.order.filter((id) => !state.decisions[id]).at(-1) ?? null : null;
  const queued = Math.max(0, total - state.order.length);
  const byId = new Map(view.charges.map((c) => [c.id, c]));

  return (
    <section className="fl-matrix" aria-label="Each charge, step by step">
      <div className="fl-mhead" aria-hidden="true">
        <span>Charge</span>
        {COLS.map((c) => <span key={c.name}>{c.name}<em>{c.who}</em></span>)}
        <span>Result</span>
      </div>
      <ul className="fl-rows">
        {state.order.map((id) => {
          const charge = state.charges[id];
          const view_ = byId.get(id);
          const current = id === currentId;
          const row = cells(id, state, view_, current);
          return (
            <li key={id}>
              <button className={`fl-row ${current ? "is-current" : ""}`} onClick={() => onOpen(id)}>
                <span className="fl-ctitle">
                  <strong>{id} · {charge.description}</strong>
                  <small>{money(charge.amount)} taken</small>
                </span>
                {row.map((cell, k) => (
                  <span key={COLS[k].name} className={`fl-cell is-${cell}`} title={`${COLS[k].name}: ${LABEL[cell]}`} role="img" aria-label={`${COLS[k].name}: ${LABEL[cell]}`}>
                    {cell === "done" ? CHECK : cell === "skipped" ? "–" : cell === "warn" ? "!" : cell === "person" ? "?" : null}
                  </span>
                ))}
                <span className="fl-result"><Result c={view_} owner={owner} /></span>
                <span className="sr-only">Open how it was decided</span>
              </button>
            </li>
          );
        })}
        {Array.from({ length: queued }, (_, k) => (
          <li key={`q${k}`} className="fl-row is-queued" aria-hidden="true">
            <span className="fl-ctitle"><strong>Charge {state.order.length + k + 1} of {total}</strong><small>In the queue</small></span>
            {COLS.map((c) => <span key={c.name} className="fl-cell is-todo" />)}
            <span className="fl-result" />
          </li>
        ))}
      </ul>
    </section>
  );
}
