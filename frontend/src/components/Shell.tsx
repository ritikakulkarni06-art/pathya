import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, Link } from 'react-router'
import { ClipboardCheck, Contrast, Download, FilePlus2, LibraryBig, LogOut, Menu, Moon, SlidersHorizontal, Sun, WifiOff, X } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { refreshReviewCount, useOnline, useReviewCount } from '../state/app'
import { usingMock } from '../api/client'
import { usePrefs, type Theme } from '../state/prefs'
import { useAuth } from '../state/auth'
import { gsap, motionOK, useGSAP } from '../lib/motion'

/** Where the pill sat on the previous screen, so it can slide from there. */
let lastPill: { y: number; height: number } | null = null

const LINKS = [
  { to: '/', label: 'Library', icon: LibraryBig },
  { to: '/review', label: 'Review desk', icon: ClipboardCheck },
  { to: '/add', label: 'Add chapter', icon: FilePlus2 },
  { to: '/downloads', label: 'Downloads', icon: Download },
  { to: '/settings', label: 'Settings', icon: SlidersHorizontal },
]
const THEMES: { id: Theme; label: string; icon: typeof Sun }[] = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
  { id: 'contrast', label: 'High contrast', icon: Contrast },
]

export function Mark() {
  return (
    <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden>
      <rect width="32" height="32" rx="8" fill="var(--primary)" />
      <path d="M9 8h9.5a5.5 5.5 0 0 1 0 11H13v5H9z" fill="var(--on-primary)" />
      <rect x="13" y="11.5" width="6" height="4" rx="2" fill="var(--accent)" />
    </svg>
  )
}

export function OfflinePill() {
  const online = useOnline()
  if (online) return null
  return (
    <span className="pill pill-warn">
      <WifiOff size={12} aria-hidden /> Offline
    </span>
  )
}

function Badge({ n }: { n: number }) {
  if (!n) return null
  return (
    <span className="pill pill-warn ml-auto">
      <span className="sr-only">, </span>{n}<span className="sr-only"> to check</span>
    </span>
  )
}

/** Sidebar on wide screens, top bar with a menu on narrow ones. Shared by every screen except the reader. */
export function Shell({ title, lead, actions, children }: { title: string; lead?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const nav = useRef<HTMLElement>(null)
  const pill = useRef<HTMLSpanElement>(null)
  const toReview = useReviewCount((s) => s.count)
  const theme = usePrefs((p) => p.theme)
  const setPrefs = usePrefs((p) => p.set)
  const online = useOnline()
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)
  useEffect(() => void refreshReviewCount(), [online])
  useGSAP(() => {
    const active = nav.current?.querySelector<HTMLElement>('[aria-current="page"]')
    if (!pill.current) return
    if (!active || !active.offsetHeight) return void gsap.set(pill.current, { autoAlpha: 0 })
    const to = { y: active.offsetTop, height: active.offsetHeight }
    if (lastPill && motionOK()) gsap.fromTo(pill.current, { ...lastPill, autoAlpha: 1 }, { ...to, duration: 0.45, ease: 'power3.out' })
    else gsap.set(pill.current, { ...to, autoAlpha: 1 })
    lastPill = to
  }, { scope: nav })

  return (
    <div className="lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-surface px-3 py-5 lg:flex">
        <Link to="/" className="mb-6 flex items-center gap-2.5 px-3 text-lg font-bold" aria-label="Pathya, go to library">
          <Mark /> Pathya
        </Link>
        <nav ref={nav} aria-label="Main" className="relative flex flex-col gap-1">
          <span ref={pill} aria-hidden className="invisible absolute left-0 top-0 w-full rounded-control bg-raised" />
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end viewTransition className={({ isActive }) => `relative flex min-h-10 items-center gap-3 rounded-control px-3 font-medium transition-colors ${isActive ? 'text-ink' : 'text-muted hover:text-ink'}`}>
              <l.icon size={18} aria-hidden className="flex-none" /> {l.label}
              {l.to === '/review' && <Badge n={toReview} />}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto grid grid-cols-[minmax(0,1fr)] gap-3 px-1">
          <div role="group" aria-label="Page colours" className="grid grid-cols-3 gap-1 rounded-control bg-raised p-1">
            {THEMES.map((t) => (
              <button key={t.id} aria-pressed={theme === t.id} aria-label={`${t.label} page colours`} title={t.label} onClick={() => setPrefs({ theme: t.id })}
                className={`grid h-8 place-items-center rounded-[6px] transition-colors ${theme === t.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'}`}>
                <t.icon size={16} aria-hidden />
              </button>
            ))}
          </div>
          {user && (
            <div className="flex items-center gap-2 rounded-control border border-border px-3 py-2">
              <p className="m-0 min-w-0 flex-1"><span className="block text-xs text-muted">Signed in as</span><span className="block truncate text-sm font-medium" title={user.email}>{user.email}</span></p>
              <button className="btn btn-ghost btn-icon flex-none text-muted" aria-label="Sign out" title="Sign out" onClick={() => void logout()}><LogOut size={16} aria-hidden /></button>
            </div>
          )}
          <div className="flex min-h-6 flex-wrap gap-2 px-2">
            <OfflinePill />
            {usingMock && <span className="pill" title="No backend URL is configured, so the app is using the built-in sample chapters.">Sample data</span>}
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:hidden">
          <Link to="/" className="mr-4 flex items-center gap-2.5 text-base font-bold" aria-label="Pathya, go to library">
            <Mark /> Pathya
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <OfflinePill />
            <Dialog.Root open={open} onOpenChange={setOpen}>
              <Dialog.Trigger className="btn btn-ghost btn-icon" aria-label="Open menu">
                <Menu size={20} aria-hidden />
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Content className="fade-in fixed inset-0 z-40 bg-ground p-4" aria-describedby={undefined}>
                  <div className="flex h-14 items-center justify-between">
                    <Dialog.Title className="m-0 text-base font-bold">Menu</Dialog.Title>
                    <Dialog.Close className="btn btn-ghost btn-icon" aria-label="Close menu"><X size={20} aria-hidden /></Dialog.Close>
                  </div>
                  <nav aria-label="Main" className="mt-2 flex flex-col">
                    {LINKS.map((l) => (
                      <NavLink key={l.to} to={l.to} end onClick={() => setOpen(false)} className={({ isActive }) => `flex items-center gap-3 border-b border-border py-4 text-xl ${isActive ? 'font-bold' : ''}`}>
                        <l.icon size={22} aria-hidden /> {l.label}
                        {l.to === '/review' && <Badge n={toReview} />}
                      </NavLink>
                    ))}
                  </nav>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </div>
        </header>
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1120px] px-4 pb-16 pt-4 outline-none sm:px-8 lg:pt-10">
          <div className="mb-7 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
            <div className="min-w-0">
              <h1 className="m-0 text-3xl font-bold tracking-tight">{title}</h1>
              {lead && <p className="m-0 mt-1.5 max-w-[65ch] text-base text-muted">{lead}</p>}
            </div>
            {actions}
          </div>
          {children}
        </main>
      </div>
    </div>
  )
}
