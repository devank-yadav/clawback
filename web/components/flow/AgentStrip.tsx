"use client";

// The agents across the top of the run and its result: who is working, who is done, who is waiting, each with its
// one-line conclusion. Click one to see what it did, step by step, and what it concluded. Built only from the run's
// events: its own log lines (LogLine.actor) and its outputs (terms read, findings, math, decisions, dispute, posts).

import { useState, type ReactNode } from "react";
import { money } from "@/lib/format";
import type { RunState } from "@/lib/useRunEvents";
import type { WorkspaceView } from "@/lib/workspace";

type Agent = {
  key: string;
  name: string;
  kind: "AI" | "CODE" | "YOU";
  actors: string[];
  state: "idle" | "working" | "done" | "waiting";
  conclusion: string;
  outputs: ReactNode[];
};

function build(state: RunState, view: WorkspaceView, owner: string, distributor: string): Agent[] {
  const feed = state.feed;
  const lastActor = feed.at(-1)?.actor;
  const running = state.run?.status === "started";
  const said = (actors: string[]) => feed.filter((l) => actors.includes(l.actor));
  const lastLine = (actors: string[]) => said(actors).at(-1)?.text ?? null;
  const status = (actors: string[], done: boolean): Agent["state"] =>
    running && lastActor && actors.includes(lastActor) ? "working" : done ? "done" : "idle";
  const r = view.remittance;
  const findings = Object.values(state.findings);
  const decisions = Object.values(state.decisions);
  const rehearsals = Object.values(state.rehearsals);
  const d = state.dispute;
  const q = view.question;
  const a = view.approval;

  return [
    {
      key: "payment", name: "Payment reader", kind: "AI", actors: ["system"],
      state: status(["system"], !!r),
      conclusion: r ? `${r.counterparty} kept ${money(r.taken)} in ${r.charge_count} charges` : "Waiting for the payment",
      outputs: r ? [<>Paid {money(r.received)} of {money(r.expected)} on invoice {r.invoice_id}. Kept {money(r.taken)} in {r.charge_count} charges.</>] : [],
    },
    {
      key: "read", name: "Deal readers", kind: "AI", actors: ["reader"],
      state: status(["reader"], state.stages.read?.status === "done" || findings.length > 0),
      conclusion: state.stages.read?.label ?? (findings.length ? "Both readers agreed on the deal’s terms" : "Reading the signed deal"),
      outputs: state.stages.docs.map((doc, i) => (
        <span key={`${i}-${doc.label}`}><b>{doc.label}</b>{doc.items.slice(0, 6).map((it, k) => <q key={k}>{it}</q>)}</span>
      )),
    },
    {
      key: "investigate", name: "Investigator", kind: "AI", actors: ["investigator"],
      state: status(["investigator"], findings.length > 0 && view.reviewed),
      conclusion: findings.length ? `Explained ${findings.length} of ${view.charges.length} charges with evidence` : "Matching sales, emails and past payments",
      outputs: findings.map((f) => <span key={f.charge_id}><b>{f.charge_id}</b>{f.finding} <em>{Math.round(f.confidence * 100)}% sure</em></span>),
    },
    {
      key: "calc", name: "Calculator", kind: "CODE", actors: [],
      state: findings.some((f) => f.math.length) ? (view.reviewed ? "done" : running ? "working" : "done") : "idle",
      conclusion: findings.length ? "Every amount from tested code, none from AI" : "Waits for the facts",
      outputs: findings.filter((f) => f.math.length).map((f) => <span key={f.charge_id}><b>{f.charge_id}</b><code>{f.math.map((m) => m.text).join(" ")}</code></span>),
    },
    {
      key: "rules", name: "Rules", kind: "CODE", actors: ["gate", "policy"],
      state: status(["gate", "policy"], decisions.length > 0 && view.reviewed),
      conclusion: decisions.length
        ? `${decisions.filter((x) => x.decision === "dispute" || x.decision === "split").length} disputed · ${decisions.filter((x) => x.decision === "accept").length} fair · ${decisions.filter((x) => x.decision === "ask").length} for you`
        : "Decides under your policy",
      outputs: decisions.map((x) => <span key={x.charge_id}><b>{x.charge_id} · {x.decision}</b>{x.reason}</span>),
    },
    {
      key: "negotiate", name: "Negotiator", kind: "AI", actors: ["negotiator"],
      state: status(["negotiator"], !!d || rehearsals.length > 0),
      conclusion: d ? `${d.id} ${d.status === "draft" || d.status === "ready_to_send" ? "ready for you to send" : "sent"} · ${money(d.total)}` : rehearsals.length ? `Prepared ${rehearsals.length} comebacks` : `Argues with ${distributor}`,
      outputs: [
        ...rehearsals.map((x) => <span key={x.charge_id}><b>{x.charge_id}</b>Expects: “{x.predicted_rebuttal}” Answer: {x.answer}</span>),
        ...(d ? [<span key="d"><b>{d.id}</b>{d.lines.length} lines, {money(d.total)}, {d.status}</span>] : []),
        ...state.portal.map((m) => <span key={m.id}><b>{m.from_party === "clawback" ? "Clawback" : distributor}</b>{m.text}</span>),
      ],
    },
    {
      key: "you", name: owner, kind: "YOU", actors: ["owner"],
      state: view.stage === "owner" || a?.status === "pending" ? "waiting" : q?.answer || a?.status === "approved" ? "done" : "idle",
      conclusion: view.stage === "owner" && q ? "One question is waiting for you" : a?.status === "pending" ? `Approve ${money(a.amount)} before it posts` : q?.answer ? `Answered: “${q.answer}”` : "Asked only when the deal is unclear",
      outputs: Object.values(state.questions).map((x) => <span key={x.id}><b>{x.charge_id}</b>{x.text}{x.answer ? <em> · Answer: {x.answer}</em> : null}</span>),
    },
    {
      key: "books", name: "Bookkeeper", kind: "CODE", actors: ["bookkeeper"],
      state: status(["bookkeeper"], state.ledger.length > 0),
      conclusion: lastLine(["bookkeeper"]) ?? view.postingLabel,
      outputs: state.ledger.map((p) => <span key={p.id}><b>{p.qbo_entity}</b>{money(p.amount)} · {p.status}{p.note ? ` · ${p.note}` : ""}</span>),
    },
  ];
}

export function AgentStrip({ state, view, owner, distributor }: { state: RunState; view: WorkspaceView; owner: string; distributor: string }) {
  const [open, setOpen] = useState<string | null>(null);
  const agents = build(state, view, owner, distributor);
  const agent = agents.find((x) => x.key === open) ?? null;
  const lines = agent ? state.feed.filter((l) => agent.actors.includes(l.actor)) : [];
  return (
    <section className="as" aria-label="The agents">
      <div className="as-row">
        {agents.map((x) => (
          <button key={x.key} className={`as-agent is-${x.state} ${open === x.key ? "is-open" : ""}`} onClick={() => setOpen(open === x.key ? null : x.key)} aria-expanded={open === x.key}>
            <span className="as-top"><i aria-hidden="true" /><strong>{x.name}</strong><em>{x.kind}</em></span>
            <span className="as-concl">{x.conclusion}</span>
          </button>
        ))}
      </div>
      {agent && (
        <div className="as-detail" role="region" aria-label={`${agent.name}: what it did`}>
          <div className="as-detail-head">
            <strong>{agent.name}</strong>
            <span>{agent.conclusion}</span>
            <button className="cx-btn is-ghost" onClick={() => setOpen(null)}>Close</button>
          </div>
          <div className="as-cols">
            <div>
              <h4>What it concluded</h4>
              {agent.outputs.length ? <div className="as-outputs">{agent.outputs}</div> : <p className="cx-small cx-muted">Nothing yet.</p>}
            </div>
            <div>
              <h4>What it did</h4>
              {lines.length ? <ol className="as-log">{lines.map((l) => <li key={l.id} className={l.level}>{l.text}</li>)}</ol> : <p className="cx-small cx-muted">{agent.kind === "CODE" ? "Plain code: no AI calls, so no log of its own." : "No steps yet."}</p>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
