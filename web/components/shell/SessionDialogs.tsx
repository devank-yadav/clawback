'use client'

import { useState } from 'react'
import { KeyRound, LogIn, X } from 'lucide-react'
import { ApiError, login } from '@/lib/api'
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

/** The admin's ID and password. On success the access code is kept for this tab and `onDone` runs. */
export function SignInForm({ role, reason, onDone, autoFocus = true }: { role: Role; reason?: string | null; onDone?: () => void; autoFocus?: boolean }) {
  const [id, setId] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function submit() {
    if (!id.trim() || !password) {
      setProblem('Enter the admin ID and password.')
      return
    }
    setBusy(true)
    setProblem(null)
    try {
      const r = await login(id.trim(), password)
      signIn(role, r.code)
      onDone?.()
    } catch (e) {
      setProblem(e instanceof ApiError && e.detail ? e.detail : `Couldn’t sign in (${(e as Error).message}). Try again.`)
      setBusy(false)
    }
  }

  return (
    <form className="signin-form" onSubmit={(event) => { event.preventDefault(); void submit() }}>
      {(problem ?? reason) && <p className="field-error" role="alert">{problem ?? reason}</p>}
      <label htmlFor="signin-id" className="note-label">Admin ID</label>
      <input id="signin-id" autoFocus={autoFocus} autoComplete="username" value={id} onChange={(event) => { setId(event.target.value); setProblem(null) }} />
      <label htmlFor="signin-password" className="note-label">Password</label>
      <input id="signin-password" type="password" autoComplete="current-password" value={password} onChange={(event) => { setPassword(event.target.value); setProblem(null) }} />
      <button className="primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
  )
}

function SignInDialog({ role, reason, account }: { role: Role; reason: string | null; account: Account | null }) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={closePrompt}>
      <div className="brand-dialog token-dialog" role="dialog" aria-modal="true" aria-labelledby="signin-title" onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="icon-button dialog-close" onClick={closePrompt} aria-label="Cancel"><X /></button>
        <span className="attention-icon"><LogIn /></span>
        <div>
          <h2 id="signin-title">Sign in as {roleName(role, account)}</h2>
          <p>The admin answers policy questions (each answer can become a rule) and approves the accounting entries. Nothing posts without a yes.</p>
        </div>
        <SignInForm role={role} reason={reason} />
      </div>
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
