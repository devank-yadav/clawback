"use client";

// /app/settings: what the owner sets once (api/autopilot.py, GET/PUT /settings/autopilot), the weekly summary with
// its one-tap answers (api/digest.py: GET /digest/preview, POST /digest/send), and doors to everything that used to
// crowd the sidebar. Amounts here are limits the owner types; the app computes no money.

import Link from "next/link";
import { useCallback, useState } from "react";
import { ArrowRight, ExternalLink } from "lucide-react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { PageHeader } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { useFetched } from "@/lib/useFetched";

function Check({ checked, onChange, label, hint }: { checked: boolean; onChange: (on: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="cb-check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="cb-check-box" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
      <span className="cb-check-text"><span>{label}</span>{hint && <small>{hint}</small>}</span>
    </label>
  );
}

function Amount({ value, onChange, disabled, label }: { value: string; onChange: (v: string) => void; disabled: boolean; label: string }) {
  return (
    <span className={`st2-amt ${disabled ? "is-off" : ""}`}>
      <span aria-hidden="true">$</span>
      <input inputMode="decimal" aria-label={label} value={value} disabled={disabled} placeholder="1,000"
        onChange={(e) => onChange(e.target.value.replace(/[^0-9.,]/g, ""))} />
    </span>
  );
}

const num = (v: string) => Number(v.replace(/,/g, ""));
const shown = (v: number | null | undefined) => (v == null ? "" : String(v));

export default function Settings() {
  const { account } = useRun();
  const fetched = useFetched(useCallback(() => api.fetchAutopilot(), []));
  return (
    <div className="fl">
      <TopBar account={account} />
      <main className="fl-main st2">
        <PageHeader title="Settings" line="Set these once. The agents follow them on every payment." />
        {fetched.error && <div className="fl-problem" role="alert">{fetched.error}</div>}
        {fetched.data ? <Form initial={fetched.data} /> : !fetched.error && <div className="hm-skel" aria-hidden="true"><i /><i /></div>}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}

/** The form, started from what's saved. */
function Form({ initial }: { initial: api.Autopilot }) {
  const { account, cast } = useRun();
  const [settings, setS] = useState<api.Autopilot>(initial);
  const [arrive, setArrive] = useState(initial.run_on_arrival);
  const [sendOn, setSendOn] = useState(initial.send_disputes_under != null);
  const [sendAmt, setSendAmt] = useState(shown(initial.send_disputes_under));
  const [postOn, setPostOn] = useState(initial.post_fair_under != null);
  const [postAmt, setPostAmt] = useState(shown(initial.post_fair_under));
  const [email, setEmail] = useState(initial.digest_email ?? "");
  const [weekly, setWeekly] = useState(initial.digest_weekly);
  const [note, setNote] = useState<{ where: "auto" | "digest"; text: string; bad?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);
  const preview = useFetched(useCallback(() => api.previewDigest(), []), String(previewKey));


  async function save(where: "auto" | "digest") {
    setBusy(true);
    setNote(null);
    try {
      let change: api.AutopilotChange;
      if (where === "auto") {
        const clear: ("send_disputes_under" | "post_fair_under")[] = [];
        change = { run_on_arrival: arrive };
        if (sendOn) {
          if (!(num(sendAmt) > 0)) throw new Error("Enter an amount like $5,000 for disputes, or untick it.");
          change.send_disputes_under = num(sendAmt);
        } else clear.push("send_disputes_under");
        if (postOn) {
          if (!(num(postAmt) > 0)) throw new Error("Enter an amount like $1,000 for fair charges, or untick it.");
          change.post_fair_under = num(postAmt);
        } else clear.push("post_fair_under");
        change.clear = clear;
      } else {
        change = email.trim() ? { digest_email: email.trim(), digest_weekly: weekly } : { digest_weekly: weekly, clear: ["digest_email"] };
      }
      const saved = await api.saveAutopilot(change);
      setS(saved);
      // A new limit applies to what comes next: memos already waiting still wait for one OK. Say so, not "Saved." alone.
      let text = "Saved.";
      if (where === "auto" && saved.post_fair_under != null) {
        const waiting = (await api.fetchCompanyOverview().catch(() => null))?.needs_you
          .filter((n) => n.kind === "approval" && n.amount != null && n.amount <= saved.post_fair_under!).length ?? 0;
        if (waiting) text = `Saved. New fair-charge memos up to that limit go to QuickBooks on their own; ${waiting === 1 ? "the one already waiting still needs" : `the ${waiting} already waiting still need`} your OK once, on Home.`;
      }
      setNote({ where, text });
      setPreviewKey((n) => n + 1);
    } catch (e) {
      setNote({ where, text: (e as Error).message, bad: true });
    } finally {
      setBusy(false);
    }
  }

  async function sendNow() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.sendDigest();
      setNote({ where: "digest", text: r.status === "sent" ? `Sent to ${r.to}.` : r.detail, bad: r.status !== "sent" });
    } catch (e) {
      setNote({ where: "digest", text: (e as Error).message, bad: true });
    } finally {
      setBusy(false);
    }
  }

  const doors = [
    { href: "/connections", title: "Connections", line: "The bank, QuickBooks, Gmail" },
    { href: "/distributors", title: "Distributors", line: "Who you sell through, and which ones the agents watch" },
  ];

  return (
    <>
        <section className="cb-card st2-sec" aria-labelledby="st2-auto">
          <h2 id="st2-auto">What the agents do on their own</h2>
          <div className="st2-row">
            <Check checked={arrive} onChange={setArrive} label="Start the agents when a payment comes in"
              hint="When this is off, each payment waits for you to press Run the agents." />
          </div>
          <div className="st2-row">
            <Check checked={sendOn} onChange={setSendOn} label="Send disputes without asking me when the total is up to"
              hint="Every figure and quote is still checked before it leaves. Bigger disputes wait for you." />
            <Amount value={sendAmt} onChange={setSendAmt} disabled={!sendOn} label="Dispute limit" />
          </div>
          <div className="st2-row">
            <Check checked={postOn} onChange={setPostOn} label="Send fair charges to QuickBooks without asking me when up to"
              hint="The credit memo for charges the contract allows. Bigger ones wait for your yes." />
            <Amount value={postAmt} onChange={setPostAmt} disabled={!postOn} label="QuickBooks limit" />
          </div>
          <p className="st2-always">Always asked: anything the contract leaves to judgment, and any charge the two readers read differently.</p>
          <div className="st2-go">
            <button className="cx-btn is-blue" onClick={() => void save("auto")} disabled={busy}>Save</button>
            {note?.where === "auto" && <span className={`st2-note ${note.bad ? "is-bad" : ""}`} role="status">{note.text}</span>}
          </div>
        </section>

        <section className="cb-card st2-sec" aria-labelledby="st2-digest">
          <h2 id="st2-digest">Weekly summary by email</h2>
          <p className="st2-lead">Where your money stands, and what needs you, with one-tap answers. No need to open Clawback.</p>
          <label className="st2-field">
            <span>Send it to</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@yourbrand.com" autoComplete="email" />
          </label>
          <div className="st2-row"><Check checked={weekly} onChange={setWeekly} label="Every Monday morning" /></div>
          <div className="st2-go">
            <button className="cx-btn is-blue" onClick={() => void save("digest")} disabled={busy}>Save</button>
            <button className="cx-btn is-ghost" onClick={() => void sendNow()} disabled={busy || !settings.digest_email}>Send me this week’s summary now</button>
            {note?.where === "digest" && <span className={`st2-note ${note.bad ? "is-bad" : ""}`} role="status">{note.text}</span>}
          </div>
          {preview.data && (
            <div className="st2-preview" aria-label="This week’s summary">
              <small>This week’s summary</small>
              <strong>{preview.data.subject}</strong>
              {preview.data.items.length > 0 ? (
                <ul>
                  {preview.data.items.map((it, i) => (
                    <li key={i}>
                      <span>{it.title.includes(it.distributor) ? it.title : `${it.distributor}: ${it.title}`}</span>
                      {it.actions.length > 0
                        ? <span className="st2-taps">{it.actions.map((a) => <em key={a.label}>{a.label}</em>)}</span>
                        : <span className="st2-taps"><em className="is-open">Open in Clawback</em></span>}
                    </li>
                  ))}
                </ul>
              ) : <p>Nothing needs you this week.</p>}
            </div>
          )}
        </section>

        <section className="st2-more" aria-labelledby="st2-more">
          <h2 id="st2-more">Everything else</h2>
          <nav className="st2-doors" aria-label="More settings">
            {doors.map((d) => (
              <Link key={d.href} className="cb-card hm2-door" href={withAccount(d.href, account?.id)}>
                <strong>{d.title}</strong><span>{d.line}</span><ArrowRight aria-hidden="true" />
              </Link>
            ))}
            {account && (
              <a className="cb-card hm2-door" href={withAccount("/portal", account.id)} target="_blank" rel="noreferrer">
                <strong>{account.distributor.portal_name ?? `${cast.distributor}’s portal`}</strong><span>What {cast.distributor} sees (demo)</span><ExternalLink aria-hidden="true" />
              </a>
            )}
          </nav>
        </section>
    </>
  );
}
