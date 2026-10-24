'use client'

// "How Clawback decided": every AI call the API recorded for one charge (GET /runs/{id}/trace?charge_id=), in order,
// with the code steps between them (the quote check, the engine's math line, the gate rule). Nothing here decides
// or computes anything; it shows what the API logged and what the decision event says.

import { useMemo, type ReactNode } from 'react'
import { Bot, Braces, CircleAlert, CircleCheck, Clock } from 'lucide-react'
import { fetchTrace, fetchTraceSummary } from '@/lib/api'
import { clock, money } from '@/lib/format'
import { cost, duration, readSummary, readUsage, tokens } from '@/lib/trace'
import type { Decision, Finding, Rule, TraceStep, TraceSummary } from '@/lib/types'
import { useFetched } from '@/lib/useFetched'

/** The decision-gate table in docs/design.md, in plain words. Copy only; the gate itself lives in api/engine/. */
export function gateRowText(row: number, distributor: string): string {
  return ({
    1: 'A deal term this charge depends on failed the quote check, so the deal can’t be verified.',
    2: 'The two deal readers disagree on a term, so the owner decides.',
    3: 'The deal leaves this to discretion, and a saved owner rule covers it.',
    4: 'The deal leaves this to discretion and no saved rule covers it, so the owner decides once.',
    5: 'The charge matches the deal to within $1.',
    6: `${distributor} took less than the deal allows. Clawback never asks for more.`,
    7: `${distributor} took more than the deal allows, two sources back it, and the likely pushback has an answer.`,
    8: 'Over $5,000, so the owner approves before anything is filed.',
    9: 'Not clear enough to act on alone, so the owner decides.',
  } as Record<number, string>)[row] ?? `Gate rule ${row}.`
}

const DECISION_WORD: Record<Decision['decision'], string> = { dispute: 'Dispute', accept: 'Accept', split: 'Split', ask: 'Ask the owner', skip: 'Hold' }

const AGENT: Record<string, string> = {
  reader: 'Deal reader',
  reader_a: 'Deal reader A',
  'reader-a': 'Deal reader A',
  reader_b: 'Deal reader B',
  'reader-b': 'Deal reader B',
  investigator: 'Investigator',
  negotiator: 'Negotiator',
  rehearsal: 'Negotiator',
  coach: 'Deal coach',
  rules: 'Rule writer',
  rule_writer: 'Rule writer',
  moss: 'Rule matcher',
}

const agentName = (a: string) => AGENT[a] ?? (a.charAt(0).toUpperCase() + a.slice(1)).replace(/[_-]/g, ' ')
const isReader = (s: TraceStep) => /reader/i.test(s.agent) || /reader/i.test(s.service)
const isInvestigator = (s: TraceStep) => /investigat/i.test(s.agent) || /investigat/i.test(s.service)

const STATUS: Record<TraceStep['status'], string> = { live: 'Live call', recorded: 'Replayed from recording', failed: 'Failed' }

type Item = { kind: 'ai'; step: TraceStep } | { kind: 'code'; key: string; title: string; at: string | null; body: ReactNode }

function pretty(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

export function DecisionTrace({ runId, chargeId, finding, decision, rule, distributor, version }: {
  runId: string | null
  chargeId: string
  finding: Finding | null
  decision: Decision | null
  rule: Rule | null
  distributor: string
  /** Changes when the charge is decided again, so the trace is read again. */
  version: string
}) {
  const load = useMemo(() => (runId ? () => fetchTrace(runId, chargeId) : null), [runId, chargeId])
  const trace = useFetched<TraceStep[]>(load, version)
  const loadSummary = useMemo(() => (runId ? () => fetchTraceSummary(runId) : null), [runId])
  const summary = useFetched<TraceSummary>(loadSummary, version)
  const totals = readSummary(summary.data)

  const items = useMemo<Item[]>(() => {
    const ai = [...(trace.data ?? [])].filter((s) => !s.charge_id || s.charge_id === chargeId).sort((a, b) => a.seq - b.seq)
    const readers = ai.filter(isReader)
    const rest = ai.filter((s) => !isReader(s))
    const out: Item[] = readers.map((step) => ({ kind: 'ai', step }))

    if (decision) {
      out.push({
        kind: 'code', key: 'quote', title: 'Quote check', at: null,
        body: decision.gate_row === 1
          ? 'A quote the readers returned was not found in the deal, so that term was rejected.'
          : finding && !finding.readers_agree
            ? 'The two readers returned different terms. A term only counts when both agree.'
            : 'Every term used here was found word for word in the deal, and both readers agree on it.',
      })
    }
    if (finding) {
      out.push({
        kind: 'code', key: 'math', title: 'Math engine', at: null,
        body: <>
          <p className="trace-math">{finding.math.length ? finding.math.map((m) => m.text).join('') : `Deal allows ${money(finding.expected)} · took ${money(finding.taken)}`}</p>
          <p className="trace-note">Deal allows {money(finding.expected)} · took {money(finding.taken)} · difference {money(finding.delta)}</p>
        </>,
      })
    }

    const gate: Item | null = decision ? {
      kind: 'code', key: 'gate', title: `Decision gate · rule ${decision.gate_row}`, at: decision.decided_at,
      body: <>
        <p><strong>{DECISION_WORD[decision.decision]}</strong>{decision.disputed > 0 ? ` · dispute ${money(decision.disputed)}` : ''}{decision.accepted > 0 ? ` · accept ${money(decision.accepted)}` : ''}{decision.waiting > 0 ? ` · hold ${money(decision.waiting)}` : ''}</p>
        <p className="trace-note">{gateRowText(decision.gate_row, distributor)}</p>
        {rule && decision.rule_id === rule.id && <p className="trace-note">Applied {rule.label}: {rule.summary}</p>}
      </>,
    } : null

    // The gate runs after the investigator; place it by its time among the later calls.
    const decidedAt = decision ? Date.parse(decision.decided_at) : NaN
    let gatePlaced = !gate
    rest.forEach((step, i) => {
      if (!gatePlaced && gate && !isInvestigator(step) && !Number.isNaN(decidedAt) && Date.parse(step.at) > decidedAt && rest.slice(0, i).some(isInvestigator)) {
        out.push(gate)
        gatePlaced = true
      }
      out.push({ kind: 'ai', step })
    })
    if (!gatePlaced && gate) out.push(gate)
    return out
  }, [trace.data, chargeId, decision, finding, rule, distributor])

  const ai = items.filter((i): i is Extract<Item, { kind: 'ai' }> => i.kind === 'ai').map((i) => i.step)
  const models = [...new Set(ai.map((s) => s.model).filter(Boolean))] as string[]
  const counts = { live: ai.filter((s) => s.status === 'live').length, recorded: ai.filter((s) => s.status === 'recorded').length, failed: ai.filter((s) => s.status === 'failed').length }
  const missing = trace.error && /answered 404/.test(trace.error)

  if (!runId) return <p className="muted small">The trace appears once the analysis has started.</p>

  return (
    <div className="trace">
      <div className="trace-summary">
        <strong>{ai.length} AI {ai.length === 1 ? 'call' : 'calls'}</strong>
        <span>{counts.live} live{counts.recorded ? ` · ${counts.recorded} replayed` : ''}{counts.failed ? ` · ${counts.failed} failed` : ''}</span>
        {models.length > 0 && <span className="trace-models">{models.join(' · ')}</span>}
        <p>Each step is a call the API logged while deciding this charge, with what went in and what came back. Amounts come from code, never from a model.</p>
      </div>
      {trace.loading && !trace.data && <p className="muted small" role="status">Loading the trace…</p>}
      {trace.error && <p className="muted small" role="status">{missing ? 'This server doesn’t keep a decision trace yet.' : trace.error}</p>}
      <ol className="trace-steps">
        {items.map((item, i) => item.kind === 'ai' ? <AiStep key={`ai-${item.step.seq}`} n={i + 1} step={item.step} /> : (
          <li key={item.key} className="trace-step code">
            <span className="trace-dot" aria-hidden><Braces /></span>
            <div className="trace-body">
              <div className="trace-head"><strong>{item.title}</strong><span className="trace-tag code">Code</span>{item.at && <span className="trace-time"><Clock />{clock(item.at)}</span>}</div>
              <div className="trace-text">{item.body}</div>
            </div>
          </li>
        ))}
      </ol>
      {trace.data && ai.length === 0 && !trace.error && <p className="muted small">No AI call was logged for this charge yet. Calls appear here as the analysis runs.</p>}
      {totals && <p className="trace-total">Whole analysis: {[
        totals.calls !== null ? `${totals.calls} AI ${totals.calls === 1 ? 'call' : 'calls'}` : null,
        totals.aiMs !== null ? `${duration(totals.aiMs)} of AI time` : null,
        totals.wallMs !== null ? `${duration(totals.wallMs)} start to finish` : null,
        totals.tokens?.total != null ? `${tokens(totals.tokens.total)} tokens` : totals.tokens && (totals.tokens.input != null || totals.tokens.output != null) ? `${tokens(totals.tokens.input ?? 0)} tokens in · ${tokens(totals.tokens.output ?? 0)} out` : null,
        totals.costUsd !== null ? `${cost(totals.costUsd)} in AI usage` : null,
      ].filter(Boolean).join(' · ')}</p>}
    </div>
  )
}

function AiStep({ n, step }: { n: number; step: TraceStep }) {
  const failed = step.status === 'failed'
  const u = readUsage(step.usage)
  const usage = u ? (u.input !== null || u.output !== null ? `${tokens(u.input ?? 0)} tokens in · ${tokens(u.output ?? 0)} out` : u.total !== null ? `${tokens(u.total)} tokens` : null) : null
  return (
    <li className={`trace-step ai ${failed ? 'failed' : ''}`} aria-label={`Step ${n}: ${agentName(step.agent)}`}>
      <span className="trace-dot" aria-hidden><Bot /></span>
      <div className="trace-body">
        <div className="trace-head">
          <strong>{agentName(step.agent)}</strong>
          <span className={`trace-tag ${step.status}`}>{failed ? <CircleAlert /> : <CircleCheck />}{STATUS[step.status] ?? step.status}</span>
          <span className="trace-time"><Clock />{clock(step.at)}{duration(step.latency_ms) ? ` · ${duration(step.latency_ms)}` : ''}</span>
        </div>
        <p className="trace-meta"><code>{step.model ?? 'model not reported'}</code> · {step.service}{step.attempts > 1 ? ` · ${step.attempts} attempts` : ''}{usage ? ` · ${usage}` : ''}</p>
        {step.error && <p className="trace-error">{step.error}</p>}
        {step.prompt && <details className="trace-io"><summary>Instructions</summary><pre>{step.prompt}</pre></details>}
        <details className="trace-io"><summary>Input</summary><pre>{pretty(step.input)}</pre></details>
        <details className="trace-io"><summary>Output</summary><pre>{pretty(step.output)}</pre></details>
      </div>
    </li>
  )
}
