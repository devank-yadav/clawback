'use client'

import { useCallback, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { ArrowRight, Check, FileCheck2, Info, ShieldCheck } from 'lucide-react'
import AppShell, { DistributorMark } from '@/components/shell/AppShell'
import { useCurrentAccount, withAccount } from '@/lib/accounts'
import { fetchLookback, fetchOverview, fetchRuns } from '@/lib/api'
import { anyDay, dollars, money, monthLabel, percent, share } from '@/lib/format'
import { useSession } from '@/lib/session'
import type { Account, Lookback, Overview, RunSummary } from '@/lib/types'
import { useFetched } from '@/lib/useFetched'
import { useRunEvents } from '@/lib/useRunEvents'
import { postingSentence, selectWorkspace, type WorkspaceView } from '@/lib/workspace'
import { ChargeList, EvidencePanel, type ChargeFilter } from './charge-workspace'
import { MonthlyChart, TypeBars } from './charts'
import { LookbackCard, PacketLink } from './impact'

/** Charges (this payment, every charge with its evidence) or Overview (six months with this distributor). */
export type View = 'overview' | 'payments'
const PLACE = { overview: 'overview', payments: 'charges' } as const
const CRUMB: Record<View, string> = { overview: 'Overview', payments: 'Charges' }

/** /charges and /overview: the account lives in the URL (?account=, and ?charge= opens one charge), so every link and
 * reload keeps it. The run itself, with its questions and approvals, is on `/`. */
export default function ClawbackApp({ view }: { view: View }) {
  const { account, accounts, error } = useCurrentAccount()
  if (!account) {
    return (
      <AppShell account={null} accounts={accounts} active={PLACE[view]} crumb={CRUMB[view]}>
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
  const { state, runId, answerQuestion, awaitingPayment, refresh, error } = run
  const ws = useMemo(() => selectWorkspace(state, account), [state, account])
  const { role } = useSession()
  // ?charge= opens a charge from a link; a click on the list overrides it.
  const chargeParam = useSearchParams().get('charge')
  const [picked, setPicked] = useState<{ id: string | null } | null>(null)
  const selectedId = picked ? picked.id : chargeParam
  const setSelectedId = (id: string | null) => setPicked({ id })
  const [filter, setFilter] = useState<ChargeFilter>('All')
  const distributor = account.distributor.name

  // The overview's numbers move as the run does (a dispute filed, a memo posted), so it is read again at each step.
  const overviewKey = `${runId}:${state.run?.status}:${state.dispute?.status}:${state.approval?.status}:${state.ledger.length}:${ws.reviewed}`
  const loadOverview = useMemo(() => () => fetchOverview(account.id), [account.id])
  const overview = useFetched<Overview>(loadOverview, overviewKey)
  // The lookback is history: read once per account (and on reset). null = this API doesn't have it, so the card hides.
  const loadLookback = useMemo(() => () => fetchLookback(account.id), [account.id])
  const lookback = useFetched<Lookback | null>(loadLookback)
  // Every run of the agents for this distributor, newest first (Overview's "Past runs").
  const loadRuns = useCallback(() => fetchRuns(account.id), [account.id])
  const runs = useFetched(view === 'overview' ? loadRuns : null, overviewKey)

  const selected = view === 'payments' ? (ws.charges.find((charge) => charge.id === selectedId) ?? null) : null
  const feedback = stageFeedback(ws, account)
  const pendingCharges = ws.remittance ? ws.remittance.charge_count - ws.charges.length : 0

  function onReset() {
    setSelectedId(null)
    setFilter('All')
    refresh()
    overview.reload()
    lookback.reload()
    runs.reload()
  }

  const heading = view === 'overview'
    ? { title: 'Overview', line: `Six months of payments from ${distributor}, and what the deal didn’t allow.` }
    : { title: 'Charges', line: `${monthLabel(account.invoice.month)} payment · ${distributor} · Invoice ${ws.remittance?.invoice_id ?? account.invoice.id}` }

  const reviewHref = withAccount('/charges', account.id)
  const runLink = <Link className="primary" href={withAccount('/', account.id)}>{awaitingPayment ? `Check ${distributor}’s payment` : 'Open the run'} <ArrowRight /></Link>

  return (
    <AppShell account={account} accounts={accounts} active={PLACE[view]} crumb={CRUMB[view]} onReset={onReset}>
      <main className={`main-content ${selected ? 'with-panel' : ''}`}>
        <div className="page-heading">
          <div><div className="eyebrow">{account.brand.name}</div><h1>{heading.title}</h1><p>{heading.line}</p></div>
          {runLink}
        </div>

        {error && <div className="feedback error" role="alert"><Info />{error}</div>}
        {feedback && view !== 'overview' && <div className={`feedback ${ws.stage === 'refused' ? 'notice' : ''}`} role="status">{ws.stage === 'refused' ? <Info /> : <Check />}{feedback}</div>}

        {view === 'overview' && <OverviewPage account={account} overview={overview.data} lookback={lookback.data} overviewError={overview.error} ws={ws} awaitingPayment={awaitingPayment} reviewHref={reviewHref} feedback={feedback} runs={runs.data} runsError={runs.error} />}

        {view === 'payments' && (
          <>
            <PaymentStrip account={account} ws={ws} awaitingPayment={awaitingPayment} />
            {ws.remittance && <Summary ws={ws} compact />}
            <div className="payment-workspace">
              <section className="surface charge-main"><div className="list-heading"><div><h2>Charges</h2><p>{awaitingPayment ? `Waiting for ${distributor}’s payment.` : 'Select a charge to see its evidence and how it was decided.'}</p></div></div><ChargeList charges={ws.charges} selected={selected?.id} onSelect={(charge) => setSelectedId(charge.id)} filter={filter} onFilterChange={setFilter} waiting={awaitingPayment} pending={pendingCharges} /><div className="table-footer"><ShieldCheck /> {ws.disputeId ? <>{ws.disputeLabel} · <a href={withAccount('/portal', account.id, { dispute: ws.disputeId })} target="_blank" rel="noreferrer">Open on {account.distributor.portal_name}</a><PacketLink disputeId={ws.disputeId} /></> : ws.disputeLabel}</div></section>
              {selected && <EvidencePanel key={selected.id} account={account} state={state} runId={runId} charge={selected} question={ws.question} rule={ws.rule} stage={ws.stage} role={role} onClose={() => setSelectedId(null)} onAnswer={answerQuestion} />}
            </div>
          </>
        )}

      </main>
    </AppShell>
  )
}

/** What the stream says just happened. Never worded as done until the matching event has arrived. */
function stageFeedback(ws: WorkspaceView, account: Account) {
  const controller = account.brand.controller.name
  if (ws.stage === 'controller' && ws.rule) return `Rule saved by ${account.brand.owner.name}. The accounting entry is ready for ${controller}.`
  if (ws.stage === 'refused') return `${controller} refused the entry. Nothing was posted.`
  if (ws.stage === 'posted') return `${controller} approved. ${postingSentence(ws)}`
  return ''
}

function statusWord(ws: WorkspaceView, awaitingPayment: boolean, overview: Overview | null): string {
  if (awaitingPayment) return 'Waiting for payment'
  if (!ws.remittance) return overview ? overview.current.status.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : 'Loading'
  if (!ws.reviewed) return 'Analyzing'
  if (ws.stage === 'owner') return 'Needs the owner'
  if (ws.stage === 'controller') return 'Needs the controller'
  if (ws.stage === 'refused') return 'Entry refused'
  if (ws.stage === 'posted') return 'Complete'
  return 'Reviewed'
}

function OverviewPage({ account, overview, lookback, overviewError, ws, awaitingPayment, reviewHref, feedback, runs, runsError }: { account: Account; overview: Overview | null; lookback: Lookback | null; overviewError: string | null; ws: WorkspaceView; awaitingPayment: boolean; reviewHref: string; feedback: string; runs: RunSummary[] | null; runsError: string | null }) {
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

      <CurrentPayment account={account} overview={overview} ws={ws} awaitingPayment={awaitingPayment} reviewHref={reviewHref} />

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

      <PastRuns account={account} runs={runs} error={runsError} />
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
      <div className="card-bottom"><span><FileCheck2 /> {awaitingPayment ? `Each charge is checked against the deal when ${account.distributor.name} pays.` : ws.reviewed ? `All ${ws.charges.length} charges checked against the deal` : 'Checking each charge against the deal…'}</span>{!awaitingPayment && <Link className="text-button" href={reviewHref}>Every charge <ArrowRight /></Link>}</div>
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
  return <section className={`summary-grid ${compact ? 'compact' : ''}`} aria-label="Deduction decisions"><div><span>Disputing</span><strong>{dollars(ws.totals?.disputed ?? 0)}</strong><small>Being challenged · not recovered yet</small></div><div><span>Accepted</span><strong>{dollars(ws.totals?.accepted ?? 0)}</strong><small>Backed by the deal or your rule</small></div><div><span>{waiting > 0 ? 'Waiting on you' : 'Pending'}</span><strong>{dollars(waiting)}</strong><small>{waiting > 0 ? 'One answer from the owner' : undecided > 0 ? 'Still checking charges' : 'Every charge decided'}</small></div></section>
}

const RUN_STATUS = { started: 'Agents working', waiting: 'Waiting on you', finished: 'Finished', failed: 'Stopped' } as const
const when = (iso: string) => new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

/** Every run of the agents for this distributor, newest first; each opens its own result on `/`. */
function PastRuns({ account, runs, error }: { account: Account; runs: RunSummary[] | null; error: string | null }) {
  return (
    <section className="surface preview-section" aria-labelledby="runs-h">
      <div className="list-heading"><div><h2 id="runs-h">Past runs</h2><p>Each time a payment from {account.distributor.name} arrived, the agents ran. Open one to see what each did and concluded.</p></div></div>
      {error && <p className="muted small table-empty">{error}</p>}
      {!runs && !error && <p className="muted small table-empty">Loading…</p>}
      {runs && runs.length === 0 && <p className="muted small table-empty">No runs yet. They appear here once a payment has been checked.</p>}
      {runs && runs.length > 0 && (
        <ol className="hs-list runs-list">
          {runs.map((r, i) => (
            <li key={r.run_id}>
              <Link className={`hs-row ${r.replaced ? 'is-replaced' : ''}`} href={withAccount('/', account.id, { run: r.run_id })}>
                <span className="hs-when"><strong>{when(r.started_at)}</strong><small>{r.kind} payment{r.invoice_id ? ` · ${r.invoice_id}` : ''}</small></span>
                <span className="hs-facts">
                  {r.taken !== null && <span>Kept <b className="is-amber">{money(r.taken)}</b></span>}
                  {r.disputed !== null && r.disputed > 0 && <span>Disputed <b className="is-dispute">{money(r.disputed)}</b></span>}
                  {r.accepted !== null && r.accepted > 0 && <span>Fair <b className="is-fair">{money(r.accepted)}</b></span>}
                  {r.questions > 0 && <span>{r.questions} question{r.questions === 1 ? '' : 's'}</span>}
                </span>
                <span className={`hs-status is-${r.replaced ? 'replaced' : r.status}`}>{r.replaced ? 'Replaced by a newer run' : i === 0 && r.status === 'waiting' ? 'Waiting on you' : RUN_STATUS[r.status]}</span>
                <span className="hs-open">Open →</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
