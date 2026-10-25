'use client'

import type { ReactNode } from 'react'
import { inkOn } from '@/lib/accounts'
import type { Account } from '@/lib/types'
import TopBar from './TopBar'
import SessionDialogs from './SessionDialogs'

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
  accounts?: Account[] | null
  active?: View | string
  crumb?: string
  approvalsWaiting?: boolean
  onReset?: () => void
  children: ReactNode
}

/** The frame for the pages outside the console group (upload): the app's sidebar and the page. Account details, the
 * presenter's controls and Sign out live in the sidebar's user menu. */
export default function AppShell({ account, children }: Props) {
  return (
    <div className="app-shell">
      <TopBar account={account} />
      <div className="main-shell">{children}</div>
      <SessionDialogs account={account} />
    </div>
  )
}
