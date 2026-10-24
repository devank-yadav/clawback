'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowRight, Check, ChevronDown, ChevronUp, CircleHelp, ClipboardCheck,
  CornerUpLeft, FileCheck2, Home, Info, Layers3, ReceiptText, RotateCcw,
  ShieldCheck, X,
} from 'lucide-react'
import { CAST } from '@/lib/cast'
import { dollars, share } from '@/lib/format'
import { useChargeDetail } from '@/lib/useChargeDetail'
import { useRunEvents } from '@/lib/useRunEvents'
import { selectWorkspace, type ChargeView, type Stage, type WorkspaceView } from '@/lib/workspace'
import { ChargeList, EvidencePanel, Status, type ChargeFilter } from './charge-workspace'

type Page = 'Overview' | 'Payments' | 'Approvals' | 'Rules'

export default function ClawbackApp() {
  const { state, answerQuestion, controllerDecides, startPayment, starting, awaitingPayment, reset: resetRun, source, error } = useRunEvents('demo')
  const view = useMemo(() => selectWorkspace(state, source), [state, source])
  const [page, setPage] = useState<Page>('Overview')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [role, setRole] = useState('Owner')
  const [note, setNote] = useState('')
  const [notice, setNotice] = useState('')
  const [dismissedFor, setDismissedFor] = useState<Stage | ''>('')
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const [brandOpen, setBrandOpen] = useState(false)
  const [breakdownOpen, setBreakdownOpen] = useState(false)
  const [filter, setFilter] = useState<ChargeFilter>('All')
  const workspaceRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (workspaceRef.current && !workspaceRef.current.contains(event.target as Node)) setWorkspaceOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const selected = view.charges.find((charge) => charge.id === selectedId) ?? null
  const detail = useChargeDetail(selected?.id ?? '', state.run?.run_id, source)
  const askedCharge = view.charges.find((charge) => charge.id === view.question?.charge_id)

  const stageMessage = stageFeedback(view)
  const feedback = notice || (dismissedFor !== view.stage ? stageMessage : '')

  function navigate(next: Page) {
    setPage(next)
    setSelectedId(null)
    setNotice('')
    setDismissedFor(view.stage)
  }
  function review(charge?: ChargeView) {
    setPage('Payments')
    setSelectedId(charge?.id ?? null)
  }
  function confirmRule() {
    if (role !== 'Owner' || !view.question) return
    answerQuestion(view.question.id)
  }
  function reset() {
    resetRun()
    setPage('Overview')
    setSelectedId(null)
    setNote('')
    setRole('Owner')
    setFilter('All')
    setBreakdownOpen(false)
    setDismissedFor('')
    setNotice('Fictional demo reset to its starting state.')
  }

  const remittance = view.remittance
  const totals = view.totals
  const taken = totals?.taken ?? remittance?.taken ?? 0
  const waiting = totals?.waiting ?? 0
  const splitCharge = view.charges.find((charge) => charge.status === 'Split decision')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="wordmark" onClick={() => navigate('Overview')} aria-label="Clawback overview">
          <span className="brand-mark"><CornerUpLeft /></span>clawback<span className="wordmark-dot">.</span>
        </button>

        <div className="workspace-wrap" ref={workspaceRef}>
          <button className="workspace" aria-expanded={workspaceOpen} aria-haspopup="menu" onClick={() => setWorkspaceOpen((open) => !open)}>
            <span className="workspace-avatar">P</span>
            <span>{CAST.brand}<small>Brand workspace</small></span>
            <ChevronDown />
          </button>
          {workspaceOpen && (
            <div className="workspace-menu" role="menu">
              <div className="workspace-menu-brand"><span className="workspace-avatar">P</span><span><strong>{CAST.brand}</strong><small>Fictional snack brand · Portland, OR</small></span></div>
              <button role="menuitem" onClick={() => { setBrandOpen(true); setWorkspaceOpen(false) }}><Info /> View brand details</button>
              <div className="menu-separator" />
              <label htmlFor="menu-role">Demo role<select id="menu-role" value={role} onChange={(event) => { setRole(event.target.value); setWorkspaceOpen(false) }}><option>Owner</option><option>Controller</option></select></label>
              <button role="menuitem" onClick={() => { reset(); setWorkspaceOpen(false) }}><RotateCcw /> Reset fictional demo</button>
            </div>
          )}
        </div>

        <span className="nav-label">Workspace</span>
        <nav aria-label="Primary navigation">
          {([{ title: 'Overview', icon: Home }, { title: 'Payments', icon: ReceiptText }, { title: 'Approvals', icon: ClipboardCheck }, { title: 'Rules', icon: Layers3 }] as const).map(({ title, icon: Icon }) => (
            <button key={title} className={`nav-item ${page === title ? 'active' : ''}`} onClick={() => navigate(title)} aria-current={page === title ? 'page' : undefined}>
              <Icon />{title}{title === 'Approvals' && view.stage === 'controller' && <span className="nav-count">1</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="quiet-note"><ShieldCheck /><p>A little clarity.<br />A lot more confidence.</p></div>
          <div className="demo-settings"><span className="demo-label"><i /> Fictional demo</span><span>{role === 'Owner' ? `${CAST.ownerFull} · Owner` : `${CAST.controllerFull} · Controller`}</span><span data-source={source}>{source === 'live' ? 'Live API data' : 'Fixture data · no backend'}</span></div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar"><span>Workspace <span className="slash">/</span> <strong>{page}</strong></span><span className="topbar-note"><span className="tiny-dot" /> Fictional scenario</span></header>
        <main className={`main-content ${selected ? 'with-panel' : ''}`}>
          <div className="page-heading">
            <div><div className="eyebrow">{CAST.brand}</div><h1>{page === 'Overview' ? 'A clearer picture of your payments.' : page}</h1><p>{page === 'Overview' ? overviewLine(view.stage, awaitingPayment) : page === 'Payments' ? `${remittance?.counterparty ?? 'Northmart'} · March payment · ${remittance?.invoice_id ?? 'INV-3102'}` : page === 'Approvals' ? 'Accounting remains separate from owner policy decisions.' : 'Reusable owner policies, with a clear audit trail.'}</p></div>
            {page === 'Overview' && (awaitingPayment || starting ? <button className="primary" disabled={starting} onClick={() => void startPayment()}>{starting ? 'Starting…' : 'Northmart pays'} <ArrowRight /></button> : <button className="primary" onClick={() => review()}>Review payment <ArrowRight /></button>)}
          </div>

          {error && <div className="feedback error" role="alert"><Info />{error}</div>}
          {feedback && <div className="feedback" role="status"><Check />{feedback}</div>}

          {page === 'Overview' && (
            <>
              <div className="overview-grid">
                <section className="payment-card surface">
                  <div className="card-top"><div className="company"><span className="northmart">N</span><div><h2>{remittance?.counterparty ?? 'Northmart'}</h2><p>March payment · {remittance?.invoice_id ?? 'INV-3102'}</p></div></div><span className="neutral-tag">{view.reviewed ? 'Reviewed' : 'Reviewing'}</span></div>
                  <div className="payment-story" aria-label="Payment summary">
                    <div><span>Invoiced</span><strong>{remittance ? dollars(remittance.expected) : '—'}</strong></div>
                    <div><span>Received</span><strong>{remittance ? dollars(remittance.received) : '—'}</strong></div>
                    <div className="deduction-gap"><span>Deducted · {remittance?.charge_count ?? 6} charges</span><strong>{remittance ? dollars(remittance.taken) : '—'}</strong><small>The gap between the invoice and payment.</small></div>
                  </div>
                  {remittance && <div className="payment-bar" role="img" aria-label={`${dollars(remittance.received)} received and ${dollars(remittance.taken)} deducted from ${dollars(remittance.expected)} invoiced`}><span style={{ width: `${share(remittance.received, remittance.expected)}%` }} /><span style={{ width: `${share(remittance.taken, remittance.expected)}%` }} /></div>}
                  {remittance && <div className="bar-legend"><span><i className="received-dot" /> Received <strong>{dollars(remittance.received)}</strong></span><span><i className="deducted-dot" /> Deducted <strong>{dollars(remittance.taken)}</strong></span></div>}
                  <button className="breakdown-toggle" aria-expanded={breakdownOpen} onClick={() => setBreakdownOpen((open) => !open)}>{breakdownOpen ? 'Hide breakdown' : 'Show breakdown'} {breakdownOpen ? <ChevronUp /> : <ChevronDown />}</button>
                  <div className={`breakdown-region ${breakdownOpen ? 'open' : ''}`} aria-hidden={!breakdownOpen}>
                    <div className="allocation-bar" role="img" aria-label={`${dollars(totals?.disputed ?? 0)} disputed, ${dollars(totals?.accepted ?? 0)} accepted, ${dollars(waiting)} pending`}><span className="disputed-allocation" style={{ width: `${share(totals?.disputed ?? 0, taken)}%` }} /><span className="accepted-allocation" style={{ width: `${share(totals?.accepted ?? 0, taken)}%` }} />{waiting > 0 && <span className="pending-allocation" style={{ width: `${share(waiting, taken)}%` }} />}</div>
                    <div className="allocation-legend"><span><i className="disputed-dot" />Disputed <strong>{dollars(totals?.disputed ?? 0)}</strong></span><span><i className="accepted-dot" />Accepted <strong>{dollars(totals?.accepted ?? 0)}</strong></span><span><i className="pending-dot" />Pending <strong>{dollars(waiting)}</strong></span></div>
                    {splitCharge && splitCharge.accepted !== null && splitCharge.disputed !== null && <p>{splitCharge.id} is one {dollars(splitCharge.amount)} charge: {dollars(splitCharge.accepted)} accepted and {dollars(splitCharge.disputed)} disputed.</p>}
                  </div>
                  <div className="card-bottom"><span><FileCheck2 /> {view.reviewed ? `All ${view.charges.length} charges checked against fictional evidence` : 'Checking each charge against fictional evidence…'}</span><button className="text-button" onClick={() => review()}>View payment <ArrowRight /></button></div>
                </section>

                <AttentionCard waitingForPayment={awaitingPayment} view={view} onReviewCharge={() => review(askedCharge)} onReviewAccounting={() => navigate('Approvals')} onViewPayment={() => review()} />
              </div>
              <Summary view={view} />
              <section className="surface preview-section"><div className="list-heading"><div><h2>Behind the deduction</h2><p>Every charge has a factual status and readable source.</p></div><button className="text-button" onClick={() => review()}>View all charges <ArrowRight /></button></div><ChargeList charges={view.charges} onSelect={review} preview /></section>
            </>
          )}

          {page === 'Payments' && (
            <>
              <section className="payment-strip" aria-label="Payment totals"><div><small>Invoiced</small><strong>{remittance ? dollars(remittance.expected) : '—'}</strong></div><div><small>Received</small><strong>{remittance ? dollars(remittance.received) : '—'}</strong></div><div className="strip-deduction"><small>Deducted · {remittance?.charge_count ?? 6} charges</small><strong>{remittance ? dollars(remittance.taken) : '—'}</strong><span>Invoice-to-payment gap</span></div></section>
              <Summary view={view} compact />
              <div className="payment-workspace">
                <section className="surface charge-main"><div className="list-heading"><div><h2>Payment charges</h2><p>Select a charge to see evidence and allocations.</p></div></div><ChargeList charges={view.charges} selected={selected?.id} onSelect={(charge) => setSelectedId(charge.id)} filter={filter} onFilterChange={setFilter} /><div className="table-footer"><ShieldCheck /> {view.disputeLabel}</div></section>
                {selected && <EvidencePanel key={selected.id} runId={state.run?.run_id} live={source === 'live'} charge={selected} detail={detail} question={view.question} rule={view.rule} stage={view.stage} onClose={() => setSelectedId(null)} onConfirm={confirmRule} role={role} />}
              </div>
            </>
          )}

          {page === 'Rules' && <RulesView view={view} review={review} askedCharge={askedCharge} />}
          {page === 'Approvals' && <ApprovalsView view={view} source={source} role={role} note={note} setNote={setNote} review={review} askedCharge={askedCharge} onDecide={controllerDecides} />}
        </main>
      </div>

      {brandOpen && <div className="dialog-backdrop" role="presentation" onMouseDown={() => setBrandOpen(false)}><section className="brand-dialog" role="dialog" aria-modal="true" aria-labelledby="brand-title" onMouseDown={(event) => event.stopPropagation()}><button autoFocus className="icon-button dialog-close" onClick={() => setBrandOpen(false)} aria-label="Close brand details"><X /></button><span className="workspace-avatar large">P</span><div><div className="eyebrow">Fictional brand</div><h2 id="brand-title">{CAST.brand}</h2><p>Illustrative consumer snack brand based in Portland, Oregon. This demo uses no connected accounting system or live documents.</p></div><dl><div><dt>Owner</dt><dd>{CAST.ownerFull}</dd></div><div><dt>Controller</dt><dd>{CAST.controllerFull}</dd></div><div><dt>Customer</dt><dd>Northmart</dd></div></dl><button className="secondary" onClick={() => setBrandOpen(false)}>Done</button></section></div>}
    </div>
  )
}

function overviewLine(stage: Stage, awaitingPayment: boolean) {
  if (awaitingPayment) return 'Waiting for Northmart’s payment. Nothing is checked until it arrives.'
  if (stage === 'checking') return 'Your March payment is being checked against the deal.'
  if (stage === 'owner') return 'Your March payment is reviewed. One policy decision needs your perspective.'
  return 'Your March payment is reviewed.'
}

/** What the stream says just happened. Never worded as done until the matching event has arrived. */
function stageFeedback(view: WorkspaceView) {
  if (view.stage === 'controller' && view.rule) return `Rule saved by ${CAST.ownerFull}. The accounting proposal is ready for ${CAST.controllerFull}.`
  if (view.stage === 'refused') return `${CAST.controllerFull} refused the proposal. It remains unposted.`
  if (view.stage === 'posted') {
    if (view.postingLabel === 'Simulated posted') return `${CAST.controllerFull} recorded the simulated accounting approval. No real entry was posted.`
    if (view.postingLabel.startsWith('Posted')) return `${CAST.controllerFull} approved. The credit memo posted to the QuickBooks sandbox.`
    return `${CAST.controllerFull} approved. Waiting for the posting to be confirmed.`
  }
  return ''
}

function AttentionCard({ waitingForPayment, view, onReviewCharge, onReviewAccounting, onViewPayment }: { waitingForPayment: boolean; view: WorkspaceView; onReviewCharge: () => void; onReviewAccounting: () => void; onViewPayment: () => void }) {
  const { stage, approval, question } = view
  const open = stage === 'owner' || stage === 'controller'
  const controller = stage !== 'checking' && stage !== 'owner'
  const heading = waitingForPayment ? 'Waiting for the payment' : stage === 'checking' ? 'Checking your charges' : stage === 'owner' ? 'What counts as enough notice?' : stage === 'controller' ? 'Ready for accounting review?' : stage === 'posted' ? 'All reviewed. All clear.' : 'Proposal left unposted.'
  const body = waitingForPayment
    ? 'Press “Northmart pays” to start. Clawback checks each charge once the money arrives.'
    : stage === 'checking'
    ? 'Clawback is reading the deal and the sales records for each charge.'
    : stage === 'owner'
      ? question?.text ?? ''
      : stage === 'controller'
        ? approval ? `${dollars(approval.amount)} in accepted charges awaits ${CAST.controllerFull}’s separate approval.` : 'The accounting proposal is being prepared.'
        : stage === 'posted'
          ? view.postingLabel === 'Simulated posted' ? `${CAST.controllerFull} recorded a simulated approval. No real entry was created.` : `${CAST.controllerFull} approved. ${view.postingLabel}.`
          : `${CAST.controllerFull} recorded a refusal. No entry was posted.`
  return (
    <section className="attention-card surface">
      <div className="attention-heading"><h2>Needs your attention</h2><span className="count-badge">{open ? '1' : '0'}</span></div>
      <div className="attention-icon">{controller ? <ClipboardCheck /> : <CircleHelp />}</div>
      <div className="eyebrow">{controller ? 'Controller approval' : stage === 'owner' ? 'Owner policy decision' : 'In progress'}</div>
      <h3>{heading}</h3>
      <p>{body}</p>
      <button className="secondary full" onClick={stage === 'owner' ? onReviewCharge : controller ? onReviewAccounting : onViewPayment}>{stage === 'owner' ? 'Review proposed rule' : controller ? 'Review accounting proposal' : 'View payment'} <ArrowRight /></button>
    </section>
  )
}

function Summary({ view, compact = false }: { view: WorkspaceView; compact?: boolean }) {
  const waiting = view.totals?.waiting ?? 0
  const undecided = view.totals?.undecided ?? 0
  return <section className={`summary-grid ${compact ? 'compact' : ''}`} aria-label="Deduction decisions"><div><span>Disputed</span><strong>{dollars(view.totals?.disputed ?? 0)}</strong><small>Being challenged · Not recovered</small></div><div><span>Accepted</span><strong>{dollars(view.totals?.accepted ?? 0)}</strong><small>Supported by agreement or owner policy</small></div><div><span>{waiting > 0 ? 'Needs input' : 'Pending'}</span><strong>{dollars(waiting)}</strong><small>{waiting > 0 ? 'Owner policy decision required' : undecided > 0 ? 'Still checking charges' : 'All charges classified'}</small></div></section>
}

function RulesView({ view, review, askedCharge }: { view: WorkspaceView; review: (charge?: ChargeView) => void; askedCharge?: ChargeView }) {
  const { rule, ruleCharges } = view
  if (!rule) return <section className="surface simple-view"><div className="list-heading"><div><h2>Owner-approved rules</h2><p>Policy decisions do not authorize accounting entries.</p></div></div><div className="empty-state"><Layers3 /><h2>No active owner policies</h2><p>{view.stage === 'owner' ? `${CAST.ownerFull} must answer the open display-fee question.` : 'No charge has needed an owner policy yet.'}</p>{askedCharge && <button className="primary" onClick={() => review(askedCharge)}>Review proposed rule <ArrowRight /></button>}</div></section>
  return <section className="surface simple-view"><div className="list-heading"><div><h2>Owner-approved rules</h2><p>Policy decisions do not authorize accounting entries.</p></div></div><div className="rule-content"><Status value="Accepted" /><h2>{rule.label} · Display fees</h2><p>{rule.summary}</p><div className="rule-meta"><span>Distributor<strong>{rule.counterparty}</strong></span><span>Approved by<strong>{rule.approver_role === 'owner' ? `${CAST.ownerFull} · Owner` : rule.approver}</strong></span><span>Applied to<strong>{ruleCharges.length ? ruleCharges.map((c) => `${c.id} · ${c.accepted !== null ? dollars(c.accepted) : ''} accepted`).join(', ') : 'No charge yet'}</strong></span></div>{ruleCharges[0] && <button className="secondary" onClick={() => review(ruleCharges[0])}>View supporting evidence</button>}</div></section>
}

function ApprovalsView({ view, source, role, note, setNote, review, askedCharge, onDecide }: { view: WorkspaceView; source: 'fixture' | 'live'; role: string; note: string; setNote: (value: string) => void; review: (charge?: ChargeView) => void; askedCharge?: ChargeView; onDecide: (approve: boolean, note: string | null) => void }) {
  const { approval, stage, postingProblem: problem } = view
  if (stage === 'checking' || stage === 'owner') return <section className="surface simple-view"><div className="empty-state"><ClipboardCheck /><h2>An owner policy decision comes first</h2><p>{CAST.ownerFull} must resolve the display fee before {CAST.controllerFull} can review accounting.</p>{askedCharge && <button className="primary" onClick={() => review(askedCharge)}>Review owner question <ArrowRight /></button>}</div></section>
  if (!approval) return <section className="surface simple-view"><div className="empty-state"><ClipboardCheck /><h2>Preparing the accounting proposal</h2><p>The accepted charges are being gathered for {CAST.controllerFull}.</p></div></section>
  // What the API recorded wins once the approval event has arrived; the textarea is only a fallback.
  const shownNote = approval.note || note.trim()
  return <section className="surface simple-view"><div className="list-heading"><div><h2>Accounting proposal</h2><p>{view.remittance?.counterparty ?? 'Northmart'} · March payment · {view.remittance?.invoice_id ?? 'INV-3102'}</p></div></div><div className="rule-content"><Status value={view.postingLabel} /><div className="proposal-amount">{dollars(approval.amount)}</div><h2>Recognize accepted deductions</h2><p>Agreement- or owner-policy-supported charges only. The disputed {dollars(view.totals?.disputed ?? 0)} remains unresolved.</p><div className="proposal-lines">{view.proposalLines.map((line) => <span key={line.chargeId}>{line.label}<strong>{dollars(line.amount)}</strong></span>)}</div>{approval.status === 'pending' ? <><div className="approval-notice"><ShieldCheck /><span><strong>Separate controller approval required</strong><small>{CAST.ownerFull} approved the policy, not this entry. Nothing is posted.</small></span></div><label className="note-label" htmlFor="controller-note">Controller note <span>(required to refuse)</span></label><textarea id="controller-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add context for the accounting decision" /><div className="approval-actions"><button className="primary" disabled={role !== 'Controller'} onClick={() => onDecide(true, note.trim() || null)}>{source === 'live' ? 'Approve credit memo' : 'Approve & simulate posting'}</button><button className="secondary" disabled={role !== 'Controller' || !note.trim()} onClick={() => onDecide(false, note.trim())}>Refuse · Leave unposted</button></div>{role !== 'Controller' && <p className="role-hint">Switch to Controller in the Peak Bar Co. menu to record this decision.</p>}</> : <div className="feedback inline" role="status"><Check />{approval.status === 'approved' ? (view.postingLabel === 'Simulated posted' ? `Simulated approval recorded by ${CAST.controllerFull}. No real entry was posted.` : `Approval recorded by ${CAST.controllerFull}. ${view.postingLabel}.${problem ? ` ${problem}` : ''}`) : `Refusal recorded by ${CAST.controllerFull}. The proposal remains unposted.${shownNote ? ` Note: “${shownNote}”` : ''}`}</div>}</div></section>
}
