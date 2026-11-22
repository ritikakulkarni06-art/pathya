import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { BookOpenCheck, Eye, EyeOff, Headphones, Loader2, WifiOff } from 'lucide-react'
import { Mark } from '../components/Shell'
import { AuthError, authApi, PASSWORD_MIN } from '../api/auth'
import { OfflineError, usingMock } from '../api/client'
import { useAuth } from '../state/auth'
import { useOnline } from '../state/app'

const POINTS = [
  { icon: BookOpenCheck, text: 'Your chapters, bookmarks and place in each book' },
  { icon: Headphones, text: 'Narration in English and Hindi, sentence by sentence' },
  { icon: WifiOff, text: 'Downloaded chapters open with no connection' },
]

type Mode = 'in' | 'new' | 'forgot' | 'reset'
const TITLES: Record<Mode, string> = { in: 'Sign in', new: 'Create your account', forgot: 'Reset your password', reset: 'Choose a new password' }
const LEADS: Record<Mode, string> = {
  in: 'Sign in to open your chapters.',
  new: 'One account keeps your chapters and corrections together.',
  forgot: 'Enter the email address of your account. We will send a link to choose a new password.',
  reset: 'The link from your email is valid for 30 minutes and works once.',
}
const BUTTONS: Record<Mode, string> = { in: 'Sign in', new: 'Create account', forgot: 'Send reset link', reset: 'Save new password' }

/** The reset link opens /reset-password?token=... */
const resetToken = () => (location.pathname === '/reset-password' ? new URLSearchParams(location.search).get('token') : null)

export default function SignIn() {
  const [token] = useState(resetToken)
  const [mode, setMode] = useState<Mode>(token ? 'reset' : 'in')
  const [notice, setNotice] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const errorBox = useRef<HTMLParagraphElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const emailId = useId()
  const passId = useId()
  const online = useOnline()
  const login = useAuth((s) => s.login)
  const register = useAuth((s) => s.register)
  const check = useAuth((s) => s.check)
  const navigate = useNavigate()
  const creating = mode === 'new'
  const needsEmail = mode !== 'reset'
  const needsPassword = mode !== 'forgot'
  const newPassword = mode === 'new' || mode === 'reset'

  useEffect(() => { document.title = `${TITLES[mode]} · Pathya` }, [mode])
  useEffect(() => { if (error) errorBox.current?.focus() }, [error])

  const fail = (message: string) => {
    setError('')
    // Set on the next tick so the same message is announced again on a second failed try.
    setTimeout(() => setError(message))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const mail = email.trim()
    if (needsEmail && !/^\S+@\S+\.\S+$/.test(mail)) return fail('Enter your email address, for example name@school.in.')
    if (needsPassword && !password) return fail(mode === 'reset' ? 'Enter a new password.' : 'Enter your password.')
    if (newPassword && password.length < PASSWORD_MIN) return fail(`Choose a password with at least ${PASSWORD_MIN} characters. Yours has ${password.length}.`)
    setBusy(true)
    setNotice('')
    try {
      if (mode === 'forgot') {
        await authApi.requestReset(mail)
        setError('')
        setNotice(`If an account uses ${mail}, a link to choose a new password is on its way. It works for 30 minutes. Check your spam folder too.`)
        setBusy(false)
        return
      }
      if (mode === 'reset') {
        await authApi.confirmReset(token ?? '', password)
        navigate('/', { replace: true })
        setPassword('')
        setMode('in')
        setError('')
        setNotice('Your password was changed, and you were signed out on every device. Sign in with the new password.')
        setBusy(false)
        void check()
        heading.current?.focus()
        return
      }
      await (creating ? register(mail, password) : login(mail, password))
    } catch (err) {
      fail(err instanceof OfflineError ? 'You are offline. Connect to the internet to sign in.'
        : err instanceof AuthError ? err.message
        : 'Sign-in did not work because the server could not be reached. Try again in a moment.')
      setBusy(false)
    }
  }

  const go = (next: Mode) => {
    if (mode === 'reset') navigate('/', { replace: true })
    setMode(next)
    setError('')
    setNotice('')
    heading.current?.focus()
  }
  const swap = () => go(creating ? 'in' : 'new')

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside aria-label="About Pathya" className="hidden flex-col justify-between bg-primary p-12 text-on-primary lg:flex">
        <p className="m-0 flex items-center gap-2.5 text-lg font-bold"><Mark /> Pathya</p>
        <div>
          <p className="m-0 max-w-[16ch] text-4xl font-bold leading-tight">Every textbook page, readable your way.</p>
          <ul className="m-0 mt-8 grid list-none gap-4 p-0">
            {POINTS.map((p) => (
              <li key={p.text} className="flex items-center gap-3"><p.icon size={20} aria-hidden className="flex-none" /> {p.text}</li>
            ))}
          </ul>
        </div>
        <p className="m-0 text-sm opacity-80">An accessible reader for English and Hindi textbooks.</p>
      </aside>

      <main id="main" tabIndex={-1} className="flex items-center justify-center px-4 py-10 outline-none sm:px-6">
        <div className="w-full max-w-[420px]">
          <p className="m-0 mb-8 flex items-center gap-2.5 text-lg font-bold lg:hidden"><Mark /> Pathya</p>
          <h1 ref={heading} tabIndex={-1} className="m-0 text-3xl font-bold outline-none">{TITLES[mode]}</h1>
          <p className="m-0 mt-2 text-muted">{LEADS[mode]}</p>
          {notice && <p role="status" className="m-0 mt-5 rounded-control bg-raised px-3 py-2.5">{notice}</p>}

          {!online && <p className="m-0 mt-5 rounded-control bg-raised px-3 py-2.5" role="status">You are offline. Signing in needs a connection.</p>}

          <form onSubmit={submit} noValidate className="mt-6 grid gap-4" aria-describedby={error ? 'signin-error' : undefined}>
            {error && <p id="signin-error" ref={errorBox} tabIndex={-1} role="alert" className="m-0 rounded-control bg-bad-bg px-3 py-2.5 text-bad-ink">{error}</p>}
            {needsEmail && <div className="grid gap-1.5">
              <label htmlFor={emailId} className="font-medium">Email address</label>
              <input id={emailId} className="field" type="email" name="email" autoComplete="username" inputMode="email" autoCapitalize="none" spellCheck={false}
                value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} />
            </div>}
            {needsPassword && <div className="grid gap-1.5">
              <label htmlFor={passId} className="font-medium">{mode === 'reset' ? 'New password' : 'Password'}</label>
              <div className="relative">
                <input id={passId} className="field pr-12" type={show ? 'text' : 'password'} name="password" autoComplete={newPassword ? 'new-password' : 'current-password'}
                  value={password} onChange={(e) => setPassword(e.target.value)} required maxLength={128} aria-describedby={newPassword ? `${passId}-hint` : undefined} />
                <button type="button" className="btn btn-ghost btn-icon absolute right-1 top-1/2 -translate-y-1/2 text-muted" aria-pressed={show} aria-label="Show password" onClick={() => setShow((s) => !s)}>
                  {show ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
                </button>
              </div>
              {newPassword && <p id={`${passId}-hint`} className="m-0 text-sm text-muted">At least {PASSWORD_MIN} characters. A few words in a row is easy to remember and hard to guess.</p>}
              {mode === 'in' && <button type="button" className="justify-self-start text-sm font-medium text-ink underline" onClick={() => go('forgot')}>Forgot your password?</button>}
            </div>}
            <button className="btn btn-primary mt-1 min-h-11 justify-center" type="submit" disabled={busy}>
              {busy && <Loader2 size={16} className="animate-spin" aria-hidden />} {busy ? 'One moment…' : BUTTONS[mode]}
            </button>
          </form>

          {mode === 'forgot' || mode === 'reset' ? (
            <p className="m-0 mt-6 text-muted">
              Remembered it?{' '}
              <button type="button" className="font-medium text-ink underline" onClick={() => go('in')}>Back to sign in</button>
            </p>
          ) : (
            <p className="m-0 mt-6 text-muted">
              {creating ? 'Already have an account?' : 'New to Pathya?'}{' '}
              <button type="button" className="font-medium text-ink underline" onClick={swap}>{creating ? 'Sign in instead' : 'Create an account'}</button>
            </p>
          )}
          {usingMock && <p className="m-0 mt-6 rounded-control bg-raised px-3 py-2.5 text-sm text-muted">Sample build: accounts are kept only in this browser. Do not reuse a real password.</p>}
        </div>
      </main>
    </div>
  )
}
