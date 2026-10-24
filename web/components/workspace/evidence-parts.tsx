'use client'

// Display pieces for evidence: a quoted sentence inside its paragraph, and data rows as a table.
// Formatting only; every value arrives from the API.

import { money, rate as perUnit, units as count, anyDay } from '@/lib/format'
import type { Evidence, Quote } from '@/lib/types'

/** The sentence highlighted inside its paragraph; a clicked phrase found in it gets the strong highlight. */
export function QuoteBlock({ quote, active }: { quote: Quote; active?: string | null }) {
  const at = active ? quote.text.indexOf(active) : -1
  const body = at >= 0 && active
    ? <>{quote.text.slice(0, at)}<span className="hl-strong">{active}</span>{quote.text.slice(at + active.length)}</>
    : quote.text
  return (
    <blockquote className="quote-block">
      {quote.context_before && <span className="quote-context">{quote.context_before}</span>}
      <mark className="hl">{body}</mark>
      {quote.context_after && <span className="quote-context">{quote.context_after}</span>}
    </blockquote>
  )
}

const HIDDEN = new Set(['id', 'remittance_id', 'promo_id', 'description'])
const MONEY = new Set(['amount', 'unit_price', 'agreed_price', 'price', 'charged_price', 'invoice_price', 'value'])
const RATE = new Set(['rate'])
const HEADER: Record<string, string> = {
  line_ref: 'Line',
  shipped_units: 'Shipped',
  received_units: 'Received',
  unit_price: 'Unit price',
  received_by: 'Signed by',
  received_at: 'Received',
  agreed_price: 'Agreed price',
  effective_from: 'From',
  effective_to: 'To',
  promo_units: 'Promo units',
  total_units: 'Total units',
  week_start: 'Week of',
  week_end: 'Through',
  period_start: 'From',
  period_end: 'To',
  paid_on: 'Paid on',
  notice_date: 'Notice date',
  ref: 'Ref',
  code: 'Code',
}

const header = (k: string) => HEADER[k] ?? (k.charAt(0).toUpperCase() + k.slice(1)).replace(/_/g, ' ')

function cell(key: string, v: string | number | null): string {
  if (v === null || v === '') return '—'
  if (typeof v === 'number') return MONEY.has(key) ? money(v) : RATE.has(key) ? perUnit(v) : count(v)
  if (/^\d{4}-\d{2}-\d{2}/.test(v)) return anyDay(v)
  return v
}

const numeric = (v: string) => /^[-$\d—]/.test(v)

/** Data rows (deliveries, prices, sales, payments) as a small table; a single row as a label list. */
export function Rows({ rows }: { rows: Evidence['rows'] }) {
  if (rows.length === 0) return null
  const cols = Object.keys(rows[0]).filter((k) => !HIDDEN.has(k) && rows.some((r) => r[k] !== null && r[k] !== undefined))
  if (rows.length === 1) {
    return (
      <dl className="row-list">
        {cols.map((k) => {
          const v = cell(k, rows[0][k] ?? null)
          return <div key={k}><dt>{header(k)}</dt><dd className={numeric(v) ? 'num' : ''}>{v}</dd></div>
        })}
      </dl>
    )
  }
  return (
    <div className="row-table-wrap">
      <table className="row-table">
        <thead><tr>{cols.map((k) => <th key={k} scope="col" className={rows.some((r) => typeof r[k] === 'number') ? 'num' : ''}>{header(k)}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{cols.map((k) => {
              const v = cell(k, r[k] ?? null)
              return <td key={k} className={numeric(v) ? 'num' : ''}>{v}</td>
            })}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One source: who it's from, its one-line summary, the quote and the rows. */
export function SourceBody({ e, active, distributor }: { e: Evidence; active?: string | null; distributor: string }) {
  return (
    <>
      <p className="source-summary">{e.summary}</p>
      {e.sender && <p className="source-meta">From {e.sender}{e.sent_at ? ` · ${anyDay(e.sent_at)}` : ''}{e.approved_sender === true ? ' · approved sender' : e.approved_sender === false ? ` · can’t change the deal` : ''}</p>}
      {e.person && <p className="source-meta">{e.person}</p>}
      {e.quote && <QuoteBlock quote={e.quote} active={active} />}
      {e.rows.length > 0 && <Rows rows={e.rows} />}
      {e.kind === 'claim' && <p className="source-meta">A claim from {distributor}, shown for context. It does not change the deal.</p>}
    </>
  )
}

/** What each kind of source is called on the panel. */
export function sourceTitle(kind: Evidence['kind'], distributor: string): string {
  switch (kind) {
    case 'clause': return 'What the deal says'
    case 'policy': return 'What the deal says'
    case 'email': return 'The email that changes it'
    case 'notice': return `${distributor}’s notice`
    case 'claim': return `What ${distributor} claims`
    case 'delivery': return 'Proof of delivery'
    case 'price': return 'Agreed price list'
    case 'sales': return 'Store sales'
    case 'prior_payment': return 'Earlier payment'
    case 'rule': return 'Your saved rule'
    case 'person': return 'Your answer'
    case 'approval': return 'Approval'
    case 'charge': return 'The remittance line'
    default: return 'Source'
  }
}
