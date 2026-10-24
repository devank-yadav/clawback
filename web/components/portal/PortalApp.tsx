"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import { inkOn, useCurrentAccount } from "@/lib/accounts";
import { dollars } from "@/lib/format";
import * as api from "@/lib/api";
import { limitMessage } from "@/lib/session";
import { setAdminToken } from "@/lib/tokens";
import type { Account, Dispute, PortalMessage } from "@/lib/types";

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** "amendment-1" → "Amendment 1". */
const docName = (id: string) => id.replace(/[-_]+/g, " ").replace(/^./, (c) => c.toUpperCase());

/** The dispute this portal shows: ?dispute= from the brand's workspace, else the one in the account's latest run. */
async function findDispute(account: string, given: string | null): Promise<string | null> {
  if (given) return given;
  const run = await api.latestRun(account);
  if (!run) return null;
  const events = await api.runEventsOnce(run.run_id);
  const last = [...events].reverse().find((e) => e.type === "dispute");
  return last && last.type === "dispute" ? last.data.id : null;
}

export default function PortalApp() {
  const { account, error: accountsError } = useCurrentAccount();
  const given = useSearchParams().get("dispute");
  if (!account) {
    return (
      <div className="portal">
        <header className="p-top"><div className="p-brand"><span className="p-logo" aria-hidden>·</span><div><strong>Supplier portal</strong></div></div></header>
        <main className="p-main"><section className="p-card"><p className={accountsError ? "p-error" : "p-muted"} role="status">{accountsError ?? "Loading…"}</p></section></main>
      </div>
    );
  }
  return <Portal key={`${account.id}:${given}`} account={account} given={given} />;
}

/** The distributor's side of a dispute: the lines Clawback filed, the thread, and a reply box the judge types into. */
function Portal({ account, given }: { account: Account; given: string | null }) {
  const d = account.distributor;
  const [disputeId, setDisputeId] = useState<string | null>(given);
  const [dispute, setDispute] = useState<Dispute | null>(null);
  const [thread, setThread] = useState<PortalMessage[]>([]);
  const [presets, setPresets] = useState<api.PortalPreset[]>([]);
  const [text, setText] = useState("");
  const [attach, setAttach] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState<string | null>(null);
  const [token, setToken] = useState("");
  const [loaded, setLoaded] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = `${d.portal_name} · Deductions`;
  }, [d.portal_name]);

  // Lines change after a concession, so the dispute is read again after every reply.
  const refresh = useCallback(async (id: string) => {
    const [dd, m] = await Promise.all([api.fetchDispute(id), api.fetchPortalMessages(id)]);
    setDispute(dd);
    setThread(m);
  }, []);

  useEffect(() => {
    let cancelled = false;
    findDispute(account.id, given)
      .then(async (id) => {
        if (cancelled) return;
        setDisputeId(id);
        if (!id) return;
        const [dd, m, p] = await Promise.all([api.fetchDispute(id), api.fetchPortalMessages(id), api.fetchPortalPresets(account.id, id).catch(() => [])]);
        if (cancelled) return;
        setDispute(dd);
        setThread(m);
        setPresets(p);
        setError(null);
      })
      .catch((e: Error) => !cancelled && setError(api.unreachable(e)))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, [account.id, given]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [thread.length]);

  async function send() {
    const body = text.trim();
    if (!body || sending || !disputeId) return;
    setSending(true);
    setError(null);
    setLimited(null);
    try {
      const added = await api.postPortalMessage(disputeId, body, attach);
      setThread((t) => [...t, ...added]);
      setText("");
      setAttach(null);
      await refresh(disputeId);
    } catch (e) {
      const limit = limitMessage(e);
      if (limit) setLimited(limit);
      else setError(`That reply wasn't accepted (${(e as Error).message}). Try again.`);
    } finally {
      setSending(false);
    }
  }

  const docs = [...new Set(presets.map((p) => p.attachment_doc_id).filter((x): x is string => !!x))];
  const theme = {
    "--brand": d.colors.primary,
    "--brand-accent": d.colors.accent,
    "--brand-ink": inkOn(d.colors.primary),
  } as CSSProperties;

  return (
    <div className="portal" style={theme}>
      <header className="p-top">
        <div className="p-brand">
          <span className="p-logo" aria-hidden>{d.name.charAt(0)}</span>
          <div><strong>{d.portal_name}</strong><small>Supplier deductions · {d.name}</small></div>
        </div>
        <span className="p-tag">{d.desk_email}</span>
      </header>

      <main className="p-main">
        <section className="p-card" aria-labelledby="dispute-h">
          <div className="p-head">
            <div>
              <small>Supplier dispute</small>
              <h1 id="dispute-h">{dispute?.id ?? disputeId ?? "No open dispute"}</h1>
              <p>{account.brand.name}{dispute ? ` · remittance ${dispute.remittance_id}` : ""}</p>
            </div>
            {dispute && (
              <div className="p-total">
                <small>Disputed total</small>
                <strong>{dollars(dispute.total)}</strong>
                <span className="p-status">{dispute.status}</span>
              </div>
            )}
          </div>
          {!loaded && <p className="p-muted">Loading the dispute…</p>}
          {loaded && !disputeId && !error && <p className="p-muted">{account.brand.name} hasn’t filed a dispute with {d.name} yet.</p>}
          {dispute && (
            <ul className="p-lines">
              {dispute.lines.map((l) => (
                <li key={l.charge_id}>
                  <div className="p-line-top">
                    <span><strong>{l.ref}</strong> · {l.reason}</span>
                    <strong className="p-amt">{dollars(l.amount)}</strong>
                  </div>
                  {l.quote && <blockquote>{l.clause_ref && <b>{l.clause_ref}</b>} “{l.quote}”</blockquote>}
                  <p className="p-math">{l.math}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        {disputeId && (
          <section className="p-card" aria-labelledby="thread-h">
            <h2 id="thread-h">Messages</h2>
            <ol className="p-thread" aria-live="polite">
              {thread.map((m) => (
                <li key={m.id} className={m.from_party === "clawback" ? "theirs" : "mine"}>
                  <small>{m.from_party === "clawback" ? `${account.brand.name} (via Clawback)` : `${d.name} deductions desk`} · {when(m.created_at)}</small>
                  <p>{m.text}</p>
                  {m.attachment_doc_id && <span className="p-attach">Attached: {docName(m.attachment_doc_id)}</span>}
                </li>
              ))}
              {loaded && thread.length === 0 && <li className="p-muted">No messages yet.</li>}
            </ol>
            <div ref={end} />

            {presets.length > 0 && (
              <div className="p-presets" role="group" aria-label="Quick replies">
                {presets.map((p) => (
                  <button key={p.id} type="button" aria-pressed={text === p.text} onClick={() => { setText(p.text); setAttach(p.attachment_doc_id); }}>{p.label}</button>
                ))}
              </div>
            )}
            <label htmlFor="reply" className="p-label">Your reply as {d.name}</label>
            <textarea id="reply" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a denial, a question, or pick a quick reply above" rows={4} />
            <div className="p-row">
              {docs.map((doc) => (
                <label className="p-check" key={doc}>
                  <input type="checkbox" checked={attach === doc} onChange={(e) => setAttach(e.target.checked ? doc : null)} />
                  Attach {docName(doc)}
                </label>
              ))}
              <button type="button" className="p-send" onClick={send} disabled={!text.trim() || sending}>{sending ? "Sending…" : "Send reply"}</button>
            </div>
            {sending && <p className="p-muted" role="status">{account.brand.name}’s side is reading your reply. This can take a few seconds.</p>}
            {limited && (
              <div className="p-limit" role="status">
                <p>{limited}</p>
                <form onSubmit={(e) => { e.preventDefault(); if (token.trim()) { setAdminToken(token.trim()); setToken(""); void send(); } }}>
                  <label htmlFor="p-admin" className="p-label">Presenting? Admin token</label>
                  <div className="p-row"><input id="p-admin" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} /><button className="p-send" type="submit" disabled={!token.trim()}>Use and send</button></div>
                </form>
              </div>
            )}
            {error && <p className="p-error" role="alert">{error}</p>}
          </section>
        )}
        {error && !disputeId && <p className="p-error" role="alert">{error}</p>}
      </main>
    </div>
  );
}
