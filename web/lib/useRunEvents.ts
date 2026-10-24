"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import * as api from "./api";
import { asRole, limitMessage } from "./session";
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
      // The run's value comes once, on the final totals; a later totals event without it keeps it.
      return { ...s, totals: { ...e.data, value: e.data.value ?? s.totals?.value ?? null } };
    default:
      // A type this screen doesn't know yet must never wipe the board.
      return s;
  }
}

/**
 * Folds one account's run into screen state. Attaches to GET /runs/latest?account= (or the run id given) and follows
 * GET /runs/{id}/events, resuming from the last event id. Only startPayment() ("<Distributor> pays") starts a run, so a
 * reload re-attaches instead of repeating the work. The actions POST to the API and their results come back as
 * events, so the screen never claims something happened before the API says so.
 */
export function useRunEvents(account: string | null, runId: string = "latest") {
  const [state, dispatch] = useReducer(reduce, initial);
  const [epoch, setEpoch] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const lastSeen = useRef(0);
  const [target, setTarget] = useState<{ key: string; run: api.StartedRun | null } | null>(null);
  const [starting, setStarting] = useState(false);
  /** The site's per-visitor limit refused the payment (a 429): friendly words, not an error. */
  const [limited, setLimited] = useState<string | null>(null);
  const paying = useRef(false);
  const key = `${account}:${runId}:${epoch}`;

  // Find the run to follow. "latest" means the account's newest run; any other id is that run.
  useEffect(() => {
    if (!account) return;
    let cancelled = false;
    const resolve = runId === "latest" ? api.latestRun(account) : Promise.resolve(api.runRef(runId));
    resolve.then(
      (run) => {
        if (cancelled) return;
        setTarget({ key, run });
        setError(null);
      },
      (e: Error) => !cancelled && setError(api.unreachable(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [account, runId, key]);

  const followed = target?.key === key ? target.run : undefined;
  const eventsUrl = followed?.events_url;
  useEffect(() => {
    dispatch({ kind: "reset" });
    lastSeen.current = 0;
    if (!eventsUrl) return;
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
        setError("Lost the connection to Clawback. Reconnecting…");
        if (es.readyState === EventSource.CLOSED && !cancelled) retry = window.setTimeout(connect, 2000);
      };
    };
    connect();
    dispatch({ kind: "playing", on: true });
    return () => {
      cancelled = true;
      window.clearTimeout(retry);
      stream?.close();
    };
  }, [eventsUrl, key]);

  const fail = useCallback((e: Error) => setError(`Clawback didn't accept that action (${e.message}).`), []);

  /** The owner's answer. Only the signed-in owner may send it; the API checks the owner's access code. */
  const answerQuestion = useCallback(
    (questionId: string, text: string) => {
      if (state.questions[questionId]?.answer || !text.trim()) return;
      asRole("owner", (code) => api.answerQuestion(questionId, text.trim(), code), fail);
    },
    [state.questions, fail],
  );

  /** The controller's yes or no. Only the signed-in controller may send it; the API checks the controller's access code. */
  const controllerDecides = useCallback(
    (approve: boolean, note: string | null = null) => {
      const approval = state.approval;
      if (approval?.status !== "pending") return;
      asRole("controller", (code) => api.decideApproval(approval.id, approve, note, code), fail);
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

  /** No run exists yet for this account: the page offers "<Distributor> pays". */
  const awaitingPayment = !!account && followed === null && !error;
  const runId_ = followed?.run_id ?? null;

  return { state, runId: runId_, answerQuestion, controllerDecides, startPayment, starting, limited, awaitingPayment, refresh, error };
}
