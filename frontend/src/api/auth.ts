// Sign-in against Role 3's session API (POST /auth/register, /auth/login, /auth/logout, GET /auth/me).
// The server keeps the session in an HttpOnly cookie; writes must echo the pathya_csrf cookie in X-CSRF-Token.
// Without VITE_API_URL a stand-in keeps accounts in this browser, with the same rules and messages.
import { OfflineError } from './client'

export interface User {
  id: string
  email: string
  role: 'user' | 'admin'
}

/** A refusal the person can act on. `code` is Role 3's machine code, `message` is ready to show. */
export class AuthError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

export const PASSWORD_MIN = 12
export const SIGNED_OUT_EVENT = 'pathya:signed-out'

export interface AuthApi {
  /** The signed-in person, or null when nobody is signed in. */
  me(): Promise<User | null>
  login(email: string, password: string): Promise<User>
  /** Creates the account and signs in. */
  register(email: string, password: string): Promise<User>
  logout(): Promise<void>
  /** Sends a reset link if an account uses this address. Never says whether one does. */
  requestReset(email: string): Promise<void>
  /** Sets a new password with the token from the link. Signs the account out everywhere. */
  confirmReset(token: string, password: string): Promise<void>
}

/** Header every write to the real server must carry. */
export function csrfHeader(): Record<string, string> {
  const token = document.cookie.split('; ').find((c) => c.startsWith('pathya_csrf='))?.slice('pathya_csrf='.length)
  return token ? { 'X-CSRF-Token': decodeURIComponent(token) } : {}
}

const online = () => {
  if (!navigator.onLine) throw new OfflineError()
}

const MESSAGES: Record<string, string> = {
  invalid_credentials: 'The email or password is incorrect.',
  account_unavailable: 'This account cannot be registered. Try signing in.',
  https_required: 'Use a secure HTTPS connection to sign in.',
  reset_link_invalid: 'This reset link has expired or was already used. Ask for a new one.',
}

function http(base: string): AuthApi {
  const send = async (path: string, body?: unknown): Promise<Response> => {
    online()
    const res = await fetch(base + path, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...csrfHeader() },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (res.ok) return res
    const problem = await res.json().catch(() => ({}))
    if (res.status === 429) throw new AuthError('rate_limited', 'Too many attempts. Wait a few minutes, then try again.')
    if (res.status === 422) throw new AuthError('invalid_input', `Check the email address, and use a password of at least ${PASSWORD_MIN} characters.`)
    throw new AuthError(problem.code ?? 'failed', MESSAGES[problem.code] ?? (typeof problem.detail === 'string' ? problem.detail : `The server answered ${res.status}.`))
  }
  const api: AuthApi = {
    async me() {
      online()
      const res = await fetch(base + '/auth/me', { credentials: 'include' })
      if (res.status === 401 || res.status === 403) return null
      if (!res.ok) throw new Error(`The server answered ${res.status}.`)
      return res.json()
    },
    login: async (email, password) => (await send('/auth/login', { email, password })).json(),
    async register(email, password) {
      await send('/auth/register', { email, password })
      return api.login(email, password) // registering does not start a session
    },
    logout: async () => void (await send('/auth/logout')),
    requestReset: async (email) => void (await send('/auth/password-reset', { email })),
    confirmReset: async (token, password) => void (await send('/auth/password-reset/confirm', { token, password })),
  }
  return api
}

// ---------- stand-in ----------
const USERS = 'pathya.mock.users.v1'
const SESSION = 'pathya.mock.session.v1'
const RESETS = 'pathya.mock.resets.v1'
const OUTBOX = 'pathya.mock.outbox.v1'
const SAMPLE: User = { id: 'sample-student', email: 'student@pathya.example', role: 'user' }
const read = <T,>(key: string, fallback: T): T => {
  try { return JSON.parse(localStorage.getItem(key) ?? '') as T } catch { return fallback }
}
const digest = async (text: string) =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map((b) => b.toString(16).padStart(2, '0')).join('')
const pause = () => new Promise((r) => setTimeout(r, 250))

const mock: AuthApi = {
  async me() {
    online()
    // The sample build starts signed in as a sample student, so the chapters can be tried at once.
    const s = read<User | 'out' | null>(SESSION, null)
    return s === 'out' ? null : s ?? SAMPLE
  },
  async login(email, password) {
    online()
    await pause()
    const users = read<Record<string, { id: string; hash: string }>>(USERS, {})
    const found = users[email.toLowerCase()]
    if (!found || found.hash !== (await digest(password))) throw new AuthError('invalid_credentials', MESSAGES.invalid_credentials)
    const user: User = { id: found.id, email, role: 'user' }
    localStorage.setItem(SESSION, JSON.stringify(user))
    return user
  },
  async register(email, password) {
    online()
    await pause()
    const users = read<Record<string, { id: string; hash: string }>>(USERS, {})
    if (users[email.toLowerCase()]) throw new AuthError('account_unavailable', MESSAGES.account_unavailable)
    users[email.toLowerCase()] = { id: crypto.randomUUID(), hash: await digest(password) }
    localStorage.setItem(USERS, JSON.stringify(users))
    return mock.login(email, password)
  },
  async logout() {
    localStorage.setItem(SESSION, JSON.stringify('out'))
  },
  // The stand-in has no email: the link is kept in this browser's "outbox" (pathya.mock.outbox.v1).
  async requestReset(email) {
    online()
    await pause()
    const users = read<Record<string, { id: string; hash: string }>>(USERS, {})
    if (!users[email.toLowerCase()]) return
    const token = crypto.randomUUID() + crypto.randomUUID()
    const resets = read<Record<string, { email: string; until: number }>>(RESETS, {})
    for (const k of Object.keys(resets)) if (resets[k].email === email.toLowerCase()) delete resets[k]
    resets[await digest(token)] = { email: email.toLowerCase(), until: Date.now() + 30 * 60_000 }
    localStorage.setItem(RESETS, JSON.stringify(resets))
    localStorage.setItem(OUTBOX, JSON.stringify({ to: email, link: `${location.origin}/reset-password?token=${token}` }))
  },
  async confirmReset(token, password) {
    online()
    await pause()
    const resets = read<Record<string, { email: string; until: number }>>(RESETS, {})
    const key = await digest(token)
    const r = resets[key]
    if (!r || r.until < Date.now()) throw new AuthError('reset_link_invalid', MESSAGES.reset_link_invalid)
    delete resets[key]
    localStorage.setItem(RESETS, JSON.stringify(resets))
    const users = read<Record<string, { id: string; hash: string }>>(USERS, {})
    users[r.email] = { ...users[r.email], hash: await digest(password) }
    localStorage.setItem(USERS, JSON.stringify(users))
    localStorage.setItem(SESSION, JSON.stringify('out'))
  },
}

const url = import.meta.env.VITE_API_URL as string | undefined
export const authApi: AuthApi = url ? http(url) : mock
