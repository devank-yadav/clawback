'use client'

// What the analysis is doing right now, from the event stream: the stages it has passed, and its own log lines.
// A live run takes tens of seconds (every answer is generated), so this keeps it from ever looking frozen.

import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { clock } from '@/lib/format'
import type { Account } from '@/lib/types'
import type { RunState } from '@/lib/useRunEvents'
import type { WorkspaceView } from '@/lib/workspace'
import { firstName } from '@/lib/accounts'
import { Meter } from '@/components/flow/parts'
import { StageRail } from '@/components/flow/StageRail'
import { buildStages } from '@/components/flow/stages'


const ACTOR: Record<string, string> = {
  system: 'Clawback', reader: 'Deal readers', investigator: 'Investigator', gate: 'Decision rules', negotiator: 'Negotiator',
  bookkeeper: 'Bookkeeper', coach: 'Deal coach', owner: 'Admin', policy: 'Policy',
}

export function RunProgress({ account, state, ws }: { account: Account; state: RunState; ws: WorkspaceView }) {
  const [all, setAll] = useState(false)
  const run = state.run
  if (!run) return null
  const failed = run.status === 'failed'
  const working = run.status === 'started' && !failed


  const feed = all ? state.feed : state.feed.slice(-6)
  const cast = { distributor: account.distributor.name, owner: firstName(account.brand.owner.name) }
  return (
    <section className={`surface run-progress ${working ? 'working' : ''}`} aria-label="Analysis progress">
      <div className="progress-head">
        <h2>{failed ? 'The analysis stopped' : working ? 'Working on it' : ws.stage === 'posted' || ws.stage === 'refused' ? 'Analysis complete' : 'Analysis paused for a person'}</h2>
        {working && <span className="working-pill"><Loader2 className="spin" /> Live</span>}
      </div>
      {/* The agents' flow's own meters and stage rail, from the same events: one app, one picture of a run. */}
      <div className="ws-run">
        <div className="fl-meters">
          <Meter label="Disputing, with proof" value={ws.totals?.disputed ?? 0} tone="dispute" />
          <Meter label="Fair, accepted" value={ws.totals?.accepted ?? 0} tone="fair" />
          <Meter label={`Waiting on ${cast.owner}`} value={(ws.totals?.waiting ?? 0) + (ws.stage === 'approval' ? ws.approval?.amount ?? 0 : 0)} tone="wait" />
        </div>
        <StageRail stages={buildStages(state, ws, cast, false)} compact />
      </div>
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
