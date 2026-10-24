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
 * live: attaches to GET /runs/latest (or the run id in the URL) and follows GET /runs/{id}/events, resuming from the last event id;
 * only startPayment() ("Northmart pays") starts a run. The actions POST to the API
 * and the result comes back as events, so the screen never claims something happened before the API says so.
 */
export function useRunEvents(runId: string, source: DataSource = DATA_SOURCE) {
  const [state, dispatch] = useReducer(reduce, initial);
  const [epoch, setEpoch] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const busy = useRef(false);
  const last = useRef<RunEvent | undefined>(undefined);
  const lastSeen = useRef(0);
  const [target, setTarget] = useState<{ epoch: number; run: api.StartedRun | null } | null>(null);
  const [starting, setStarting] = useState(false);

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

    return () => {
      window.clearTimeout(clear);
    };
  }, [runId, source, epoch, play]);

  // Live: find the run to follow. "demo" and "latest" mean whatever run is newest; any other id is that run.
  // Nothing here starts a run: only startPayment() does, so a refresh re-attaches instead of repeating the work.
  useEffect(() => {
    if (source !== "live") return;
    let cancelled = false;
    const resolve = runId === "demo" || runId === "latest" ? api.latestRun() : Promise.resolve(api.runRef(runId));
    resolve.then(
      (run) => !cancelled && setTarget({ epoch, run }),
      (e: Error) => !cancelled && setError(`Can't reach the Clawback API (${e.message}). Check NEXT_PUBLIC_API_BASE.`),
    );
    return () => {
      cancelled = true;
    };
  }, [runId, source, epoch]);

  const followed = target?.epoch === epoch ? target.run : undefined;
  const followedId = followed?.run_id;
  const eventsUrl = followed?.events_url;
  useEffect(() => {
    if (source !== "live" || !eventsUrl) return;
    let stream: EventSource | null = null;
    let retry: number | undefined;
    let cancelled = false;
    const connect = () => {
      // The browser resends Last-Event-ID by itself when it reconnects. If it gives up, or on a fresh page, ask from the last id we hold.
      const url = `${eventsUrl}${eventsUrl.includes("?") ? "&" : "?"}after=${lastSeen.current}`;
      const es = new EventSource(api.apiUrl(url));
      stream = es;
      es.onmessage = (m) => {
        try {
          const event = JSON.parse(m.data) as RunEvent;
          lastSeen.current = Math.max(lastSeen.current, event.id);
          dispatch({ kind: "event", event });
        } catch {
          /* a malformed frame must not wipe the board */
        }
      };
      es.onopen = () => setError(null);
      es.onerror = () => {
        setError("Lost the connection to the Clawback API. Reconnecting…");
        if (es.readyState === EventSource.CLOSED && !cancelled) retry = window.setTimeout(connect, 2000);
      };
    };
    lastSeen.current = 0;
    dispatch({ kind: "reset" });
    connect();
    dispatch({ kind: "playing", on: true });
    return () => {
      cancelled = true;
      window.clearTimeout(retry);
      stream?.close();
    };
  }, [source, eventsUrl, followedId]);

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

  /** "Northmart pays" (live only): POST /payments/northmart, then follow the run it started. */
  const startPayment = useCallback(async () => {
    if (source !== "live" || starting) return;
    setStarting(true);
    try {
      const paid = await api.northmartPays();
      let run: api.StartedRun | null = paid.run_id ? api.runRef(paid.run_id) : null;
      // With Nessie the poller starts the run within about 5 seconds of the deposit.
      for (let i = 0; !run && i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        run = await api.latestRun();
      }
      if (!run) throw new Error("the deposit was posted but no run has started yet");
      setTarget({ epoch, run });
    } catch (e) {
      fail(e as Error);
    } finally {
      setStarting(false);
    }
  }, [source, starting, epoch]);

  /** Back to the start of the demo (live: POST /demo/reset, then wait for the next "Northmart pays"). */
  const reset = useCallback(() => {
    if (source === "live") {
      api.resetDemo().then(() => {
        dispatch({ kind: "reset" });
        setEpoch((n) => n + 1);
      }, fail);
    } else setEpoch((n) => n + 1);
  }, [source]);

  /** Live and no run exists yet: the page shows the "Northmart pays" button. */
  const awaitingPayment = source === "live" && followed === null && !error;

  return { state, answerQuestion, controllerDecides, startPayment, starting, awaitingPayment, reset, source, error };
}
