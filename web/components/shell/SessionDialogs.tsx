'use client'

import { useState } from 'react'
import { KeyRound, X } from 'lucide-react'
import { closePrompt, submitAdminToken, useSession } from '@/lib/session'
import type { Account } from '@/lib/types'

/** The presenter's admin-token prompt (demo reset, per-visitor limits). Mounted once per page; it opens when an action
 * needs the token. Signing in has no dialog: it happens on /signin. */
// `account` stays in the props for the callers.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export default function SessionDialogs(_props: { account: Account | null }) {
  const { prompt } = useSession()
  if (!prompt) return null
  return <AdminDialog key={`admin-${prompt.reason}`} reason={prompt.reason} />
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
