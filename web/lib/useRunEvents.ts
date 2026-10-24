"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ApprovalData, DecisionData, DisputeData, FindingData, LedgerPostData, QuestionData, RunEvent, TotalsData } from "./types";
import {
  ANSWER_SCRIPT,
  CONTROLLER_APPROVE_SCRIPT,
  CONTROLLER_REFUSE_SCRIPT,
  RUN_SCRIPT,
  type Scripted,
} from "./prototype/run";

export type FeedLine = { id: number; text: string; level: "info" | "ok" | "warn" };

export type RunState = {
  order: string[];
  findings: Record<string, FindingData>;
  decisions: Record<string, DecisionData>;
  questions: Record<string, QuestionData & { answer?: string; rule_id?: string | null }>;
  approval: ApprovalData | null;
  dispute: DisputeData | null;
  ledger: LedgerPostData[];
  totals: TotalsData | null;
  feed: FeedLine[];
  lastEventId: number;
  /** The first pass over all charges has finished streaming. */
  complete: boolean;
};

const initial: RunState = {
  order: [],
  findings: {},
  decisions: {},
  questions: {},
  approval: null,
  dispute: null,
  ledger: [],
  totals: null,
  feed: [],
  lastEventId: 0,
  complete: false,
};

type Action = { kind: "event"; event: RunEvent } | { kind: "reset" } | { kind: "complete" };

function reduce(state: RunState, action: Action): RunState {
  if (action.kind === "reset") return initial;
  if (action.kind === "complete") return { ...state, complete: true };
  const e = action.event;
  const s = { ...state, lastEventId: e.id };
  switch (e.type) {
    case "log":
      return { ...s, feed: [...s.feed, { id: e.id, ...e.data }] };
    case "finding":
      return {
        ...s,
        findings: { ...s.findings, [e.data.charge_id]: e.data },
        order: s.order.includes(e.data.charge_id) ? s.order : [...s.order, e.data.charge_id],
      };
    case "decision":
      return { ...s, decisions: { ...s.decisions, [e.data.charge_id]: e.data } };
    case "question":
      return { ...s, questions: { ...s.questions, [e.data.id]: e.data } };
    case "answer": {
      const q = s.questions[e.data.question_id];
      if (!q) return s;
      return { ...s, questions: { ...s.questions, [q.id]: { ...q, answer: e.data.text, rule_id: e.data.rule_id } } };
    }
    case "approval":
      return { ...s, approval: e.data };
    case "dispute":
      return { ...s, dispute: e.data };
    case "ledger_post":
      return { ...s, ledger: [...s.ledger, e.data] };
    case "totals":
      return { ...s, totals: e.data };
  }
}

/**
 * Folds the run's event stream into screen state.
 * Today it replays local prototype data. Later (card R7) it opens GET /runs/{id}/events with
 * Last-Event-ID, and the actions below POST to the API instead of appending scripted events.
 */
export function useRunEvents(runId: string) {
  const [state, dispatch] = useReducer(reduce, initial);
  const timers = useRef<number[]>([]);
  const nextId = useRef(1);
  const busy = useRef(false);

  const play = useCallback((script: Scripted[], onDone?: () => void) => {
    let wait = 0;
    busy.current = true;
    script.forEach((step, i) => {
      wait += step.delay;
      const t = window.setTimeout(() => {
        const event = { ...step.event, id: nextId.current++, at: new Date().toISOString() } as RunEvent;
        dispatch({ kind: "event", event });
        if (i === script.length - 1) {
          busy.current = false;
          onDone?.();
        }
      }, wait);
      timers.current.push(t);
    });
  }, []);

  useEffect(() => {
    dispatch({ kind: "reset" });
    nextId.current = 1;
    play(RUN_SCRIPT, () => dispatch({ kind: "complete" }));
    const pending = timers.current;
    return () => {
      pending.forEach((t) => window.clearTimeout(t));
      timers.current = [];
    };
  }, [runId, play]);

  const answerQuestion = useCallback(
    (questionId: string) => {
      if (busy.current || state.questions[questionId]?.answer) return;
      play(ANSWER_SCRIPT);
    },
    [play, state.questions],
  );

  const controllerDecides = useCallback(
    (approve: boolean) => {
      if (busy.current || state.approval?.status !== "pending") return;
      play(approve ? CONTROLLER_APPROVE_SCRIPT : CONTROLLER_REFUSE_SCRIPT);
    },
    [play, state.approval],
  );

  return { state, answerQuestion, controllerDecides, source: "prototype" as const };
}
