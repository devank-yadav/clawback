"use client";

// /app: the company across all its distributors (GET /overview). First what needs the admin, one queue already ranked
// by the API (highest risk, then the oldest), each row a link straight to its action; then the money at a glance; the
// open disputes with the days left to file; and the latest activity. The distributor list lives on Distributors.
// Every amount is the API's: "recovered" counts only what evidence shows came back, and each piece links to it.

import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, ArrowRight, CircleAlert, Clock, MinusCircle } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar, { DistributorMark } from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { PageHeader } from "@/components/ui/kit";
import { Claw, landPulse } from "@/components/ui/Claw";
import CheckPayments from "./CheckPayments";
import { ReceivedList, RunAgentsButton, useReceivedPayments } from "./ReceivedPayments";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money } from "@/lib/format";
import type { NeedsYou, OverviewLink } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const STATUS: Record<string, string> = { ready_to_send: "Ready to send", draft: "Ready to send", filed: "Filed, awaiting reply", answered: "Replied" };
const ACTION: Record<NeedsYou["kind"], string> = { question: "Answer", dispute_email: "Review and send", reply_email: "Send the reply", approval: "Approve" };
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Where a link from the overview lands: a dispute's thread, or the run (its question or approval is on its result). */
function hrefOf(account: string, link: OverviewLink): string {
  if (link.page === "dispute" && link.dispute_id) return withAccount("/disputes", account, { id: link.dispute_id, ...(link.run_id ? { run: link.run_id } : {}) });
  return withAccount("/", account, link.run_id ? { run: link.run_id } : undefined);
}

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

/** Days left in the dispute window: amber at 14 or fewer, red at 7 or fewer, always with the number and an icon. */
function DaysLeft({ days }: { days: number | null }) {
  if (days == null) return <span className="hm-none">Not known</span>;
  const tone = days <= 7 ? "is-red" : days <= 14 ? "is-amber" : "";
  return <span className={`hm-days ${tone}`}>{tone ? <AlertTriangle aria-hidden="true" /> : <Clock aria-hidden="true" />}{days} day{days === 1 ? "" : "s"}</span>;
}

export default function Dashboard() {
  const { account } = useRun();
  const still = useReducedMotion();
  const [tick, setTick] = useState(0);
  // Home looks again every 15 seconds, so an answered item leaves and a new reply arrives without a reload.
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 15_000);
    return () => window.clearInterval(id);
  }, []);
  const load = useCallback(() => api.fetchCompanyOverview(), []);
  const fetched = useFetched(load, String(tick));
  const o = fetched.data;
  const t = o?.totals;
  const evidence = t?.evidence ?? [];
  const dash = <span className="hm-none">–</span>;
  const seenRaw = useSyncExternalStore(noSub, readSeen, () => "server");
  const seen = seenRaw === "server" ? null : Number(seenRaw ?? 0) || 0;
  const [moneyEl, setMoneyEl] = useState<HTMLElement | null>(null);
  const [landed, setLanded] = useState(false);
  const rising = !!t && seen !== null && t.recovered > seen + 0.005;
  // When it went down (a demo reset), remember the lower figure so the next rise plays.
  useEffect(() => { if (t && seen !== null && t.recovered < seen - 0.005) writeSeen(t.recovered); }, [t, seen]);
  // A payment sent from a distributor's portal waits here too: "Run the agents" takes "Check for new payments"' place.
  const received = useReceivedPayments();

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main bp ap hm">
        <PageHeader title="Home" line={o ? `${account?.brand.name ?? "Your company"} across ${o.distributors} distributor${o.distributors === 1 ? "" : "s"}` : undefined}
          actions={<><Link className="cx-btn is-ghost" href={withAccount("/upload", account?.id)}>Add a remittance</Link>{received.pending.length ? <RunAgentsButton received={received} /> : <CheckPayments account={account?.id} />}</>} />
        <ReceivedList received={received} />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}

        <section className="hm-block" aria-labelledby="hm-needs">
          <h2 id="hm-needs">Needs you</h2>
          {!o && !fetched.error && <div className="hm-skel" aria-hidden="true"><i /><i /></div>}
          {o && o.needs_you.length === 0 && <p className="hm-empty">Nothing needs you. When a contract leaves a charge to your judgment, the question lands here.</p>}
          {o && o.needs_you.length > 0 && (
            <ol className="hm-queue">
              {/* An answered item leaves the queue with a short slide, so it's clear it's done. */}
              <AnimatePresence initial={false}>
                {o.needs_you.map((n, i) => (
                  <motion.li key={`${n.kind}-${n.account_id}-${n.link.run_id ?? ""}-${n.link.dispute_id ?? i}`}
                    initial={still ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={still ? { opacity: 0 } : { opacity: 0, x: 40 }} transition={{ duration: 0.25 }}>
                    <Link href={hrefOf(n.account_id, n.link)} className="hm-item">
                      <Level level={n.risk_level} />
                      <span className="hm-what"><strong>{n.title}</strong><small>{n.distributor}{n.since ? ` · waiting since ${when(n.since)}` : ""}</small></span>
                      {n.amount != null && <span className="hm-amt">{money(n.amount)}</span>}
                      <span className="hm-go">{ACTION[n.kind] ?? "Open"}<ArrowRight aria-hidden="true" /></span>
                    </Link>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ol>
          )}
        </section>

        <section className="hm-block cw-host" aria-labelledby="hm-money" ref={setMoneyEl}>
          {rising && t && seen !== null && (
            <Claw host={moneyEl} mode="drop" to=".hm-recovered" label={`+${money(t.recovered - seen)}`} tone="good" delay={0.5} maxWait={1.5}
              onLand={() => { setLanded(true); landPulse(document.querySelector(".hm-recovered")); }}
              onDone={() => { writeSeen(t.recovered); setLanded(false); }} />
          )}
          <h2 id="hm-money">Money at a glance</h2>
          <dl className="hm-money">
            <div><dt>Taken from payments</dt><dd>{t ? <Count value={t.taken} /> : dash}</dd></div>
            <div><dt><i className="is-dispute" aria-hidden="true" />Disputed, awaiting reply</dt><dd>{t ? <Count value={t.disputed_awaiting_reply} /> : dash}</dd></div>
            <div><dt><i className="is-fair" aria-hidden="true" />Fair, accepted</dt><dd>{t ? <Count value={t.fair} /> : dash}</dd></div>
            <div>
              <dt>Recovered</dt>
              <dd className="hm-recovered">{t ? (rising && seen !== null ? <Count value={t.recovered} from={seen} hold={!landed} /> : <Count value={t.recovered} />) : dash}</dd>
              {t && (evidence.length === 0
                ? <small>No reply or credit yet</small>
                : <small>
                    {evidence.length} piece{evidence.length === 1 ? "" : "s"} of evidence:{" "}
                    {evidence.map((e, i) => (
                      <span key={`${e.dispute_id ?? e.remittance_ref}-${i}`}>
                        {i > 0 && ", "}
                        {e.dispute_id
                          ? <Link href={withAccount("/disputes", account?.id, { id: e.dispute_id })}>{e.message_id ? "reply" : "credit"} on {e.dispute_id}</Link>
                          : <span>credit {e.remittance_ref}</span>}
                      </span>
                    ))}
                  </small>)}
            </div>
          </dl>
        </section>

        <section className="hm-block" aria-labelledby="hm-disputes">
          <h2 id="hm-disputes">Open disputes</h2>
          {o && o.open_disputes.length === 0 && <p className="hm-empty">No open disputes.</p>}
          {o && o.open_disputes.length > 0 && (
            <ul className="hm-rows">
              {o.open_disputes.map((d) => (
                <li key={`${d.run_id}-${d.dispute_id}`}>
                  <Link href={withAccount("/disputes", d.account_id, { id: d.dispute_id, run: d.run_id })} className="hm-row">
                    <DistributorMark name={d.distributor} size={30} />
                    <span className="hm-what"><strong>{d.distributor} · {d.dispute_id}</strong><small>{d.file_by ? `File by ${new Date(`${d.file_by}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })}` : "Dispute window not known"}</small></span>
                    <span className={`hm-chip ${d.status === "ready_to_send" || d.status === "draft" ? "is-ready" : ""}`}>{STATUS[d.status] ?? d.status}</span>
                    <DaysLeft days={d.days_left} />
                    <span className="hm-amt">{(d.agreed ?? 0) > 0 ? <>{money(d.amount)} awaiting<small>{money(d.agreed ?? 0)} agreed</small></> : money(d.amount)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {o && o.recent.length > 0 && (
          <section className="hm-block" aria-labelledby="hm-recent">
            <h2 id="hm-recent">Recent activity</h2>
            <ol className="hm-recent">
              {o.recent.slice(0, 6).map((r, i) => (
                <li key={`${r.at}-${i}`}>
                  <Link href={hrefOf(r.account_id, r.link)}>{r.text}</Link>
                  <time dateTime={r.at}>{when(r.at)}</time>
                </li>
              ))}
            </ol>
          </section>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
