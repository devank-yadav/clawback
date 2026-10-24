"use client";

import { useMemo } from "react";
import ToolFrame from "./ToolFrame";
import { dollars } from "@/lib/format";
import { fetchEval } from "@/lib/api";
import type { Account, EvalReport, LedgerPost } from "@/lib/types";
import { useRunEvents } from "@/lib/useRunEvents";
import { useFetched } from "@/lib/useFetched";
import { reachedQuickBooks } from "@/lib/workspace";

const ENTITY: Record<string, string> = { credit_memo: "Credit memo", invoice_note: "Open balance note", payment: "Payment", invoice: "Invoice", customer: "Customer", item: "Item" };

function postStatus(p: LedgerPost) {
  if (p.status === "posted") return reachedQuickBooks(p) ? "Posted to QuickBooks" : "Recorded · QuickBooks not connected";
  return { pending: "Waiting for approval", held: "Held", failed: "Failed", voided: "Voided" }[p.status];
}

function EvalCard({ report }: { report: EvalReport }) {
  if (report.status !== "done") return <p className="muted">{report.status === "running" ? "The 30-charge check is running." : "The 30-charge check hasn't been run on this server yet."}</p>;
  const stat = (label: string, value: number | null, of?: number) => (
    <div><span>{label}</span><strong>{value === null ? "—" : of ? `${value} of ${of}` : value}</strong></div>
  );
  return (
    <>
      <p className="muted">Planted charges, scored against an answer key written first · {report.mode === "agent" ? "with the AI readers and agents in the loop" : "math and decision rules alone"}</p>
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

function Results({ account }: { account: Account }) {
  const { state, error, awaitingPayment } = useRunEvents(account.id);
  const report = useFetched<EvalReport>(useMemo(() => fetchEval, []));
  const t = state.totals;
  const posts = state.ledger.filter((p) => p.qbo_entity === "credit_memo" || p.qbo_entity === "invoice_note");

  return (
    <>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {awaitingPayment && <p className="feedback" role="status">No analysis yet. It starts when {account.distributor.name} pays.</p>}
      {t && (
        <section className="surface tool-card" aria-label="Final totals">
          <div className="tool-stats big">
            <div><span>Disputing</span><strong>{dollars(t.disputed)}</strong><small>Being challenged · not recovered yet</small></div>
            <div><span>Accepted</span><strong>{dollars(t.accepted)}</strong><small>Fair under the deal or an owner rule</small></div>
            <div><span>Waiting on a person</span><strong>{dollars(t.waiting)}</strong></div>
            <div><span>Questions asked</span><strong>{t.questions}</strong></div>
          </div>
        </section>
      )}

      <section className="surface tool-card" aria-labelledby="qb-h">
        <h2 id="qb-h">QuickBooks</h2>
        {posts.length === 0 && <p className="muted">Nothing posted. The credit memo waits for {account.brand.owner.name}; nothing posts without a yes.</p>}
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
        {report.error && <p className="feedback error" role="alert">{report.error}</p>}
        {report.data && <EvalCard report={report.data} />}
      </section>

      {t && t.waiting === 0 && t.undecided === 0 && <p className="tool-closing">{dollars(t.disputed)} disputed, {dollars(t.accepted)} accepted, {t.questions === 0 ? "no questions" : t.questions === 1 ? "one question" : `${t.questions} questions`}.</p>}
    </>
  );
}

export default function ResultsApp() {
  return (
    <ToolFrame href="/results" title="Results" lead={(a) => `Where ${a.distributor.name}’s deductions stand, what went to QuickBooks, and how accurate the checks are.`}>
      {(account) => <Results account={account} />}
    </ToolFrame>
  );
}
