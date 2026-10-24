"use client";

import { useMemo, useState } from "react";
import { dollars } from "@/lib/format";
import * as api from "@/lib/live";
import type { ScenarioExample, ScenarioResponse } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";
import { DATA_SOURCE } from "@/lib/useRunEvents";

const VERDICT: Record<string, string> = { dispute: "Dispute", accept: "Accept", split: "Split", ask: "Ask a person", skip: "Can't verify the deal" };

function Result({ r }: { r: ScenarioResponse }) {
  const d = r.decision;
  return (
    <section className="surface tool-card" aria-live="polite" aria-label="Decision">
      {r.stub && <p className="muted">Stub answer: the live pipeline isn&apos;t wired for this request.</p>}
      {r.message && <p className="feedback" role="status">{r.message}</p>}
      {d && (
        <>
          <span className={`status ${d.decision === "accept" ? "accepted" : d.decision === "ask" || d.decision === "skip" ? "pending" : d.decision === "split" ? "split" : "disputed"}`}><i />{VERDICT[d.decision] ?? d.decision}</span>
          <h2>{d.reason}</h2>
          <div className="allocation">
            <div><small>Disputed</small><strong>{dollars(d.disputed)}</strong></div>
            <div><small>Accepted</small><strong>{dollars(d.accepted)}</strong></div>
            <div><small>Waiting</small><strong>{dollars(d.waiting)}</strong></div>
          </div>
        </>
      )}
      {r.finding && <p className="finding">{r.finding.finding}</p>}
      {r.finding && r.finding.math.length > 0 && <p className="tool-math">{r.finding.math.map((m) => m.text).join("")}</p>}
      {r.rule && <p className="muted">Applied {r.rule.label}: {r.rule.summary}</p>}

      {r.terms.length > 0 && (
        <>
          <div className="section-eyebrow">What the clause said</div>
          {r.terms.filter((t) => t.reader === "merged" || r.terms.every((x) => x.reader !== "merged")).map((t) => (
            <div className="tool-row" key={t.id}>
              <div><strong>{t.type.replace(/_/g, " ")}</strong><small>“{t.exact_quote}”</small>{t.reasons.map((x) => <small key={x}>{x}</small>)}</div>
              <span className={`status ${t.status === "verified" ? "accepted" : t.status === "pending" ? "" : "disputed"}`}><i />{t.status === "verified" ? "Verified word for word" : t.status}</span>
            </div>
          ))}
        </>
      )}
      {r.unclear.length > 0 && <p className="muted">Unclear: {r.unclear.join("; ")}</p>}
      {r.rehearsal && (
        <>
          <div className="section-eyebrow">Ready for their pushback</div>
          <div className="rebuttal"><small>Northmart may say</small><p>“{r.rehearsal.predicted_rebuttal}”</p><small>Clawback answers</small><p>{r.rehearsal.answer}</p></div>
        </>
      )}
      {r.evidence.length > 0 && (
        <>
          <div className="section-eyebrow">Evidence</div>
          {r.evidence.map((e) => (
            <details className="source-detail" key={e.id}><summary><span>{e.label}<small>{e.summary}</small></span></summary><div className="source-preview"><p>{e.quote ? `“${e.quote.text}”` : e.summary}</p></div></details>
          ))}
        </>
      )}
    </section>
  );
}

export default function ScenarioApp() {
  const examples = useFetched<ScenarioExample[]>(useMemo(() => (DATA_SOURCE === "live" ? api.fetchScenarioExamples : null), []));
  const [clause, setClause] = useState("");
  const [desc, setDesc] = useState("");
  const [amount, setAmount] = useState("");
  const [code, setCode] = useState<"" | "PA" | "DF">("");
  const [units, setUnits] = useState("");
  const [rate, setRate] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScenarioResponse | null>(null);

  function fill(ex: ScenarioExample) {
    const c = ex.request.charge;
    setClause(ex.request.clause);
    setDesc(c.description);
    setAmount(String(c.amount));
    setCode(c.code ?? "");
    setUnits(c.units != null ? String(c.units) : "");
    setRate(c.rate != null ? String(c.rate) : "");
    setNotice(c.notice_date ?? "");
    setResult(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      // Numbers are passed through as typed; the API does all the math.
      setResult(
        await api.postScenario({
          clause: clause.trim(),
          charge: {
            description: desc.trim(),
            amount: Number(amount),
            ...(code ? { code } : {}),
            ...(units ? { units: Number(units) } : {}),
            ...(rate ? { rate: Number(rate) } : {}),
            ...(notice ? { notice_date: notice } : {}),
          },
        }),
      );
    } catch (err) {
      setError(`No decision came back (${(err as Error).message}). It can take up to 30 seconds; try again.`);
    } finally {
      setBusy(false);
    }
  }

  if (DATA_SOURCE !== "live") return <p className="feedback" role="status">This screen sends your clause to the API, so it only works in live mode (NEXT_PUBLIC_DATA_SOURCE=live).</p>;
  const ready = clause.trim() && desc.trim() && amount && Number(amount) > 0;

  return (
    <>
      {examples.data && (
        <div className="tool-actions" role="group" aria-label="Examples">
          {examples.data.map((ex) => <button key={ex.id} className="secondary" type="button" onClick={() => fill(ex)}>{ex.label}</button>)}
        </div>
      )}
      {examples.error && <p className="feedback error" role="alert">{examples.error}</p>}
      <form className="surface tool-card tool-form" onSubmit={submit}>
        <label htmlFor="sc-clause">The clause</label>
        <textarea id="sc-clause" rows={5} value={clause} onChange={(e) => setClause(e.target.value)} placeholder="Paste a sentence from a deal, for example the promo or fee clause" />
        <label htmlFor="sc-desc">What was charged</label>
        <input id="sc-desc" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Display fee, April" />
        <div className="tool-grid">
          <div><label htmlFor="sc-amount">Amount taken ($)</label><input id="sc-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
          <div><label htmlFor="sc-code">Type</label><select id="sc-code" value={code} onChange={(e) => setCode(e.target.value as "" | "PA" | "DF")}><option value="">Let Clawback guess</option><option value="PA">Promo allowance</option><option value="DF">Display fee</option></select></div>
          <div><label htmlFor="sc-units">Bars (promo)</label><input id="sc-units" inputMode="numeric" value={units} onChange={(e) => setUnits(e.target.value)} /></div>
          <div><label htmlFor="sc-rate">Rate per bar ($)</label><input id="sc-rate" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} /></div>
          <div><label htmlFor="sc-notice">Notice date (fees)</label><input id="sc-notice" type="date" value={notice} onChange={(e) => setNotice(e.target.value)} /></div>
        </div>
        <button className="primary" type="submit" disabled={!ready || busy}>{busy ? "Checking… up to 30 seconds" : "Decide this charge"}</button>
        {busy && <p className="muted" role="status"><span className="spinner" aria-hidden /> Two readers are reading the clause and the engine is checking the math.</p>}
      </form>
      {error && <p className="feedback error" role="alert">{error}</p>}
      {result && <Result r={result} />}
    </>
  );
}
