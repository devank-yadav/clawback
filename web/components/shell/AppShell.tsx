'use client'

import { useState, type ReactNode } from 'react'
import { Check, Info, LogIn, LogOut, X } from 'lucide-react'
import { inkOn } from '@/lib/accounts'
import { ApiError, resetWorkspace } from '@/lib/api'
import { askAdminToken, askSignIn, signOut, useSession } from '@/lib/session'
import type { Account } from '@/lib/types'
import TopBar from './TopBar'
import SessionDialogs, { roleName } from './SessionDialogs'

export type View = 'overview' | 'payments' | 'approvals' | 'rules'

export function BrandAvatar({ account, large = false }: { account: Account | null; large?: boolean }) {
  const bg = account?.brand.colors.primary ?? '#ecebdc'
  return <span className={`workspace-avatar ${large ? 'large' : ''}`} style={{ background: bg, color: inkOn(bg) }} aria-hidden>{account?.brand.initials ?? '·'}</span>
}

export function DistributorMark({ account }: { account: Account | null }) {
  const bg = account?.distributor.colors.primary ?? '#f0efe9'
  return <span className="distributor-mark" style={{ background: bg, color: inkOn(bg) }} aria-hidden>{account?.distributor.name.charAt(0) ?? '·'}</span>
}

type Props = {
  account: Account | null
  accounts: Account[] | null
  /** The workspace view or the route this page is. */
  active: View | string
  crumb: string
  /** Badge on Approvals when a controller decision is waiting. */
  approvalsWaiting?: boolean
  /** Called after a reset succeeds; without it the page reloads. */
  onReset?: () => void
  children: ReactNode
}

/** The frame every brand screen shares: brand menu, navigation, who is viewing, and the page. */
// `accounts` and `approvalsWaiting` stay in the props for the callers; the top bar's switcher loads its own list.
export default function AppShell({ account, active, crumb, onReset, children }: Props) {
  const { role } = useSession()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [resetState, setResetState] = useState<{ busy: boolean; message: string | null; error: boolean }>({ busy: false, message: null, error: false })

  /** POST /demo/reset; a 401 asks for the admin token, then tries again with it. */
  async function reset(retried = false) {
    setResetState({ busy: true, message: null, error: false })
    try {
      await resetWorkspace()
      setResetState({ busy: false, message: 'Workspace reset. Every account is back to waiting for its payment.', error: false })
      if (onReset) onReset()
      else window.location.reload()
    } catch (e) {
      setResetState({ busy: false, message: null, error: false })
      if (e instanceof ApiError && e.status === 401) {
        askAdminToken(retried ? 'That token wasn’t accepted. Check it and try again.' : 'Resetting clears every account’s analysis on this server, so it needs the admin token.', () => void reset(true))
      } else {
        setResetState({ busy: false, message: `The reset didn’t go through (${(e as Error).message}).`, error: true })
      }
    }
  }

  const person = role ? roleName(role, account) : null
  const roleWord = role === 'owner' ? 'Owner' : 'Controller'

  return (
    <div className="app-shell">
      <TopBar
        account={account}
        active={active === '/results' ? 'results' : undefined}
        right={account && (person
          ? <span className="viewer"><span className="viewer-avatar" aria-hidden>{person.split(' ').map((p) => p[0]).join('').slice(0, 2)}</span><span><strong>{person}</strong></span><button className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut /></button></span>
          : <button className="secondary viewer-signin" onClick={() => askSignIn('owner')}><LogIn /> Sign in</button>)}
        extra={<>
          <button role="menuitem" className="tb-row" onClick={() => setDetailsOpen(true)}><span><strong>Account details</strong><small>{account?.brand.name ?? ''} · {account?.distributor.name ?? ''}</small></span></button>
          <button role="menuitem" className="tb-row" disabled={resetState.busy} onClick={() => void reset()}><span><strong>{resetState.busy ? 'Resetting…' : 'Reset the demo'}</strong><small>Every distributor back to waiting for its payment</small></span></button>
        </>}
      />

      <div className="main-shell">
        <header className="topbar">
          <span>{account?.brand.name ?? 'Clawback'} <span className="slash">/</span> <strong>{crumb}</strong></span>
          {account && <span className="topbar-note"><span className="tiny-dot" /> {person ? `Signed in as ${person} · ${roleWord}` : 'Not signed in'}</span>}
        </header>
        {resetState.message && <div className={`feedback shell-feedback ${resetState.error ? 'error' : ''}`} role="status">{resetState.error ? <Info /> : <Check />}{resetState.message}<button className="icon-button" aria-label="Dismiss" onClick={() => setResetState((s) => ({ ...s, message: null }))}><X /></button></div>}
        {children}
      </div>

      {detailsOpen && account && (
        <div className="dialog-backdrop" role="presentation" onMouseDown={() => setDetailsOpen(false)}>
          <section className="brand-dialog" role="dialog" aria-modal="true" aria-labelledby="brand-title" onMouseDown={(event) => event.stopPropagation()}>
            <button autoFocus className="icon-button dialog-close" onClick={() => setDetailsOpen(false)} aria-label="Close account details"><X /></button>
            <BrandAvatar account={account} large />
            <div><div className="eyebrow">{account.brand.kind} · {account.brand.city}</div><h2 id="brand-title">{account.brand.name}</h2><p>Deductions from {account.distributor.name} are checked against the signed deal before anything is accepted or disputed.</p></div>
            <dl>
              <div><dt>Owner</dt><dd>{account.brand.owner.name}<small>{account.brand.owner.email}</small></dd></div>
              <div><dt>Controller</dt><dd>{account.brand.controller.name}</dd></div>
              <div><dt>Distributor</dt><dd>{account.distributor.name}<small>{account.distributor.desk_email}</small></dd></div>
            </dl>
            <button className="secondary" onClick={() => setDetailsOpen(false)}>Done</button>
          </section>
        </div>
      )}

      <SessionDialogs account={account} />
    </div>
  )
}
