"use client";

// Where payments, records and contracts come from. Each card says what it brings in and its real state on this server:
// connected, not connected (the app says what happens instead), ready (upload), or coming soon. Upload is always there.

import Link from "next/link";
import { useCallback } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { useFetched } from "@/lib/useFetched";

const LABEL = { connected: "Connected", not_connected: "Not connected", ready: "Ready", coming_soon: "Coming soon" } as const;

export default function Connections() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchConnections(), []);
  const conns = useFetched(load);
  const live = (conns.data ?? []).filter((c) => c.status !== "coming_soon");
  const soon = (conns.data ?? []).filter((c) => c.status === "coming_soon");

  return (
    <div className="fl">
      <TopBar account={account} />
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
              {c.id === "upload" && <Link className="cx-btn is-ghost" href={withAccount("/", account?.id)}>Upload a file</Link>}
              {c.id === "bank" && <Link className="cx-btn is-ghost" href={withAccount("/", account?.id)}>Go to the agents</Link>}
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
