"use client";

// The card under the rail for the stage that needs the eye: the two readers at work, the admin's one question, the
// admin's approval of the credit memo, or the dispute and the distributor's replies. People act here, on the same page as the run.

import Link from "next/link";
import { useState } from "react";
import { money } from "@/lib/format";
import { DisputeThread, ReviewAndSend } from "@/components/disputes/DisputeMail";
import { OwnerDecision } from "@/components/console/Review";
import { useRun } from "@/components/console/RunProvider";
import { Money } from "@/components/console/ui";
import type { Stage } from "./stages";

export function ReaderCard({ live }: { live: boolean }) {
  const { state } = useRun();
  const read = state.stages.read;
  const docs = state.stages.docs;
  return (
    <section className="fl-card" aria-label="The deal readers">
      <div className="cx-head" style={{ alignItems: "center" }}>
        <h2>Two readers, one deal. Every term must match word for word.</h2>
        {read && <span className="cx-tiny">{read.done} of {read.total} documents</span>}
      </div>
      <div className="fl-readers">
        <span className={`fl-reader ${live ? "is-live" : ""}`}><b>C</b>Claude</span>
        <span className={`fl-reader ${live ? "is-live" : ""}`}><b>G</b>Gemini</span>
        <span className="fl-reader"><b>✓</b>Quote check (code)</span>
      </div>
      {live && read && <p className="cx-small cx-muted">{read.label}…</p>}
      {docs.length > 0 && (
        <ul className="fl-docs">
          {docs.map((d) => (
            <li key={`${d.at}-${d.label}`} className="fl-doc">
              <span>{d.label}</span>
              {d.items.length > 0 && (
                <ul className="fl-quotes">
                  {d.items.slice(0, 4).map((q, i) => <li key={`${i}-${q}`}><q>{q}</q></li>)}
                  {d.items.length > 4 && <li>+{d.items.length - 4} more, each found word for word</li>}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ApprovalCard() {
  const { view, decideApproval, cast } = useRun();
  const [note, setNote] = useState("");
  const [autoPost, setAutoPost] = useState(false);
  const a = view.approval;
  if (!a || a.status !== "pending") return null;
  return (
    <section className="fl-card is-amber" aria-label="Your approval">
      <span className="cx-eyebrow">Waiting on you · {cast.ownerFull}</span>
      <div className="cx-head" style={{ alignItems: "flex-end" }}>
        <h2>Approve the credit memo for the fair charges?</h2>
        <Money value={a.amount} className="cx-big" />
      </div>
      <div className="cx-rows">
        {view.proposalLines.map((l) => (
          <div key={l.chargeId}><span>{l.label}</span><Money value={l.amount} /></div>
        ))}
      </div>
      <p className="cx-small cx-muted">Nothing posts to QuickBooks until you say yes. The disputed money stays open with {cast.distributor}.</p>
      <label className="cx-tiny" htmlFor="fl-note">Note (needed only to hold it)</label>
      <textarea id="fl-note" className="cx-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you’re holding it, if you are" />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="cx-btn" onClick={() => decideApproval(true, note || null, autoPost)}>Approve {money(a.amount)}</button>
        <button className="cx-btn is-ghost" onClick={() => decideApproval(false, note || `Held by ${cast.owner}`)}>Hold</button>
      </div>
      <AutoPostBox checked={autoPost} onChange={setAutoPost} limit={a.amount} />
      <p className="cx-tiny">Only the admin can approve, signed in.</p>
    </section>
  );
}

/** "Post fair charges like these automatically from now on": with a yes, memos up to this amount post without asking. */
export function AutoPostBox({ checked, onChange, limit }: { checked: boolean; onChange: (on: boolean) => void; limit: number }) {
  return (
    <label className="cx-check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>Post fair charges like these automatically from now on <small className="cx-tiny">(memos up to {money(limit)} post without asking)</small></span>
    </label>
  );
}

export function DisputeCard() {
  const { state, account, cast, link } = useRun();
  const d = state.dispute;
  if (!d) return null;
  const runId = state.run?.run_id ?? null;
  const unsent = d.status === "ready_to_send" || d.status === "draft";
  const replies = state.portal.filter((m) => m.dispute_id === d.id).length;
  return (
    <section className={`fl-card dm-card ${unsent ? "is-review" : ""}`} aria-label={`Dispute ${d.id}`}>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <h2>{unsent ? "Review and send" : "Dispute sent"} · {d.id} · {money(d.total)}</h2>
        <span className="cx-tiny">{d.lines.length} line{d.lines.length === 1 ? "" : "s"}, each with the deal’s sentence, the data and the math</span>
      </div>
      {unsent ? (
        <>
          <p className="cx-small cx-muted">Nothing goes to {cast.distributor} until you send it. Edit anything; code checks every figure and quote again before it leaves.</p>
          <ReviewAndSend disputeId={d.id} runId={runId} />
        </>
      ) : (
        <DisputeThread disputeId={d.id} runId={runId} distributor={cast.distributor} refreshKey={`${d.status}:${replies}`} limit={4} />
      )}
      <div className="dm-links">
        <Link className="cx-btn is-ghost" href={link("/disputes", { id: d.id, ...(runId ? { run: runId } : {}) })}>Open the thread</Link>
        <a className="cx-btn is-ghost" href={link("/portal")} target="_blank" rel="noreferrer">Open {account?.distributor.portal_name ?? `${cast.distributor}’s portal`} ↗</a>
      </div>
    </section>
  );
}

/** The card for the focused stage; the matrix speaks for the charges themselves. */
export function Spotlight({ focus }: { focus: Stage | null }) {
  const { view } = useRun();
  if (!focus) return null;
  if (focus.key === "read") return <div className="fl-spot"><ReaderCard live={focus.state === "active"} /></div>;
  if (focus.key === "owner" && focus.state === "waiting" && view.question) {
    const charge = view.charges.find((c) => c.id === view.question?.charge_id);
    return charge ? <div className="fl-spot"><OwnerDecision charge={charge} key={charge.id} /></div> : null;
  }
  if (focus.key === "approval" && focus.state === "waiting") return <div className="fl-spot"><ApprovalCard /></div>;
  if (focus.key === "file" && focus.state === "waiting") return <div className="fl-spot"><DisputeCard /></div>;
  return null;
}
