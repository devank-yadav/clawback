"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import * as api from "./api";
import { asAdmin, limitMessage } from "./session";
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
  StageInfo,
  Totals,
} from "./types";

/** `at` is the event's own timestamp, so screens can show when each agent acted. */
export type FeedLine = LogLine & { id: number; at: string };

/** One document the two readers finished: what the board says about it and the quotes they agreed on. */
export type ReadDoc = { label: string; items: string[]; at: string };

/** The latest stage event of each kind, with when the stage started (runs saved before stage events have none). */
export type Stages = {
  read: (StageInfo & { startedAt: string; at: string }) | null;
  check: (StageInfo & { startedAt: string; at: string }) | null;
  docs: ReadDoc[];
};

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
  stages: Stages;
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
  stages: { read: null, check: null, docs: [] },
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
      return { ...s, feed: [...s.feed, { id: e.id, at: e.at, ...e.data }] };
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
      // The run's value comes once, on the final totals; a later totals event without it keeps it.
      return { ...s, totals: { ...e.data, value: e.data.value ?? s.totals?.value ?? null } };
    case "stage": {
      const prev = s.stages[e.data.stage];
      const next = { ...e.data, startedAt: e.data.status === "started" || !prev ? e.at : prev.startedAt, at: e.at };
      // A document is finished when its tick moves done forward with the quotes it agreed on.
      const finished = e.data.stage === "read" && e.data.status === "progress" && e.data.done > (prev?.done ?? 0);
      return {
        ...s,
        stages: {
          ...s.stages,
          [e.data.stage]: next,
          docs: finished ? [...s.stages.docs, { label: e.data.label, items: e.data.items, at: e.at }] : s.stages.docs,
        },
      };
    }
    default:
      // A type this screen doesn't know yet must never wipe the board.
      return s;
  }
}

/** Said when the run a screen asked for by id is gone and the screen doesn't fall back to the latest one. */
export const RUN_GONE = "That run is no longer on the server. Start it again.";

class RunGone extends Error {}

/**
 * Folds one account's run into screen state. Attaches to GET /runs/latest?account= (or the run id given) and follows
 * GET /runs/{id}/events, resuming from the last event id. Only startPayment() ("<Distributor> pays") starts a run, so a
 * reload re-attaches instead of repeating the work. The actions POST to the API and their results come back as
 * events, so the screen never claims something happened before the API says so.
 *
 * A run the API answers 404 for (one from before the last deploy, or a stale ?run= link) is forgotten for the life of
 * the page and never asked for again: the hook looks up the account's latest run instead, or the start screen when
 * there is none. With `fallback: false` (a screen that follows one particular run) it stops and says so.
 */
export function useRunEvents(account: string | null, runId: string = "latest", { fallback = true }: { fallback?: boolean } = {}) {
  const [state, dispatch] = useReducer(reduce, initial);
  const [epoch, setEpoch] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const lastSeen = useRef(0);
  const [target, setTarget] = useState<{ key: string; run: api.StartedRun | null } | null>(null);
  const [starting, setStarting] = useState(false);
  /** The site's per-visitor limit refused the payment (a 429): friendly words, not an error. */
  const [limited, setLimited] = useState<string | null>(null);
  /** Runs the API answered 404 for, in the order they were lost. */
  const [gone, setGone] = useState<string[]>([]);
  const paying = useRef(false);
  const key = `${account}:${runId}:${epoch}:${gone.length}`;

  // Find the run to follow. "latest" means the account's newest run; any other id is that run, unless it is gone.
  useEffect(() => {
    if (!account) return;
    let cancelled = false;
    const lost = runId !== "latest" && gone.includes(runId);
    const resolve: Promise<api.StartedRun | null> =
      runId === "latest" || (lost && fallback)
        ? api.latestRun(account).then((run) => (run && gone.includes(run.run_id) ? null : run))
        : lost ? Promise.reject(new RunGone()) : Promise.resolve(api.runRef(runId));
    resolve.then(
      (run) => {
        if (cancelled) return;
        setTarget({ key, run });
        setError(null);
      },
      (e: Error) => !cancelled && setError(e instanceof RunGone ? RUN_GONE : api.unreachable(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [account, runId, key, gone, fallback]);

  const followed = target?.key === key ? target.run : undefined;
  const eventsUrl = followed?.events_url;
  const followedId = followed?.run_id;
  useEffect(() => {
    dispatch({ kind: "reset" });
    lastSeen.current = 0;
    if (!eventsUrl) return;
    let stream: EventSource | null = null;
    let retry: number | undefined;
    let cancelled = false;
    let failures = 0;
    const connect = () => {
      // The browser resends Last-Event-ID by itself when it reconnects. If it gives up, or on a fresh page, ask from the last id we hold.
      const url = `${eventsUrl}${eventsUrl.includes("?") ? "&" : "?"}after=${lastSeen.current}`;
      const es = new EventSource(api.apiUrl(url), { withCredentials: true });
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
      es.onopen = () => {
        failures = 0;
        setError(null);
      };
      es.onerror = () => {
        // While the browser retries by itself (a dropped network) the stream stays CONNECTING. CLOSED means the API
        // answered with something other than a stream: ask once why before trying again.
        if (es.readyState !== EventSource.CLOSED || cancelled) {
          setError("Lost the connection to Clawback. Reconnecting…");
          return;
        }
        es.close();
        void api.runEventsStatus(eventsUrl, lastSeen.current).then((status) => {
          if (cancelled) return;
          if (status === 404 || status === 410) {
            // The API no longer has this run: forget it for good and look again (the effect above re-resolves).
            if (followedId) setGone((g) => (g.includes(followedId) ? g : [...g, followedId]));
            return;
          }
          // Anything else (the API restarting behind the proxy, a timeout) is worth another try, a little later each time.
          setError("Lost the connection to Clawback. Reconnecting…");
          failures += 1;
          retry = window.setTimeout(connect, Math.min(30_000, 2000 * 2 ** (failures - 1)));
        });
      };
    };
    connect();
    dispatch({ kind: "playing", on: true });
    return () => {
      cancelled = true;
      window.clearTimeout(retry);
      stream?.close();
    };
  }, [eventsUrl, key, followedId]);

  const fail = useCallback((e: Error) => setError(
    e instanceof api.ApiError && e.status === 409
      ? "That was already taken care of (by text, the weekly email or another tab). This page shows where it stands now."
      : "That didn’t go through. Try again in a moment."), []);

  /** The admin's answer; saveRule false settles this charge only. The API checks the session. */
  const answerQuestion = useCallback(
    (questionId: string, text: string, saveRule = true) => {
      if (state.questions[questionId]?.answer || !text.trim()) return;
      asAdmin(() => api.answerQuestion(questionId, text.trim(), saveRule), fail);
    },
    [state.questions, fail],
  );

  /** The admin's yes or no on the credit memo; autoPost with a yes posts memos like it without asking from now on. */
  const decideApproval = useCallback(
    (approve: boolean, note: string | null = null, autoPost = false) => {
      const approval = state.approval;
      if (approval?.status !== "pending") return;
      asAdmin(() => api.decideApproval(approval.id, approve, note, approve && autoPost), fail);
    },
    [state.approval, fail],
  );

  /** "<Distributor> pays": one POST /payments/{account} per click, then follow the run it started. */
  const startPayment = useCallback(async () => {
    if (!account || paying.current) return;
    paying.current = true;
    setStarting(true);
    setLimited(null);
    try {
      const paid = await api.accountPays(account);
      let run: api.StartedRun | null = paid.run_id ? api.runRef(paid.run_id) : null;
      // With Nessie the poller starts the run within about 5 seconds of the deposit.
      for (let i = 0; !run && i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        run = await api.latestRun(account);
      }
      if (!run) throw new Error("the deposit was posted but no run has started yet");
      setTarget({ key, run });
    } catch (e) {
      const limit = limitMessage(e);
      if (limit) setLimited(limit);
      else fail(e as Error);
    } finally {
      paying.current = false;
      setStarting(false);
    }
  }, [account, key, fail]);

  /** Forget the run and look again (after a reset). */
  const refresh = useCallback(() => setEpoch((n) => n + 1), []);

  /** Follow a run another action started (an uploaded remittance's run). */
  const follow = useCallback((id: string) => setTarget({ key, run: api.runRef(id) }), [key]);

  /** No run exists yet for this account: the page offers "<Distributor> pays". */
  const awaitingPayment = !!account && followed === null && !error;
  const runId_ = followed?.run_id ?? null;

  // ---- Replay: a finished run's saved events played back into the same screen at their recorded pace (each event's
  // `at`), long waits shortened to a few seconds. The screen is the live one; only the source of events differs.
  const [replaying, setReplaying] = useState(false);
  const replayTimers = useRef<number[]>([]);
  const replayEvents = useRef<RunEvent[]>([]);
  const stopReplay = useCallback(() => {
    replayTimers.current.forEach((t) => window.clearTimeout(t));
    replayTimers.current = [];
  }, []);
  useEffect(() => stopReplay, [stopReplay]);

  const replay = useCallback(async () => {
    if (!runId_) return;
    const events = await api.runEventsOnce(runId_);
    if (!events.length) return;
    stopReplay();
    replayEvents.current = events;
    dispatch({ kind: "reset" });
    setReplaying(true);
    let t = 0;
    events.forEach((e, i) => {
      if (i > 0) {
        const gap = Date.parse(e.at) - Date.parse(events[i - 1].at);
        t += Number.isFinite(gap) ? Math.min(Math.max(gap, 0), 3000) : 300;
      }
      replayTimers.current.push(window.setTimeout(() => dispatch({ kind: "event", event: e }), t));
    });
    replayTimers.current.push(window.setTimeout(() => setReplaying(false), t + 100));
  }, [runId_, stopReplay]);

  /** Straight to the result: every event not yet played lands at once (the reducer skips the ones it has). */
  const skipReplay = useCallback(() => {
    stopReplay();
    replayEvents.current.forEach((event) => dispatch({ kind: "event", event }));
    setReplaying(false);
  }, [stopReplay]);

  return { state, runId: runId_, answerQuestion, decideApproval, startPayment, follow, starting, limited, awaitingPayment, refresh, error, gone, replay, replaying, skipReplay };
}
