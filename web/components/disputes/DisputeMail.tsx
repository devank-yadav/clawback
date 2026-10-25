"use client";

// The dispute by email (api/routes/dispute_mail.py), in billow's insight-card look:
//  ReviewAndSend: the drafted email, editable, its attachments, any problems the outbound filter found (amber), and one
//    blue Send button; after sending, where it went and when (or that it was saved to the outbox in demo mode).
//  DisputeThread: every message on the dispute, from the portal and by email, with the Negotiator's drafted replies
//    and their Send buttons.
// Nothing here computes money or writes a figure: the API drafts and checks every word that goes out.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { withAccount } from "@/lib/accounts";
import { AlertTriangle, Check, Mail, Paperclip, Send } from "lucide-react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { DisputeEmail, PortalMessage } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";

const WRITER: Record<DisputeEmail["written_by"], string> = {
  claude: "Drafted by the email agent, checked by code",
  template: "Drafted from the dispute lines by code",
  admin: "Edited by you, checked by code",
  negotiator: "Drafted by the Negotiator, checked by code",
  code: "Written by code",
};

/** What happened to an email that left (or tried to). */
export function SentLine({ email }: { email: DisputeEmail }) {
  if (email.status === "sent") return <div className="dm-sent"><Check aria-hidden="true" /><span>Sent to {email.to} {email.sent_at ? `at ${when(email.sent_at)}` : ""}{email.detail && <small>{email.detail}</small>}</span></div>;
  // Kept in the app because no mail account is connected: say so plainly, and never claim it went out.
  if (email.status === "outbox") return <div className="dm-sent is-outbox"><Mail aria-hidden="true" /><span>Saved, not sent{email.sent_at ? ` · ${when(email.sent_at)}` : ""}<small>Connect Gmail to send it from your address. <Link href={withAccount("/connections", email.account_id)}>Open Connections</Link></small></span></div>;
  if (email.status === "failed") return <p className="dm-problems" role="alert"><AlertTriangle aria-hidden="true" /> Couldn’t send{email.detail ? `: ${email.detail}` : ""}. Send again to retry.</p>;
  return null;
}

const failure = (e: unknown) =>
  e instanceof ApiError && e.status === 409 ? (e.detail || "This email can’t go out as it is.") : e instanceof ApiError && e.status === 401 ? null : `That didn’t go through (${(e as Error).message}).`;

/** Drafts this page has already typed in, so a draft types in once and later renders whole. */
const typedIn = new Set<string>();

/** The finished draft typed into the box over about 1.5 s the first time it appears (the API doesn't stream it).
 * Returns the text so far while typing, then null. Off with reduced motion. */
function useTypeIn(id: string, text: string): string | null {
  const [shown, setShown] = useState<number | null>(null);
  useEffect(() => {
    if (typedIn.has(id)) return;
    typedIn.add(id);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !text) return;
    const start = performance.now();
    let frame = 0;
    let done = false;
    const step = (now: number) => {
      const n = Math.min(text.length, Math.round((text.length * (now - start)) / 1500));
      setShown(n >= text.length ? null : n);
      if (n < text.length) frame = requestAnimationFrame(step);
      else done = true;
    };
    frame = requestAnimationFrame(step);
    // Unmounted before it finished (or a dev double mount): it types in again next time.
    return () => { cancelAnimationFrame(frame); if (!done) typedIn.delete(id); setShown(null); };
  }, [id, text]);
  return shown === null ? null : text.slice(0, shown);
}

/** The editor shared by the dispute email and a reply draft: subject, body, attachments, problems, Send. */
function EmailEditor({ email, sendLabel, onSend, onSave, busy, problem }: {
  email: DisputeEmail;
  sendLabel: string;
  onSend: (subject: string, body: string) => void;
  onSave?: (subject: string, body: string) => void;
  busy: boolean;
  problem: string | null;
}) {
  const [subject, setSubject] = useState(email.subject);
  const [body, setBody] = useState(email.body);
  const edited = subject !== email.subject || body !== email.body;
  const typing = useTypeIn(email.id, email.body);
  const id = email.id.replace(/[^a-zA-Z0-9-]/g, "-");
  return (
    <form className="dm-editor" onSubmit={(e) => { e.preventDefault(); onSend(subject, body); }}>
      <dl className="dm-meta">
        <div><dt>From</dt><dd>{email.from_addr}</dd></div>
        <div><dt>To</dt><dd>{email.to}</dd></div>
        {email.reply_to && <div><dt>Replies go to</dt><dd>{email.reply_to}</dd></div>}
      </dl>
      <label htmlFor={`dm-subject-${id}`}>Subject</label>
      <input id={`dm-subject-${id}`} value={subject} onChange={(e) => setSubject(e.target.value)} />
      <label htmlFor={`dm-body-${id}`}>Message</label>
      <textarea id={`dm-body-${id}`} value={typing ?? body} readOnly={typing !== null} aria-busy={typing !== null} onChange={(e) => setBody(e.target.value)} rows={Math.min(10, Math.max(6, body.split("\n").length + 1))} />
      {email.attachments.length > 0 && (
        <ul className="dm-attachments" aria-label="Attachments">
          {email.attachments.map((a) => <li key={a}><Paperclip aria-hidden="true" />{a}</li>)}
        </ul>
      )}
      {(problem || email.problems.length > 0) && (
        <div className="dm-problems" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>{email.status === "held" ? "Held: fix this before it can go out" : "Can’t send yet"}</strong>
            <ul>{problem && <li>{problem}</li>}{email.problems.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>
        </div>
      )}
      <div className="dm-actions">
        <button className="cx-btn is-blue" type="submit" disabled={busy || typing !== null || !body.trim()}><Send aria-hidden="true" />{busy ? "Sending…" : sendLabel}</button>
        {onSave && edited && <button className="cx-btn is-ghost" type="button" disabled={busy} onClick={() => onSave(subject, body)}>Save edit</button>}
        <span className="dm-writer">{WRITER[email.written_by]}</span>
      </div>
    </form>
  );
}

/** "Review and send": the dispute's email, drafted on the first look. `onSent` runs once it was sent or outboxed. */
export function ReviewAndSend({ disputeId, runId, onSent }: { disputeId: string; runId: string | null; onSent?: () => void }) {
  const load = useCallback(() => api.fetchDisputeEmail(disputeId, runId), [disputeId, runId]);
  const fetched = useFetched(load);
  const [email, setEmail] = useState<DisputeEmail | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const shown = email ?? fetched.data;

  async function act(run: () => Promise<DisputeEmail>, sent: boolean) {
    setBusy(true);
    setProblem(null);
    try {
      const next = await run();
      setEmail(next);
      if (sent && (next.status === "sent" || next.status === "outbox")) onSent?.();
    } catch (e) {
      setProblem(failure(e));
      try { setEmail(await api.fetchDisputeEmail(disputeId, runId)); } catch { /* keep what's shown */ }
    } finally {
      setBusy(false);
    }
  }

  if (!shown) {
    return fetched.error
      ? <p className="dm-problems" role="alert"><AlertTriangle aria-hidden="true" /> {fetched.error}</p>
      : <p className="dm-loading" role="status">Drafting the email from the dispute lines…</p>;
  }
  if (shown.status === "sent" || shown.status === "outbox") return <SentLine email={shown} />;
  return (
    <>
      {shown.status === "failed" && <SentLine email={shown} />}
      <EmailEditor key={`${shown.id}-${shown.subject}-${shown.body.length}`} email={shown} busy={busy} problem={problem}
        sendLabel={`Send to ${shown.to}`}
        onSend={(s, b) => void act(async () => (await api.sendDispute(disputeId, runId, s, b)).email, true)}
        onSave={(s, b) => void act(() => api.saveDisputeEmail(disputeId, runId, s, b), false)} />
    </>
  );
}

/** Every message on a dispute (portal and email), and the Negotiator's drafted replies with their Send buttons.
 * `refreshKey` reloads it (a new portal message on the run). */
export function DisputeThread({ disputeId, runId, distributor, refreshKey = "", limit }: {
  disputeId: string; runId: string | null; distributor: string; refreshKey?: string; limit?: number;
}) {
  const load = useCallback(() => api.fetchDisputeThread(disputeId, runId), [disputeId, runId]);
  const thread = useFetched(load, refreshKey);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<{ id: string; text: string | null } | null>(null);
  const { reload } = thread;

  // A thread changes when the distributor replies by email too, which no run event announces: look again now and then.
  useEffect(() => {
    const t = window.setInterval(reload, 15_000);
    return () => window.clearInterval(t);
  }, [reload]);

  if (!thread.data) {
    return thread.error ? <p className="dm-problems" role="alert"><AlertTriangle aria-hidden="true" /> {thread.error}</p> : <p className="dm-loading" role="status">Loading the thread…</p>;
  }
  const { messages, emails } = thread.data;
  const drafts = emails.filter((e) => e.kind === "reply" && (e.status === "ready" || e.status === "held" || e.status === "failed"));
  const dispute = emails.find((e) => e.kind === "dispute" && (e.status === "sent" || e.status === "outbox"));
  const shown = limit ? messages.slice(-limit) : messages;

  async function sendReply(email: DisputeEmail, subject: string, body: string) {
    setBusy(email.id);
    setProblem(null);
    try {
      await api.sendDisputeReply(disputeId, email.id, runId, subject, body);
      reload();
    } catch (e) {
      setProblem({ id: email.id, text: failure(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="dm-thread">
      {dispute && <SentLine email={dispute} />}
      {shown.length === 0 && drafts.length === 0 ? (
        <p className="dm-empty">No replies yet. {distributor}’s answer will show here, from their portal or by email.</p>
      ) : (
        <ol className="dm-messages" aria-live="polite">
          {limit && messages.length > limit && <li className="dm-more">{messages.length - limit} earlier message{messages.length - limit === 1 ? "" : "s"}</li>}
          {shown.map((m: PortalMessage) => (
            <li key={m.id} className={m.from_party === "clawback" ? "is-us" : ""}>
              <div className="dm-who">
                <b>{m.from_party === "clawback" ? "Negotiator" : distributor}</b>
                <span className="dm-chip">{m.channel === "email" ? "Email" : "Portal"}</span>
                <time dateTime={m.created_at}>{when(m.created_at)}</time>
              </div>
              <p>{m.text}</p>
            </li>
          ))}
        </ol>
      )}
      {drafts.map((d) => (
        <section key={d.id} className="dm-draft" aria-label="The Negotiator's reply, waiting for you">
          <h4 className="dm-draft-h">The Negotiator’s reply, ready for you to send</h4>
          <EmailEditor email={d} busy={busy === d.id} problem={problem?.id === d.id ? problem.text : null} sendLabel="Send reply" onSend={(s, b) => void sendReply(d, s, b)} />
        </section>
      ))}
    </div>
  );
}
