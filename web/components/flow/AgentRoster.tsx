"use client";

// The Agents tab when no payment is being checked here: the sources payments come from (each with when it last looked,
// from GET /connections) and the roster, one row per agent with what it does, its state and its last action, read
// from the company overview (GET /overview: recent, needs_you, open disputes). "Watching" only while a source is
// connected; "Working" while any of the supplier's payments is being checked; a received payment waits on you.

import { useCallback, useEffect, useState } from "react";
import { Bot, Calculator, FileSearch, Landmark, Mail, MessagesSquare, ScrollText, Scale, BookOpenCheck, Gavel } from "lucide-react";
import * as api from "@/lib/api";
import type { CompanyOverview, Connection } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const ago = (iso: string | null | undefined, now: number) => {
  if (!iso) return null;
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

type State = "Watching" | "Idle" | "Working" | "Waiting on you";

/** A clock that ticks once a second, so "checked 12 s ago" stays true. */
function useNow() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return now;
}

const SOURCE_ICON: Record<string, React.ReactNode> = { bank: <Landmark />, quickbooks: <BookOpenCheck />, inbox: <Mail />, gmail: <Mail /> };

export function AgentRoster({ account, working, received = null }: { account: string | null | undefined; working: boolean; received?: string | null }) {
  const now = useNow();
  const load = useCallback(() => Promise.all([
    api.fetchCompanyOverview().catch(() => null as CompanyOverview | null),
    account ? api.fetchConnections(account).catch(() => [] as Connection[]) : Promise.resolve([] as Connection[]),
  ]), [account]);
  const [tick, setTick] = useState(0);
  // The sources look on their own; the page reads their last look again every 15 seconds.
  useEffect(() => {
    const t = window.setInterval(() => setTick((n) => n + 1), 15_000);
    return () => window.clearInterval(t);
  }, []);
  const fetched = useFetched(load, String(tick));
  const overview = fetched.data?.[0] ?? null;
  // The sources that bring payments in by themselves: the bank, QuickBooks and the mailbox (not the manual upload).
  const sources = (fetched.data?.[1] ?? []).filter((c) => ["bank", "quickbooks", "inbox", "gmail"].includes(c.id));
  const watching = sources.some((c) => c.status === "connected" || !!c.checked_at);

  const decided = overview?.recent.find((r) => r.kind === "run_decided") ?? null;
  const reply = overview?.recent.find((r) => r.kind === "reply" || r.kind === "sent") ?? null;
  const asks = overview?.needs_you ?? [];
  const waitingEmail = asks.find((n) => n.kind === "dispute_email" || n.kind === "reply_email") ?? null;
  const waitingApproval = asks.find((n) => n.kind === "approval") ?? null;
  const waitingQuestion = asks.find((n) => n.kind === "question") ?? null;
  const last = (text: string | null, at: string | null | undefined) => (text ? `Last: ${text}${at ? ` · ${ago(at, now)}` : ""}` : "Nothing yet");
  const who = decided?.distributor ?? null;

  const roster: { name: string; tag: "AI" | "CODE"; icon: React.ReactNode; does: string; state: State; last: string }[] = [
    { name: "Payment reader", tag: "AI", icon: <FileSearch />, does: "Lists every deduction in a payment and checks the lines add up", state: working ? "Working" : received ? "Waiting on you" : watching ? "Watching" : "Idle", last: received ? `Received ${received}’s payment: run the agents to read it` : last(who ? `read ${who}’s payment` : null, decided?.at) },
    { name: "Deal readers · Claude + Gemini", tag: "AI", icon: <ScrollText />, does: "Read the contract twice; a term counts only if both agree word for word", state: working ? "Working" : "Idle", last: last(who ? `read ${who}’s deal` : null, decided?.at) },
    { name: "Calculator", tag: "CODE", icon: <Calculator />, does: "Works out what the deal allows for each charge, in tested code", state: working ? "Working" : "Idle", last: last(who ? `checked ${who}’s charges` : null, decided?.at) },
    { name: "Investigator", tag: "AI", icon: <Bot />, does: "Explains each difference with the clause, the sales rows and the math", state: working ? "Working" : "Idle", last: last(who ? `explained ${who}’s charges` : null, decided?.at) },
    { name: "Rules", tag: "CODE", icon: <Scale />, does: "Decides dispute, accept or ask, under your saved rules", state: working ? "Working" : waitingQuestion ? "Waiting on you" : "Idle", last: last(waitingQuestion ? `asked you about ${waitingQuestion.distributor}` : who ? `decided ${who}’s payment` : null, waitingQuestion?.since ?? decided?.at) },
    { name: "Negotiator", tag: "AI", icon: <Gavel />, does: "Drafts each dispute with proof and answers the distributor’s replies", state: waitingEmail ? "Waiting on you" : "Idle", last: last(reply ? reply.text.replace(/\.$/, "").replace(/^./, (c) => c.toLowerCase()) : waitingEmail ? `drafted ${waitingEmail.title.split(":")[0]}` : null, reply?.at ?? waitingEmail?.since) },
    { name: "Bookkeeper", tag: "CODE", icon: <MessagesSquare />, does: "Drafts the credit memo for fair charges; posts only after your yes", state: waitingApproval ? "Waiting on you" : "Idle", last: last(waitingApproval ? `drafted a credit memo for ${waitingApproval.distributor}` : null, waitingApproval?.since) },
  ];

  return (
    <div className="ar">
      <section className="ar-sources" aria-label="Where payments come from">
        <h2>{watching ? "Watching for payments" : "Where payments come from"}</h2>
        <ul>
          {(sources.length ? sources : []).map((c) => (
            <li key={c.id}>
              <span className="ar-src-icon" aria-hidden="true">{SOURCE_ICON[c.id] ?? <Landmark />}</span>
              <span><strong>{c.name}</strong><small>{c.checked_at ? `Checked ${ago(c.checked_at, now)}` : c.status === "connected" ? "Connected" : "Not connected"}</small></span>
              <i className={`tb-dot ${c.status === "connected" || c.checked_at ? "is-live" : "is-idle"}`} aria-label={c.status === "connected" || c.checked_at ? "Watching" : "Not connected"} />
            </li>
          ))}
          {fetched.data && sources.length === 0 && <li className="ar-src-none">No source connected yet. Connect the bank, QuickBooks or Gmail on Connections.</li>}
        </ul>
      </section>
      <section className="ar-roster" aria-label="The agents">
        <h2>The agents</h2>
        <ul>
          {roster.map((a) => (
            <li key={a.name}>
              <span className="ar-icon" aria-hidden="true">{a.icon}</span>
              <span className="ar-who"><strong>{a.name} <em className={a.tag === "CODE" ? "is-code" : ""}>{a.tag === "CODE" ? "code" : "AI"}</em></strong><small>{a.does}</small></span>
              <span className="ar-last">{a.last}</span>
              <span className={`ar-state is-${a.state.toLowerCase().replace(/ /g, "-")}`}><i aria-hidden="true" />{a.state}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
