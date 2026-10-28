"use client";

// /app/rules: what the agents learned from you and will apply next time, across every distributor. Each rule came
// from one of your answers ("save as a rule"), so a charge like it is never asked about twice. Below them, the
// short fixed list of what the agents always bring to you. Contracts, records and the audit trail live elsewhere.

import Link from "next/link";
import { useCallback } from "react";
import { ArrowUpRight } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { shortDate } from "@/lib/format";
import type { Rule, TermType } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

/** A rule and the distributors it was saved for (the same rule can come back from more than one account). */
type Learned = { rule: Rule; covers: string[] };
type Loaded = { rules: Learned[]; undone: number; failed: string[] };

const ABOUT: Record<TermType, string> = {
  fee_discretion: "Fees the contract leaves to judgment",
  promo_rate: "Promo rates",
  product_scope: "Which products a promo covers",
  unit_cap: "Promo unit limits",
  date_range: "Promo dates",
  amendment: "Changes to the contract",
};

const DO: Record<Rule["decision"], string> = { accept: "Accept it as fair", dispute: "Dispute it", ask: "Ask you" };

const ALWAYS_ASK = [
  { title: "Anything the contract leaves to judgment", line: "Words like “at its discretion” or “reasonable”, until you answer once and it becomes a rule here." },
  { title: "When the two contract readers disagree", line: "Two different AI models read every contract. If they don’t agree on a term, a person decides, not the agents." },
  { title: "Disputes over your limit", line: "A dispute above the amount you set waits for your OK before it goes out." },
];

export default function Rules() {
  const { account, accounts, accountsError } = useRun();

  const load = useCallback(async (): Promise<Loaded> => {
    const all = accounts ?? [];
    const failed: string[] = [];
    const per = await Promise.all(
      all.map((a) =>
        api.fetchSaved(a.id).then(
          (s) => s.rules.map((rule) => ({ rule, distributor: a.distributor.name })),
          () => {
            failed.push(a.distributor.name);
            return [] as { rule: Rule; distributor: string }[];
          },
        ),
      ),
    );
    if (all.length > 0 && failed.length === all.length) throw new Error("no distributor's rules could be loaded");
    const byId = new Map<string, Learned>();
    let undone = 0;
    for (const { rule, distributor } of per.flat()) {
      const known = byId.get(rule.id);
      if (known) {
        for (const name of [rule.counterparty, distributor]) if (name && !known.covers.includes(name)) known.covers.push(name);
        continue;
      }
      if (rule.status === "undone") {
        undone += 1;
        continue;
      }
      byId.set(rule.id, { rule, covers: [...new Set([rule.counterparty || distributor].filter(Boolean))] });
    }
    // Newest first.
    const rules = [...byId.values()].sort((a, b) => Date.parse(b.rule.learned_at) - Date.parse(a.rule.learned_at));
    return { rules, undone, failed };
  }, [accounts]);
  const saved = useFetched(accounts ? load : null);
  const data = saved.data;
  const loading = !data && !saved.error && !accountsError;
  const problem = saved.error ?? accountsError;
  const settings = withAccount("/settings", account?.id);
  const count = data?.rules.length ?? 0;

  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main rl">
        <PageHeader
          title="Rules"
          line="What the agents learned from your answers, and will apply next time without asking you again."
        />
        {problem && <div className="fl-problem" role="alert">{problem}</div>}
        {data && data.failed.length > 0 && (
          <p className="rl-note" role="status">Couldn’t load the rules for {data.failed.join(", ")} just now. The rest are below.</p>
        )}

        <section className="rl-section" aria-labelledby="rl-learned">
          <h2 id="rl-learned" className="rl-h">Your rules{data && <span>{count}</span>}</h2>
          {loading && (
            <div className="rl-grid" aria-hidden="true">
              {[0, 1].map((n) => <div key={n} className="cb-card rl-card is-skel"><i /><i /><i /></div>)}
            </div>
          )}
          {data && count === 0 && (
            <EmptyState
              title="No rules yet."
              line="When you answer a question about a charge, your answer becomes a rule here, so you’re never asked twice."
            />
          )}
          {data && count > 0 && (
            <ul className="rl-grid">
              {data.rules.map(({ rule: r, covers }) => (
                <li key={r.id} className="cb-card rl-card">
                  <div className="rl-card-top">
                    <span className="cx-tag is-rule">{r.label}</span>
                    {r.status === "pending"
                      ? <span className="cx-pill is-amber">Waiting for your OK</span>
                      : <span className="cx-pill is-green">In use</span>}
                  </div>
                  <h3>{r.summary || r.pattern_text}</h3>
                  <dl className="rl-facts">
                    <div><dt>Covers</dt><dd>{covers.length ? covers.join(", ") : "Every distributor"}</dd></div>
                    <div><dt>About</dt><dd>{ABOUT[r.term_type] ?? r.term_type.replace(/_/g, " ")}</dd></div>
                    <div>
                      <dt>Then</dt>
                      <dd>
                        {DO[r.decision]}
                        {r.else_decision && r.else_decision !== r.decision && <>; otherwise {DO[r.else_decision].toLowerCase()}</>}
                      </dd>
                    </div>
                    <div>
                      <dt>Set by</dt>
                      <dd>{setBy(r)}</dd>
                    </div>
                  </dl>
                  {r.summary && r.pattern_text && <p className="rl-quote">When a contract says something like “{r.pattern_text}”</p>}
                </li>
              ))}
            </ul>
          )}
          {data && data.undone > 0 && (
            <p className="rl-fine">{data.undone === 1 ? "1 rule you undid isn’t shown" : `${data.undone} rules you undid aren’t shown`}: the agents don’t apply it any more.</p>
          )}
        </section>

        <section className="rl-section" aria-labelledby="rl-always">
          <h2 id="rl-always" className="rl-h">What the agents always ask you about</h2>
          <ul className="cb-card rl-always">
            {ALWAYS_ASK.map((a) => (
              <li key={a.title}>
                <strong>{a.title}</strong>
                <span>{a.line}</span>
              </li>
            ))}
          </ul>
          <Link className="cx-btn is-ghost is-small rl-settings" href={settings}>Change your limits in Settings<ArrowUpRight aria-hidden="true" /></Link>
        </section>
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}

/** "You, Oct 28, by answering a question": the owner is the one person who sets rules. */
function setBy(r: Rule): string {
  const who = r.approver_role === "owner" ? "You" : r.approver;
  const when = Number.isNaN(Date.parse(r.learned_at)) ? "" : `, ${shortDate(r.learned_at)}`;
  return `${who}${when}${r.source_question_id ? ", by answering a question" : ""}`;
}
