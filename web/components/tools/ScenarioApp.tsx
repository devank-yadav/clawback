"use client";

import { useMemo, useState } from "react";
import { KeyRound } from "lucide-react";
import ToolFrame from "./ToolFrame";
import { codeLabel } from "@/lib/accounts";
import { dollars } from "@/lib/format";
import * as api from "@/lib/api";
import { askAdminToken, LIMIT_ADMIN_REASON, limitMessage } from "@/lib/session";
import type { Account, ScenarioCharge, ScenarioExample, ScenarioRequest, ScenarioResponse } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const VERDICT: Record<string, string> = { dispute: "Dispute", accept: "Accept", split: "Split", ask: "Ask the owner", skip: "Can't verify the deal" };

function Result({ r, distributor }: { r: ScenarioResponse; distributor: string }) {
  const d = r.decision;
  return (
    <section className="surface tool-card" aria-live="polite" aria-label="Decision">
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
              <span className={`status ${t.status === "verified" ? "accepted" : t.status === "pending" ? "" : "disputed"}`}><i />{t.status === "verified" ? "Found word for word" : t.status}</span>
            </div>
          ))}
        </>
      )}
      {r.unclear.length > 0 && <p className="muted">Unclear: {r.unclear.join("; ")}</p>}
      {r.rehearsal && (
        <>
          <div className="section-eyebrow">Ready for their pushback</div>
          <div className="rebuttal"><small>{distributor} may say</small><p>“{r.rehearsal.predicted_rebuttal}”</p><small>Clawback answers</small><p>{r.rehearsal.answer}</p></div>
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

type Form = { clause: string; desc: string; amount: string; code: string; product: string; units: string; rate: string; start: string; end: string; notice: string };
const EMPTY: Form = { clause: "", desc: "", amount: "", code: "", product: "", units: "", rate: "", start: "", end: "", notice: "" };

function formOf(ex: ScenarioExample): Form {
  const c = ex.request.charge;
  const s = (v: string | number | null | undefined) => (v === null || v === undefined ? "" : String(v));
  return { clause: ex.request.clause, desc: c.description, amount: s(c.amount), code: s(c.code), product: s(c.product), units: s(c.units), rate: s(c.rate), start: s(c.period_start), end: s(c.period_end), notice: s(c.notice_date) };
}

/**
 * What to send. An example nobody edited goes exactly as the API gave it (product and dates included), so its answer
 * matches the recorded one. An edited example keeps its other fields; a typed-in charge sends only what was typed.
 */
function requestOf(form: Form, example: ScenarioExample | null, edited: boolean): ScenarioRequest {
  if (example && !edited) return example.request;
  const base: Record<string, unknown> = example ? { ...example.request.charge } : {};
  const set = (key: keyof ScenarioCharge, value: unknown) => {
    if (value === undefined) delete base[key];
    else base[key] = value;
  };
  set("description", form.desc.trim());
  set("amount", Number(form.amount));
  set("code", form.code || undefined);
  set("product", form.product.trim() || undefined);
  set("units", form.units ? Number(form.units) : undefined);
  set("rate", form.rate ? Number(form.rate) : undefined);
  set("period_start", form.start || undefined);
  set("period_end", form.end || undefined);
  set("notice_date", form.notice || undefined);
  return { clause: form.clause.trim(), charge: base as ScenarioCharge };
}

function Scenario({ account }: { account: Account }) {
  const examples = useFetched<ScenarioExample[]>(useMemo(() => api.fetchScenarioExamples, []));
  const [form, setForm] = useState<Form>(EMPTY);
  const [example, setExample] = useState<ScenarioExample | null>(null);
  const [edited, setEdited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limited, setLimited] = useState<string | null>(null);
  const [result, setResult] = useState<ScenarioResponse | null>(null);

  const field = (key: keyof Form) => ({
    value: form[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      setForm((f) => ({ ...f, [key]: e.target.value }));
      setEdited(true);
    },
  });

  function fill(ex: ScenarioExample) {
    setForm(formOf(ex));
    setExample(ex);
    setEdited(false);
    setResult(null);
  }

  async function send() {
    setBusy(true);
    setError(null);
    setLimited(null);
    setResult(null);
    try {
      // Numbers are passed through as typed; the API does all the math.
      setResult(await api.postScenario(requestOf(form, example, edited)));
    } catch (err) {
      const limit = limitMessage(err);
      if (limit) setLimited(limit);
      else setError(`No decision came back (${(err as Error).message}). It can take up to 30 seconds; try again.`);
    } finally {
      setBusy(false);
    }
  }

  const ready = form.clause.trim() && form.desc.trim() && form.amount && Number(form.amount) > 0;
  const codes = ["PA", "DF", ...(form.code && !["PA", "DF"].includes(form.code) ? [form.code] : [])];

  return (
    <>
      {examples.data && examples.data.length > 0 && (
        <div className="tool-actions" role="group" aria-label="Examples">
          {examples.data.map((ex) => <button key={ex.id} className="secondary" type="button" aria-pressed={example?.id === ex.id && !edited} onClick={() => fill(ex)}>{ex.label}</button>)}
        </div>
      )}
      {examples.error && <p className="feedback error" role="alert">{examples.error}</p>}
      <form className="surface tool-card tool-form" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <label htmlFor="sc-clause">The clause</label>
        <textarea id="sc-clause" rows={5} {...field("clause")} placeholder="Paste a sentence from a deal, for example a promo, pricing or fee clause" />
        <label htmlFor="sc-desc">What was charged</label>
        <input id="sc-desc" {...field("desc")} placeholder="Display fee, April" />
        <div className="tool-grid">
          <div><label htmlFor="sc-amount">Amount taken ($)</label><input id="sc-amount" inputMode="decimal" {...field("amount")} /></div>
          <div><label htmlFor="sc-code">Type</label><select id="sc-code" {...field("code")}><option value="">Let Clawback tell</option>{codes.map((c) => <option key={c} value={c}>{codeLabel(c)}</option>)}</select></div>
          <div><label htmlFor="sc-product">Product</label><input id="sc-product" {...field("product")} /></div>
          <div><label htmlFor="sc-units">Units</label><input id="sc-units" inputMode="numeric" {...field("units")} /></div>
          <div><label htmlFor="sc-rate">Rate per unit ($)</label><input id="sc-rate" inputMode="decimal" {...field("rate")} /></div>
          <div><label htmlFor="sc-start">From</label><input id="sc-start" type="date" {...field("start")} /></div>
          <div><label htmlFor="sc-end">To</label><input id="sc-end" type="date" {...field("end")} /></div>
          <div><label htmlFor="sc-notice">Notice date (fees)</label><input id="sc-notice" type="date" {...field("notice")} /></div>
        </div>
        <button className="primary" type="submit" disabled={!ready || busy}>{busy ? "Checking… up to 30 seconds" : "Decide this charge"}</button>
        {busy && <p className="muted" role="status"><span className="spinner" aria-hidden /> Two readers are reading the clause and the engine is checking the math.</p>}
      </form>
      {limited && <div className="feedback notice" role="status"><span>{limited}</span><button className="text-button" onClick={() => askAdminToken(LIMIT_ADMIN_REASON, () => void send())}><KeyRound /> Use admin token</button></div>}
      {error && <p className="feedback error" role="alert">{error}</p>}
      {result && <Result r={result} distributor={account.distributor.name} />}
    </>
  );
}

export default function ScenarioApp() {
  return (
    <ToolFrame title="Try a clause" lead={() => "Paste any clause and a charge. Clawback reads it, does the math and decides, with its evidence."}>
      {(account) => <Scenario account={account} />}
    </ToolFrame>
  );
}
