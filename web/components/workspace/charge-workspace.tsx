'use client'

import { ArrowLeft, Check, ChevronRight, FileText, ShieldCheck, X } from 'lucide-react'
import { CAST, OWNER_RULE_REPLY } from '@/lib/cast'
import { dollars } from '@/lib/format'
import type { ChargeDetail, Question, Rule } from '@/lib/types'
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

export function EvidencePanel({ charge, detail, question, rule, stage, onClose, onConfirm, role }: { charge: ChargeView; detail: ChargeDetail | null; question: Question | null; rule: Rule | null; stage: Stage; onClose: () => void; onConfirm: () => void; role: string }) {
  const asksOwner = charge.status === 'Needs your input' && !!question && question.charge_id === charge.id && !question.answer
  const rows = evidenceRows(detail)
  const lead = rows[0]
  const math = (detail?.finding?.math ?? []).map((p) => p.text).join('').split(/ · |(?<=\.)(?=[A-Z])/).map((l) => l.trim()).filter(Boolean)
  const rehearsal = detail?.rehearsal ?? null
  return <aside className="evidence-panel" aria-label="Charge evidence"><div className="evidence-top"><span><FileText /> Charge details <span className="muted">/ {charge.id}</span></span><button className="icon-button" onClick={onClose} aria-label="Close evidence"><X /></button></div><div className="evidence-body"><button onClick={onClose} className="text-button mobile-back"><ArrowLeft /> Back to charges</button><Status value={charge.status} /><h2>{charge.title}</h2><p className="finding">{charge.finding}</p><div className="allocation"><div><small>Charged</small><strong>{dollars(charge.amount)}</strong></div><div><small>Accepted</small><strong>{amountLabel(charge, charge.accepted)}</strong></div><div><small>Disputed</small><strong>{amountLabel(charge, charge.disputed)}</strong></div></div>{charge.status === 'Split decision' && charge.accepted !== null && charge.disputed !== null && <p className="muted small">One {dollars(charge.amount)} charge: {dollars(charge.accepted)} accepted and {dollars(charge.disputed)} disputed.</p>}<div className="section-eyebrow">Supporting evidence</div>{lead ? <blockquote>“{lead.text}”<footer>{lead.label} · Fictional demo</footer></blockquote> : <p className="muted small">Loading the evidence for this charge…</p>}{math.length > 0 && <><div className="section-eyebrow">The math</div><ol className="math-lines">{math.map((line, i) => <li key={i}>{line}</li>)}</ol><p className="muted small">Worked out in code, not by AI.</p></>}{(charge.status === 'Disputed' || charge.status === 'Split decision') && <><div className="section-eyebrow">Ready for their pushback</div>{rehearsal ? <div className="rebuttal"><small>Northmart may say</small><p>“{rehearsal.predicted_rebuttal}”</p><small>Clawback answers</small><p>{rehearsal.answer}</p></div> : <p className="muted small">No rehearsal recorded yet.</p>}</>}{rows.map((row) => <details className="source-detail" key={row.id}><summary><FileText /><span>{row.label}<small>{row.summary}</small></span><ChevronRight /></summary><div className="source-preview"><span>Readable source preview</span><p>{row.text}</p><small>Fictional demo data. No external document is connected.</small></div></details>)}{asksOwner && <div className="policy-box"><div className="eyebrow"><ShieldCheck /> Owner policy decision</div><h3>Set a rule for future display fees</h3><p>Accept Northmart display fees when written notice is given at least <strong>14 days</strong> in advance.</p><p className="small muted">{question.text}</p><p className="small muted">Confirming sends {CAST.owner}’s reply, “{OWNER_RULE_REPLY}”, and the fee is decided again under that rule. {CAST.controllerFull} still reviews accounting separately.</p><button className="primary full" disabled={role !== 'Owner'} onClick={onConfirm}><Check /> Confirm rule as {CAST.ownerFull}</button>{role !== 'Owner' && <p className="role-hint">Switch to Owner in the Peak Bar Co. menu to confirm policy.</p>}</div>}{!asksOwner && charge.status !== 'Needs your input' && charge.status !== 'Reviewing' && <div className="decision-note"><ShieldCheck /><p><strong>{charge.ruleId && rule ? `Applied ${rule.label}, saved by ${CAST.ownerFull}.` : charge.status === 'Accepted' ? 'Supported by the agreement or approved evidence.' : charge.status === 'Split decision' ? 'Part accepted; the unsupported amount is disputed.' : 'Evidence supports challenging this amount.'}</strong><span>Accounting approval is a separate controller action.</span></p></div>}{stage === 'checking' && charge.status === 'Reviewing' && <p className="muted small">This charge is still being checked.</p>}</div></aside>
}
