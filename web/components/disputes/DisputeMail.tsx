"use client";

// The dispute by email (api/routes/dispute_mail.py), in billow's insight-card look:
//  ReviewAndSend: the drafted email, editable, its attachments, any problems the outbound filter found (amber), and one
//    blue Send button; after sending, where it went and when (or that it was saved to the outbox in demo mode).
//  DisputeThread: every message on the dispute, from the portal and by email, with the Negotiator's drafted replies
//    and their Send buttons.
// Nothing here computes money or writes a figure: the API drafts and checks every word that goes out.

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Mail, Paperclip, Send } from "lucide-react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { DisputeEmail, PortalMessage } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { motion } from "framer-motion";
import { SlideOver } from "@/components/ui/SlideOver";

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";

const WRITER: Record<DisputeEmail["written_by"], string> = {
  claude: "Drafted by the email agent, checked by code",
  template: "Drafted from the dispute lines by code",
  admin: "Edited by you, checked by code",
  negotiator: "Drafted by the Negotiator, checked by code",
  code: "Written by code",
};

/** Where a dispute went, in the same words everywhere: sent by email, or filed on the distributor's portal with the
 * email copy kept here (no mailbox connected yet), or why it couldn't go and a way to try again. */
export function sentWords(email: Pick<DisputeEmail, "status" | "to" | "sent_at">, distributor?: string): string | null {
  if (email.status === "sent") return `Sent to ${email.to}${email.sent_at ? ` at ${when(email.sent_at)}` : ""}`;
  if (email.status === "outbox") return `Filed on ${distributor ? `${distributor}’s` : "the distributor’s"} portal · email copy saved (no mailbox connected yet)`;
  return null;
}

/** What happened to an email that left (or tried to). */
export function SentLine({ email, distributor, onRetry }: { email: DisputeEmail; distributor?: string; onRetry?: () => void }) {
  if (email.status === "sent") return <div className="dm-sent"><Check aria-hidden="true" /><span>{sentWords(email, distributor)}{email.detail && <small>{email.detail}</small>}</span></div>;
  // Filed on the portal; the email copy is kept here because no mailbox is connected. Never claim it was emailed.
  if (email.status === "outbox") return <div className="dm-sent is-outbox"><Check aria-hidden="true" /><span>{sentWords(email, distributor)}{email.sent_at ? <small>{when(email.sent_at)}</small> : null}</span></div>;
  if (email.status === "failed") {
    return (
      <div className="dm-problems" role="alert">
        <AlertTriangle aria-hidden="true" />
        <div><strong>Couldn’t send{email.detail ? `: ${email.detail}` : ""}</strong>{onRetry && <button className="cx-btn is-ghost" onClick={onRetry}>Try again</button>}</div>
      </div>
    );
  }
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

/** The outbound check's findings (api/engine/outbound_filter.py: "- amount: '$999' (…)") in plain words. Anything
 * it doesn't recognise is shown as it came. */
function plainProblems(problem: string): string[] {
  const found = [...problem.matchAll(/- (\w+): (['"])(.*?)\2 \(/g)].map(([, kind, , text]) =>
    kind === "amount" ? `${text} isn’t a figure from this dispute or the contract. Use the dispute’s own numbers.`
      : kind === "quote" ? `“${text}” isn’t a sentence from the contract or the findings.`
        : `“${text}” reads like a ${kind}. Take it out: nothing is offered that your settings didn’t set.`);
  return found.length ? found : [problem];
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
            <ul>{problem && <li>{problem}</li>}{email.problems.flatMap(plainProblems).map((p) => <li key={p}>{p}</li>)}</ul>
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
export function ReviewAndSend({ disputeId, runId, distributor, onSent, startOpen = false }: { disputeId: string; runId: string | null; distributor?: string; onSent?: () => void; startOpen?: boolean }) {
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

  const [open, setOpen] = useState(startOpen);
  const [editing, setEditing] = useState(false);
  const close = useCallback(() => { setOpen(false); setEditing(false); }, []);

  if (!shown) {
    return fetched.error
      ? <p className="dm-problems" role="alert"><AlertTriangle aria-hidden="true" /> {fetched.error}</p>
      : <p className="dm-loading" role="status">Drafting the email from the dispute lines…</p>;
  }
  const done = shown.status === "sent" || shown.status === "outbox";
  const retry = () => void act(async () => (await api.sendDispute(disputeId, runId, shown.subject, shown.body)).email, true);
  if (done && !open) return <SentLine email={shown} distributor={distributor} />;
  return (
    <>
      {shown.status === "failed" && <SentLine email={shown} distributor={distributor} onRetry={busy ? undefined : retry} />}
      {!done && (
        <div className="cm-ready">
          <span className="cm-ready-text"><Mail aria-hidden="true" /><span><strong>{shown.subject}</strong><small>To {shown.to} · {shown.attachments.length} attachment{shown.attachments.length === 1 ? "" : "s"}{shown.problems.length ? " · needs a fix before it can go" : ""}</small></span></span>
          <button className="cm-send is-glow" onClick={() => setOpen(true)}><Send aria-hidden="true" />Review and send</button>
        </div>
      )}
      <SlideOver open={open} onClose={close} title={done ? (shown.status === "sent" ? "Sent" : "Dispute filed") : "Review and send"} wide>
        {done ? (
          <motion.div className="cm-done" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 22 }}>
            <motion.span className="cm-check" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 420, damping: 16, delay: 0.05 }}><Check aria-hidden="true" /></motion.span>
            <h3>{shown.status === "sent" ? `Sent to ${shown.to}` : `Dispute filed · ${shown.dispute_id}`}</h3>
            <SentLine email={shown} distributor={distributor} />
            <button className="cx-btn is-ghost" onClick={close}>Done</button>
          </motion.div>
        ) : editing ? (
          <EmailEditor key={`${shown.id}-${shown.subject}-${shown.body.length}`} email={shown} busy={busy} problem={problem}
            sendLabel={`Send to ${shown.to}`}
            onSend={(s, b) => void act(async () => (await api.sendDispute(disputeId, runId, s, b)).email, true)}
            onSave={(s, b) => void act(async () => { const next = await api.saveDisputeEmail(disputeId, runId, s, b); setEditing(false); return next; }, false)} />
        ) : (
          <Letter email={shown} problem={problem} busy={busy}
            onEdit={() => setEditing(true)}
            onSend={() => void act(async () => (await api.sendDispute(disputeId, runId, shown.subject, shown.body)).email, true)} />
        )}
      </SlideOver>
    </>
  );
}

/** The email as a letter: letterhead, subject, the body typing in the first time, the attachments, one blue Send. */
function Letter({ email, problem, busy, onEdit, onSend }: { email: DisputeEmail; problem: string | null; busy: boolean; onEdit: () => void; onSend: () => void }) {
  const typing = useTypeIn(email.id, email.body);
  return (
    <div className="cm-letter-wrap">
      <article className="cm-letter" aria-label="The email">
        <header className="cm-head">
          <dl>
            <div><dt>From</dt><dd>{email.from_addr}</dd></div>
            <div><dt>To</dt><dd>{email.to}</dd></div>
            {email.reply_to && <div><dt>Replies to</dt><dd>{email.reply_to}</dd></div>}
          </dl>
          <h3>{email.subject}</h3>
        </header>
        <div className="cm-body" aria-busy={typing !== null}>{typing ?? email.body}{typing !== null && <span className="cm-caret" aria-hidden="true" />}</div>
        {email.attachments.length > 0 && (
          <ul className="dm-attachments" aria-label="Attachments">{email.attachments.map((a) => <li key={a}><Paperclip aria-hidden="true" />{a}</li>)}</ul>
        )}
      </article>
      {(problem || email.problems.length > 0) && (
        <div className="dm-problems" role="alert"><AlertTriangle aria-hidden="true" /><div><strong>Fix this before it can go out</strong><ul>{problem && <li>{problem}</li>}{email.problems.flatMap(plainProblems).map((p) => <li key={p}>{p}</li>)}</ul></div></div>
      )}
      <div className="cm-actions">
        <span className="dm-writer">{WRITER[email.written_by]}</span>
        <button className="cx-btn is-ghost" onClick={onEdit} disabled={busy}>Edit</button>
        <button className="cm-send is-glow" onClick={onSend} disabled={busy || typing !== null}><Send aria-hidden="true" />{busy ? "Sending…" : `Send to ${email.to}`}</button>
      </div>
    </div>
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
  // The distributor had the last word and nothing is drafted: the admin answers in their own words.
  const theirTurn = messages.length > 0 && messages[messages.length - 1].from_party !== "clawback" && drafts.length === 0;
  // Messages the admin wrote (matched to their email) say "You", the rest are the Negotiator's.
  const mine = new Set(emails.filter((e) => e.written_by === "admin" && e.message_id).map((e) => e.message_id));

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
      {dispute && <SentLine email={dispute} distributor={distributor} />}
      {shown.length === 0 && drafts.length === 0 ? (
        <p className="dm-empty">No replies yet. {distributor}’s answer will show here, from their portal or by email.</p>
      ) : (
        <ol className="dm-messages" aria-live="polite">
          {limit && messages.length > limit && <li className="dm-more">{messages.length - limit} earlier message{messages.length - limit === 1 ? "" : "s"}</li>}
          {shown.map((m: PortalMessage) => (
            <li key={m.id} className={m.from_party === "clawback" ? "is-us" : ""}>
              <div className="dm-who">
                <b>{m.from_party === "clawback" ? (m.email_message_id && mine.has(m.email_message_id) ? "You" : "Negotiator") : distributor}</b>
                <span className="dm-chip">{m.channel === "email" ? "Email" : "Portal"}</span>
                <time dateTime={m.created_at}>{when(m.created_at)}</time>
              </div>
              <p>{m.text}</p>
            </li>
          ))}
        </ol>
      )}
      {theirTurn && <AnswerThem disputeId={disputeId} runId={runId} distributor={distributor} onDone={reload} />}
      {drafts.map((d) => (
        <section key={d.id} className="dm-draft" aria-label={d.written_by === "admin" ? "Your answer, waiting for a fix" : "The Negotiator's reply, waiting for you"}>
          <h4 className="dm-draft-h">{d.status === "failed" ? "This answer didn’t go out: send it again" : d.written_by === "admin" ? "Your answer, held: fix it, then send" : "The Negotiator’s reply, ready for you to send"}</h4>
          <EmailEditor email={d} busy={busy === d.id} problem={problem?.id === d.id ? problem.text : null} sendLabel="Send reply" onSend={(s, b) => void sendReply(d, s, b)} />
        </section>
      ))}
    </div>
  );
}

/** The admin's own answer to the distributor's last message. It goes through the same outbound check as the
 * Negotiator's: a figure the dispute doesn't back, or a promise, holds it for a fix instead of sending. */
function AnswerThem({ disputeId, runId, distributor, onDone }: { disputeId: string; runId: string | null; distributor: string; onDone: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  async function send() {
    setBusy(true);
    setProblem(null);
    try {
      await api.writeDisputeReply(disputeId, runId, text.trim());
      setText("");
      onDone();
    } catch (e) {
      setProblem(failure(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="dm-draft dm-answer" aria-label={`Answer ${distributor}`} onSubmit={(e) => { e.preventDefault(); if (text.trim()) void send(); }}>
      <h4 className="dm-draft-h">Your turn: answer {distributor}</h4>
      <p className="dm-answer-hint">It goes on the same email thread. Dollar amounts and quotes are checked against the dispute first, and nothing can be promised; other numbers, like unit counts, aren’t checked, so copy them from the dispute itself.</p>
      <textarea aria-label="Your answer" rows={4} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="For example: The signed contract doesn’t allow this charge. If it was changed, please send the signed change." />
      {problem && <div className="dm-problems" role="alert"><AlertTriangle aria-hidden="true" /><div><strong>Couldn’t send</strong><ul><li>{problem}</li></ul></div></div>}
      <div className="dm-actions">
        <button className="cx-btn is-blue" type="submit" disabled={busy || !text.trim()}><Send aria-hidden="true" />{busy ? "Sending…" : `Send to ${distributor}`}</button>
      </div>
    </form>
  );
}
