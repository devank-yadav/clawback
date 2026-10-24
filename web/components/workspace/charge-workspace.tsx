'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, Check, ChevronRight, FileText, ShieldCheck, X } from 'lucide-react'
import { CAST, OWNER_RULE_REPLY } from '@/lib/cast'
import { dollars } from '@/lib/format'
import { evidence as recordedEvidence } from '@/lib/fixture'
import { fetchEvidence } from '@/lib/live'
import type { ChargeDetail, Evidence, MathPart, Question, Rule } from '@/lib/types'
import { evidenceRows, type ChargeView, type Stage } from '@/lib/workspace'

export type ChargeFilter = 'All' | 'Disputed' | 'Accepted' | 'Needs input'

export function Status({ value }: { value: string }) {
  const className = value === 'Accepted' || value === 'Simulated posted' || value.startsWith('Posted')
    ? 'accepted'
    : value === 'Needs your input' || value === 'Awaiting approval' || value === 'Can’t verify' || value === 'Posting held' || value.startsWith('Approved')
      ? 'pending'
      : value === 'Split decision'
        ? 'split'
        : value === 'Reviewing'
          ? ''
          : 'disputed'
  return <span className={`status ${className}`}><i />{value}</span>
}

function matchesFilter(charge: ChargeView, filter: ChargeFilter) {
  if (filter === 'All') return true
  if (filter === 'Disputed') return charge.status === 'Disputed' || charge.status === 'Split decision'
  if (filter === 'Accepted') return charge.status === 'Accepted' || charge.status === 'Split decision'
  return charge.status === 'Needs your input'
}

export function ChargeList({ charges, selected, onSelect, preview = false, filter = 'All', onFilterChange }: { charges: ChargeView[]; selected?: string; onSelect: (charge: ChargeView) => void; preview?: boolean; filter?: ChargeFilter; onFilterChange?: (filter: ChargeFilter) => void }) {
  const visibleCharges = charges.filter((charge) => matchesFilter(charge, filter))
  return <div className={`charge-table ${preview ? 'preview-table' : ''}`}>
    {onFilterChange && <div className="charge-filters" aria-label="Filter charges">{(['All', 'Disputed', 'Accepted', 'Needs input'] as ChargeFilter[]).map((value) => <button key={value} className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => onFilterChange(value)}>{value}</button>)}</div>}
    <div className="table-head"><span>Charge</span><span>Amount</span><span>Decision</span>{preview && <span>What we found</span>}<span /></div>
    {visibleCharges.map((charge) => <button className={`charge-row ${selected === charge.id ? 'selected' : ''}`} key={charge.id} onClick={() => onSelect(charge)} aria-label={`Review ${charge.title}`}><span className="charge-name"><span className="charge-icon"><FileText /></span><span>{charge.title}{!preview && <small>{charge.reason}</small>}</span></span><span className="money">{dollars(charge.amount)}</span><Status value={charge.status} />{preview && <span className="row-reason">{charge.reason}</span>}<ChevronRight /></button>)}
    {charges.length === 0 && <div className="filtered-empty"><FileText /><h3>Checking the charges</h3><p>Each deduction appears here as it is checked against the deal.</p></div>}
    {charges.length > 0 && visibleCharges.length === 0 && <div className="filtered-empty"><FileText /><h3>No charges match this filter</h3><p>Try another status to view the {charges.length} reviewed deductions.</p></div>}
  </div>
}

function amountLabel(charge: ChargeView, value: number | null) {
  return value === null || charge.status === 'Needs your input' || charge.status === 'Reviewing' ? 'Pending' : dollars(value)
}

export function EvidencePanel({ runId, live, charge, detail, question, rule, stage, onClose, onConfirm, role }: { runId?: string; live: boolean; charge: ChargeView; detail: ChargeDetail | null; question: Question | null; rule: Rule | null; stage: Stage; onClose: () => void; onConfirm: () => void; role: string }) {
  const asksOwner = charge.status === 'Needs your input' && !!question && question.charge_id === charge.id && !question.answer
  const rows = evidenceRows(detail)
  const lead = rows[0]
  const math = mathLines(detail?.finding?.math ?? [])
  const rehearsal = detail?.rehearsal ?? null
  const [openSource, setOpenSource] = useState<string | null>(null)
  return <aside className="evidence-panel" aria-label="Charge evidence"><div className="evidence-top"><span><FileText /> Charge details <span className="muted">/ {charge.id}</span></span><button className="icon-button" onClick={onClose} aria-label="Close evidence"><X /></button></div><div className="evidence-body"><button onClick={onClose} className="text-button mobile-back"><ArrowLeft /> Back to charges</button><Status value={charge.status} /><h2>{charge.title}</h2><p className="finding">{charge.finding}</p><div className="allocation"><div><small>Charged</small><strong>{dollars(charge.amount)}</strong></div><div><small>Accepted</small><strong>{amountLabel(charge, charge.accepted)}</strong></div><div><small>Disputed</small><strong>{amountLabel(charge, charge.disputed)}</strong></div></div>{charge.status === 'Split decision' && charge.accepted !== null && charge.disputed !== null && <p className="muted small">One {dollars(charge.amount)} charge: {dollars(charge.accepted)} accepted and {dollars(charge.disputed)} disputed.</p>}<div className="section-eyebrow">Supporting evidence</div>{lead ? <blockquote>“{lead.text}”<footer>{lead.label} · Fictional demo</footer></blockquote> : <p className="muted small">Loading the evidence for this charge…</p>}{math.length > 0 && <><div className="section-eyebrow">The math</div><ol className="math-lines">{math.map((line, i) => <li key={i}>{line.map((p, j) => p.evidence_id ? <button key={j} className="math-ref" aria-pressed={openSource === p.evidence_id} title="Show where this number comes from" onClick={() => setOpenSource(openSource === p.evidence_id ? null : p.evidence_id)}>{p.text}</button> : <span key={j}>{p.text}</span>)}</li>)}</ol>{openSource && <SourceCard evidenceId={openSource} runId={runId} live={live} detail={detail} />}<p className="muted small">Worked out in code, not by AI. Select a number to see its source.</p></>}{(charge.status === 'Disputed' || charge.status === 'Split decision') && <><div className="section-eyebrow">Ready for their pushback</div>{rehearsal ? <div className="rebuttal"><small>Northmart may say</small><p>“{rehearsal.predicted_rebuttal}”</p><small>Clawback answers</small><p>{rehearsal.answer}</p></div> : <p className="muted small">No rehearsal recorded yet.</p>}</>}{rows.map((row) => <details className="source-detail" key={row.id}><summary><FileText /><span>{row.label}<small>{row.summary}</small></span><ChevronRight /></summary><div className="source-preview"><span>Readable source preview</span><p>{row.text}</p><small>Fictional demo data. No external document is connected.</small></div></details>)}{asksOwner && <div className="policy-box"><div className="eyebrow"><ShieldCheck /> Owner policy decision</div><h3>Set a rule for future display fees</h3><p>Accept Northmart display fees when written notice is given at least <strong>14 days</strong> in advance.</p><p className="small muted">{question.text}</p><p className="small muted">Confirming sends {CAST.owner}’s reply, “{OWNER_RULE_REPLY}”, and the fee is decided again under that rule. {CAST.controllerFull} still reviews accounting separately.</p><button className="primary full" disabled={role !== 'Owner'} onClick={onConfirm}><Check /> Confirm rule as {CAST.ownerFull}</button>{role !== 'Owner' && <p className="role-hint">Switch to Owner in the Peak Bar Co. menu to confirm policy.</p>}</div>}{!asksOwner && charge.status !== 'Needs your input' && charge.status !== 'Reviewing' && <div className="decision-note"><ShieldCheck /><p><strong>{charge.ruleId && rule ? `Applied ${rule.label}, saved by ${CAST.ownerFull}.` : charge.status === 'Accepted' ? 'Supported by the agreement or approved evidence.' : charge.status === 'Split decision' ? 'Part accepted; the unsupported amount is disputed.' : 'Evidence supports challenging this amount.'}</strong><span>Accounting approval is a separate controller action.</span></p></div>}{stage === 'checking' && charge.status === 'Reviewing' && <p className="muted small">This charge is still being checked.</p>}</div></aside>
}

/** The engine's math line, one clause per row (split on its " · " separators and between sentences). */
function mathLines(parts: MathPart[]): MathPart[][] {
  const lines: MathPart[][] = [[]]
  for (const p of parts) {
    if (p.evidence_id) { lines[lines.length - 1].push(p); continue }
    p.text.split(/ · |(?<=\.)\s+(?=[A-Z])/).forEach((chunk, i) => {
      if (i > 0) lines.push([])
      if (chunk) lines[lines.length - 1].push({ text: chunk, evidence_id: null })
    })
  }
  return lines.filter((l) => l.length > 0)
}

/** The source behind one clicked number: the charge's own evidence list first, then GET /evidence/{id} (live) or the recording. */
function SourceCard({ evidenceId, runId, live, detail }: { evidenceId: string; runId?: string; live: boolean; detail: ChargeDetail | null }) {
  const local = detail?.evidence.find((e) => e.id === evidenceId) ?? (live ? null : recordedEvidence(evidenceId))
  const [fetched, setFetched] = useState<{ id: string; ev: Evidence | null } | null>(null)
  useEffect(() => {
    if (local || !live) return
    let cancelled = false
    fetchEvidence(evidenceId, runId).then((ev) => !cancelled && setFetched({ id: evidenceId, ev }), () => !cancelled && setFetched({ id: evidenceId, ev: null }))
    return () => { cancelled = true }
  }, [local, live, evidenceId, runId])
  const ev = local ?? (fetched?.id === evidenceId ? fetched.ev : null)
  if (!ev) return <p className="muted small" role="status">{fetched?.id === evidenceId ? 'This source could not be loaded.' : 'Loading the source…'}</p>
  const detailRows = ev.rows.slice(0, 4)
  return <div className="source-card" role="region" aria-label={`Source: ${ev.label}`}><small>{ev.label}</small><p>{ev.quote ? `“${ev.quote.text}”` : ev.summary}</p>{ev.sender && <small>From {ev.sender}{ev.approved_sender === false ? ' · not an approved sender' : ''}</small>}{detailRows.map((row, i) => <small key={i} className="source-row">{Object.entries(row).map(([k, v]) => `${k}: ${v ?? '—'}`).join(' · ')}</small>)}</div>
}
