"use client";

// Your approval (Figma: "Clawback · Controller approval", now the admin's). The admin, the brand's owner, approves the
// accounting entry for the fair charges only; disputes are never posted from here. Every amount comes from the
// approval event.

import Link from "next/link";
import { useState } from "react";
import { AutoPostBox } from "@/components/flow/Spotlight";
import { money } from "@/lib/format";
import { useRun } from "./RunProvider";
import { Shell } from "./Shell";
import { Money, Pill } from "./ui";

export default function Approval() {
  const { view, decideApproval, cast: CAST, link } = useRun();
  const [note, setNote] = useState("");
  const [autoPost, setAutoPost] = useState(false);
  const a = view.approval;
  const r = view.remittance;
  const totals = view.totals;
  const pending = a?.status === "pending";

  return (
    <Shell crumbs={["Accounting", "Your approval", a?.id ?? "—"]} right={`${CAST.ownerFull} · admin`}>
      <div className="cx-head">
        <div>
          <h1 className="cx-h1">Your approval</h1>
          <p className="cx-meta">You approve the accounting entry for the fair charges. Disputed money stays open.</p>
        </div>
        <Pill tone={pending ? "accent" : a?.status === "approved" ? "green" : ""}>{a ? (pending ? "Awaiting your yes" : a.status === "approved" ? "Approved" : "Held") : "Not ready yet"}</Pill>
      </div>

      <div className="cx-banner">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
        <div>
          <strong style={{ fontWeight: 500, fontSize: 13 }}>Your approval required</strong>
          <p className="cx-small cx-muted">This confirms the accounting entry only. Disputes are decided elsewhere and are never posted from here.</p>
        </div>
      </div>

      {!a ? (
        <div className="cx-card cx-muted">
          Nothing to approve yet. Once {CAST.owner} has answered any open question, the Bookkeeper agent drafts the entry for the fair charges.{" "}
          <Link href={link("/review")}>Go to payment review →</Link>
        </div>
      ) : (
        <div className="cx-approval">
          <section className="cx-card" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="cx-head">
              <div>
                <h2 style={{ fontSize: 18, fontWeight: 400 }}>Proposed credit memo</h2>
                <p className="cx-tiny">{a.id} · drafted by the Bookkeeper agent · for {CAST.ownerFull}</p>
              </div>
              <Pill>Fair charges only</Pill>
            </div>
            <div>
              <p className="cx-small">{r?.counterparty}</p>
              <p className="cx-tiny">Invoice {r?.invoice_id} · the cash received is recorded separately</p>
            </div>
            <table className="cx-table">
              <thead><tr><th>Line</th><th>Debit</th><th>Credit</th></tr></thead>
              <tbody>
                {view.proposalLines.map((l) => (
                  <tr key={l.chargeId}><td>{l.label}</td><td><Money value={l.amount} /></td><td>—</td></tr>
                ))}
                <tr><td>Accounts receivable · {r?.counterparty}</td><td>—</td><td><Money value={a.amount} /></td></tr>
              </tbody>
              <tfoot><tr><td>Balanced entry</td><td><Money value={a.amount} /></td><td><Money value={a.amount} /></td></tr></tfoot>
            </table>
          </section>

          <aside className="cx-card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <h3 style={{ fontSize: 15, fontWeight: 400 }}>Your decision</h3>
            <span className="cx-tiny">Fair charges to approve</span>
            <Money value={a.amount} className="cx-big" />
            <p className="cx-small cx-muted">{CAST.ownerFull} · admin. Confirm the accounts and amounts.</p>
            {pending && (
              <>
                <label className="cx-tiny" htmlFor="note">Note (optional)</label>
                <textarea id="note" className="cx-note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you’re holding it, if you are" />
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button className="cx-btn" onClick={() => decideApproval(true, note || null, autoPost)}>Approve entry</button>
                  <button className="cx-btn is-ghost" onClick={() => decideApproval(false, note || `Held by ${CAST.owner}`)}>Hold entry</button>
                </div>
                <AutoPostBox checked={autoPost} onChange={setAutoPost} limit={a.amount} />
              </>
            )}
            {a.posted_by_auto_post && <p className="cx-small">Posted by your auto-post rule: fair-charge memos up to {money(a.posted_by_auto_post.limit)} post without asking (set when approving {a.posted_by_auto_post.approval_id}).</p>}
            {a.sets_auto_post && <p className="cx-small">From now on, fair-charge memos up to {money(a.sets_auto_post.limit)} post without asking.</p>}
            {!pending && a.note && <p className="cx-small">Note: {a.note}</p>}
            <hr style={{ border: 0, borderTop: "1px solid var(--line)", width: "100%" }} />
            <strong style={{ fontWeight: 500, fontSize: 13 }}>QuickBooks</strong>
            <p className="cx-small cx-muted">{view.postingLabel}</p>
            {view.postingProblem && <p className="cx-small" style={{ color: "var(--amber)" }}>{view.postingProblem}</p>}
            <p className="cx-tiny">Posts to QuickBooks only after approval. Only the admin can approve, signed in.</p>
          </aside>
        </div>
      )}

      {totals && (
        <section className="cx-card" style={{ maxWidth: 720 }}>
          <h3 style={{ fontSize: 14, fontWeight: 400, marginBottom: 6 }}>Money still open with {r?.counterparty ?? "the distributor"}</h3>
          <div className="cx-rows">
            <div><span>Proposed dispute</span><Money value={totals.disputed} /></div>
            <div><span>Waiting on owner policy</span><Money value={totals.waiting} /></div>
          </div>
          <p className="cx-tiny" style={{ marginTop: 8 }}>This stays open after approval. It is not written off and not counted as recovered.</p>
        </section>
      )}
    </Shell>
  );
}
