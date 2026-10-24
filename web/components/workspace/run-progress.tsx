'use client'

// What the analysis is doing right now, from the event stream: the stages it has passed, and its own log lines.
// A live run takes tens of seconds (every answer is generated), so this keeps it from ever looking frozen.

import { useState } from 'react'
import { Check, CircleAlert, Loader2 } from 'lucide-react'
import { clock } from '@/lib/format'
import type { Account } from '@/lib/types'
import type { RunState } from '@/lib/useRunEvents'
import type { WorkspaceView } from '@/lib/workspace'

type StepState = 'done' | 'active' | 'todo' | 'failed'

const ACTOR: Record<string, string> = {
  system: 'Clawback', reader: 'Deal readers', investigator: 'Investigator', gate: 'Decision rules', negotiator: 'Negotiator',
  bookkeeper: 'Bookkeeper', coach: 'Deal coach', owner: 'Owner', controller: 'Controller', policy: 'Policy',
}

export function RunProgress({ account, state, ws }: { account: Account; state: RunState; ws: WorkspaceView }) {
  const [all, setAll] = useState(false)
  const run = state.run
  if (!run) return null
  const failed = run.status === 'failed'
  const working = run.status === 'started' && !failed
  const total = ws.remittance?.charge_count ?? ws.charges.length
  const decided = ws.charges.filter((c) => c.status !== 'Reviewing').length
  const anyFinding = Object.keys(state.findings).length > 0 || decided > 0
  const disputed = (ws.totals?.disputed ?? 0) > 0
  const filed = state.dispute && state.dispute.status !== 'draft'
  const people = ws.stage === 'owner' ? `Waiting on ${account.brand.owner.name}` : ws.stage === 'controller' ? `Waiting on ${account.brand.controller.name}` : ws.stage === 'posted' ? 'Approved' : ws.stage === 'refused' ? 'Entry refused' : 'People approve'

  const steps: { label: string; state: StepState }[] = [
    { label: `${account.distributor.name}’s payment received`, state: 'done' },
    { label: 'Reading the deal and the emails', state: anyFinding ? 'done' : failed ? 'failed' : 'active' },
    { label: `Checking each charge · ${decided} of ${total}`, state: ws.reviewed ? 'done' : !anyFinding ? 'todo' : failed ? 'failed' : 'active' },
    ...(disputed || filed ? [{ label: filed ? `Dispute ${state.dispute!.id} filed` : 'Filing the dispute', state: (filed ? 'done' : ws.reviewed ? (failed ? 'failed' : 'active') : 'todo') as StepState }] : []),
    { label: people, state: ws.stage === 'posted' || ws.stage === 'refused' ? 'done' : ws.stage === 'owner' || ws.stage === 'controller' ? 'active' : 'todo' },
  ]

  const feed = all ? state.feed : state.feed.slice(-6)
  return (
    <section className={`surface run-progress ${working ? 'working' : ''}`} aria-label="Analysis progress">
      <div className="progress-head">
        <h2>{failed ? 'The analysis stopped' : working ? 'Working on it' : ws.stage === 'posted' || ws.stage === 'refused' ? 'Analysis complete' : 'Analysis paused for a person'}</h2>
        {working && <span className="working-pill"><Loader2 className="spin" /> Live</span>}
      </div>
      <ol className="progress-steps">
        {steps.map((s) => <li key={s.label} className={s.state}><span className="step-mark" aria-hidden>{s.state === 'done' ? <Check /> : s.state === 'failed' ? <CircleAlert /> : s.state === 'active' ? <Loader2 className="spin" /> : null}</span>{s.label}<span className="sr-only"> · {s.state}</span></li>)}
      </ol>
      {state.feed.length > 0 && (
        <>
          <ol className="activity" aria-live="polite" aria-label="Activity">
            {feed.map((line) => <li key={line.id} className={line.level}><span className="activity-actor">{ACTOR[line.actor] ?? line.actor}</span><span className="activity-text">{line.text}</span></li>)}
          </ol>
          {state.feed.length > 6 && <button className="text-button" onClick={() => setAll((v) => !v)}>{all ? 'Show recent only' : `Show all ${state.feed.length} steps`}</button>}
        </>
      )}
      {working && run.remittance?.received_at && <p className="muted small">Started {clock(run.remittance.received_at)}. Each answer is generated live, so this takes a little while.</p>}
    </section>
  )
}
