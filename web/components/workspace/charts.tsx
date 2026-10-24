'use client'

// The overview's two charts, drawn as plain SVG. Layout math only (scales and bar widths); every amount is the API's.

import { useEffect, useRef, useState } from 'react'
import { codeLabel } from '@/lib/accounts'
import { compactMoney, dollars, monthLabel, monthShortLabel, share } from '@/lib/format'
import type { Overview } from '@/lib/types'

// Validated categorical slots 1-3 (dataviz palette check: adjacent CVD ΔE ≥ 9, normal-vision ≥ 24). Paid sits below
// 3:1 contrast, so the chart always ships with a legend and a table view.
const SERIES = [
  { key: 'invoiced', label: 'Invoiced', color: '#2a78d6' },
  { key: 'paid', label: 'Paid', color: '#1baf7a' },
  { key: 'deducted', label: 'Deducted', color: '#eb6834' },
] as const

type Month = Overview['months'][number]

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

/** A clean axis top: 1, 2, 2.5 or 5 times a power of ten, at or above the largest value. */
function niceTop(max: number) {
  if (max <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(max))
  const step = [1, 2, 2.5, 5, 10].find((s) => s * p >= max) ?? 10
  return step * p
}

/** A column with a 4px rounded top and a square foot on the baseline. */
function column(x: number, y: number, w: number, h: number) {
  if (h <= 0) return ''
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

export function MonthlyChart({ months }: { months: Month[] }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const height = 240
  const pad = { top: 12, right: 8, bottom: 28, left: 48 }
  const innerW = Math.max(0, width - pad.left - pad.right)
  const innerH = height - pad.top - pad.bottom
  const top = niceTop(Math.max(0, ...months.flatMap((m) => [m.invoiced, m.paid, m.deducted])))
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * top)
  const slot = months.length ? innerW / months.length : 0
  const bar = Math.max(4, Math.min(20, (slot * 0.7 - 4) / 3))
  const group = bar * 3 + 4
  const y = (v: number) => pad.top + innerH - (innerH * v) / top

  return (
    <div className="chart" ref={ref}>
      <div className="chart-legend" aria-hidden>{SERIES.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`Invoiced, paid and deducted by month, ${months.length} months`} onMouseLeave={() => setHover(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className="chart-grid" />
              <text x={pad.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="chart-tick">{compactMoney(t)}</text>
            </g>
          ))}
          {months.map((m, i) => {
            const x0 = pad.left + slot * i + (slot - group) / 2
            return (
              <g key={m.month}>
                {SERIES.map((s, k) => {
                  const v = m[s.key]
                  const h = (innerH * v) / top
                  return <path key={s.key} d={column(x0 + k * (bar + 2), y(v), bar, h)} fill={s.color} opacity={hover === null || hover === i ? 1 : 0.35} />
                })}
                <text x={pad.left + slot * i + slot / 2} y={height - 8} textAnchor="middle" className="chart-tick">{monthShortLabel(m.month)}</text>
                <rect
                  x={pad.left + slot * i} y={pad.top} width={slot} height={innerH} fill="transparent" tabIndex={0}
                  aria-label={`${monthLabel(m.month)}: invoiced ${dollars(m.invoiced)}, paid ${dollars(m.paid)}, deducted ${dollars(m.deducted)}`}
                  onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
                />
              </g>
            )
          })}
        </svg>
      )}
      {hover !== null && months[hover] && (
        <div className="chart-tip" role="status" style={{ left: Math.min(Math.max(pad.left + slot * hover + slot / 2, 90), width - 90) }}>
          <strong>{monthLabel(months[hover].month)}</strong>
          {SERIES.map((s) => <span key={s.key}><i style={{ background: s.color }} /><b>{dollars(months[hover][s.key])}</b> {s.label}</span>)}
        </div>
      )}
      <details className="chart-table">
        <summary>View as table</summary>
        <div className="row-table-wrap">
          <table className="row-table">
            <thead><tr><th scope="col">Month</th><th scope="col" className="num">Invoiced</th><th scope="col" className="num">Paid</th><th scope="col" className="num">Deducted</th><th scope="col" className="num">Recovered</th></tr></thead>
            <tbody>{months.map((m) => <tr key={m.month}><td>{monthLabel(m.month)}</td><td className="num">{dollars(m.invoiced)}</td><td className="num">{dollars(m.paid)}</td><td className="num">{dollars(m.deducted)}</td><td className="num">{dollars(m.recovered)}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

/** Deductions by type: one series, so one color and no legend; the amount sits at the bar's end. */
export function TypeBars({ rows }: { rows: Overview['deductions_by_type'] }) {
  const max = Math.max(0, ...rows.map((r) => r.amount))
  if (rows.length === 0) return <p className="muted small">No deductions in the last six months.</p>
  return (
    <ul className="type-bars">
      {rows.map((r) => (
        <li key={r.code}>
          <div className="type-bar-top"><span>{r.label || codeLabel(r.code)}<small>{r.count} {r.count === 1 ? 'charge' : 'charges'}</small></span><strong>{dollars(r.amount)}</strong></div>
          <div className="type-bar-track" role="img" aria-label={`${r.label || codeLabel(r.code)}: ${dollars(r.amount)} across ${r.count} charges`}><span style={{ width: `${share(r.amount, max)}%` }} /></div>
        </li>
      ))}
    </ul>
  )
}
