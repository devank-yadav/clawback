"use client";

// The card under the rail for the stage that needs the eye: the two readers at work, the owner's one question, the
// controller's approval, or the dispute and the distributor's replies. People act here, on the same page as the run.

import { useState } from "react";
import { money } from "@/lib/format";
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
            <li key={d.at} className="fl-doc">
              <span>{d.label}</span>
              {d.items.length > 0 && (
                <ul className="fl-quotes">
                  {d.items.slice(0, 4).map((q) => <li key={q}><q>{q}</q></li>)}
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

export function ControllerCard() {
  const { view, controllerDecides, cast } = useRun();
  const [note, setNote] = useState("");
  const a = view.approval;
  if (!a || a.status !== "pending") return null;
  return (
    <section className="fl-card is-amber" aria-label="Controller approval">
      <span className="cx-eyebrow">Waiting on {cast.controllerFull} · controller</span>
      <div className="cx-head" style={{ alignItems: "flex-end" }}>
        <h2>Approve the credit memo for the fair charges?</h2>
        <Money value={a.amount} className="cx-big" />
      </div>
      <div className="cx-rows">
        {view.proposalLines.map((l) => (
          <div key={l.chargeId}><span>{l.label}</span><Money value={l.amount} /></div>
        ))}
      </div>
      <p className="cx-small cx-muted">Nothing posts to QuickBooks until {cast.controller} says yes. The disputed money stays open with {cast.distributor}.</p>
      <label className="cx-tiny" htmlFor="fl-note">Note (needed only to hold it)</label>
      <textarea id="fl-note" className="cx-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you’re holding it, if you are" />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="cx-btn" onClick={() => controllerDecides(true, note || null)}>Approve {money(a.amount)}</button>
        <button className="cx-btn is-ghost" onClick={() => controllerDecides(false, note || "Held by controller")}>Hold</button>
      </div>
      <p className="cx-tiny">Only the controller can approve: you sign in with {cast.controller}’s code.</p>
    </section>
  );
}

export function DisputeCard() {
  const { state, account, cast, link } = useRun();
  const d = state.dispute;
  if (!d) return null;
  const thread = state.portal.filter((m) => m.dispute_id === d.id);
  return (
    <section className="fl-card" aria-label={`Dispute ${d.id}`}>
      <div className="cx-head" style={{ alignItems: "center" }}>
        <h2>Dispute {d.id} · {money(d.total)}</h2>
        <span className="cx-tiny">{d.lines.length} line{d.lines.length === 1 ? "" : "s"} · {d.status === "draft" ? `held for ${cast.owner}` : "filed with proof"}</span>
      </div>
      <p className="cx-small cx-muted">
        Each line carries the deal’s sentence, the data rows and the math. Reply as {cast.distributor} on their portal and the Negotiator answers here, or concedes if you show a signed change.
      </p>
      {thread.length > 0 && (
        <ul className="fl-thread" aria-live="polite">
          {thread.slice(-4).map((m) => (
            <li key={m.id} className={m.from_party === "clawback" ? "is-us" : ""}>
              <b>{m.from_party === "clawback" ? "Negotiator" : cast.distributor}</b>
              {m.text}
            </li>
          ))}
        </ul>
      )}
      <div>
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
  if (focus.key === "controller" && focus.state === "waiting") return <div className="fl-spot"><ControllerCard /></div>;
  if (focus.key === "file" && focus.state === "waiting") return <div className="fl-spot"><DisputeCard /></div>;
  return null;
}
