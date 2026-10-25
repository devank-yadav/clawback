"use client";

// Where payments, records and contracts come from. Each card says what it brings in and its real state on this server:
// connected, not connected (the app says what happens instead), ready (upload), or coming soon. Upload is always there.
// The three that start the agents on their own (bank, QuickBooks, remittance inbox) also say when they last looked,
// what they last found for the distributor in view and which run it started; the page refreshes every 10 seconds.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { Connection } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const LABEL = { connected: "Connected", not_connected: "Not connected", ready: "Ready", coming_soon: "Coming soon" } as const;
const REFRESH_MS = 10_000;

/** "4 s ago", "3 min ago", "2 h ago": how long since the source looked or found something. */
function ago(at: string | null | undefined, now: number): string | null {
  if (!at) return null;
  const s = Math.max(0, Math.round((now - new Date(at).getTime()) / 1000));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

function Seen({ c, accountId, now }: { c: Connection; accountId: string | undefined; now: number }) {
  const checked = ago(c.checked_at, now);
  const found = ago(c.last_seen_at, now);
  if (!checked && !c.last_seen && !c.address && !c.problem) return null;
  return (
    <div className="cx-small" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {c.address && (
        <span>Send to <strong style={{ fontWeight: 500, wordBreak: "break-all" }}>{c.address}</strong></span>
      )}
      {checked && <span className="cx-muted">{c.id === "inbox" ? "Last email" : "Last checked"} {checked}</span>}
      {c.problem && <span role="status" style={{ color: "var(--amber)" }}>Last look failed: {c.problem}. Trying again.</span>}
      {c.last_seen ? (
        <span>
          {c.last_seen}
          {found && <span className="cx-muted"> · {found}</span>}
          {c.run_id && (
            <> · <Link href={withAccount("/", accountId, { run: c.run_id })}>Open the run</Link></>
          )}
        </span>
      ) : (
        checked && <span className="cx-muted">Nothing new for this distributor yet.</span>
      )}
    </div>
  );
}

export default function Connections() {
  const { account, cast } = useRun();
  const accountId = account?.id;
  const load = useCallback(() => api.fetchConnections(accountId), [accountId]);
  const conns = useFetched(load);
  const { reload } = conns;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => {
      setNow(Date.now());
      reload();
    }, REFRESH_MS);
    return () => clearInterval(t);
  }, [reload]);
  const live = (conns.data ?? []).filter((c) => c.status !== "coming_soon");
  const soon = (conns.data ?? []).filter((c) => c.status === "coming_soon");

  return (
    <div className="fl">
      <TopBar account={account} active="connections" />
      <main className="fl-main">
        <header className="ds-head">
          <span className="cx-eyebrow">{account?.brand.name ?? " "}</span>
          <h1>Where the agents get their information</h1>
          <p>Payments, records and contracts come in through these. When a payment from {cast.distributor} arrives, the agents start on their own.</p>
        </header>
        {conns.error && <div className="fl-problem" role="alert">{conns.error}</div>}
        <div className="cn-grid">
          {live.map((c) => (
            <article key={c.id} className={`cn-card is-${c.status}`}>
              <div className="cn-top"><strong>{c.name}</strong><span className={`cn-status is-${c.status}`}><i />{LABEL[c.status]}</span></div>
              <p className="cn-brings">{c.brings}</p>
              <p className="cx-small cx-muted">{c.detail}</p>
              <Seen c={c} accountId={accountId} now={now} />
              {c.id === "upload" && <Link className="cx-btn is-ghost" href={withAccount("/upload", accountId)}>Upload a file</Link>}
              {c.id === "bank" && <Link className="cx-btn is-ghost" href={withAccount("/", accountId)}>Go to the agents</Link>}
            </article>
          ))}
        </div>
        {soon.length > 0 && (
          <section className="cn-soon">
            <h2>Coming soon</h2>
            <div className="cn-grid">
              {soon.map((c) => (
                <article key={c.id} className="cn-card is-coming_soon">
                  <div className="cn-top"><strong>{c.name}</strong><span className="cn-status is-coming_soon"><i />{LABEL[c.status]}</span></div>
                  <p className="cn-brings">{c.brings}</p>
                  <p className="cx-small cx-muted">{c.detail}. Until then, upload the file.</p>
                </article>
              ))}
            </div>
          </section>
        )}
      </main>
      <SessionDialogs account={account} />
    </div>
  );
}
