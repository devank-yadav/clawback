"use client";

// The landing page: one input, then the agents. Three phases on one page, chosen from the run the API streams:
//  start: nothing running here yet (the last payment, if any, opens from a card);
//  run:   a run is working or waiting on a person (or this tab just started one);
//  done:  this tab's run finished and nobody is waiting.
// A run started anywhere else (the Nessie deposit, another device) switches the page to it by itself.

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { SlideOver } from "@/components/ui/SlideOver";
import { useRouter, useSearchParams } from "next/navigation";
import { withAccount } from "@/lib/accounts";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { ChargeDrawer } from "@/components/console/Review";
import { useRun } from "@/components/console/RunProvider";
import { DonePanel } from "./DonePanel";
import { ChargeMatrix } from "./ChargeMatrix";
import { Elapsed, Meter, ACTOR } from "./parts";
import { NeedsYou, ReaderCard } from "./Spotlight";
import { StageRail } from "./StageRail";
import { StageHero } from "./StageHero";
import { AgentTalk } from "./AgentTalk";
import { StageAgents } from "./AgentStrip";
import { StartPanel } from "./StartPanel";
import { buildStages, focusStage, type Stage, type StageKey } from "./stages";
import { money } from "@/lib/format";

const noop = () => () => {};
// The decisions that wait on the admin, in the order to take them: the question first (its answer can change the
// memo), then the credit memo's approval, then the dispute to send. All of them show at once, never one at a time.
const NEEDS: StageKey[] = ["owner", "approval", "file"];
const stageAgents = (key: StageKey) => <StageAgents stage={key} />;
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
  const home = useSearchParams().get("home") === "1";
  // A new account starts fresh: nothing "started in this tab" carries over. So does each click on the logo (home) or
  // on Agents: the logo always opens the start screen, Agents the latest run.
  return <FlowFor key={`${account?.id ?? "none"}:${home ? "home" : "agents"}`} />;
}

function FlowFor() {
  const run = useRun();
  const { state, view, account, cast, runId, starting, gone, replay, replaying, skipReplay, error } = run;
  const openLatest = useOpenLatest();
  const wantedRun = useSearchParams().get("run");
  // A run opened by its link while its events load: say so instead of flashing the start screen.
  const opening = !!wantedRun && wantedRun !== "latest" && !state.run && !gone.includes(wantedRun) && !error && !starting;
  // The logo opens ?home=1: the start screen, whatever this tab last watched. "Agents" opens the latest run.
  const home = useSearchParams().get("home") === "1";
  const router = useRouter();
  // The run this tab was following when it started one; any newer run is "ours" from then on, unless the API has
  // lost a run since (a deploy): then no run is ours and the page falls back to the latest run or the start.
  const [startedFrom, setStartedFrom] = useState<{ run: string | null; lost: number } | undefined>(undefined);
  const [opened, setOpened] = useState(false);
  // "Check a new payment" pressed: the start screen shows even while an older run waits on you (it stays one click
  // away). A new payment then replaces that run, and its open question closes on the server.
  const [fresh, setFresh] = useState(false);
  const [drawer, setDrawer] = useState<string | null>(null);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const [, setCleared] = useState(0); // a re-render after forgetting the watched run

  const mine = startedFrom !== undefined && runId !== startedFrom.run && gone.length === startedFrom.lost;
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
      : (fresh || (home && !opened)) && !mine ? "start"
      : !state.run ? "start"
        : working ? "run"
          : mine || opened || openLatest || watched || waitingOnPerson ? "done"
            : "start";

  useEffect(() => {
    if (runId && (mine || (live && !fresh))) writeFollowed(account?.id, runId);
  }, [runId, live, mine, fresh, account?.id]);
  // A watched run the API no longer has (404) is forgotten, so a reload doesn't ask for it again.
  useEffect(() => {
    if (followed && gone.includes(followed)) writeFollowed(account?.id, null);
  }, [followed, gone, account?.id]);

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
  const pending = NEEDS.map((k) => stages.find((s) => s.key === k && s.state === "waiting")).filter((s): s is Stage => !!s);
  const r = view.remittance;
  const t = view.totals;
  const charge = drawer ? view.charges.find((c) => c.id === drawer) ?? null : null;

  return (
    <div className="fl">
      <TopBar account={account} active={phase === "start" && home ? undefined : "agents"} />

      {phase === "start" && opening && (
        <main className="fl-main">
          <p className="fl-opening" role="status"><span className="cx-pill is-live">Opening the run…</span></p>
        </main>
      )}

      {phase === "start" && !opening && (
        <main className="fl-main" style={{ paddingTop: 0, paddingBottom: 0 }}>
          <StartPanel onStart={() => (home ? router.replace(withAccount("/", account?.id)) : setStartedFrom({ run: runId ?? null, lost: gone.length }))} onOpenLast={() => { setOpened(true); setFresh(false); }} />
        </main>
      )}

      {phase === "run" && (
        <main className="fl-main fl-run">
          <div className="fl-pay">
            <p className="fl-pay-line">
              {r
                ? <>{r.counterparty} paid {money(r.received)} of {money(r.expected)} and <b>kept {money(r.taken)}</b> in {r.charge_count} charges</>
                : state.run ? `${cast.distributor}’s charges` : `Waiting for ${cast.distributor}’s payment…`}
            </p>
            {replaying ? (
              <span className="fl-replay" role="status"><span className="fl-replay-tag">Replaying the run</span><button className="cx-btn is-ghost" onClick={skipReplay}>Skip to the result</button></span>
            ) : (
              <Elapsed from={r?.received_at ?? state.feed[0]?.at ?? null} running={status === "started"} decidedIn={view.value?.seconds_to_decided ?? null} />
            )}
          </div>
          {/* Top to bottom: the seven steps (each opens what its agents did), the totals, then the charges with what's
              happening now beside them, all above the fold; the full activity below. */}
          <div className="bw-stage">
            <div className="bw-frame">
              <StageRail stages={stages} compact details={stageAgents} />
              <div className="fl-meters">
                <Meter label="Disputed, with proof" value={t?.disputed ?? 0} tone="dispute" />
                <Meter label="Fair, accepted" value={t?.accepted ?? 0} tone="fair" />
                <Meter label="Waits on you" value={t?.waiting ?? 0} tone="wait" />
              </div>
              <div className="fl-now">
                <div className="fl-now-main">
                  <NeedsYou stages={pending} />
                  {(state.order.length > 0 || state.stages.check || (r?.charge_count ?? 0) > 0) && <ChargeMatrix state={state} view={view} owner={cast.owner} onOpen={setDrawer} />}
                </div>
                <div className="fl-now-side">
                  <StageHero stage={focus} stages={stages} feed={state.feed} done={status === "finished"} compact />
                  {focus?.key === "read" ? <ReaderCard live={focus.state === "active"} /> : <AgentTalk />}
                </div>
              </div>
            </div>
          </div>
          {status === "failed" && <div className="fl-problem" role="alert">The run stopped. {state.feed.filter((l) => l.level === "error").at(-1)?.text}</div>}
          <Feed />
        </main>
      )}

      {phase === "done" && (
        <main className="fl-main">
          <DonePanel onOpen={setDrawer} onNew={restart} onReplay={() => { setOpened(true); window.scrollTo({ top: 0 }); void replay(); }}
            rail={<StageRail stages={stages} compact details={stageAgents} />} next={pending.length ? <NeedsYou stages={pending} /> : null} disputeInNext={pending.some((s) => s.key === "file")} failed={status === "failed"} />
        </main>
      )}

      <SlideOver open={!!charge} onClose={closeDrawer} title={charge ? `${charge.id} · ${charge.title}` : ""} wide>
        {charge && <ChargeDrawer charge={charge} onClose={closeDrawer} source="live" runId={state.run?.run_id} key={charge.id} />}
      </SlideOver>
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
      <ol>
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
