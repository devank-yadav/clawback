"use client";

// The landing page: one input, then the agents. Three phases on one page, chosen from the run the API streams:
//  start: nothing running here yet (the last payment, if any, opens from a card);
//  run:   a run is working or waiting on a person (or this tab just started one);
//  done:  this tab's run finished and nobody is waiting.
// A run started anywhere else (the Nessie deposit, another device) switches the page to it by itself.

import { useEffect, useState, useSyncExternalStore } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { ChargeDrawer } from "@/components/console/Review";
import { useRun } from "@/components/console/RunProvider";
import { DonePanel } from "./DonePanel";
import { ChargeMatrix } from "./ChargeMatrix";
import { Elapsed, Meter, ACTOR } from "./parts";
import { ReaderCard, Spotlight } from "./Spotlight";
import { StageRail } from "./StageRail";
import { StageHero } from "./StageHero";
import { AgentStrip } from "./AgentStrip";
import { StartPanel } from "./StartPanel";
import { buildStages, focusStage } from "./stages";
import { money } from "@/lib/format";

const noop = () => () => {};
/** ?run=latest opens the account's last run instead of the start screen. */
function useOpenLatest() {
  return useSyncExternalStore(noop, () => !!new URLSearchParams(window.location.search).get("run"), () => false);
}

// The run this tab watched while it worked, kept for the session: once it finishes the page shows its result, even
// after a reload or a remount. Browser storage is a convenience only; without it the page falls back to the start.
const followedKey = (account: string) => `clawback:flow:${account}`;
function readFollowed(account: string | undefined): string | null {
  if (!account) return null;
  try {
    return window.sessionStorage.getItem(followedKey(account));
  } catch {
    return null;
  }
}
function writeFollowed(account: string | undefined, runId: string | null) {
  if (!account) return;
  try {
    if (runId) window.sessionStorage.setItem(followedKey(account), runId);
    else window.sessionStorage.removeItem(followedKey(account));
  } catch {
    /* private window: the page still works, it just forgets */
  }
}

export default function Flow() {
  const { account } = useRun();
  // A new account starts fresh: nothing "started in this tab" carries over.
  return <FlowFor key={account?.id ?? "none"} />;
}

function FlowFor() {
  const run = useRun();
  const { state, view, account, cast, runId, starting } = run;
  const openLatest = useOpenLatest();
  // The run this tab was following when it started one; any newer run is "ours" from then on.
  const [startedFrom, setStartedFrom] = useState<string | null | undefined>(undefined);
  const [opened, setOpened] = useState(false);
  // "Check a new payment" pressed: the start screen shows even while an older run waits on you (it stays one click
  // away). A new payment then replaces that run, and its open question closes on the server.
  const [fresh, setFresh] = useState(false);
  const [drawer, setDrawer] = useState<string | null>(null);
  const [, setCleared] = useState(0); // a re-render after forgetting the watched run

  const mine = startedFrom !== undefined && runId !== startedFrom;
  const status = state.run?.status;
  const waitingOnPerson = view.approval?.status === "pending" || view.stage === "owner";
  // The agents are still working until every charge has a decision. After that the result shows, even while a decision
  // of yours is waiting: it appears on the result as your next step. A stopped run shows its result too.
  const working = status === "started" && !view.reviewed;
  const live = working || waitingOnPerson;
  const followed = useSyncExternalStore(noop, () => readFollowed(account?.id), () => null);
  const watched = !!runId && followed === runId;
  const phase: "start" | "run" | "done" =
    starting || (mine && !state.run) ? "run"
      : fresh && !mine ? "start"
      : !state.run ? "start"
        : working ? "run"
          : mine || opened || openLatest || watched || waitingOnPerson ? "done"
            : "start";

  useEffect(() => {
    if (runId && (mine || (live && !fresh))) writeFollowed(account?.id, runId);
  }, [runId, live, mine, fresh, account?.id]);

  /** Back to the start screen: forget the watched run for this tab. */
  const restart = () => {
    writeFollowed(account?.id, null);
    setStartedFrom(undefined);
    setOpened(false);
    setFresh(true);
    setCleared((n) => n + 1);
  };

  const stages = buildStages(state, view, { distributor: cast.distributor, owner: cast.owner }, starting || (mine && !state.run));
  const focus = focusStage(stages);
  const r = view.remittance;
  const t = view.totals;
  const charge = drawer ? view.charges.find((c) => c.id === drawer) ?? null : null;

  return (
    <div className="fl">
      <TopBar account={account} active="agents" />

      {phase === "start" && (
        <main className="fl-main" style={{ paddingTop: 0, paddingBottom: 0 }}>
          <StartPanel onStart={() => setStartedFrom(runId ?? null)} onOpenLast={() => { setOpened(true); setFresh(false); }} />
        </main>
      )}

      {phase === "run" && (
        <main className="fl-main">
          <div className="fl-pay">
            <p className="fl-pay-line">
              {r
                ? <>{r.counterparty} paid {money(r.received)} of {money(r.expected)} and <b>kept {money(r.taken)}</b> in {r.charge_count} charges</>
                : state.run ? `${cast.distributor}’s charges` : `Waiting for ${cast.distributor}’s payment…`}
            </p>
            <Elapsed from={r?.received_at ?? state.feed[0]?.at ?? null} running={status === "started"} decidedIn={view.value?.seconds_to_decided ?? null} />
          </div>
          <div className="bw-stage">
            <div className="bw-frame">
              <AgentStrip state={state} view={view} owner={cast.owner} distributor={cast.distributor} />
              <StageHero stage={focus} stages={stages} feed={state.feed} done={status === "finished"} />
              <Spotlight focus={focus} />
              <StageRail stages={stages} compact />
              <div className="fl-meters">
                <Meter label="Disputing, with proof" value={t?.disputed ?? 0} tone="dispute" />
                <Meter label="Fair, accepted" value={t?.accepted ?? 0} tone="fair" />
                <Meter label={`Waiting on ${cast.owner}`} value={(t?.waiting ?? 0) + (view.stage === "approval" ? view.approval?.amount ?? 0 : 0)} tone="wait" />
              </div>
            </div>
          </div>
          {state.order.length > 0 || state.stages.check ? (
            <div className="fl-work">
              <ChargeMatrix state={state} view={view} owner={cast.owner} onOpen={setDrawer} />
              <Feed />
            </div>
          ) : state.stages.docs.length > 0 && focus?.key !== "read" ? <ReaderCard live={false} /> : null}
          {status === "failed" && <div className="fl-problem" role="alert">The run stopped. {state.feed.filter((l) => l.level === "error").at(-1)?.text}</div>}
        </main>
      )}

      {phase === "done" && (
        <main className="fl-main">
          <AgentStrip state={state} view={view} owner={cast.owner} distributor={cast.distributor} />
          <DonePanel onOpen={setDrawer} onNew={restart} rail={<StageRail stages={stages} compact />} next={focus && focus.state === "waiting" ? <Spotlight focus={focus} /> : null} failed={status === "failed"} />
        </main>
      )}

      {charge && (
        <div className="fl-overlay" onClick={() => setDrawer(null)} role="presentation">
          <div onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${charge.title}: how it was decided`}>
            <ChargeDrawer charge={charge} onClose={() => setDrawer(null)} source="live" runId={state.run?.run_id} key={charge.id} />
          </div>
        </div>
      )}
      <SessionDialogs account={account} />
    </div>
  );
}

/** Each agent's own lines as they arrive. */
function Feed() {
  const { state } = useRun();
  const [all, setAll] = useState(false);
  const lines = all ? state.feed : state.feed.slice(-10);
  return (
    <aside className="fl-feed" aria-label="Activity">
      <div className="cx-head" style={{ alignItems: "center" }}>
        <strong style={{ fontWeight: 500, fontSize: 13 }}>Activity</strong>
        {state.feed.length > 10 && <button className="cx-btn is-ghost" style={{ minHeight: 28, padding: "0 10px", fontSize: 11 }} onClick={() => setAll((v) => !v)}>{all ? "Recent" : `All ${state.feed.length}`}</button>}
      </div>
      <ol aria-live="polite">
        {lines.map((l) => (
          <li key={l.id} className={l.level}>
            <b>{ACTOR[l.actor] ?? l.actor}</b>
            {l.text}
          </li>
        ))}
      </ol>
    </aside>
  );
}
