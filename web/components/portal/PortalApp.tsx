"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { dollars } from "@/lib/format";
import * as api from "@/lib/live";
import type { Dispute, PortalMessage } from "@/lib/types";

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** Northmart's side of dispute D-0417: the lines Clawback filed, the thread, and a reply box the judge types into. */
export default function PortalApp() {
  const [dispute, setDispute] = useState<Dispute | null>(null);
  const [thread, setThread] = useState<PortalMessage[]>([]);
  const [presets, setPresets] = useState<api.PortalPreset[]>([]);
  const [text, setText] = useState("");
  const [attach, setAttach] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  // Lines change after a concession (C4 drops to $540), so the dispute is refetched after every reply.
  const refresh = useCallback(async () => {
    const [d, m] = await Promise.all([api.fetchDispute(), api.fetchPortalMessages()]);
    setDispute(d);
    setThread(m);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.fetchDispute(), api.fetchPortalMessages(), api.fetchPortalPresets()])
      .then(([d, m, p]) => {
        if (cancelled) return;
        setDispute(d);
        setThread(m);
        setPresets(p);
        setError(null);
      })
      .catch((e: Error) => !cancelled && setError(`Can't reach the Clawback API (${e.message}). Start it with make api, or check NEXT_PUBLIC_API_BASE.`))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [thread.length]);

  async function send() {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      const added = await api.postPortalMessage(body, attach);
      setThread((t) => [...t, ...added]);
      setText("");
      setAttach(null);
      await refresh();
    } catch (e) {
      setError(`That reply wasn't accepted (${(e as Error).message}). Try again.`);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="portal">
      <header className="p-top">
        <div className="p-brand">
          <span className="p-logo" aria-hidden>N</span>
          <div><strong>Northmart</strong><small>Supplier deductions portal</small></div>
        </div>
        <span className="p-tag">Fictional demo</span>
      </header>

      <main className="p-main">
        <section className="p-card" aria-labelledby="dispute-h">
          <div className="p-head">
            <div>
              <small>Dispute</small>
              <h1 id="dispute-h">{dispute?.id ?? api.DISPUTE_ID}</h1>
              <p>{dispute ? `Peak Bar Co. · remittance ${dispute.remittance_id}` : "Peak Bar Co."}</p>
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
          {loaded && !dispute && !error && <p className="p-muted">No dispute has been filed yet.</p>}
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

        <section className="p-card" aria-labelledby="thread-h">
          <h2 id="thread-h">Messages</h2>
          <ol className="p-thread" aria-live="polite">
            {thread.map((m) => (
              <li key={m.id} className={m.from_party === "northmart" ? "mine" : "theirs"}>
                <small>{m.from_party === "northmart" ? "Northmart deductions desk" : "Peak Bar Co. (Clawback)"} · {when(m.created_at)}</small>
                <p>{m.text}</p>
                {m.attachment_doc_id && <span className="p-attach">Attached: {m.attachment_doc_id === "amendment-1" ? "Signed amendment" : m.attachment_doc_id}</span>}
              </li>
            ))}
            {loaded && thread.length === 0 && <li className="p-muted">No messages yet.</li>}
          </ol>
          <div ref={end} />

          {presets.length > 0 && (
            <div className="p-presets" role="group" aria-label="Quick replies">
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  aria-pressed={text === p.text}
                  onClick={() => {
                    setText(p.text);
                    setAttach(p.attachment_doc_id);
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          )}
          <label htmlFor="reply" className="p-label">Your reply as Northmart</label>
          <textarea id="reply" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a denial, a question, or pick a quick reply above" rows={4} />
          <div className="p-row">
            <label className="p-check">
              <input type="checkbox" checked={attach === "amendment-1"} onChange={(e) => setAttach(e.target.checked ? "amendment-1" : null)} />
              Attach signed amendment
            </label>
            <button type="button" className="p-send" onClick={send} disabled={!text.trim() || sending}>{sending ? "Sending…" : "Send reply"}</button>
          </div>
          {error && <p className="p-error" role="alert">{error}</p>}
        </section>
      </main>
    </div>
  );
}
