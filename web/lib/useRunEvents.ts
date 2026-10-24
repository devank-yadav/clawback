"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { eventsAfter, replayDelay, waitsForPerson } from "./fixture";
import type {
  Answer,
  Approval,
  Charge,
  Decision,
  Dispute,
  Finding,
  LedgerPost,
  LogLine,
  PortalMessage,
  Question,
  Rehearsal,
  Rule,
  RunEvent,
  RunInfo,
  Totals,
} from "./types";

export type FeedLine = LogLine & { id: number };

export type RunState = {
  run: RunInfo | null;
  order: string[];
  charges: Record<string, Charge>;
  findings: Record<string, Finding>;
  rehearsals: Record<string, Rehearsal>;
  decisions: Record<string, Decision>;
  questions: Record<string, Question>;
  answers: Record<string, Answer>;
  rules: Record<string, Rule>;
  approval: Approval | null;
  dispute: Dispute | null;
  portal: PortalMessage[];
  ledger: LedgerPost[];
  totals: Totals | null;
  feed: FeedLine[];
  lastEventId: number;
  /** Events are still arriving (false while the run waits on a person, and once it finishes). */
  playing: boolean;
};

const initial: RunState = {
  run: null,
  order: [],
  charges: {},
  findings: {},
  rehearsals: {},
  decisions: {},
  questions: {},
  answers: {},
  rules: {},
  approval: null,
  dispute: null,
  portal: [],
  ledger: [],
  totals: null,
  feed: [],
  lastEventId: 0,
  playing: false,
};

type Action = { kind: "event"; event: RunEvent } | { kind: "reset" } | { kind: "playing"; on: boolean };

function reduce(state: RunState, action: Action): RunState {
  if (action.kind === "reset") return initial;
  if (action.kind === "playing") return { ...state, playing: action.on };
  const e = action.event;
  if (e.id <= state.lastEventId) return state; // replayed after a reconnect
  const s = { ...state, lastEventId: e.id };
  switch (e.type) {
    case "run":
      // Later run events (waiting, finished) carry no remittance; keep the one from the start.
      return { ...s, run: { ...e.data, remittance: e.data.remittance ?? s.run?.remittance ?? null } };
    case "log":
      return { ...s, feed: [...s.feed, { id: e.id, ...e.data }] };
    case "charge":
      return {
        ...s,
        charges: { ...s.charges, [e.data.id]: e.data },
        order: s.order.includes(e.data.id) ? s.order : [...s.order, e.data.id],
      };
    case "finding":
      return { ...s, findings: { ...s.findings, [e.data.charge_id]: e.data } };
    case "rehearsal":
      return { ...s, rehearsals: { ...s.rehearsals, [e.data.charge_id]: e.data } };
    case "decision":
      return { ...s, decisions: { ...s.decisions, [e.data.charge_id]: e.data } };
    case "question":
      return { ...s, questions: { ...s.questions, [e.data.id]: e.data } };
    case "answer": {
      const q = s.questions[e.data.question_id];
      return {
        ...s,
        answers: { ...s.answers, [e.data.question_id]: e.data },
        questions: q
          ? { ...s.questions, [q.id]: { ...q, answer: e.data.text, answered_at: e.data.answered_at, rule_id: e.data.rule_id } }
          : s.questions,
      };
    }
    case "rule":
      return { ...s, rules: { ...s.rules, [e.data.id]: e.data } };
    case "approval":
      return { ...s, approval: e.data };
    case "dispute":
      return { ...s, dispute: e.data };
    case "portal_message":
      return { ...s, portal: [...s.portal, e.data] };
    case "ledger_post":
      return { ...s, ledger: [...s.ledger.filter((p) => p.id !== e.data.id), e.data] };
    case "totals":
      return { ...s, totals: e.data };
    default:
      // A type this screen doesn't know yet must never wipe the board.
      return s;
  }
}

/**
 * Folds the run's event stream into screen state.
 * Today it replays web/fixtures/ and pauses wherever a person has to act. Card R7 swaps the source for
 * GET /runs/{id}/events (Last-Event-ID = state.lastEventId), and the two actions POST to the API instead.
 */
export function useRunEvents(runId: string) {
  const [state, dispatch] = useReducer(reduce, initial);
  const timers = useRef<number[]>([]);
  const busy = useRef(false);
  const last = useRef<RunEvent | undefined>(undefined);

  /** Plays events until the next point where a person must act (or the end). */
  const play = useCallback((events: RunEvent[], resume = false) => {
    let wait = 0;
    let i = 0;
    busy.current = true;
    dispatch({ kind: "playing", on: true });
    for (; i < events.length; i++) {
      const e = events[i];
      if (i > 0 && waitsForPerson(e)) break;
      if (i === 0 && waitsForPerson(e) && !resume) break;
      wait += replayDelay(last.current, e);
      last.current = e;
      timers.current.push(window.setTimeout(() => dispatch({ kind: "event", event: e }), wait));
    }
    timers.current.push(
      window.setTimeout(() => {
        busy.current = false;
        dispatch({ kind: "playing", on: false });
      }, wait),
    );
  }, []);

  useEffect(() => {
    dispatch({ kind: "reset" });
    last.current = undefined;
    play(eventsAfter(0));
    const pending = timers.current;
    return () => {
      pending.forEach((t) => window.clearTimeout(t));
      timers.current = [];
    };
  }, [runId, play]);

  const answerQuestion = useCallback(
    (questionId: string) => {
      if (busy.current || state.questions[questionId]?.answer) return;
      play(eventsAfter(state.lastEventId), true);
    },
    [play, state.questions, state.lastEventId],
  );

  const controllerDecides = useCallback(
    (approve: boolean) => {
      if (busy.current || state.approval?.status !== "pending") return;
      play(eventsAfter(state.lastEventId, approve ? "approved" : "refused"), true);
    },
    [play, state.approval, state.lastEventId],
  );

  return { state, answerQuestion, controllerDecides, source: "fixture" as const };
}
