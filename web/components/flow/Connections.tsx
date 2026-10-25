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
import { EmptyState, HeroPill, PageHero, SectionHead } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { Connection } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const LABEL = { connected: "Connected", not_connected: "Not connected", ready: "Ready", coming_soon: "Coming soon" } as const;
const TONE = { connected: "is-green", not_connected: "is-off", ready: "is-ready", coming_soon: "is-soon" } as const;
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
    <div className="bp-fine" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {c.address && (
        <span>Send to <strong style={{ fontWeight: 500, color: "var(--sub)", wordBreak: "break-all" }}>{c.address}</strong></span>
      )}
      {checked && <span>{c.id === "inbox" ? "Last email" : "Last checked"} {checked}</span>}
      {c.problem && <span role="status" style={{ color: "var(--amber)" }}>Last look failed: {c.problem}. Trying again.</span>}
      {c.last_seen ? (
        <span style={{ color: "var(--sub)" }}>
          {c.last_seen}
          {found && <span className="bp-fine"> · {found}</span>}
          {c.run_id && (
            <> · <Link className="bp-link" href={withAccount("/", accountId, { run: c.run_id })}>Open the run</Link></>
          )}
        </span>
      ) : (
        checked && <span>Nothing new for this distributor yet.</span>
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
  const sources = live.filter((c) => c.id !== "upload");
  const upload = live.find((c) => c.id === "upload");
  const uploadHref = withAccount("/upload", accountId);

  return (
    <div className="fl">
      <TopBar account={account} active="connections" />
      <main className="fl-main bp bp-cn">
        <PageHero
          pill={<HeroPill>{account?.brand.name ?? "Connections"}</HeroPill>}
          title={<>Where the agents get<em>their information.</em></>}
          sub={`Payments, records and contracts come in through these. When a payment from ${cast.distributor} arrives, the agents start on their own.`}
        />
        {conns.error && <div className="fl-problem" role="alert">{conns.error}</div>}
        {conns.data && conns.data.length === 0 && <EmptyState title="No sources on this server." line="Upload a remittance, a contract or records as a file and the agents read it." />}

        {!conns.data && !conns.error && (
          <div className="bp-start" aria-hidden="true">
            {[0, 1, 2].map((i) => <div key={i} className="bp-start-card"><i className="bp-skel-block" style={{ width: "40%" }} /><i className="bp-skel-block" /><i className="bp-skel-block" style={{ width: "75%" }} /></div>)}
          </div>
        )}

        {live.length > 0 && (
          <section className="bp-section">
            <SectionHead title="Connected sources" muted="What each brings in, and its state on this server." />
            <div className="bp-start">
              {sources.map((c, i) => (
                <article key={c.id} className={`bp-start-card is-${c.status}`}>
                  <div className="bp-start-top"><span className="bp-step" aria-hidden="true">{i + 1}</span><span className={`bp-chip ${TONE[c.status]}`}>{LABEL[c.status]}</span></div>
                  <h3>{c.name}</h3>
                  <p>{c.brings}</p>
                  <p className="bp-sync">{c.detail}</p>
                  <Seen c={c} accountId={accountId} now={now} />
                  <div className="bp-card-links">
                    {c.id === "bank" && <Link className="cx-btn is-ghost" href={withAccount("/", accountId)}>Go to the agents</Link>}
                    <Link className="bp-link" href={uploadHref}>Or upload a file</Link>
                  </div>
                </article>
              ))}
            </div>
            {upload && (
              <div className="bp-upload">
                <span>
                  <strong>{upload.name}<span className={`bp-chip ${TONE[upload.status]}`}>{LABEL[upload.status]}</span></strong>
                  <small>{upload.brings}. {upload.detail}.</small>
                </span>
                <Link className="cx-btn is-ghost" href={uploadHref}>Upload a file</Link>
              </div>
            )}
          </section>
        )}

        {soon.length > 0 && (
          <section className="bp-section">
            <SectionHead title="Coming soon" muted="Not on this server yet." />
            <div className="bp-soon">
              {soon.map((c) => (
                <article key={c.id}>
                  <div className="bp-soon-top"><strong>{c.name}</strong><span className="bp-chip is-soon">Soon</span></div>
                  <p>{c.brings}</p>
                  <p className="bp-fine">{c.detail}. Until then, <Link href={uploadHref}>upload the file</Link>.</p>
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
