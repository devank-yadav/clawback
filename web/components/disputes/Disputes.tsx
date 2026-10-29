"use client";

// /app/disputes: every dispute the agents filed, across every distributor, like a mail app. The list on the left
// (on top on a phone), filtered by where each one stands or by distributor; the open one on the right: what it
// disputes in plain sentences, where it stands, Review and send while it's unsent, and the full thread (every email
// and portal message, sent or received, and the Negotiator's reply drafts).
// ?id=D-0417&run=<run id>&account=<id> opens one; otherwise the newest. Amounts are the API's; nothing is summed here.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpRight, Mail, Paperclip } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import type { Account, Dispute, DisputeThread as Thread } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { DisputeThread, ReviewAndSend } from "./DisputeMail";
import NextUp from "@/components/app/NextUp";

type Item = { account: Account; t: Thread };
type Group = { head: Item; earlier: Item[] };
type Bucket = "needs" | "waiting" | "settled";
type Filter = "all" | Bucket | `acct:${string}`;
type Loaded = { items: Item[]; failed: string[] };
type Standing = { label: string; tone: string; bucket: Bucket; stamp: "is-dispute" | "is-fair" | "is-wait" | "is-neutral"; word: string };

const STATE_FILTERS: [Filter, string][] = [["all", "All"], ["waiting", "Waiting on them"], ["needs", "Needs you"], ["settled", "Settled"]];

const unsent = (d: Dispute) => d.status === "ready_to_send" || d.status === "draft";
const theirs = (t: Thread) => t.messages.filter((m) => m.from_party !== "clawback");
const replyDrafts = (t: Thread) => t.emails.filter((e) => e.kind === "reply" && (e.status === "ready" || e.status === "held" || e.status === "failed"));
const dist = (i: Item) => i.account.distributor.name || i.t.dispute.counterparty;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const noDot = (s: string) => s.trim().replace(/[.\s]+$/, "");
const href = (i: Item) => withAccount("/disputes", i.account.id, { id: i.t.dispute.id, run: i.t.run_id });

/** "4 charges the contract doesn't allow", or, for a single line, that line's own reason. The distributor and the
 * total sit right beside it, so the title doesn't repeat them. */
function titleOf(i: Item): string {
  const { lines } = i.t.dispute;
  if (lines.length === 1) return noDot(lines[0].reason);
  return `${plural(lines.length, "charge")} the contract doesn’t allow`;
}

/** Where a dispute stands, in words, from the API's status and its messages (the API classifies the distributor's
 * replies: "agrees", "new_document" and so on). */
function standing(i: Item): Standing {
  const d = i.t.dispute;
  const name = dist(i);
  const replies = theirs(i.t);
  const agreed = replies.some((m) => m.classification === "agrees");
  const partly = replies.some((m) => m.classification === "new_document");
  if (unsent(d)) return { label: "Ready for you to send", tone: "is-amber", bucket: "needs", stamp: "is-wait", word: "To send" };
  if (d.status === "withdrawn") return { label: "Closed", tone: "", bucket: "settled", stamp: "is-neutral", word: "Closed" };
  if (replyDrafts(i.t).length > 0) return { label: "Reply ready for you to send", tone: "is-amber", bucket: "needs", stamp: "is-wait", word: "Reply ready" };
  // Their last message is unanswered and isn't an agreement: it's your turn (Home lists it too).
  const last = i.t.messages.at(-1);
  if (d.status !== "resolved" && last && last.from_party !== "clawback" && last.classification !== "agrees") {
    return { label: `${name} replied`, tone: "is-accent", bucket: "needs", stamp: "is-dispute", word: "Disputing" };
  }
  // They agreed to some lines only (UNFI's one line of four): the rest of the dispute is still open with them.
  const agreedIds = new Set(replies.filter((m) => m.classification === "agrees").flatMap((m) => m.charge_ids ?? []));
  if (d.status !== "resolved" && agreed && agreedIds.size > 0 && d.lines.some((l) => !agreedIds.has(l.charge_id))) {
    return { label: `${name} agreed to part · the rest is open`, tone: "is-fair", bucket: "waiting", stamp: "is-dispute", word: "Partly agreed" };
  }
  if (d.status === "resolved" || agreed) {
    return partly
      ? { label: "Partly agreed", tone: "is-fair", bucket: "settled", stamp: "is-fair", word: "Partly agreed" }
      : { label: "Agreed", tone: "is-green", bucket: "settled", stamp: "is-fair", word: "Agreed" };
  }
  if (replies.length > 0) return { label: `Answered · waiting for ${name}`, tone: "", bucket: "waiting", stamp: "is-dispute", word: "Disputing" };
  return { label: `Sent · waiting for ${name}`, tone: "", bucket: "waiting", stamp: "is-dispute", word: "Disputing" };
}

function passes(i: Item, f: Filter): boolean {
  if (f === "all") return true;
  if (f.startsWith("acct:")) return i.account.id === f.slice(5);
  return standing(i).bucket === f;
}

/** The newest moment on a dispute, for sorting: its newest message or email, else when it was filed. Unsent ones
 * (no time yet) go first: they're the newest and they need you. */
function latest(t: Thread): number {
  const times = [t.dispute.filed_at, ...t.messages.map((m) => m.created_at), ...t.emails.map((e) => e.sent_at)]
    .filter((s): s is string => !!s)
    .map((s) => Date.parse(s))
    .filter((n) => !Number.isNaN(n));
  return times.length ? Math.max(...times) : Number.POSITIVE_INFINITY;
}

/** Emails on the record: sent by the app, kept here (filed on the portal, no mailbox connected), and received. */
function emailCounts(t: Thread) {
  return {
    sent: t.emails.filter((e) => e.status === "sent").length,
    kept: t.emails.filter((e) => e.status === "outbox").length,
    received: theirs(t).filter((m) => m.channel === "email").length,
  };
}

/** "2 emails sent · 1 received", or, with no mailbox connected, "Filed on their portal · email not sent (no mailbox
 * connected)": never a count that reads as if nothing happened. */
function emailWords(t: Thread, distributor: string): string {
  const c = emailCounts(t);
  const parts: string[] = [];
  if (c.sent) parts.push(`${c.sent} email${c.sent === 1 ? "" : "s"} sent`);
  if (c.kept) parts.push(`Filed on ${distributor}’s portal · email not sent (no mailbox connected)`);
  if (c.received) parts.push(`${c.received} received`);
  return parts.length ? parts.join(" · ") : "No emails yet";
}

function ListItem({ i, current, replaced = false }: { i: Item; current: boolean; replaced?: boolean }) {
  const s = standing(i);
  const c = emailCounts(i.t);
  const emails = c.sent + c.kept + c.received;
  return (
    <Link href={href(i)} className={`dp-item ${replaced ? "is-replaced" : ""}`} aria-current={current ? "page" : undefined}>
      <span className="dp-item-top">
        <span className="dp-item-who">{dist(i)}</span>
        <b className="dp-item-amt">{money(i.t.dispute.total)}</b>
      </span>
      <strong className="dp-item-title">{titleOf(i)}</strong>
      <span className="dp-item-foot">
        <span className={`cx-pill ${replaced ? "" : s.tone}`}>{replaced ? "Replaced by a newer check" : s.label}</span>
        <small>{i.t.dispute.id}{emails > 0 ? ` · ${plural(emails, "email")}` : ""}</small>
      </span>
    </Link>
  );
}

export default function Disputes() {
  const { account, accounts, accountsError, state } = useRun();
  const params = useSearchParams();
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(async (): Promise<Loaded> => {
    const all = accounts ?? [];
    const failed: string[] = [];
    const per = await Promise.all(
      all.map((a) =>
        api.fetchDisputes(a.id).then(
          (ts) => ts.map((t): Item => ({ account: a, t })),
          () => {
            failed.push(a.distributor.name);
            return [] as Item[];
          },
        ),
      ),
    );
    if (all.length > 0 && failed.length === all.length) throw new Error("no distributor's disputes could be loaded");
    return { items: per.flat(), failed };
  }, [accounts]);
  const replies = state.portal.length;
  const list = useFetched(accounts ? load : null, `${state.dispute?.status ?? ""}:${replies}`);

  // One entry per dispute and account: the newest run's (the API lists newest first), with the runs it replaced
  // folded under it. Only the newest can be sent; an earlier run's is shown for the record. The ones that need you
  // first (so the page opens on one), then newest first.
  const groups = useMemo(() => {
    const out: Group[] = [];
    for (const it of list.data?.items ?? []) {
      const g = out.find((x) => x.head.account.id === it.account.id && x.head.t.dispute.id === it.t.dispute.id);
      if (g) g.earlier.push(it);
      else out.push({ head: it, earlier: [] });
    }
    return out
      .map((g, n) => ({ g, n, at: latest(g.head.t), needs: standing(g.head).bucket === "needs" ? 1 : 0 }))
      .sort((a, b) => b.needs - a.needs || (b.at === a.at ? a.n - b.n : b.at - a.at))
      .map((x) => x.g);
  }, [list.data]);

  const items = list.data?.items ?? [];
  const wantId = params.get("id");
  const wantRun = params.get("run");
  const wantAccount = params.get("account");
  const matches = (i: Item) => i.t.dispute.id === wantId && (!wantAccount || i.account.id === wantAccount);
  const open: Item | null =
    items.find((i) => matches(i) && (!wantRun || i.t.run_id === wantRun)) ?? items.find(matches) ?? groups[0]?.head ?? null;
  const isHead = !!open && groups.some((g) => g.head === open);

  const distributors = useMemo(() => {
    const seen = new Map<string, string>();
    for (const g of groups) seen.set(g.head.account.id, dist(g.head));
    return [...seen.entries()];
  }, [groups]);
  const count = (f: Filter) => groups.filter((g) => passes(g.head, f)).length;
  const shown = groups.filter((g) => passes(g.head, filter));
  const loading = !list.data && !list.error && !accountsError;
  const problem = list.error ?? accountsError;

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main dp">
        <PageHeader
          title="Disputes"
          line="Every charge the agents are disputing, with every distributor. It’s also the record of every email sent and received about them."
        />
        {problem && <div className="fl-problem" role="alert">{problem}</div>}
        {list.data && list.data.failed.length > 0 && (
          <p className="dp-note" role="status">Couldn’t load the disputes with {list.data.failed.join(", ")} just now. The rest are below.</p>
        )}

        {list.data && groups.length === 0 ? (
          <EmptyState
            title="No disputes yet."
            line="A dispute appears here when the agents find a charge the contract doesn’t allow."
            action={<Link className="cx-btn" href={withAccount("/payments", account?.id)}>See your payments</Link>}
          />
        ) : (
          <>
            <div className="dp-filters" role="toolbar" aria-label="Show">
              {STATE_FILTERS.map(([f, label]) => (
                <button key={f} type="button" className="dp-chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {label}{list.data && <span>{count(f)}</span>}
                </button>
              ))}
              {distributors.length > 1 && <span className="dp-filters-gap" aria-hidden="true" />}
              {distributors.length > 1 && distributors.map(([id, name]) => {
                const f: Filter = `acct:${id}`;
                return (
                  <button key={id} type="button" className="dp-chip is-dist" aria-pressed={filter === f} onClick={() => setFilter(filter === f ? "all" : f)}>
                    {name}<span>{count(f)}</span>
                  </button>
                );
              })}
            </div>

            <div className="dp-layout">
              <nav className="dp-list" aria-label="Disputes">
                {loading && [0, 1, 2].map((n) => <div key={n} className="dp-item is-skel" aria-hidden="true"><i /><i /><i /></div>)}
                {list.data && shown.length === 0 && <p className="dp-none">Nothing here right now.</p>}
                {shown.map(({ head, earlier }) => (
                  <div key={`${head.account.id}:${head.t.dispute.id}`} className="dp-group">
                    <ListItem i={head} current={open === head} />
                    {earlier.length > 0 && (
                      <details className="dp-earlier" open={!!open && earlier.includes(open)}>
                        <summary>{plural(earlier.length, "earlier check")}, replaced</summary>
                        {earlier.map((i) => <ListItem key={`${i.t.run_id}:${i.t.dispute.id}`} i={i} current={open === i} replaced />)}
                      </details>
                    )}
                  </div>
                ))}
              </nav>

              {open && <Detail item={open} head={isHead} replies={replies} onSent={list.reload} review={params.get("send") === "1" && !!wantId && matches(open)} picked={!!wantId} />}
            </div>
          </>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}

/** The open dispute: a compact header (what it disputes, where it stands, its emails), then Review and send while
 * it's unsent, then the whole thread in time order. */
/** `review`: opened from "Review and send" elsewhere (?send=1): the letter opens at once, one click from sending. */
function Detail({ item, head, replies, onSent, review = false, picked = false }: { item: Item; head: boolean; replies: number; onSent: () => void; review?: boolean; picked?: boolean }) {
  const { t, account } = item;
  const d = t.dispute;
  const name = dist(item);
  const s = standing(item);
  const firstReply = theirs(t).map((m) => m.created_at).sort()[0] ?? null;
  const sentAt = d.filed_at ?? t.emails.find((e) => e.kind === "dispute" && e.sent_at)?.sent_at ?? null;
  const steps: { key: string; word: string; when: string | null; done: boolean }[] = [
    { key: "drafted", word: "Drafted by the agents", when: null, done: true },
    { key: "sent", word: `Sent to ${name}`, when: sentAt, done: !unsent(d) },
    { key: "replied", word: `${name} replied`, when: firstReply, done: !!firstReply },
    { key: "settled", word: s.bucket === "settled" ? s.label : "Settled", when: null, done: s.bucket === "settled" },
  ];
  const key = `${account.id}:${t.run_id}:${d.id}`;
  // On a narrow screen the open dispute sits below the list: one you picked scrolls into view, so the tap shows it.
  const here = useRef<HTMLElement>(null);
  useEffect(() => {
    if (picked && window.matchMedia("(max-width: 960px)").matches) here.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [picked, key]);
  // The dispute email as it went out (the thread below shows only that it went, then the replies).
  const letter = t.emails.find((e) => e.kind === "dispute" && (e.status === "sent" || e.status === "outbox")) ?? null;

  return (
    <article ref={here} className="cb-card dp-detail" aria-label={`${dist(item)}: ${titleOf(item)}`}>
      <header className="dp-head">
        <div className="dp-head-text">
          <span className="dp-head-who">{name}<small> · {d.id}{head ? "" : " · replaced by a newer check"}</small></span>
          <h2>{titleOf(item)}</h2>
          <div className="dp-head-meta">
            <span className={`cx-pill ${head ? s.tone : ""}`}>{head ? s.label : "Replaced by a newer check"}</span>
            <span className="cx-pill dp-emails" title="Every email the app sent or received about this dispute"><Mail aria-hidden="true" />{emailWords(t, name)}</span>
          </div>
        </div>
        <span className={`cb-stamp is-still ${s.stamp}`} aria-hidden="true"><b>{s.word}</b><span className="cb-stamp-amt">{money(d.total)}</span></span>
      </header>

      <section className="dp-section" aria-label="What it disputes">
        <h3>What it disputes</h3>
        <ul className="dp-lines">
          {d.lines.map((l) => (
            <li key={l.charge_id}>
              <span>{noDot(l.reason)}.<small>Charge {l.ref}{l.clause_ref ? ` · contract ${l.clause_ref}` : ""}</small></span>
              <b>{money(l.amount)}</b>
            </li>
          ))}
        </ul>
      </section>

      <ol className="dp-steps" aria-label="Where it stands">
        {steps.map((st) => (
          <li key={st.key} className={st.done ? "is-done" : ""}>
            <i aria-hidden="true" />
            <span>{st.word}{st.when && <small>{shortDate(st.when)}</small>}</span>
          </li>
        ))}
      </ol>

      {unsent(d) && head && (
        <section className="dp-section" aria-label="Review and send">
          <h3>Review and send</h3>
          <ReviewAndSend key={`${key}:${review ? "open" : "closed"}`} disputeId={d.id} runId={t.run_id} distributor={name} onSent={onSent} startOpen={review} />
        </section>
      )}

      <section className="dp-section" aria-label="The thread">
        <h3>The thread<small>Every email and portal message, oldest first</small></h3>
        {letter && (
          <details className="dp-letter">
            <summary>
              <Mail aria-hidden="true" />
              <span><strong>{letter.subject}</strong><small>The dispute email · to {letter.to}{letter.sent_at ? ` · ${shortDate(letter.sent_at)}` : ""}</small></span>
            </summary>
            <div className="dp-letter-body">{letter.body}</div>
            {letter.attachments.length > 0 && (
              <ul className="dp-letter-files" aria-label="Attachments">{letter.attachments.map((a) => <li key={a}><Paperclip aria-hidden="true" />{a}</li>)}</ul>
            )}
          </details>
        )}
        <DisputeThread key={key} disputeId={d.id} runId={t.run_id} distributor={name} refreshKey={`${d.status}:${replies}`} />
      </section>

      <NextUp here={{ disputeId: d.id }} homeAccount={account.id} refresh={`${d.status}:${replies}`} />

      <a className="cx-btn is-ghost is-small dp-portal" href={withAccount("/portal", account.id, { dispute: d.id })} target="_blank" rel="noreferrer">
        Open {account.distributor.portal_name || `${name}’s portal`}<ArrowUpRight aria-hidden="true" />
      </a>
    </article>
  );
}
