'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { ArrowRight, Check, CircleHelp, ClipboardCheck, FileCheck2, Info, KeyRound, Layers3, ShieldCheck } from 'lucide-react'
import AppShell, { DistributorMark, type View } from '@/components/shell/AppShell'
import { firstName, useCurrentAccount, withAccount } from '@/lib/accounts'
import { fetchLookback, fetchOverview } from '@/lib/api'
import { anyDay, dollars, money, monthLabel, percent, share } from '@/lib/format'
import { askAdminToken, LIMIT_ADMIN_REASON, useSession, type Role } from '@/lib/session'
import type { Account, Lookback, Overview, RunValue } from '@/lib/types'
import { useFetched } from '@/lib/useFetched'
import { useRunEvents } from '@/lib/useRunEvents'
import { approvedBy, postingSentence, selectWorkspace, type ChargeView, type WorkspaceView } from '@/lib/workspace'
import { ChargeList, EvidencePanel, Status, type ChargeFilter } from './charge-workspace'
import { MonthlyChart, TypeBars } from './charts'
import { LookbackCard, PacketLink, ValueStrip } from './impact'
import { RunProgress } from './run-progress'

const VIEWS: View[] = ['overview', 'payments', 'approvals', 'rules']
const CRUMB: Record<View, string> = { overview: 'Overview', payments: 'Payments', approvals: 'Approvals', rules: 'Rules' }

/** The brand workspace at /workspace?account=…&view=…: the account and the view live in the URL, so every link and reload keeps them. */
export default function ClawbackApp() {
  const { account, accounts, error } = useCurrentAccount()
  const param = useSearchParams().get('view')
  const view: View = VIEWS.includes(param as View) ? (param as View) : 'overview'
  if (!account) {
    return (
      <AppShell account={null} accounts={accounts} active={view} crumb={CRUMB[view]}>
        <main className="main-content">
          {error ? <div className="feedback error" role="alert"><Info />{error}</div> : <p className="muted" role="status">Loading your accounts…</p>}
        </main>
      </AppShell>
    )
  }
  return <Workspace key={account.id} account={account} accounts={accounts} view={view} />
}

function Workspace({ account, accounts, view }: { account: Account; accounts: Account[] | null; view: View }) {
  const run = useRunEvents(account.id)
  const { state, runId, answerQuestion, decideApproval, startPayment, starting, limited, awaitingPayment, refresh, error } = run
  const ws = useMemo(() => selectWorkspace(state, account), [state, account])
  const { role } = useSession()
  const router = useRouter()
  // ?charge= opens a charge from a link; a click on the list overrides it.
  const chargeParam = useSearchParams().get('charge')
  const [picked, setPicked] = useState<{ id: string | null } | null>(null)
  const selectedId = picked ? picked.id : chargeParam
  const setSelectedId = (id: string | null) => setPicked({ id })
  const [note, setNote] = useState('')
  const [filter, setFilter] = useState<ChargeFilter>('All')
  const distributor = account.distributor.name

  // The overview's numbers move as the run does (a dispute filed, a memo posted), so it is read again at each step.
  const overviewKey = `${runId}:${state.run?.status}:${state.dispute?.status}:${state.approval?.status}:${state.ledger.length}:${ws.reviewed}`
  const loadOverview = useMemo(() => () => fetchOverview(account.id), [account.id])
  const overview = useFetched<Overview>(loadOverview, overviewKey)
  // The lookback is history: read once per account (and on reset). null = this API doesn't have it, so the card hides.
  const loadLookback = useMemo(() => () => fetchLookback(account.id), [account.id])
  const lookback = useFetched<Lookback | null>(loadLookback)
  const value = ws.value ?? overview.data?.current.value ?? null

  const selected = view === 'payments' ? (ws.charges.find((charge) => charge.id === selectedId) ?? null) : null
  const askedCharge = ws.charges.find((charge) => charge.id === ws.question?.charge_id)
  const feedback = stageFeedback(ws, account)
  const payLabel = `${distributor} pays`
  const pendingCharges = ws.remittance ? ws.remittance.charge_count - ws.charges.length : 0

  function onReset() {
    setSelectedId(null)
    setNote('')
    setFilter('All')
    refresh()
    overview.reload()
    lookback.reload()
  }

  const heading = view === 'overview'
    ? { title: 'Overview', line: `Deductions from ${distributor}, last six months.` }
    : view === 'payments'
      ? { title: `${monthLabel(account.invoice.month)} payment`, line: `${distributor} · Invoice ${ws.remittance?.invoice_id ?? account.invoice.id}` }
      : view === 'approvals'
        ? { title: 'Approvals', line: `Accounting entries wait for ${account.brand.owner.name}’s yes. Policy answers don’t post anything.` }
        : { title: 'Rules', line: `Answers ${account.brand.owner.name} gave once, applied every time after.` }

  const payButton = <button className="primary" disabled={starting} onClick={() => void startPayment()}>{starting ? 'Waiting for the deposit…' : payLabel} <ArrowRight /></button>
  const reviewHref = withAccount('/workspace', account.id, { view: 'payments' })

  return (
    <AppShell account={account} accounts={accounts} active={view} crumb={CRUMB[view]} approvalsWaiting={ws.stage === 'approval' && ws.approval?.status === 'pending'} onReset={onReset}>
      <main className={`main-content ${selected ? 'with-panel' : ''}`}>
        <div className="page-heading">
          <div><div className="eyebrow">{account.brand.name}</div><h1>{heading.title}</h1><p>{heading.line}</p></div>
          {(view === 'overview' || view === 'payments') && (awaitingPayment || starting ? payButton : view === 'overview' && <Link className="primary" href={reviewHref}>Open analysis <ArrowRight /></Link>)}
        </div>

        {error && <div className="feedback error" role="alert"><Info />{error}</div>}
        {limited && <div className="feedback notice" role="status"><Info /><span>{limited}</span><button className="text-button" onClick={() => askAdminToken(LIMIT_ADMIN_REASON, () => void startPayment())}><KeyRound /> Use admin token</button></div>}
        {feedback && view !== 'overview' && <div className={`feedback ${ws.stage === 'refused' ? 'notice' : ''}`} role="status">{ws.stage === 'refused' ? <Info /> : <Check />}{feedback}</div>}

        {view === 'overview' && state.run?.status === 'started' && <RunProgress account={account} state={state} ws={ws} />}
        {view === 'overview' && <OverviewPage account={account} overview={overview.data} lookback={lookback.data} value={value} overviewError={overview.error} ws={ws} awaitingPayment={awaitingPayment} reviewHref={reviewHref} feedback={feedback} onOpenCharge={(id) => router.push(withAccount('/workspace', account.id, { view: 'payments', charge: id }))} />}

        {view === 'payments' && (
          <>
            <PaymentStrip account={account} ws={ws} awaitingPayment={awaitingPayment} />
            {value && !awaitingPayment && <ValueStrip value={value} />}
            {/* With a run, the flow's meters inside RunProgress show these totals; without one, the summary does. */}
            {!state.run && <Summary ws={ws} compact />}
            <RunProgress account={account} state={state} ws={ws} />
            <div className="payment-workspace">
              <section className="surface charge-main"><div className="list-heading"><div><h2>Charges</h2><p>{awaitingPayment ? `Waiting for ${distributor}’s payment.` : 'Select a charge to see its evidence and how it was decided.'}</p></div></div><ChargeList charges={ws.charges} selected={selected?.id} onSelect={(charge) => setSelectedId(charge.id)} filter={filter} onFilterChange={setFilter} waiting={awaitingPayment} pending={pendingCharges} /><div className="table-footer"><ShieldCheck /> {ws.disputeId ? <>{ws.disputeLabel} · <a href={withAccount('/portal', account.id, { dispute: ws.disputeId })} target="_blank" rel="noreferrer">Open on {account.distributor.portal_name}</a><PacketLink disputeId={ws.disputeId} /></> : ws.disputeLabel}</div></section>
              {selected && <EvidencePanel key={selected.id} account={account} state={state} runId={runId} charge={selected} question={ws.question} rule={ws.rule} stage={ws.stage} role={role} onClose={() => setSelectedId(null)} onAnswer={answerQuestion} />}
            </div>
          </>
        )}

        {view === 'rules' && <RulesView account={account} ws={ws} askedCharge={askedCharge} reviewHref={reviewHref} />}
        {view === 'approvals' && <ApprovalsView account={account} ws={ws} role={role} note={note} setNote={setNote} reviewHref={reviewHref} onDecide={decideApproval} />}
      </main>
    </AppShell>
  )
}

/** What the stream says just happened. Never worded as done until the matching event has arrived. */
function stageFeedback(ws: WorkspaceView, account: Account) {
  const owner = account.brand.owner.name
  if (ws.stage === 'approval' && ws.rule) return `Rule saved by ${owner}. The accounting entry is ready for your approval.`
  if (ws.stage === 'refused') return `${owner} held the entry. Nothing was posted.`
  if (ws.stage === 'posted') return `${approvedBy(ws, owner)}. ${postingSentence(ws)}`
  return ''
}

function statusWord(ws: WorkspaceView, awaitingPayment: boolean, overview: Overview | null): string {
  if (awaitingPayment) return 'Waiting for payment'
  if (!ws.remittance) return overview ? overview.current.status.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : 'Loading'
  if (!ws.reviewed) return 'Analyzing'
  if (ws.stage === 'owner') return 'Needs your answer'
  if (ws.stage === 'approval') return 'Needs your approval'
  if (ws.stage === 'refused') return 'Entry refused'
  if (ws.stage === 'posted') return 'Complete'
  return 'Reviewed'
}

function OverviewPage({ account, overview, lookback, value, overviewError, ws, awaitingPayment, reviewHref, feedback, onOpenCharge }: { account: Account; overview: Overview | null; lookback: Lookback | null; value: RunValue | null; overviewError: string | null; ws: WorkspaceView; awaitingPayment: boolean; reviewHref: string; feedback: string; onOpenCharge: (id: string) => void }) {
  const k = overview?.kpis
  const tiles: { label: string; value: string; note?: string; tone?: string }[] = k ? [
    { label: 'Invoiced', value: money(k.invoiced_6m), note: 'Last 6 months' },
    { label: 'Collected', value: money(k.collected_6m) },
    { label: 'Deducted', value: money(k.deducted_6m), tone: 'deducted' },
    { label: 'Recovered', value: money(k.recovered_6m), tone: 'good' },
    { label: 'Recovery rate', value: percent(k.recovery_rate), note: 'Of disputed money won back' },
    { label: 'Open disputes', value: String(k.open_disputes) },
    { label: 'Open balance', value: money(k.open_balance), note: 'Still owed by the distributor' },
  ] : []

  return (
    <>
      {overviewError && <div className="feedback error" role="alert"><Info />{overviewError}</div>}
      {feedback && <div className={`feedback ${ws.stage === 'refused' ? 'notice' : ''}`} role="status">{ws.stage === 'refused' ? <Info /> : <Check />}{feedback}</div>}
      <section className="kpi-grid" aria-label="Last six months">
        {k ? tiles.map((t) => <div key={t.label} className={`kpi surface ${t.tone ?? ''}`}><span>{t.label}</span><strong>{t.value}</strong>{t.note && <small>{t.note}</small>}</div>) : Array.from({ length: 7 }, (_, i) => <div key={i} className="kpi surface skeleton" aria-hidden><span /><strong /></div>)}
      </section>

      {value && !awaitingPayment && <ValueStrip value={value} />}
      <div className="overview-grid">
        <CurrentPayment account={account} overview={overview} ws={ws} awaitingPayment={awaitingPayment} reviewHref={reviewHref} />
        <AttentionCard account={account} ws={ws} awaitingPayment={awaitingPayment} reviewHref={reviewHref} />
      </div>

      {lookback && <LookbackCard lookback={lookback} distributor={account.distributor.name} />}

      <div className="insight-grid">
        <section className="surface chart-card" aria-labelledby="months-h">
          <div className="card-heading"><h2 id="months-h">Invoiced, paid and deducted</h2><p>By month</p></div>
          {overview ? <MonthlyChart months={overview.months} /> : <div className="chart-skeleton" aria-hidden />}
        </section>
        <section className="surface chart-card" aria-labelledby="types-h">
          <div className="card-heading"><h2 id="types-h">Deductions by type</h2><p>Last six months</p></div>
          {overview ? <TypeBars rows={overview.deductions_by_type} /> : <div className="chart-skeleton short" aria-hidden />}
        </section>
      </div>

      <section className="surface preview-section" aria-labelledby="rem-h">
        <div className="list-heading"><div><h2 id="rem-h">Recent remittances</h2><p>Payments from {account.distributor.name} and what was taken out of each.</p></div></div>
        {overview ? (
          <div className="row-table-wrap">
            <table className="row-table remittance-table">
              <thead><tr><th scope="col">Date</th><th scope="col">Invoice</th><th scope="col" className="num">Paid</th><th scope="col" className="num">Deducted</th></tr></thead>
              <tbody>{overview.recent_remittances.map((r, i) => <tr key={`${r.invoice}-${i}`}><td>{anyDay(r.date)}</td><td>{r.invoice}</td><td className="num">{dollars(r.paid)}</td><td className="num deducted">{dollars(r.deducted)}</td></tr>)}</tbody>
            </table>
            {overview.recent_remittances.length === 0 && <p className="muted small table-empty">No payments yet.</p>}
          </div>
        ) : <p className="muted small table-empty">Loading…</p>}
      </section>

      {ws.charges.length > 0 && <section className="surface preview-section"><div className="list-heading"><div><h2>This payment’s charges</h2><p>Each one checked against the deal, with its source.</p></div><Link className="text-button" href={reviewHref}>All charges <ArrowRight /></Link></div><ChargeList charges={ws.charges} onSelect={(c) => onOpenCharge(c.id)} preview /></section>}
    </>
  )
}

function CurrentPayment({ account, overview, ws, awaitingPayment, reviewHref }: { account: Account; overview: Overview | null; ws: WorkspaceView; awaitingPayment: boolean; reviewHref: string }) {
  const r = ws.remittance
  const totals = ws.totals
  const taken = totals?.taken ?? r?.taken ?? 0
  const waiting = totals?.waiting ?? 0
  const invoiceId = r?.invoice_id ?? overview?.current.invoice ?? account.invoice.id
  const expected = r?.expected ?? overview?.current.expected ?? account.invoice.expected
  return (
    <section className="payment-card surface">
      <div className="card-top"><div className="company"><DistributorMark account={account} /><div><h2>{account.distributor.name}</h2><p>{monthLabel(account.invoice.month)} · {invoiceId}</p></div></div><span className="neutral-tag">{statusWord(ws, awaitingPayment, overview)}</span></div>
      <div className="payment-story" aria-label="Payment summary">
        <div><span>Invoiced</span><strong>{dollars(expected)}</strong></div>
        <div><span>Received</span><strong>{r ? dollars(r.received) : '—'}</strong>{!r && <small>Not paid yet</small>}</div>
        <div className="deduction-gap"><span>Deducted{r ? ` · ${r.charge_count} charges` : ''}</span><strong>{r ? dollars(r.taken) : '—'}</strong><small>{r ? 'The gap between the invoice and the payment.' : 'Known once the payment arrives.'}</small></div>
      </div>
      {r && <div className="payment-bar" role="img" aria-label={`${dollars(r.received)} received and ${dollars(r.taken)} deducted from ${dollars(r.expected)} invoiced`}><span style={{ width: `${share(r.received, r.expected)}%` }} /><span style={{ width: `${share(r.taken, r.expected)}%` }} /></div>}
      {r && totals && <>
        <div className="allocation-bar" role="img" aria-label={`${dollars(totals.disputed)} disputed, ${dollars(totals.accepted)} accepted, ${dollars(waiting)} waiting`}><span className="disputed-allocation" style={{ width: `${share(totals.disputed, taken)}%` }} /><span className="accepted-allocation" style={{ width: `${share(totals.accepted, taken)}%` }} />{waiting > 0 && <span className="pending-allocation" style={{ width: `${share(waiting, taken)}%` }} />}</div>
        <div className="allocation-legend"><span><i className="disputed-dot" />Disputing <strong>{dollars(totals.disputed)}</strong></span><span><i className="accepted-dot" />Accepted <strong>{dollars(totals.accepted)}</strong></span><span><i className="pending-dot" />Waiting on you <strong>{dollars(waiting)}</strong></span></div>
      </>}
      <div className="card-bottom"><span><FileCheck2 /> {awaitingPayment ? `Each charge is checked against the deal when ${account.distributor.name} pays.` : ws.reviewed ? `All ${ws.charges.length} charges checked against the deal` : 'Checking each charge against the deal…'}</span>{!awaitingPayment && <Link className="text-button" href={reviewHref}>Open analysis <ArrowRight /></Link>}</div>
    </section>
  )
}

function AttentionCard({ account, ws, awaitingPayment, reviewHref }: { account: Account; ws: WorkspaceView; awaitingPayment: boolean; reviewHref: string }) {
  const { stage, approval, question } = ws
  const owner = account.brand.owner.name
  const open = (stage === 'owner' && !!question && !question.answer) || (stage === 'approval' && approval?.status === 'pending')
  const accounting = stage !== 'checking' && stage !== 'owner'
  const heading = awaitingPayment ? 'Nothing yet' : stage === 'checking' ? 'Checking your charges' : stage === 'owner' ? 'One question for you' : stage === 'approval' ? 'Ready for accounting' : stage === 'posted' ? 'All done' : 'Entry refused'
  const body = awaitingPayment
    ? `When ${account.distributor.name} pays, Clawback checks every deduction against the deal.`
    : stage === 'checking'
      ? 'Reading the deal, the emails and the records for each charge.'
      : stage === 'owner'
        ? question?.text ?? ''
        : stage === 'approval'
          ? approval ? `${dollars(approval.amount)} in accepted charges waits for your approval.` : 'The accounting entry is being prepared.'
          : stage === 'posted'
            ? `${approvedBy(ws, owner)}. ${postingSentence(ws)}`
            : `${owner} held it. Nothing was posted.${approval?.note ? ` “${approval.note}”` : ''}`
  const href = stage === 'owner' ? withAccount('/workspace', account.id, { view: 'payments' }) : accounting ? withAccount('/workspace', account.id, { view: 'approvals' }) : reviewHref
  return (
    <section className="attention-card surface">
      <div className="attention-heading"><h2>Needs your attention</h2><span className="count-badge">{open ? '1' : '0'}</span></div>
      <div className="attention-icon">{accounting ? <ClipboardCheck /> : <CircleHelp />}</div>
      <div className="eyebrow">{stage === 'checking' ? 'Status' : `For ${firstName(owner)} · Admin`}</div>
      <h3>{heading}</h3>
      <p>{body}</p>
      {!awaitingPayment && <Link className="secondary full" href={href}>{stage === 'owner' ? 'Answer the question' : accounting ? 'Review the entry' : 'Open analysis'} <ArrowRight /></Link>}
    </section>
  )
}

function PaymentStrip({ account, ws, awaitingPayment }: { account: Account; ws: WorkspaceView; awaitingPayment: boolean }) {
  const r = ws.remittance
  return <section className="payment-strip" aria-label="Payment totals"><div><small>Invoiced</small><strong>{dollars(r?.expected ?? account.invoice.expected)}</strong></div><div><small>Received</small><strong>{r ? dollars(r.received) : '—'}</strong>{awaitingPayment && <span>Not paid yet</span>}</div><div className="strip-deduction"><small>Deducted{r ? ` · ${r.charge_count} charges` : ''}</small><strong>{r ? dollars(r.taken) : '—'}</strong><span>Invoice-to-payment gap</span></div></section>
}

function Summary({ ws, compact = false }: { ws: WorkspaceView; compact?: boolean }) {
  const waiting = ws.totals?.waiting ?? 0
  const undecided = ws.totals?.undecided ?? 0
  return <section className={`summary-grid ${compact ? 'compact' : ''}`} aria-label="Deduction decisions"><div><span>Disputing</span><strong>{dollars(ws.totals?.disputed ?? 0)}</strong><small>Being challenged · not recovered yet</small></div><div><span>Accepted</span><strong>{dollars(ws.totals?.accepted ?? 0)}</strong><small>Backed by the deal or your rule</small></div><div><span>{waiting > 0 ? 'Waiting on you' : 'Pending'}</span><strong>{dollars(waiting)}</strong><small>{waiting > 0 ? 'One answer from you' : undecided > 0 ? 'Still checking charges' : 'Every charge decided'}</small></div></section>
}

function RulesView({ account, ws, askedCharge, reviewHref }: { account: Account; ws: WorkspaceView; askedCharge?: ChargeView; reviewHref: string }) {
  const { rule, ruleCharges } = ws
  const owner = account.brand.owner.name
  if (!rule) return <section className="surface simple-view"><div className="list-heading"><div><h2>Saved rules</h2><p>A rule decides; it never posts an accounting entry.</p></div></div><div className="empty-state"><Layers3 /><h2>No rules yet</h2><p>{ws.stage === 'owner' ? `${owner} has one question to answer. The answer is saved as a rule.` : `When the deal leaves a charge to judgment, ${owner} answers once and it becomes a rule.`}</p>{askedCharge && <Link className="primary" href={reviewHref}>Answer the question <ArrowRight /></Link>}</div></section>
  return <section className="surface simple-view"><div className="list-heading"><div><h2>Saved rules</h2><p>A rule decides; it never posts an accounting entry.</p></div></div><div className="rule-content"><Status value="Accepted" /><h2>{rule.label}</h2><p>{rule.summary}</p><div className="rule-meta"><span>Distributor<strong>{rule.counterparty}</strong></span><span>Set by<strong>{`${rule.approver} · Admin`}</strong></span><span>Applied to<strong>{ruleCharges.length ? ruleCharges.map((c) => `${c.ref} · ${c.accepted !== null ? dollars(c.accepted) : ''} accepted`).join(', ') : 'No charge yet'}</strong></span></div>{ruleCharges[0] && <Link className="secondary" href={reviewHref}>See the evidence</Link>}</div></section>
}

function ApprovalsView({ account, ws, role, note, setNote, reviewHref, onDecide }: { account: Account; ws: WorkspaceView; role: Role | null; note: string; setNote: (value: string) => void; reviewHref: string; onDecide: (approve: boolean, note: string | null, autoPost: boolean) => void }) {
  const { approval, stage } = ws
  const owner = account.brand.owner.name
  const [autoPost, setAutoPost] = useState(false)
  if (stage === 'checking' || stage === 'owner') return <section className="surface simple-view"><div className="empty-state"><ClipboardCheck /><h2>{stage === 'owner' ? 'Your answer comes first' : 'Nothing to approve yet'}</h2><p>{stage === 'owner' ? `${owner} answers the open question, then reviews the accounting entry.` : `When every charge is decided, the accepted ones come to ${owner} as one credit memo.`}</p>{stage === 'owner' && <Link className="primary" href={reviewHref}>Go to the question <ArrowRight /></Link>}</div></section>
  if (!approval) return <section className="surface simple-view"><div className="empty-state"><ClipboardCheck /><h2>Preparing the entry</h2><p>The accepted charges are being gathered for {owner}.</p></div></section>
  // What the API recorded wins once the approval event has arrived; the textarea is only a fallback.
  const shownNote = approval.note || note.trim()
  return <section className="surface simple-view"><div className="list-heading"><div><h2>Credit memo</h2><p>{account.distributor.name} · {monthLabel(account.invoice.month)} · {ws.remittance?.invoice_id ?? account.invoice.id}</p></div></div><div className="rule-content"><Status value={ws.postingLabel} /><div className="proposal-amount">{dollars(approval.amount)}</div><h2>Book the accepted deductions</h2><p>Only charges the deal or {firstName(owner)}’s rule supports. The disputed {dollars(ws.totals?.disputed ?? 0)} stays open on the invoice.</p><div className="proposal-lines">{ws.proposalLines.map((line) => <span key={line.chargeId}>{line.label}<strong>{dollars(line.amount)}</strong></span>)}</div>{approval.status === 'pending' ? <><div className="approval-notice"><ShieldCheck /><span><strong>Needs {firstName(owner)}’s approval</strong><small>Nothing posts until you say yes.</small></span></div><label className="note-label" htmlFor="approval-note">Note <span>(required to refuse)</span></label><textarea id="approval-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Why you’re approving or refusing" /><label className="cx-check"><input type="checkbox" checked={autoPost} onChange={(event) => setAutoPost(event.target.checked)} /><span>Post fair charges like these automatically from now on <small className="muted">(memos up to {dollars(approval.amount)} post without asking)</small></span></label><div className="approval-actions"><button className="primary" onClick={() => onDecide(true, note.trim() || null, autoPost)}>Approve credit memo</button><button className="secondary" disabled={!note.trim()} onClick={() => onDecide(false, note.trim(), false)}>Refuse · don’t post</button></div>{role !== 'owner' && <p className="role-hint">Only {firstName(owner)} can approve. You’ll be asked to sign in as the admin.</p>}</> : <div className="feedback inline" role="status"><Check />{approval.status === 'approved' ? `${approvedBy(ws, owner)}. ${postingSentence(ws)}${approval.sets_auto_post ? ` From now on, fair-charge memos up to ${dollars(approval.sets_auto_post.limit)} post without asking.` : ''}` : `Refused by ${owner}. Nothing was posted.${shownNote ? ` Note: “${shownNote}”` : ''}`}</div>}</div></section>
}
