// The run as seven stages on a rail, built only from what the run has streamed so far. Reading the deal and checking
// the charges have their own stage events (with counts); a run saved before those existed falls back to the charge,
// finding and decision events. The later stages come from the events that already mark them exactly: dispute,
// question, approval and ledger_post. Wording only: every amount is one the API sent.

import { money } from "@/lib/format";
import type { FeedLine, RunState } from "@/lib/useRunEvents";
import type { WorkspaceView } from "@/lib/workspace";

export type StageKey = "payment" | "read" | "check" | "file" | "owner" | "approval" | "books";
export type StageState = "todo" | "active" | "waiting" | "done" | "skipped" | "failed";
export type Who = "AI" | "CODE" | "PERSON";

export type Stage = {
  key: StageKey;
  name: string;
  /** Who does the work: "Claude + Gemini", "Negotiator", "Dana (admin)". */
  agent: string;
  who: Who;
  state: StageState;
  /** One plain line: what's happening now, or what came out. */
  line: string;
  done: number | null;
  total: number | null;
};

/** owner: the admin, the brand's owner: the one person who answers the question and approves the memo. */
export type Cast = { distributor: string; owner: string };

const last = (feed: FeedLine[], actors: string[]) => {
  for (let i = feed.length - 1; i >= 0; i--) if (actors.includes(feed[i].actor)) return feed[i];
  return null;
};

/** `arriving`: a payment was just started and its run hasn't streamed yet (the Nessie deposit takes a few seconds). */
export function buildStages(state: RunState, view: WorkspaceView, cast: Cast, arriving = false): Stage[] {
  const run = state.run;
  const failed = run?.status === "failed";
  const r = view.remittance;
  const { read, check } = state.stages;
  const total = check?.total ?? r?.charge_count ?? view.charges.length;
  const decided = Object.keys(state.decisions).length;
  const anyCharge = state.order.length > 0;
  const checked = check ? check.status === "done" : total > 0 && decided >= total;
  const valued = !!state.totals?.value;

  const payment: Stage = {
    key: "payment", name: "Payment in", agent: "Bank deposit", who: "CODE",
    state: run ? "done" : arriving ? "active" : "todo",
    line: r
      ? `${r.counterparty} paid ${money(r.received)} of ${money(r.expected)} · took ${money(r.taken)} in ${r.charge_count} charges`
      : run ? `${total} charges taken` : arriving ? `Waiting for ${cast.distributor}’s deposit to land` : "Waiting for the payment",
    done: null, total: null,
  };

  const readDone = read ? read.status === "done" : anyCharge;
  const readStage: Stage = {
    key: "read", name: "Read the deal", agent: "Claude + Gemini", who: "AI",
    state: readDone ? "done" : run ? (failed ? "failed" : "active") : "todo",
    line: read?.label ?? (readDone ? "Both readers agreed on the terms, every quote found word for word" : run ? "Two readers on the signed deal and the emails" : "Two AI readers must agree on every term"),
    done: read ? read.done : null, total: read ? read.total : null,
  };

  const current = check?.charge_id ? state.charges[check.charge_id] : null;
  const live = last(state.feed, ["investigator", "negotiator"]);
  const checkStage: Stage = {
    key: "check", name: "Check each charge", agent: "Calculator · Investigator · Negotiator · Rules", who: "AI",
    state: checked ? "done" : readDone ? (failed ? "failed" : "active") : "todo",
    line: checked
      ? `${total} of ${total} charges decided`
      : current ? `${current.id}: ${live?.charge_id === current.id ? live.text : current.description}` : readDone ? "Starting on the first charge" : "Math in tested code, words by AI, decisions by your policy",
    done: check ? (check.status === "done" ? check.total : check.done) : decided, total,
  };

  const d = state.dispute;
  const disputedNow = (view.totals?.disputed ?? 0) > 0;
  const lastReply = [...state.portal].reverse().find((m) => m.from_party !== "clawback") ?? null;
  const file: Stage = {
    key: "file", name: "File the dispute", agent: "Negotiator", who: "AI",
    state: d ? (d.status === "draft" ? "waiting" : "done") : checked && valued && !disputedNow ? "skipped" : checked && disputedNow ? "active" : "todo",
    line: d
      ? d.status === "draft"
        ? `${d.id} · ${money(d.total)} is over the limit ${cast.owner} set: held for ${cast.owner}`
        : lastReply
          ? `${cast.distributor} replied on ${d.id}: “${lastReply.text.slice(0, 90)}${lastReply.text.length > 90 ? "…" : ""}”`
          : `${d.id} filed · ${d.lines.length} line${d.lines.length === 1 ? "" : "s"} · ${money(d.total)}, each comeback answered`
      : checked && valued && !disputedNow
        ? (view.totals?.waiting ?? 0) > 0 ? "Nothing to dispute so far" : "Nothing to dispute: every charge is fair"
        : "Clause, data and math on every line",
    done: null, total: null,
  };

  const q = view.question;
  const asked = Object.values(state.questions).filter((x) => !x.closed_at);
  const owner: Stage = {
    key: "owner", name: "Your answer", agent: `${cast.owner} (admin)`, who: "PERSON",
    state: view.stage === "owner" ? "waiting" : view.rule || asked.some((x) => x.answer) ? "done" : checked && valued && asked.length === 0 ? "skipped" : "todo",
    line: view.stage === "owner" && q
      ? `One question about ${q.charge_id}: the deal leaves it to judgment`
      : view.rule
        ? `${view.rule.label} saved: ${view.rule.summary}`
        : asked.some((x) => x.answer)
          ? `${cast.owner} answered`
          : checked && valued && asked.length === 0 ? "No questions needed" : "Asked only when the deal is unclear, once",
    done: null, total: null,
  };

  const a = view.approval;
  const finished = run?.status === "finished";
  const approval: Stage = {
    key: "approval", name: "Your approval", agent: `${cast.owner} (admin)`, who: "PERSON",
    state: !a
      ? finished && (view.totals?.accepted ?? 0) === 0 ? "skipped" : "todo"
      : a.status === "pending" ? "waiting" : a.status === "refused" ? "failed" : "done",
    line: !a
      ? finished && (view.totals?.accepted ?? 0) === 0 ? "Nothing fair to post" : "Approves money before anything posts"
      : a.status === "pending"
        ? `Approve credit memo of ${money(a.amount)} (${a.lines.length} line${a.lines.length === 1 ? "" : "s"})?`
        : a.status === "refused"
          ? `Held by ${cast.owner}${a.note ? `: “${a.note}”` : ""}`
          : a.posted_by_auto_post
            ? `Posted by ${cast.owner}’s auto-post rule (up to ${money(a.posted_by_auto_post.limit)})`
            : a.note?.startsWith("Within policy") ? "Within policy: no approval needed" : `${cast.owner} approved ${money(a.amount)}`,
    done: null, total: null,
  };

  const books: Stage = {
    key: "books", name: "QuickBooks", agent: "Bookkeeper", who: "CODE",
    state: view.stage === "posted" ? "done" : view.postingProblem ? "failed" : view.stage === "refused" || approval.state === "skipped" ? "skipped" : a?.status === "approved" ? "active" : "todo",
    line: view.stage === "refused" ? "Nothing posted" : approval.state === "skipped" ? "Nothing to post" : view.postingProblem ?? view.postingLabel,
    done: null, total: null,
  };

  return [payment, readStage, checkStage, file, owner, approval, books];
}

/** The stage the eye should go to: the first one waiting on a person, else the one working, else the last done. */
export function focusStage(stages: Stage[]): Stage | null {
  return stages.find((s) => s.state === "waiting") ?? stages.find((s) => s.state === "active" || s.state === "failed") ?? null;
}
