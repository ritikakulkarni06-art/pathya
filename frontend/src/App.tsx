import { lazy, Suspense, useEffect } from 'react'
import { Route, Routes } from 'react-router'
import { applyRootPrefs, usePrefs } from './state/prefs'
import { Notices } from './components/Notices'
import Library from './routes/Library'

const Reader = lazy(() => import('./routes/Reader'))
const Downloads = lazy(() => import('./routes/Downloads'))
const Settings = lazy(() => import('./routes/Settings'))
const AddChapter = lazy(() => import('./routes/AddChapter'))
const ReviewDesk = lazy(() => import('./routes/ReviewDesk'))
const Chapter = lazy(() => import('./routes/Chapter'))

export default function App() {
  const theme = usePrefs((p) => p.theme)
  const reduceMotion = usePrefs((p) => p.reduceMotion)
  useEffect(() => applyRootPrefs({ theme, reduceMotion }), [theme, reduceMotion])

  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <Suspense fallback={<p className="p-6 text-muted" role="status">Loading…</p>}>
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
      </Suspense>
      <Notices />
    </>
  )
}
