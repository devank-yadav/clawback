"use client";

// The landing page: one input, then the agents. Three phases on one page, chosen from the run the API streams:
//  start: nothing running here yet (the last payment, if any, opens from a card);
//  run:   a run is working or waiting on a person (or this tab just started one);
//  done:  this tab's run finished and nobody is waiting.
// A run started anywhere else (the Nessie deposit, another device) switches the page to it by itself.

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { ArrowLeft } from "lucide-react";
import { SlideOver } from "@/components/ui/SlideOver";
import { useRouter, useSearchParams } from "next/navigation";
import { withAccount } from "@/lib/accounts";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { ChargeDrawer } from "@/components/console/Review";
import { useRun } from "@/components/console/RunProvider";
import { Elapsed } from "./parts";
import { StartPanel } from "./StartPanel";
import { PlayRun } from "@/components/play/PlayRun";
import { buildStages, type Stage, type StageKey } from "./stages";

const noop = () => () => {};
// The decisions that wait on the admin, in the order to take them: the question first (its answer can change the
// memo), then the credit memo's approval, then the dispute to send. The play screen shows them one at a time.
const NEEDS: StageKey[] = ["owner", "approval", "file"];
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
  const pending = NEEDS.map((k) => stages.find((s) => s.key === k && s.state === "waiting")).filter((s): s is Stage => !!s);
  const r = view.remittance;
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

      {(phase === "run" || phase === "done") && (
        <main className="fl-main fl-play">
          <PlayRun pending={pending} done={phase === "done"} onOpen={setDrawer}
            head={
              <span className="fl-pay-actions">
                {replaying ? (
                  <span className="fl-replay" role="status"><span className="fl-replay-tag">Replaying the run</span><button className="cx-btn is-ghost is-small" onClick={skipReplay}>Skip to the result</button></span>
                ) : phase === "run" ? (
                  <Elapsed from={r?.received_at ?? state.feed[0]?.at ?? null} running={status === "started"} decidedIn={view.value?.seconds_to_decided ?? null} />
                ) : pending.length === 0 ? (
                  <button className="cx-btn is-ghost is-small" onClick={() => { setOpened(true); window.scrollTo({ top: 0 }); void replay(); }}>Replay</button>
                ) : null}
                {/* Back to the start screen; the agents keep going on the server, and the run stays one click away. */}
                <button className="cx-btn is-ghost is-small fl-back" onClick={restart}><ArrowLeft aria-hidden="true" />{phase === "done" ? "Back to the start" : "Back"}</button>
              </span>
            } />
          {status === "failed" && <div className="fl-problem" role="alert">The run stopped. {state.feed.filter((l) => l.level === "error").at(-1)?.text}</div>}
        </main>
      )}

      <SlideOver open={!!charge} onClose={closeDrawer} title={charge ? `${charge.id} · ${charge.title}` : ""} wide>
        {charge && <ChargeDrawer charge={charge} onClose={closeDrawer} source="live" runId={state.run?.run_id} key={charge.id} />}
      </SlideOver>
      <SessionDialogs account={account} />
    </div>
  );
}
