"use client";

import { useMemo } from "react";
import { MARCH_EVENTS } from "@/lib/fixture";
import { dollars } from "@/lib/format";
import { fetchEval } from "@/lib/live";
import type { EvalReport, LedgerPost } from "@/lib/types";
import { DATA_SOURCE, useRunEvents } from "@/lib/useRunEvents";
import { useFetched } from "@/lib/useFetched";

const ENTITY: Record<string, string> = { credit_memo: "Credit memo", invoice_note: "Open balance note", payment: "Payment", invoice: "Invoice", customer: "Customer", item: "Item" };

function postStatus(p: LedgerPost) {
  if (p.status === "posted") return p.qbo_id?.startsWith("sim-") || /simulated/i.test(p.note ?? "") ? "Simulated posted" : "Posted to QuickBooks sandbox";
  return { pending: "Waiting for approval", held: "Held", failed: "Failed", voided: "Voided" }[p.status];
}

function EvalCard({ report }: { report: EvalReport }) {
  if (report.status !== "done") return <p className="muted">{report.status === "running" ? "The 30-charge check is running." : "The 30-charge check hasn't been run yet (make eval)."}</p>;
  const stat = (label: string, value: number | null, of?: number) => (
    <div><span>{label}</span><strong>{value === null ? "—" : of ? `${value} of ${of}` : value}</strong></div>
  );
  return (
    <>
      <p className="muted">Planted charges, scored against an answer key written first · {report.mode === "agent" ? "agent mode (readers and agents in the loop)" : "engine mode (math and decision rules alone)"}</p>
      <div className="tool-stats">
        {stat("Correct decisions", report.correct, report.cases)}
        {stat("Correct amounts", report.amounts_correct, report.cases)}
        {stat("Asked a person", report.asked)}
        {stat("Wrong automatic actions", report.wrong_automatic)}
        {stat("Unnecessary questions", report.unnecessary_questions)}
      </div>
    </>
  );
}

export default function ResultsApp() {
  const { state } = useRunEvents("latest", DATA_SOURCE, MARCH_EVENTS);
  const evalLoad = useMemo(() => (DATA_SOURCE === "live" ? fetchEval : null), []);
  const report = useFetched<EvalReport>(evalLoad);
  const t = state.totals;
  const posts = state.ledger.filter((p) => p.qbo_entity === "credit_memo" || p.qbo_entity === "invoice_note");

  return (
    <>
      {!t && <p className="feedback" role="status">{DATA_SOURCE === "live" ? "No run yet. Press “Northmart pays” on the workspace first." : "Loading the recorded run…"}</p>}
      {t && (
        <section className="surface tool-card" aria-label="Final totals">
          <div className="tool-stats big">
            <div><span>Disputed</span><strong>{dollars(t.disputed)}</strong><small>Being challenged · not recovered yet</small></div>
            <div><span>Accepted</span><strong>{dollars(t.accepted)}</strong><small>Fair under the deal or an owner rule</small></div>
            <div><span>Waiting on a person</span><strong>{dollars(t.waiting)}</strong></div>
            <div><span>Questions asked</span><strong>{t.questions}</strong></div>
          </div>
        </section>
      )}

      <section className="surface tool-card" aria-labelledby="qb-h">
        <h2 id="qb-h">QuickBooks</h2>
        {posts.length === 0 && <p className="muted">Nothing has been posted. A credit memo waits for the controller; nothing posts without a yes.</p>}
        {posts.map((p) => (
          <div className="tool-row" key={p.id}>
            <div>
              <strong>{ENTITY[p.qbo_entity] ?? p.qbo_entity}</strong> · {dollars(p.amount)}
              {p.lines.length > 0 && <small>{p.lines.length} {p.lines.length === 1 ? "line" : "lines"}</small>}
              {p.note && <small>{p.note}</small>}
            </div>
            <div className="tool-right">
              <span className={`status ${p.status === "posted" ? "accepted" : p.status === "failed" || p.status === "voided" ? "disputed" : "pending"}`}><i />{postStatus(p)}</span>
              {p.qbo_url && <a href={p.qbo_url} target="_blank" rel="noreferrer">Open in QuickBooks</a>}
            </div>
          </div>
        ))}
      </section>

      <section className="surface tool-card" aria-labelledby="eval-h">
        <h2 id="eval-h">Accuracy check</h2>
        {DATA_SOURCE !== "live" && <p className="muted">The score comes from the API; it isn&apos;t part of the recorded fixtures.</p>}
        {report.error && <p className="feedback error" role="alert">{report.error}</p>}
        {report.data && <EvalCard report={report.data} />}
      </section>

      {t && t.waiting === 0 && <p className="tool-closing">{dollars(t.disputed)} disputed, {dollars(t.accepted)} accepted, {t.questions === 1 ? "one question" : `${t.questions} questions`}.</p>}
    </>
  );
}
