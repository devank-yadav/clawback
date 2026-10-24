"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { eventsAfter, replayDelay, waitsForPerson } from "./fixture";
import { OWNER_RULE_REPLY } from "./cast";
import * as api from "./live";
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

/** "fixture" replays web/fixtures/ (no backend, no keys); "live" follows the FastAPI event stream. */
export type DataSource = "fixture" | "live";
export const DATA_SOURCE: DataSource = process.env.NEXT_PUBLIC_DATA_SOURCE === "live" ? "live" : "fixture";

/**
 * Folds the run's event stream into screen state.
 * fixture: replays web/fixtures/ and pauses wherever a person has to act; the two actions continue the recording.
 * live: POST /runs, then GET /runs/{id}/events (EventSource reconnects with Last-Event-ID); the actions POST to the API
 * and the result comes back as events, so the screen never claims something happened before the API says so.
 */
export function useRunEvents(runId: string, source: DataSource = DATA_SOURCE) {
  const [state, dispatch] = useReducer(reduce, initial);
  const [epoch, setEpoch] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const busy = useRef(false);
  const last = useRef<RunEvent | undefined>(undefined);
  const started = useRef<{ epoch: number; run: Promise<api.StartedRun> } | null>(null);

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
    // Deferred so every setState here happens outside the effect body.
    const clear = window.setTimeout(() => setError(null), 0);
    last.current = undefined;
    busy.current = false;

    if (source === "fixture") {
      play(eventsAfter(0));
      const pending = timers.current;
      return () => {
        window.clearTimeout(clear);
        pending.forEach((t) => window.clearTimeout(t));
        timers.current = [];
        busy.current = false;
      };
    }

    // One POST /runs per epoch, even though React StrictMode mounts this effect twice in dev.
    if (started.current?.epoch !== epoch) started.current = { epoch, run: api.startRun() };
    let stream: EventSource | null = null;
    let cancelled = false;
    started.current.run
      .then((run) => {
        if (cancelled) return;
        stream = new EventSource(api.apiUrl(run.events_url));
        stream.onmessage = (m) => {
          try {
            dispatch({ kind: "event", event: JSON.parse(m.data) as RunEvent });
          } catch {
            /* a malformed frame must not wipe the board */
          }
        };
        stream.onopen = () => setError(null);
        stream.onerror = () => setError("Lost the connection to the Clawback API. Reconnecting…");
        dispatch({ kind: "playing", on: true });
      })
      .catch((e: Error) => !cancelled && setError(`Can't reach the Clawback API (${e.message}). Check NEXT_PUBLIC_API_BASE.`));
    return () => {
      cancelled = true;
      window.clearTimeout(clear);
      stream?.close();
    };
  }, [runId, source, epoch, play]);

  const fail = (e: Error) => setError(`The API didn't accept that action (${e.message}).`);

  const answerQuestion = useCallback(
    (questionId: string, text: string = OWNER_RULE_REPLY) => {
      if (state.questions[questionId]?.answer) return;
      if (source === "live") {
        api.answerQuestion(questionId, text).catch(fail);
        return;
      }
      if (busy.current) return;
      play(eventsAfter(state.lastEventId), true);
    },
    [play, source, state.questions, state.lastEventId],
  );

  const controllerDecides = useCallback(
    (approve: boolean, note: string | null = null) => {
      const approval = state.approval;
      if (approval?.status !== "pending") return;
      if (source === "live") {
        api.decideApproval(approval.id, approve, note).catch(fail);
        return;
      }
      if (busy.current) return;
      play(eventsAfter(state.lastEventId, approve ? "approved" : "refused"), true);
    },
    [play, source, state.approval, state.lastEventId],
  );

  /** Back to the start of the demo (live: POST /demo/reset first, then a fresh run). */
  const reset = useCallback(() => {
    if (source === "live") api.resetDemo().then(() => setEpoch((n) => n + 1), fail);
    else setEpoch((n) => n + 1);
  }, [source]);

  return { state, answerQuestion, controllerDecides, reset, source, error };
}
