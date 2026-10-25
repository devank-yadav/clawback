"use client";

// Where payments, records and contracts come from. Each card says what it brings in and its real state on this server:
// connected, not connected (the app says what happens instead), ready (upload), or coming soon. Upload is always there.

import Link from "next/link";
import { useCallback } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "@/components/console/RunProvider";
import { EmptyState, HeroPill, PageHero, SectionHead } from "@/components/ui/kit";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import { useFetched } from "@/lib/useFetched";

const LABEL = { connected: "Connected", not_connected: "Not connected", ready: "Ready", coming_soon: "Coming soon" } as const;
const TONE = { connected: "is-green", not_connected: "is-off", ready: "is-ready", coming_soon: "is-soon" } as const;

export default function Connections() {
  const { account, cast } = useRun();
  const load = useCallback(() => api.fetchConnections(), []);
  const conns = useFetched(load);
  const live = (conns.data ?? []).filter((c) => c.status !== "coming_soon");
  const soon = (conns.data ?? []).filter((c) => c.status === "coming_soon");
  const sources = live.filter((c) => c.id !== "upload");
  const upload = live.find((c) => c.id === "upload");
  const uploadHref = withAccount("/upload", account?.id);

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
                  <div className="bp-card-links">
                    {c.id === "bank" && <Link className="cx-btn is-ghost" href={withAccount("/", account?.id)}>Go to the agents</Link>}
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
