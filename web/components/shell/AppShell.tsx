'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  CalendarClock, ChartColumn, Check, ChevronDown, ClipboardCheck, CornerUpLeft, ExternalLink, FileUp, FlaskConical, Home, Info,
  Layers3, LogIn, LogOut, PenLine, ReceiptText, RotateCcw, ScrollText, X,
} from 'lucide-react'
import { inkOn, withAccount } from '@/lib/accounts'
import { ApiError, resetWorkspace } from '@/lib/api'
import { askAdminToken, askSignIn, signOut, useSession } from '@/lib/session'
import type { Account } from '@/lib/types'
import SessionDialogs, { roleName } from './SessionDialogs'

export type View = 'overview' | 'payments' | 'approvals' | 'rules'

const WORKSPACE: { key: View; label: string; icon: typeof Home }[] = [
  { key: 'overview', label: 'Overview', icon: Home },
  { key: 'payments', label: 'Payments', icon: ReceiptText },
  { key: 'approvals', label: 'Approvals', icon: ClipboardCheck },
  { key: 'rules', label: 'Rules', icon: Layers3 },
]

const TOOLS: { href: string; label: string; icon: typeof Home }[] = [
  { href: '/upload', label: 'Upload remittance', icon: FileUp },
  { href: '/results', label: 'Results', icon: ChartColumn },
  { href: '/april', label: 'Next month', icon: CalendarClock },
  { href: '/coach', label: 'Deal coach', icon: PenLine },
  { href: '/scenario', label: 'Try a clause', icon: FlaskConical },
  { href: '/audit', label: 'Audit log', icon: ScrollText },
]

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
export default function AppShell({ account, accounts, active, crumb, approvalsWaiting = false, onReset, children }: Props) {
  const { role } = useSession()
  const [menuOpen, setMenuOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [resetState, setResetState] = useState<{ busy: boolean; message: string | null; error: boolean }>({ busy: false, message: null, error: false })
  const menuRef = useRef<HTMLDivElement>(null)
  const pathname = usePathname()
  const router = useRouter()
  const id = account?.id

  useEffect(() => {
    const close = (event: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false) }
    const esc = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [])

  function switchTo(next: Account) {
    setMenuOpen(false)
    if (next.id === id) return
    router.push(withAccount(pathname === '/portal' ? '/' : pathname, next.id))
  }

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
      <aside className="sidebar">
        <Link className="wordmark" href={withAccount('/', id)} aria-label="Clawback: watch the agents work">
          <span className="brand-mark"><CornerUpLeft /></span>clawback<span className="wordmark-dot">.</span>
        </Link>

        <div className="workspace-wrap" ref={menuRef}>
          <button className="workspace" aria-expanded={menuOpen} aria-haspopup="menu" onClick={() => setMenuOpen((open) => !open)} disabled={!account}>
            <BrandAvatar account={account} />
            <span className="workspace-name">{account?.brand.name ?? 'Loading…'}<small>{account ? `${account.brand.kind} · ${account.brand.city}` : ' '}</small></span>
            <ChevronDown />
          </button>
          {menuOpen && account && (
            <div className="workspace-menu" role="menu" aria-label="Accounts">
              <span className="menu-label">Accounts</span>
              {(accounts ?? []).map((a) => (
                <button key={a.id} role="menuitemradio" aria-checked={a.id === id} className="account-option" onClick={() => switchTo(a)}>
                  <BrandAvatar account={a} />
                  <span><strong>{a.brand.name}</strong><small>Sells through {a.distributor.name}</small></span>
                  {a.id === id && <Check className="account-check" />}
                </button>
              ))}
              <div className="menu-separator" />
              <button role="menuitem" onClick={() => { setDetailsOpen(true); setMenuOpen(false) }}><Info /> Account details</button>
              <div className="menu-separator" />
              <span className="menu-label">{person ? `Signed in as ${person} · ${roleWord}` : 'Not signed in'}</span>
              {role !== 'owner' && <button role="menuitem" onClick={() => { setMenuOpen(false); askSignIn('owner') }}><LogIn /> Sign in as owner<small className="menu-hint">{account.brand.owner.name}</small></button>}
              {role !== 'controller' && <button role="menuitem" onClick={() => { setMenuOpen(false); askSignIn('controller') }}><LogIn /> Sign in as controller<small className="menu-hint">{account.brand.controller.name}</small></button>}
              {role && <button role="menuitem" onClick={() => { setMenuOpen(false); signOut() }}><LogOut /> Sign out</button>}
              <div className="menu-separator" />
              <button role="menuitem" disabled={resetState.busy} onClick={() => { setMenuOpen(false); void reset() }}><RotateCcw /> {resetState.busy ? 'Resetting…' : 'Reset workspace'}</button>
            </div>
          )}
        </div>

        <span className="nav-label">Workspace</span>
        <nav aria-label="Workspace">
          {WORKSPACE.map(({ key, label, icon: Icon }) => (
            <Link key={key} href={withAccount('/workspace', id, key === 'overview' ? undefined : { view: key })} className={`nav-item ${active === key ? 'active' : ''}`} aria-current={active === key ? 'page' : undefined}>
              <Icon />{label}{key === 'approvals' && approvalsWaiting && <span className="nav-count" aria-label="1 waiting">1</span>}
            </Link>
          ))}
          <span className="nav-label nav-label-inline">Tools</span>
          {TOOLS.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={withAccount(href, id)} className={`nav-item ${active === href ? 'active' : ''}`} aria-current={active === href ? 'page' : undefined}>
              <Icon />{label}
            </Link>
          ))}
          {account && (
            <a className="nav-item" href={withAccount('/portal', id)} target="_blank" rel="noreferrer">
              <ExternalLink />{account.distributor.portal_name}
            </a>
          )}
        </nav>

        <div className="sidebar-bottom">
          {account && person && (
            <div className="viewer">
              <span className="viewer-avatar" aria-hidden>{person.split(' ').map((p) => p[0]).join('').slice(0, 2)}</span>
              <span><strong>{person}</strong><small>{roleWord} · {account.brand.name}</small></span>
              <button className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut /></button>
            </div>
          )}
          {account && !person && <button className="secondary full viewer-signin" onClick={() => askSignIn('owner')}><LogIn /> Sign in</button>}
        </div>
      </aside>

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
