import { lazy, Suspense, useEffect } from 'react'
import { Route, Routes, useLocation } from 'react-router'
import { applyRootPrefs, usePrefs } from './state/prefs'
import { Notices } from './components/Notices'
import Library from './routes/Library'
import { useAuth } from './state/auth'
import { revalidateDownloads, useOnline } from './state/app'

const Reader = lazy(() => import('./routes/Reader'))
const Downloads = lazy(() => import('./routes/Downloads'))
const Settings = lazy(() => import('./routes/Settings'))
const AddChapter = lazy(() => import('./routes/AddChapter'))
const ReviewDesk = lazy(() => import('./routes/ReviewDesk'))
const Chapter = lazy(() => import('./routes/Chapter'))
const SignIn = lazy(() => import('./routes/SignIn'))

export default function App() {
  const theme = usePrefs((p) => p.theme)
  const reduceMotion = usePrefs((p) => p.reduceMotion)
  useEffect(() => applyRootPrefs({ theme, reduceMotion }), [theme, reduceMotion])

  const auth = useAuth((s) => s.status)
  const check = useAuth((s) => s.check)
  useEffect(() => void check(), [check])
  const online = useOnline()
  const resetting = useLocation().pathname === '/reset-password'
  useEffect(() => { if (auth === 'in' && online) void revalidateDownloads() }, [auth, online])

  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <Suspense fallback={<p className="p-6 text-muted" role="status">Loading…</p>}>
        {auth === 'checking' ? <p className="p-6 text-muted" role="status">Loading…</p> : auth === 'out' || resetting ? <SignIn /> : (
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/read/:docId" element={<Reader />} />
          <Route path="/downloads" element={<Downloads />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/add" element={<AddChapter />} />
          <Route path="/review" element={<ReviewDesk />} />
          <Route path="/chapter/:docId" element={<Chapter />} />
          <Route path="*" element={<Library />} />
        </Routes>
        )}
      </Suspense>
      <Notices />
    </>
  )
}
