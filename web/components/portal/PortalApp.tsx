"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useSearchParams } from "next/navigation";
import { inkOn, useCurrentAccount, withAccount } from "@/lib/accounts";
import { anyDay, daysLeftLabel, dollars, URGENT_DAYS } from "@/lib/format";
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

/** "File by Apr 27 · 12 days left" under a line; urgent under two weeks. */
function FileByLine({ fileBy, daysLeft }: { fileBy?: string | null; daysLeft?: number | null }) {
  const hasDays = daysLeft !== null && daysLeft !== undefined;
  if (!fileBy && !hasDays) return null;
  const text = [fileBy ? `File by ${anyDay(fileBy)}` : null, hasDays ? daysLeftLabel(daysLeft) : null].filter(Boolean).join(" · ");
  return <p className={`p-fileby ${hasDays && daysLeft < URGENT_DAYS ? "urgent" : ""}`}>{text}</p>;
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

/** One line as the distributor edits it: the number it types (units for a promo line, the amount for a fee). */
type Edit = { id: string; value: string; rate: string };
const asEdits = (d: api.PaymentDraft): Edit[] =>
  d.lines.map((l) => ({ id: l.id, value: String(l.fee ? l.rate : l.units), rate: l.rate.toFixed(2) }));
const num = (v: string) => (v.trim() === "" ? NaN : Number(v.replace(/[$,\s]/g, "")));

/** The distributor pays its invoice from here, and can change the payment first: how many units each promo line
 * charges and at what rate, what each fee is, or leave a line out. Every amount and the total come from the API
 * (POST /portal/payments/{account}/preview); "Send payment" sends exactly what's on screen. The payment shows on the
 * supplier's side as received, and their agents check it. */
function PayCard({ account }: { account: Account }) {
  const [base, setBase] = useState<api.PaymentDraft | null>(null);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [shown, setShown] = useState<api.PaymentDraft | null>(null);
  const [sent, setSent] = useState<api.PendingPayment | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.fetchPaymentDraft(account.id)
      .then((d) => { if (live) { setBase(d); setEdits(asEdits(d)); setShown(d); } })
      .catch((e) => { if (live) setProblem(api.unreachable(e as Error)); });
    return () => { live = false; };
  }, [account.id]);

  const fee = useCallback((id: string) => !!base?.lines.find((l) => l.id === id)?.fee, [base]);
  const lines = useCallback((): api.PortalLine[] | null => {
    const out: api.PortalLine[] = [];
    for (const e of edits) {
      const v = num(e.value), r = num(e.rate);
      if (fee(e.id) ? !(v >= 0) : !(Number.isInteger(v) && v >= 0 && r >= 0)) return null;
      out.push(fee(e.id) ? { id: e.id, units: 1, rate: v } : { id: e.id, units: v, rate: r });
    }
    return out;
  }, [edits, fee]);

  // The summary follows the edits: the API prices each line and totals them a moment after typing stops.
  const timer = useRef<number | undefined>(undefined);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    if (!base) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const ls = lines();
      setInvalid(ls === null);
      if (ls) api.previewPayment(account.id, ls).then(setShown).catch((e) => setProblem(api.unreachable(e as Error)));
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [base, edits, lines, account.id]);

  const set = (id: string, patch: Partial<Edit>) => setEdits((es) => es.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  async function pay() {
    const ls = lines();
    if (!ls) return;
    setBusy(true);
    setProblem(null);
    try {
      setSent(await api.sendPortalPayment(account.id, shown?.edited ? ls : undefined));
    } catch (e) {
      setProblem(api.unreachable(e as Error));
    } finally {
      setBusy(false);
    }
  }

  const amountOf = (id: string) => shown?.lines.find((l) => l.id === id)?.amount;
  const total = shown ?? base;
  return (
    <section className="p-card" aria-labelledby="pay-h">
      <div className="p-head">
        <div>
          <small>Invoice from {account.brand.name}</small>
          <h2 id="pay-h">{account.invoice.id}</h2>
          <p>Invoiced {dollars(account.invoice.expected)}</p>
        </div>
        <div className="p-total"><small>You pay</small><strong>{total ? dollars(total.paid) : "–"}</strong></div>
      </div>

      {base && !sent && (
        <>
          <ul className="p-lines" aria-label="Deductions taken from this payment">
            {edits.map((e) => {
              const l = base.lines.find((x) => x.id === e.id)!;
              const amt = amountOf(e.id);
              return (
                <li key={e.id} className="p-line">
                  <div className="p-line-what"><strong>{l.description}</strong><small>{l.ref} · {l.fee ? "fee" : l.product}</small></div>
                  {l.fee ? (
                    <label className="p-line-edit">
                      <span className="p-sr">Amount for {l.description}</span>
                      <span aria-hidden="true">$</span>
                      <input inputMode="decimal" value={e.value} onChange={(ev) => set(e.id, { value: ev.target.value })} />
                    </label>
                  ) : (
                    <span className="p-line-edit">
                      <label><span className="p-sr">Units for {l.description}</span>
                        <input inputMode="numeric" value={e.value} onChange={(ev) => set(e.id, { value: ev.target.value })} /></label>
                      <span className="p-line-at">units at $</span>
                      <label><span className="p-sr">Rate per unit for {l.description}</span>
                        <input className="p-rate" inputMode="decimal" value={e.rate} onChange={(ev) => set(e.id, { rate: ev.target.value })} /></label>
                    </span>
                  )}
                  <strong className="p-amt p-line-amt">{amt != null ? dollars(amt) : "–"}</strong>
                  <button type="button" className="p-line-x" aria-label={`Don't take ${l.description}`} title="Don't take this one"
                    onClick={() => setEdits((es) => es.filter((x) => x.id !== e.id))}>×</button>
                </li>
              );
            })}
          </ul>
          {edits.length < base.lines.length && <p className="p-muted">{base.lines.length - edits.length} deduction{base.lines.length - edits.length === 1 ? "" : "s"} left out.</p>}
        </>
      )}

      <div className="p-row">
        <p className="p-muted" role="status">
          {sent
            ? `Sent ${when(sent.received_at)}: ${dollars(sent.received)} of ${dollars(sent.expected)}. ` + (sent.run_id
              ? `${account.brand.name}’s agents are checking it now.`
              : `${account.brand.name} sees it as received; their agents check it.`)
            : invalid ? "Enter a number on each line."
            : total ? `Paying ${dollars(total.paid)} of ${dollars(total.expected)} · ${dollars(total.taken)} taken in ${total.lines.length} deduction${total.lines.length === 1 ? "" : "s"}.`
            : "Loading the invoice…"}
        </p>
        {!sent && base && shown?.edited && (
          <button type="button" className="p-reset" onClick={() => { setEdits(asEdits(base)); setShown(base); }}>Start over</button>
        )}
        {sent?.run_id ? (
          // The agents started the moment it arrived (the owner's setting): their run on the payment page, in this tab.
          <a className="p-send p-watch" href={withAccount("/", account.id, { run: sent.run_id })}>
            Watch {account.brand.name}’s agents check it <span aria-hidden="true">→</span>
          </a>
        ) : (
          <button type="button" className="p-send" onClick={() => void pay()} disabled={busy || !!sent || !base || invalid}>{sent ? "Payment sent" : busy ? "Sending…" : "Send payment"}</button>
        )}
      </div>
      {sent && (
        <div className="p-row"><button type="button" className="p-reset" onClick={() => { setSent(null); if (base) { setEdits(asEdits(base)); setShown(base); } }}>Send another payment</button></div>
      )}
      {problem && <p className="p-error" role="alert">{problem}</p>}
    </section>
  );
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
        <PayCard account={account} />
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
                  <FileByLine fileBy={l.file_by} daysLeft={l.days_left} />
                </li>
              ))}
            </ul>
          )}
        </section>

        {disputeId && (
          <section className="p-card" aria-labelledby="thread-h">
            <div className="p-thread-head">
              <h2 id="thread-h">Messages</h2>
              <a className="p-packet" href={api.disputePacketUrl(disputeId)} target="_blank" rel="noreferrer" download={`${disputeId}.pdf`}>Download dispute packet</a>
            </div>
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
