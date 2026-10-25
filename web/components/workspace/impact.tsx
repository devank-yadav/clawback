'use client'

// What Clawback is worth, in the API's own numbers: the six-month lookback ("Before Clawback"),
// the file-by date on a disputed line, and the dispute packet link. Layout math only; every amount is the API's.

import { useEffect, useRef, useState } from 'react'
import { Clock, Download } from 'lucide-react'
import { disputePacketUrl } from '@/lib/api'
import { anyDay, compactMoney, daysLeftLabel, dollars, money, monthLabel, monthShortLabel, URGENT_DAYS } from '@/lib/format'
import type { Lookback, LookbackStatus } from '@/lib/types'
/** "$4,120 being recovered · decided in 71 s · $0.38 of AI · by hand: about 45 min" once a run has decided. */
export function FileBy({ fileBy, daysLeft, className = '' }: { fileBy?: string | null; daysLeft?: number | null; className?: string }) {
  if (!fileBy && (daysLeft === null || daysLeft === undefined)) return null
  const urgent = daysLeft !== null && daysLeft !== undefined && daysLeft < URGENT_DAYS
  const parts = [fileBy ? `File by ${anyDay(fileBy)}` : null, daysLeft !== null && daysLeft !== undefined ? daysLeftLabel(daysLeft) : null].filter(Boolean)
  return <span className={`file-by ${urgent ? 'urgent' : ''} ${className}`}><Clock aria-hidden />{parts.join(' · ')}</span>
}

/** The dispute's PDF packet (GET /portal/disputes/{id}/packet.pdf), opened in a new tab. */
export function PacketLink({ disputeId, className = 'text-button' }: { disputeId: string; className?: string }) {
  return <a className={`packet-link ${className}`} href={disputePacketUrl(disputeId)} target="_blank" rel="noreferrer" download={`${disputeId}.pdf`}><Download aria-hidden /> Download dispute packet</a>
}

// ---- Before Clawback

type Row = Lookback['rows'][number]

const STATUS_WORD: Record<LookbackStatus, string> = {
  claimable: 'Still claimable',
  past_window: 'Too late to claim',
  settled: 'Settled',
  fair: 'Fair',
  not_checked: 'Not checked',
}

// Stacked bottom to top. Past-window money is hatched so it reads as gone without relying on color alone.
const SEGMENTS: { status: LookbackStatus; label: string; color: string; hatch?: boolean }[] = [
  { status: 'past_window', label: 'Too late to claim', color: '#8b8ea3', hatch: true },
  { status: 'settled', label: 'Settled', color: '#9cd9bc' },
  { status: 'claimable', label: 'Still claimable', color: '#ebc28c' },
]

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

const charted = (r: Row) => r.wrongly_taken > 0 && SEGMENTS.some((s) => s.status === r.status)

/** One column per month, one stacked block per wrongly taken charge (each block is a row's own amount). */
function LookbackChart({ rows }: { rows: Row[] }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const months = [...new Set(rows.map((r) => r.month.slice(0, 7)))].sort()
  const shown = rows.filter(charted)
  const byMonth = months.map((m) => SEGMENTS.flatMap((s) => shown.filter((r) => r.month.slice(0, 7) === m && r.status === s.status).map((r) => ({ row: r, seg: s }))))
  // Column height for the scale: layout only, never shown as a number.
  const tallest = Math.max(0, ...byMonth.map((blocks) => blocks.reduce((h, b) => h + b.row.wrongly_taken, 0)))
  const height = 200
  const pad = { top: 10, right: 6, bottom: 26, left: 44 }
  const innerW = Math.max(0, width - pad.left - pad.right)
  const innerH = height - pad.top - pad.bottom
  const slot = months.length ? innerW / months.length : 0
  const bar = Math.max(10, Math.min(36, slot * 0.55))
  const scale = (v: number) => (tallest > 0 ? (innerH * v) / tallest : 0)

  if (shown.length === 0) return <p className="muted small">Nothing was taken wrongly in these months.</p>
  return (
    <div className="chart lookback-chart" ref={ref}>
      <div className="chart-legend" aria-hidden>{SEGMENTS.map((s) => <span key={s.status}><i className={s.hatch ? 'hatched' : ''} style={{ background: s.hatch ? undefined : s.color, color: s.color }} />{s.label}</span>)}</div>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`Money taken wrongly by month, ${months.length} months`} onMouseLeave={() => setHover(null)}>
          <defs>
            <pattern id="lookback-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="#282a37" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="#8b8ea3" strokeWidth="3" />
            </pattern>
          </defs>
          <line x1={pad.left} x2={width - pad.right} y1={pad.top + innerH} y2={pad.top + innerH} className="chart-grid" />
          <line x1={pad.left} x2={width - pad.right} y1={pad.top} y2={pad.top} className="chart-grid" />
          <text x={pad.left - 8} y={pad.top} dy="0.32em" textAnchor="end" className="chart-tick">{compactMoney(tallest)}</text>
          <text x={pad.left - 8} y={pad.top + innerH} dy="0.32em" textAnchor="end" className="chart-tick">$0</text>
          {months.map((m, i) => {
            const x = pad.left + slot * i + (slot - bar) / 2
            let base = pad.top + innerH
            return (
              <g key={m} opacity={hover === null || hover === i ? 1 : 0.4}>
                {byMonth[i].map(({ row, seg }) => {
                  const h = scale(row.wrongly_taken)
                  base -= h
                  return <rect key={`${row.month}-${row.ref}`} x={x} y={base} width={bar} height={Math.max(0, h - 1)} rx={2} fill={seg.hatch ? 'url(#lookback-hatch)' : seg.color} stroke={seg.hatch ? seg.color : 'none'} strokeWidth={seg.hatch ? 1 : 0} />
                })}
                <text x={pad.left + slot * i + slot / 2} y={height - 8} textAnchor="middle" className="chart-tick">{monthShortLabel(m)}</text>
                <rect
                  x={pad.left + slot * i} y={pad.top} width={slot} height={innerH} fill="transparent" tabIndex={0}
                  aria-label={`${monthLabel(m)}: ${byMonth[i].map(({ row }) => `${row.ref} ${dollars(row.wrongly_taken)} ${STATUS_WORD[row.status].toLowerCase()}`).join(', ') || 'nothing taken wrongly'}`}
                  onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
                />
              </g>
            )
          })}
        </svg>
      )}
      {hover !== null && months[hover] && (
        <div className="chart-tip" role="status" style={{ left: Math.min(Math.max(pad.left + slot * hover + slot / 2, 100), width - 100) }}>
          <strong>{monthLabel(months[hover])}</strong>
          {byMonth[hover].length === 0 ? <span>Nothing taken wrongly</span> : byMonth[hover].map(({ row, seg }) => <span key={`${row.month}-${row.ref}`}><i className={seg.hatch ? 'hatched' : ''} style={{ background: seg.hatch ? undefined : seg.color, color: seg.color }} /><b>{dollars(row.wrongly_taken)}</b> {row.ref} · {seg.label.toLowerCase()}</span>)}
        </div>
      )}
      <details className="chart-table">
        <summary>View as table</summary>
        <div className="row-table-wrap">
          <table className="row-table">
            <thead><tr><th scope="col">Month</th><th scope="col">Charge</th><th scope="col" className="num">Taken wrongly</th><th scope="col">Now</th></tr></thead>
            <tbody>{shown.map((r) => <tr key={`${r.month}-${r.ref}`}><td>{monthShortLabel(r.month)}</td><td>{r.ref} · {r.description}</td><td className="num">{dollars(r.wrongly_taken)}</td><td>{STATUS_WORD[r.status]}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

/** "Before Clawback": what was taken wrongly in six months, what is already lost, and what can still be claimed. */
export function LookbackCard({ lookback, distributor }: { lookback: Lookback; distributor: string }) {
  const t = lookback.totals
  const claimable = lookback.rows
    .filter((r) => r.status === 'claimable')
    .sort((a, b) => (a.days_left ?? Infinity) - (b.days_left ?? Infinity))
  return (
    <section className="surface lookback-card" aria-labelledby="lookback-h">
      <div className="card-heading">
        <h2 id="lookback-h">Before Clawback</h2>
        <p>Last six months, checked now · {distributor} allows {lookback.dispute_window_days} days to dispute</p>
      </div>
      <div className="lookback-numbers">
        <div><span>Taken wrongly</span><strong>{money(t.wrongly_taken)}</strong><small>In six months</small></div>
        <div className="lost"><span>Already lost</span><strong>{money(t.lost_past_window)}</strong><small>Too late to dispute</small></div>
        <div className="claimable"><span>Still claimable</span><strong>{money(t.claimable_now)}</strong><small>If filed in time</small></div>
      </div>
      <div className="lookback-grid">
        <LookbackChart rows={lookback.rows} />
        <div className="claim-now">
          <h3>Claim these now</h3>
          {claimable.length === 0 ? <p className="muted small">Nothing left to claim.</p> : (
            <ul>
              {claimable.map((r) => (
                <li key={`${r.month}-${r.ref}`}>
                  <div className="claim-top"><span><span className="charge-kind">{monthShortLabel(r.month)} · {r.ref}</span>{r.description}</span><strong>{dollars(r.wrongly_taken)}</strong></div>
                  <FileBy fileBy={r.file_by} daysLeft={r.days_left} />
                </li>
              ))}
            </ul>
          )}
          {t.not_checked > 0 && <p className="muted small">{t.not_checked} {t.not_checked === 1 ? 'charge' : 'charges'} couldn’t be checked and {t.not_checked === 1 ? 'isn’t' : 'aren’t'} counted.</p>}
        </div>
      </div>
    </section>
  )
}
