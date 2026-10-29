"use client";

// /app: the company across all its distributors (GET /overview), kept to what a glance can take in: the money in three
// numbers (being clawed back, recovered, fair), then the ONE thing that needs the admin next (the API ranks them:
// highest risk, then the oldest) with its single button, and two doors to the rest (Disputes, Payments). Every amount
// is the API's: "recovered" counts only what evidence shows came back.

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, ArrowRight, CircleAlert, MinusCircle } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { PageHeader } from "@/components/ui/kit";
import { Claw, landPulse } from "@/components/ui/Claw";
import { DecisionCard } from "@/components/play/PlayKit";
import { consequenceOf } from "@/components/console/Review";
import CheckPayments from "./CheckPayments";
import { ReceivedList, RunAgentsButton, useReceivedPayments } from "./ReceivedPayments";
import { withAccount } from "@/lib/accounts";
import { needsHref } from "@/lib/needs";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { NeedsYou } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const ACTION: Record<NeedsYou["kind"], string> = { question: "Answer", dispute_email: "Review and send", reply_email: "Answer them", approval: "Approve" };
const LEVEL = { high: "High", medium: "Medium", low: "Low" } as const;
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });


/** An amount that counts up when it first appears (whole dollars on the way, the exact figure at the end). `from` is
 * where it starts; `hold` keeps it there until the moment it should move (the claw's coin landing).
 * Reduced motion: the figure, at once. */
function Count({ value, from = 0, hold = false }: { value: number; from?: number; hold?: boolean }) {
  const [shown, setShown] = useState<number | null>(null);
  useEffect(() => {
    if (hold || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 700);
      const eased = 1 - (1 - k) ** 3;
      setShown(k < 1 ? Math.round(from + (value - from) * eased) : null);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, from, hold]);
  return <>{money(hold ? from : shown ?? value)}</>;
}

// What Recovered showed the last time this browser saw Home, so the claw drops a coin only when it has gone up.
const SEEN = "clawback:recovered-seen";
const noSub = () => () => {};
function readSeen(): string | null {
  try { return window.localStorage.getItem(SEEN); } catch { return null; }
}
function writeSeen(v: number) {
  try { window.localStorage.setItem(SEEN, String(v)); } catch { /* private window: the claw just plays again next time */ }
}

function Level({ level }: { level: NeedsYou["risk_level"] }) {
  if (level === "high") return <span className="dc-level is-high"><AlertTriangle aria-hidden="true" />High</span>;
  if (level === "medium") return <span className="dc-level is-medium"><CircleAlert aria-hidden="true" />Medium</span>;
  return <span className="dc-level is-low"><MinusCircle aria-hidden="true" />Low</span>;
}

export default function Dashboard() {
  const { account } = useRun();
  const still = useReducedMotion();
  const [tick, setTick] = useState(0);
  const [showAll, setShowAll] = useState(false);
  // Home looks again every 15 seconds, so an answered item leaves and a new reply arrives without a reload.
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 15_000);
    return () => window.clearInterval(id);
  }, []);
  const load = useCallback(() => api.fetchCompanyOverview(), []);
  const fetched = useFetched(load, String(tick));
  const o = fetched.data;
  const t = o?.totals;
  const seenRaw = useSyncExternalStore(noSub, readSeen, () => "server");
  const seen = seenRaw === "server" ? null : Number(seenRaw ?? 0) || 0;
  const [moneyEl, setMoneyEl] = useState<HTMLElement | null>(null);
  const [landed, setLanded] = useState(false);
  const rising = !!t && seen !== null && t.recovered > seen + 0.005;
  // When it went down (a demo reset), remember the lower figure so the next rise plays.
  useEffect(() => { if (t && seen !== null && t.recovered < seen - 0.005) writeSeen(t.recovered); }, [t, seen]);
  // A payment sent from a distributor's portal waits here too: "Run the agents" takes "Check for new payments"' place.
  const received = useReceivedPayments();
  const needs = o?.needs_you ?? [];
  const next = needs[0] ?? null;
  const rest = needs.slice(1);
  const openCount = o?.open_disputes.length ?? 0;
  const disputesNeedingYou = needs.filter((n) => n.kind === "dispute_email" || n.kind === "reply_email").length;
  // Answering in place: the question's choice or the memo's yes goes straight to the API, then the list moves on.
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; bad?: boolean } | null>(null);
  const { reload } = fetched;
  // The answered card leaves; keyboard focus goes to the note saying what was done, not back to the page top.
  const noteRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (!note) return;
    noteRef.current?.focus();
    if (note.bad) return;
    const t = window.setTimeout(() => setNote(null), 5000);
    return () => window.clearTimeout(t);
  }, [note]);
  async function act(n: NeedsYou, pick: number, remember = true) {
    const c = n.choices?.[pick];
    if (!c || !n.target_id) return;
    setBusy(true);
    setNote(null);
    try {
      if (n.kind === "question") {
        // Say what the API did, not what was asked: a rule answer that couldn't become a rule leaves the question open.
        const r = await api.answerQuestion(n.target_id, c.text, c.rule && remember);
        setNote(c.rule && !r.rule
          ? { text: `That answer couldn’t become a rule for ${n.distributor}’s charge, so it’s still open. Pick “Accept this one” or “Dispute this one”.`, bad: true }
          : { text: `Done: “${c.label}” for ${n.distributor}.${r.rule ? ` Saved as ${r.rule.label}.` : ""}` });
      } else {
        await api.decideApproval(n.target_id, true, null);
        setNote({ text: `Done: sent to QuickBooks for ${n.distributor}.` });
      }
      reload();
    } catch (e) {
      // Already answered or approved elsewhere (another tab, the weekly email), or replaced by a newer check: say so
      // and show the list as it is now. Anything else: a plain retry note, not the API's words.
      const gone = e instanceof api.ApiError && (e.status === 404 || e.status === 409);
      setNote(gone ? { text: "That one was already taken care of. Here’s what’s left." } : { text: "That didn’t go through. Try again in a moment.", bad: true });
      if (gone) reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main hm2">
        <PageHeader title="Home" line={o ? `${account?.brand.name ?? "Your company"} across ${o.distributors} distributor${o.distributors === 1 ? "" : "s"}` : undefined}
          actions={<><Link className="cx-btn is-ghost" href={withAccount("/upload", account?.id)}>Upload a payment slip</Link>{received.pending.length ? <RunAgentsButton received={received} /> : <CheckPayments account={account?.id} />}</>} />
        <ReceivedList received={received} />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        {/* 1. The money, in three numbers. */}
        <section className="cb-score hm2-money cw-host" aria-label="The money" ref={setMoneyEl}>
          {rising && t && seen !== null && (
            <Claw host={moneyEl} mode="drop" to=".hm-recovered" label={`+${money(t.recovered - seen)}`} tone="good" delay={0.5} maxWait={1.5}
              onLand={() => { setLanded(true); landPulse(document.querySelector(".hm-recovered")); }}
              onDone={() => { writeSeen(t.recovered); setLanded(false); }} />
          )}
          <div className="cb-score-main">
            <span className="cb-score-label">Getting back</span>
            <strong className="cb-score-big">{t ? <Count value={t.disputed_awaiting_reply} /> : "–"}</strong>
            {t && <span className="cb-score-line">in {openCount} open dispute{openCount === 1 ? "" : "s"}, of {money(t.taken)} taken from payments</span>}
          </div>
          <div className="cb-score-cells">
            <div className="cb-score-cell is-good"><span>Back in your account</span><b className="hm-recovered">{t ? (rising && seen !== null ? <Count value={t.recovered} from={seen} hold={!landed} /> : <Count value={t.recovered} />) : "–"}</b></div>
            <div className="cb-score-cell is-fair"><span>Fair charges</span><b>{t ? <Count value={t.fair} /> : "–"}</b></div>
          </div>
        </section>

        {/* 2. The one thing that needs you next. */}
        <section className="hm2-next-wrap" aria-labelledby="hm2-next">
          <h2 id="hm2-next" className="hm2-h">Next for you</h2>
          {note && <p ref={noteRef} tabIndex={-1} className={`hm2-note ${note.bad ? "is-bad" : ""}`} role={note.bad ? "alert" : "status"}>{note.text}</p>}
          {!o && !fetched.error && <div className="hm-skel" aria-hidden="true"><i /></div>}
          {o && !next && (
            <div className="cb-card hm2-calm"><strong>You’re all caught up.</strong><span>When a payment comes in short or a distributor replies, it shows up here.</span></div>
          )}
          <AnimatePresence initial={false} mode="popLayout">
            {next && (
              <motion.article key={`${next.kind}-${next.account_id}-${next.link.run_id ?? ""}-${next.link.dispute_id ?? ""}-${next.target_id ?? ""}`}
                className={`hm2-next ${next.kind === "question" && next.choices?.length ? "is-decide" : "cb-card"}`}
                initial={still ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={still ? { opacity: 0 } : { opacity: 0, x: 40 }} transition={{ duration: 0.25 }}>
                <div className="hm2-next-top">
                  {next.kind !== "approval" && !(next.kind === "question" && next.choices?.length) && <Level level={next.risk_level} />}
                  <span className="hm2-next-who">{next.distributor}{next.since ? ` · since ${when(next.since)}` : ""}</span>
                  {needs.length > 1 && <span className="hm2-next-count">{needs.length} waiting</span>}
                </div>
                {next.kind === "question" && next.choices?.length ? (
                  <>
                    <DecisionCard key={next.target_id ?? next.title} question={next.title} why={next.detail ?? undefined} level={LEVEL[next.risk_level]}
                      amount={next.amount ?? undefined} busy={busy} rememberLabel={null} goLabel="Decide"
                      choices={next.choices.map((c, i) => ({ value: String(i), label: c.label, consequence: consequenceOf(c.rule ? "rule" : /dispute/i.test(c.text) ? "dispute" : "accept", next.amount) }))}
                      onDecide={(v) => void act(next, Number(v))} />
                    <Link className="hm2-next-more" href={needsHref(next)}>See the contract and the proof<ArrowRight aria-hidden="true" /></Link>
                  </>
                ) : (
                  <>
                    <h3>{next.title}</h3>
                    {next.detail && <p className="hm2-next-detail">{next.detail}</p>}
                    <div className="hm2-next-go">
                      {next.amount != null && <span className="hm2-next-amt">{money(next.amount)}</span>}
                      {next.kind === "approval" && next.choices?.length ? (
                        <>
                          <Link className="cx-btn is-ghost" href={needsHref(next)}>See what’s in it</Link>
                          <button type="button" className="cx-btn is-blue" disabled={busy} onClick={() => void act(next, 0)}>{busy ? "Sending…" : next.choices[0].label}</button>
                        </>
                      ) : (
                        <Link className="cx-btn is-blue" href={needsHref(next)}>{ACTION[next.kind] ?? "Open"}<ArrowRight aria-hidden="true" /></Link>
                      )}
                    </div>
                  </>
                )}
              </motion.article>
            )}
          </AnimatePresence>
          {rest.length > 0 && (
            <div className="hm2-more">
              <button type="button" className="cx-btn is-ghost is-small" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Hide the rest" : `${rest.length} more after this`}
              </button>
              {showAll && (
                <ol className="hm2-rest">
                  {rest.map((n, i) => (
                    <li key={`${n.kind}-${n.account_id}-${n.link.run_id ?? ""}-${n.link.dispute_id ?? i}`}>
                      <Link href={needsHref(n)}><Level level={n.risk_level} /><span>{n.title}</span><ArrowRight aria-hidden="true" /></Link>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </section>

        {/* 3. Two doors to the rest. */}
        <nav className="hm2-doors" aria-label="More">
          <Link className="cb-card hm2-door" href={withAccount("/disputes", account?.id)}>
            <strong>Disputes</strong><span>{openCount} open{disputesNeedingYou ? ` · ${disputesNeedingYou} need${disputesNeedingYou === 1 ? "s" : ""} you` : ", waiting for replies"}</span><ArrowRight aria-hidden="true" />
          </Link>
          <Link className="cb-card hm2-door" href={withAccount("/payments", account?.id)}>
            <strong>All payments</strong><span>Every payment from every distributor</span><ArrowRight aria-hidden="true" />
          </Link>
        </nav>
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
