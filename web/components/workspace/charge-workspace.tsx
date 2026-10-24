'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, Check, ChevronRight, FileText, ShieldCheck, X } from 'lucide-react'
import { firstName } from '@/lib/accounts'
import { fetchEvidence } from '@/lib/api'
import { dollars } from '@/lib/format'
import type { Role } from '@/lib/session'
import type { Account, ChargeDetail, Evidence, MathPart, Question, Rule } from '@/lib/types'
import { useChargeDetail } from '@/lib/useChargeDetail'
import type { RunState } from '@/lib/useRunEvents'
import { orderedEvidence, type ChargeView, type Stage } from '@/lib/workspace'
import { DecisionTrace } from './decision-trace'
import { QuoteBlock, SourceBody, sourceTitle } from './evidence-parts'

export type ChargeFilter = 'All' | 'Disputed' | 'Accepted' | 'Needs input'

export function Status({ value }: { value: string }) {
  const className = value === 'Accepted' || value.startsWith('Posted')
    ? 'accepted'
    : value === 'Needs your input' || value === 'Awaiting approval' || value === 'Can’t verify' || value === 'Posting held' || value.startsWith('Approved')
      ? 'pending'
      : value === 'Split decision'
        ? 'split'
        : value === 'Reviewing'
          ? 'working'
          : 'disputed'
  return <span className={`status ${className}`}><i />{value === 'Reviewing' ? 'Checking…' : value}</span>
}

function matchesFilter(charge: ChargeView, filter: ChargeFilter) {
  if (filter === 'All') return true
  if (filter === 'Disputed') return charge.status === 'Disputed' || charge.status === 'Split decision'
  if (filter === 'Accepted') return charge.status === 'Accepted' || charge.status === 'Split decision'
  return charge.status === 'Needs your input'
}

export function ChargeList({ charges, selected, onSelect, preview = false, filter = 'All', onFilterChange, waiting = false, pending = 0 }: { charges: ChargeView[]; selected?: string; onSelect: (charge: ChargeView) => void; preview?: boolean; filter?: ChargeFilter; onFilterChange?: (filter: ChargeFilter) => void; waiting?: boolean; /** Charges on the remittance not read yet. */ pending?: number }) {
  const visibleCharges = charges.filter((charge) => matchesFilter(charge, filter))
  return <div className={`charge-table ${preview ? 'preview-table' : ''}`}>
    {onFilterChange && <div className="charge-filters" aria-label="Filter charges">{(['All', 'Disputed', 'Accepted', 'Needs input'] as ChargeFilter[]).map((value) => <button key={value} className={filter === value ? 'active' : ''} aria-pressed={filter === value} onClick={() => onFilterChange(value)}>{value}</button>)}</div>}
    <div className="table-head"><span>Charge</span><span>Amount</span><span>Decision</span>{preview && <span>What we found</span>}<span /></div>
    {visibleCharges.map((charge) => <button className={`charge-row ${selected === charge.id ? 'selected' : ''}`} key={charge.id} onClick={() => onSelect(charge)} aria-label={`Review ${charge.title}`}><span className="charge-name"><span className="charge-icon"><FileText /></span><span><span className="charge-kind">{charge.kind} · {charge.ref}</span>{charge.title}{!preview && <small>{charge.reason}</small>}</span></span><span className="money">{dollars(charge.amount)}</span><Status value={charge.status} />{preview && <span className="row-reason">{charge.reason}</span>}<ChevronRight /></button>)}
    {filter === 'All' && Array.from({ length: Math.max(0, pending) }, (_, i) => <div className="charge-row placeholder" key={`pending-${i}`} aria-hidden><span className="charge-name"><span className="charge-icon"><FileText /></span><span><span className="charge-kind">Next on the remittance</span>Waiting to be read</span></span><span className="money">—</span><span className="status working"><i />Queued</span>{preview && <span className="row-reason" />}<span /></div>)}
    {charges.length === 0 && pending === 0 && <div className="filtered-empty"><FileText /><h3>{waiting ? 'No payment yet' : 'Checking the charges'}</h3><p>{waiting ? 'Each deduction is listed here once the payment arrives.' : 'Each deduction appears here as it is checked against the deal.'}</p></div>}
    {charges.length > 0 && visibleCharges.length === 0 && <div className="filtered-empty"><FileText /><h3>No charges match this filter</h3><p>Try another status to see the {charges.length} deductions.</p></div>}
  </div>
}

function amountLabel(charge: ChargeView, value: number | null) {
  return value === null || charge.status === 'Needs your input' || charge.status === 'Reviewing' ? 'Pending' : dollars(value)
}

/** The one-tap answers offered to the owner. The display-fee reply is the one the recorded demo expects, word for word. */
function suggestedReplies(code: string): string[] {
  if (code === 'DF') return ['accept if notice is at least 14 days', 'dispute it']
  return ['accept it this time', 'dispute it']
}

type PanelProps = {
  account: Account
  state: RunState
  runId: string | null
  charge: ChargeView
  question: Question | null
  rule: Rule | null
  stage: Stage
  role: Role | null
  onClose: () => void
  onAnswer: (questionId: string, text: string) => void
}

export function EvidencePanel({ account, state, runId, charge, question, rule, stage, role, onClose, onAnswer }: PanelProps) {
  const decision = state.decisions[charge.id] ?? null
  const version = `${decision?.decision ?? ''}:${decision?.rule_id ?? ''}:${decision?.decided_at ?? ''}`
  const detail = useChargeDetail(charge.id, runId, version)
  const [tab, setTab] = useState<'evidence' | 'trace'>('evidence')
  const distributor = account.distributor.name
  const owner = account.brand.owner.name
  const asksOwner = charge.status === 'Needs your input' && !!question && question.charge_id === charge.id && !question.answer
  const finding = state.findings[charge.id] ?? detail?.finding ?? null
  const rehearsal = state.rehearsals[charge.id] ?? detail?.rehearsal ?? null
  const appliedRule = decision?.rule_id ? (state.rules[decision.rule_id] ?? detail?.rule ?? rule) : null

  return <aside className="evidence-panel" aria-label="Charge evidence">
    <div className="evidence-top"><span><FileText /> {charge.kind} <span className="muted">/ {charge.ref}</span></span><button className="icon-button" onClick={onClose} aria-label="Close evidence"><X /></button></div>
    <div className="evidence-body">
      <button onClick={onClose} className="text-button mobile-back"><ArrowLeft /> Back to charges</button>
      <Status value={charge.status} />
      <h2>{charge.title}</h2>
      <p className="finding">{charge.finding}</p>
      <div className="allocation"><div><small>Charged</small><strong>{dollars(charge.amount)}</strong></div><div><small>Accepted</small><strong>{amountLabel(charge, charge.accepted)}</strong></div><div><small>Disputed</small><strong>{amountLabel(charge, charge.disputed)}</strong></div></div>
      {charge.status === 'Split decision' && charge.accepted !== null && charge.disputed !== null && <p className="muted small">One {dollars(charge.amount)} charge: {dollars(charge.accepted)} accepted and {dollars(charge.disputed)} disputed.</p>}

      {asksOwner && <OwnerQuestion key={question.id} question={question} code={charge.code} owner={owner} controller={account.brand.controller.name} role={role} onAnswer={onAnswer} />}

      <div className="panel-tabs" role="tablist" aria-label="Charge details">
        <button role="tab" id="tab-evidence" aria-controls="pane-evidence" aria-selected={tab === 'evidence'} className={tab === 'evidence' ? 'active' : ''} onClick={() => setTab('evidence')}>Evidence</button>
        <button role="tab" id="tab-trace" aria-controls="pane-trace" aria-selected={tab === 'trace'} className={tab === 'trace' ? 'active' : ''} onClick={() => setTab('trace')}>How Clawback decided</button>
      </div>

      {tab === 'evidence' && <div role="tabpanel" id="pane-evidence" aria-labelledby="tab-evidence">
        <EvidenceTab charge={charge} detail={detail} runId={runId} distributor={distributor} finding={finding} rehearsal={rehearsal} />
        {!asksOwner && charge.status !== 'Needs your input' && charge.status !== 'Reviewing' && <div className="decision-note"><ShieldCheck /><p><strong>{appliedRule ? `Applied ${appliedRule.label}, set by ${owner}.` : charge.status === 'Accepted' ? 'Supported by the deal and its evidence.' : charge.status === 'Split decision' ? 'Part accepted; the unsupported part is disputed.' : charge.status === 'Can’t verify' ? 'The deal term couldn’t be verified, so nothing was decided.' : 'The evidence supports challenging this amount.'}</strong><span>Accounting entries still need the controller’s approval.</span></p></div>}
        {stage === 'checking' && charge.status === 'Reviewing' && <p className="muted small">This charge is still being checked.</p>}
      </div>}
      {tab === 'trace' && <div role="tabpanel" id="pane-trace" aria-labelledby="tab-trace">
        <DecisionTrace runId={runId} chargeId={charge.id} finding={finding} decision={decision} rule={appliedRule} distributor={distributor} version={version} />
      </div>}
    </div>
  </aside>
}

function OwnerQuestion({ question, code, owner, controller, role, onAnswer }: { question: Question; code: string; owner: string; controller: string; role: Role | null; onAnswer: (questionId: string, text: string) => void }) {
  const replies = suggestedReplies(code)
  const [text, setText] = useState(replies[0])
  const [sent, setSent] = useState(false)
  return <div className="policy-box">
    <div className="eyebrow"><ShieldCheck /> Your decision</div>
    <h3>{question.text}</h3>
    <p className="small muted">Your answer becomes a rule, so a charge like this is never asked about twice. {controller} still approves the accounting separately.</p>
    <div className="reply-chips" role="group" aria-label="Suggested answers">{replies.map((r) => <button key={r} type="button" aria-pressed={text === r} onClick={() => setText(r)}>{r.charAt(0).toUpperCase() + r.slice(1)}</button>)}</div>
    <label className="note-label" htmlFor="owner-answer">Your answer</label>
    <textarea id="owner-answer" value={text} onChange={(event) => setText(event.target.value)} rows={2} />
    <button className="primary full" disabled={!text.trim() || sent} onClick={() => { if (role === 'owner') setSent(true); onAnswer(question.id, text) }}><Check /> {sent ? 'Sent · saving the rule' : `Send as ${owner}`}</button>
    {role !== 'owner' && <p className="role-hint">Only {firstName(owner)} can answer. You’ll be asked to sign in as the owner.</p>}
  </div>
}

function EvidenceTab({ charge, detail, runId, distributor, finding, rehearsal }: { charge: ChargeView; detail: ChargeDetail | null; runId: string | null; distributor: string; finding: ChargeDetail['finding']; rehearsal: ChargeDetail['rehearsal'] }) {
  const all = orderedEvidence(detail)
  const lead = all.find((e) => e.quote && (e.kind === 'clause' || e.kind === 'policy' || e.kind === 'email' || e.kind === 'notice'))
  const others = all.filter((e) => e !== lead)
  const math = mathLines(finding?.math ?? [])
  const [open, setOpen] = useState<{ id: string; text: string } | null>(null)
  const disputed = charge.status === 'Disputed' || charge.status === 'Split decision'

  return <>
    {lead?.quote && <>
      <div className="section-eyebrow">{sourceTitle(lead.kind, distributor)}</div>
      <QuoteBlock quote={lead.quote} active={open?.id === lead.id ? open.text : null} />
      <p className="quote-label">{lead.label}{lead.sender ? ` · from ${lead.sender}` : ''}</p>
    </>}
    {!detail && <p className="muted small">Loading the evidence for this charge…</p>}

    {math.length > 0 && <>
      <div className="section-eyebrow">The math</div>
      <ol className="math-lines">{math.map((line, i) => <li key={i}>{line.map((p, j) => p.evidence_id ? <button key={j} className="math-ref" aria-pressed={open?.id === p.evidence_id && open.text === p.text} title="Show where this number comes from" onClick={() => setOpen(open?.id === p.evidence_id && open.text === p.text ? null : { id: p.evidence_id!, text: p.text })}>{p.text}</button> : <span key={j}>{p.text}</span>)}</li>)}</ol>
      {open && <SourceCard evidenceId={open.id} active={open.text} runId={runId} detail={detail} distributor={distributor} />}
      <p className="muted small">Worked out in code, not by AI. Tap an underlined number to see its source.</p>
    </>}

    {disputed && <>
      <div className="section-eyebrow">Ready for their pushback</div>
      {rehearsal ? <div className="rebuttal"><small>{distributor} may say</small><p>“{rehearsal.predicted_rebuttal}”</p><small>Clawback answers</small><p>{rehearsal.answer}</p></div> : <p className="muted small">The comeback is prepared before the dispute is filed.</p>}
    </>}

    {others.length > 0 && <div className="section-eyebrow">Sources · {others.length}</div>}
    {others.map((e) => <details className="source-detail" key={e.id} open={e.kind === 'delivery' || e.kind === 'price'}>
      <summary><FileText /><span>{e.label}<small>{sourceTitle(e.kind, distributor)}</small></span><ChevronRight /></summary>
      <div className="source-preview"><SourceBody e={e} distributor={distributor} /></div>
    </details>)}
  </>
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

/** The source behind one clicked number: the charge's own evidence list first, then GET /evidence/{id}. */
function SourceCard({ evidenceId, active, runId, detail, distributor }: { evidenceId: string; active: string; runId: string | null; detail: ChargeDetail | null; distributor: string }) {
  const local = detail?.evidence.find((e) => e.id === evidenceId) ?? null
  const [fetched, setFetched] = useState<{ id: string; ev: Evidence | null } | null>(null)
  useEffect(() => {
    if (local) return
    let cancelled = false
    fetchEvidence(evidenceId, runId ?? undefined).then((ev) => !cancelled && setFetched({ id: evidenceId, ev }), () => !cancelled && setFetched({ id: evidenceId, ev: null }))
    return () => { cancelled = true }
  }, [local, evidenceId, runId])
  const ev = local ?? (fetched?.id === evidenceId ? fetched.ev : null)
  if (!ev) return <p className="muted small" role="status">{fetched?.id === evidenceId ? 'This source could not be loaded.' : 'Loading the source…'}</p>
  return <div className="source-card" role="region" aria-label={`Source: ${ev.label}`}><small>{ev.label} · {sourceTitle(ev.kind, distributor)}</small><SourceBody e={ev} active={active} distributor={distributor} /></div>
}
