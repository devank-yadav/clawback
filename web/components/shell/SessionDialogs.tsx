'use client'

import { useState } from 'react'
import { KeyRound, LogIn, X } from 'lucide-react'
import { closePrompt, signIn, submitAdminToken, useSession, type Role } from '@/lib/session'
import type { Account } from '@/lib/types'

/** The sign-in and admin-token prompts. Mounted once per page; they open when an action needs them. */
export default function SessionDialogs({ account }: { account: Account | null }) {
  const { prompt } = useSession()
  if (!prompt) return null
  if (prompt.kind === 'role') return <SignInDialog key={`role-${prompt.role}-${prompt.reason}`} role={prompt.role} reason={prompt.reason} account={account} />
  return <AdminDialog key={`admin-${prompt.reason}`} reason={prompt.reason} />
}

/** The admin's name: the brand's owner, the one person who answers and approves. */
export const roleName = (_role: Role, account: Account | null) => account?.brand.owner.name ?? 'Admin'

function SignInDialog({ role, reason, account }: { role: Role; reason: string | null; account: Account | null }) {
  const [code, setCode] = useState('')
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={closePrompt}>
      <form className="brand-dialog token-dialog" role="dialog" aria-modal="true" aria-labelledby="signin-title" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); signIn(role, code.trim() || null) }}>
        <button type="button" className="icon-button dialog-close" onClick={closePrompt} aria-label="Cancel"><X /></button>
        <span className="attention-icon"><LogIn /></span>
        <div>
          <h2 id="signin-title">Sign in as {roleName(role, account)}</h2>
          <p>The admin answers policy questions (each answer can become a rule) and approves the accounting entries. Nothing posts without a yes.</p>
        </div>
        {reason && <p className="field-error" role="alert">{reason}</p>}
        <label htmlFor="role-code" className="note-label">Admin access code <span>(leave empty if your server has none)</span></label>
        <input id="role-code" type="password" autoFocus autoComplete="off" value={code} onChange={(event) => setCode(event.target.value)} />
        <button className="primary" type="submit">Sign in</button>
      </form>
    </div>
  )
}

function AdminDialog({ reason }: { reason: string }) {
  const [token, setToken] = useState('')
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={closePrompt}>
      <form className="brand-dialog token-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-title" onMouseDown={(event) => event.stopPropagation()} onSubmit={(event) => { event.preventDefault(); if (token.trim()) submitAdminToken(token.trim()) }}>
        <button type="button" className="icon-button dialog-close" onClick={closePrompt} aria-label="Cancel"><X /></button>
        <span className="attention-icon"><KeyRound /></span>
        <div><h2 id="admin-title">Admin token</h2><p>{reason}</p></div>
        <label htmlFor="admin-token" className="note-label">Admin token</label>
        <input id="admin-token" type="password" autoFocus autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} />
        <button className="primary" type="submit" disabled={!token.trim()}>Continue</button>
      </form>
    </div>
  )
}
