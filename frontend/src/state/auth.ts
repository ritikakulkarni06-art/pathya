import { create } from 'zustand'
import { authApi, SIGNED_OUT_EVENT, type User } from '../api/auth'
import { setOwner, store } from '../lib/db'

// The last person who signed in on this device. It lets downloaded chapters open with no connection;
// it is not proof of identity, and the server checks the real session on every request.
const REMEMBERED = 'pathya.user.v1'
const remembered = (): User | null => {
  try { return JSON.parse(localStorage.getItem(REMEMBERED) ?? 'null') } catch { return null }
}
const remember = (user: User | null) => {
  if (user) setOwner(user.id)
  try {
    if (user) localStorage.setItem(REMEMBERED, JSON.stringify(user))
    else localStorage.removeItem(REMEMBERED)
  } catch { /* private window: the session still works until the tab closes */ }
}

interface AuthState {
  status: 'checking' | 'in' | 'out'
  user: User | null
  /** True when the server could not be reached and the remembered account is used for downloaded chapters. */
  offline: boolean
  check(): Promise<void>
  login(email: string, password: string): Promise<void>
  register(email: string, password: string): Promise<void>
  logout(): Promise<void>
}

export const useAuth = create<AuthState>((set) => ({
  status: 'checking',
  user: null,
  offline: false,
  async check() {
    try {
      const user = await authApi.me()
      remember(user)
      set({ status: user ? 'in' : 'out', user, offline: false })
    } catch {
      const user = remembered()
      if (user) setOwner(user.id)
      set({ status: user ? 'in' : 'out', user, offline: !!user })
    }
  },
  async login(email, password) {
    const user = await authApi.login(email, password)
    remember(user)
    set({ status: 'in', user, offline: false })
  },
  async register(email, password) {
    const user = await authApi.register(email, password)
    remember(user)
    set({ status: 'in', user, offline: false })
  },
  async logout() {
    // Leave this device signed out even if the server cannot be told right now.
    await authApi.logout().catch(() => {})
    // Signing out on purpose clears this account's copies, so a shared device keeps nothing private.
    await store.purgeAll().catch(() => {})
    remember(null)
    set({ status: 'out', user: null, offline: false })
  },
}))

// The server said the session ended (HTTP 401 on any request).
window.addEventListener(SIGNED_OUT_EVENT, () => {
  remember(null)
  useAuth.setState({ status: 'out', user: null, offline: false })
})
window.addEventListener('online', () => void useAuth.getState().check())
