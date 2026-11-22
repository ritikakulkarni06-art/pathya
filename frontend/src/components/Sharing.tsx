// Share a chapter with classmates by the email address of their Pathya account (owners only).
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Loader2, UserMinus } from 'lucide-react'
import { api, ShareError, type Grant } from '../api/client'
import { say } from '../state/app'

const ROLE: Record<Grant['role'], string> = { reader: 'Can read and listen', reviewer: 'Can also review and correct' }

export function Sharing({ docId, title, online }: { docId: string; title: string; online: boolean }) {
  const [grants, setGrants] = useState<Grant[] | null | undefined>(undefined)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Grant['role']>('reader')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const errorBox = useRef<HTMLParagraphElement>(null)
  const ids = { email: useId(), role: useId(), hint: useId() }

  const load = () => api.listGrants(docId).then(setGrants, () => setGrants(undefined))
  useEffect(() => { if (online) void load() }, [docId, online])
  useEffect(() => { if (error) errorBox.current?.focus() }, [error])

  // Only the owner can share; for everyone else the section is not shown.
  if (grants === null) return null

  const add = async (e: FormEvent) => {
    e.preventDefault()
    const mail = email.trim()
    if (!/^\S+@\S+\.\S+$/.test(mail)) return setError('Enter the email address of your classmate’s Pathya account.')
    setBusy(true)
    setError('')
    try {
      await api.share(docId, mail, role)
      setEmail('')
      say(`${mail} can now open “${title}”.`, 'ok')
      await load()
    } catch (err) {
      setError(err instanceof ShareError ? err.message : online ? 'Sharing did not work. Try again.' : 'You are offline. Sharing needs internet.')
    }
    setBusy(false)
  }

  const remove = async (g: Grant) => {
    try {
      await api.unshare(docId, g.user_id)
      say(`${g.email} can no longer open “${title}”. Any copy they downloaded is deleted when their device next connects.`, 'ok')
      await load()
    } catch {
      say('Access could not be removed. Nothing was changed. Try again.', 'bad')
    }
  }

  return (
    <section aria-labelledby="ch-share" className="card px-5 py-5">
      <h2 id="ch-share" className="m-0 text-lg font-bold tracking-tight">Share with classmates</h2>
      {!online ? (
        <p className="m-0 mt-2 text-muted">Sharing needs internet.</p>
      ) : grants === undefined ? (
        <p className="m-0 mt-2 text-muted">Loading…</p>
      ) : (
        <>
          {grants.length === 0 ? (
            <p className="m-0 mt-2 text-muted">Only you can open this chapter.</p>
          ) : (
            <ul className="m-0 mt-3 grid list-none gap-2 p-0" aria-label="People who can open this chapter">
              {grants.map((g) => (
                <li key={g.user_id} className="flex items-center gap-3">
                  <span className="min-w-0 flex-1"><span className="block truncate font-medium">{g.email}</span><span className="text-sm text-muted">{ROLE[g.role]}</span></span>
                  <button type="button" className="btn" onClick={() => void remove(g)} aria-label={`Remove access for ${g.email}`}><UserMinus size={16} aria-hidden /> Remove</button>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={add} noValidate className="mt-4 grid gap-3">
            {error && <p ref={errorBox} tabIndex={-1} role="alert" className="m-0 rounded-control bg-bad-bg px-3 py-2.5 text-bad-ink">{error}</p>}
            <div className="grid gap-1.5">
              <label htmlFor={ids.email} className="font-medium">Classmate’s email address</label>
              <input id={ids.email} className="field" type="email" autoComplete="off" inputMode="email" autoCapitalize="none" spellCheck={false}
                value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} aria-describedby={ids.hint} />
              <p id={ids.hint} className="m-0 text-sm text-muted">They need a Pathya account with this address.</p>
            </div>
            <div className="grid gap-1.5">
              <label htmlFor={ids.role} className="font-medium">What they can do</label>
              <select id={ids.role} className="field" value={role} onChange={(e) => setRole(e.target.value as Grant['role'])}>
                <option value="reader">{ROLE.reader}</option>
                <option value="reviewer">{ROLE.reviewer}</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary justify-self-start" disabled={busy}>
              {busy && <Loader2 size={16} className="animate-spin" aria-hidden />} {busy ? 'Sharing…' : 'Share'}
            </button>
          </form>
        </>
      )}
    </section>
  )
}
