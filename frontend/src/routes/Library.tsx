import { useRef, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ArrowRight, Check, ClipboardCheck, Download, HardDriveDownload, Loader2, Plus, Type } from 'lucide-react'
import { Shell } from '../components/Shell'
import { useLibrary, type LibraryRow } from '../components/useLibrary'
import { usePrefs } from '../state/prefs'
import { formatBytes } from '../lib/db'
import type { DocumentSummary } from '../types'
import { gsap, motionOK, useGSAP } from '../lib/motion'

// Cover colours, like the cloth of a textbook spine. White text reads on all of them.
const FIELDS = ['#0f5e59', '#23466e', '#8a3b2a', '#5f5210']

/** A small book: the coloured board swings open when the card is hovered or focused. */
export function Cover({ doc, index }: { doc: DocumentSummary; index: number }) {
  return (
    <div aria-hidden className="book-cover relative h-36 w-28 flex-none" lang={doc.languages[0]}>
      <div className="absolute inset-0 flex items-center justify-end rounded-[10px] border border-border bg-ground pr-2 text-primary"><ArrowRight size={20} /></div>
      <div className="book-board absolute inset-0 flex flex-col justify-between rounded-[10px] p-3 text-white" style={{ background: FIELDS[index % FIELDS.length] }}>
        <span className="text-xs opacity-85">{doc.subject.split(' · ')[0]}</span>
        <span className="text-4xl font-bold leading-none">{[...doc.title][0]}</span>
        <span className="text-xs opacity-85" lang="en">{doc.printed_range ? `pp. ${doc.printed_range}` : `${doc.page_count} pages`}</span>
      </div>
    </div>
  )
}

function Bar({ value, onPrimary }: { value: number; onPrimary?: boolean }) {
  const pct = Math.round(value * 100)
  return (
    <div className={`h-2 overflow-hidden rounded-full ${onPrimary ? 'bg-on-primary/25' : 'bg-raised'}`} role="img" aria-label={`${pct}% read`}>
      <div data-bar-fill className={`h-full origin-left rounded-full ${onPrimary ? 'bg-on-primary' : 'bg-primary'}`} style={{ width: `${Math.max(pct, 2)}%` }} />
    </div>
  )
}

/** The page on the banner: a highlight walks down the lines, the way narration follows the text. */
function ReadingPage() {
  const widths = [78, 92, 86, 60, 0, 90, 82, 94, 48]
  return (
    <svg aria-hidden viewBox="0 0 150 180" className="hidden w-44 flex-none rotate-3 drop-shadow-xl md:block">
      <rect width="150" height="180" rx="10" fill="var(--surface)" />
      <rect x="18" y="20" width="62" height="9" rx="3" fill="var(--text)" />
      <rect className="read-line" x="12" y="41" width="126" height="12" rx="4" fill="var(--mark-bg)" />
      {widths.map((w, i) => w > 0 && <rect key={i} x="18" y={44 + i * 14} width={w} height="5" rx="2.5" fill="var(--control)" />)}
      <circle cx="126" cy="24" r="6" fill="var(--accent)" />
    </svg>
  )
}

function Tile({ to, icon, label, value, note }: { to: string; icon: ReactNode; label: string; value: ReactNode; note: string }) {
  return (
    <Link data-side to={to} viewTransition className="card tile flex items-start gap-3.5 px-5 py-4">
      <span className="grid size-10 flex-none place-items-center rounded-control bg-raised text-primary" aria-hidden>{icon}</span>
      <span className="min-w-0">
        <span className="block text-muted">{label}</span>
        <span className="block text-xl font-bold leading-tight">{value}</span>
        <span className="mt-0.5 block text-xs text-muted">{note}</span>
      </span>
    </Link>
  )
}

function Status({ row, busy, online, onDownload }: { row: LibraryRow; busy: boolean; online: boolean; onDownload: () => void }) {
  if (busy) return <span className="inline-flex items-center gap-1.5 text-muted" role="status"><Loader2 size={14} className="animate-spin" aria-hidden /> Downloading…</span>
  if (row.downloaded && !row.updateAvailable) return <span className="inline-flex items-center gap-1.5 text-muted"><Check size={14} aria-hidden /> On this device</span>
  if (!online) return <span className="text-muted">Not downloaded</span>
  return (
    <button className="btn" onClick={onDownload} aria-label={`${row.updateAvailable ? 'Update download of' : 'Download'} ${row.doc.title}`}>
      <Download size={16} aria-hidden /> {row.updateAvailable ? 'Update' : 'Download'}
    </button>
  )
}

export default function Library() {
  const { rows, online, failed, busy, download, reload } = useLibrary()
  const prefs = usePrefs()
  const root = useRef<HTMLDivElement>(null)
  const loaded = !!rows
  // Entrance: the banner rises, its progress bar fills and counts up, then the tiles and cards follow.
  useGSAP(() => {
    if (!loaded || !motionOK()) return
    // CSS hover transitions are paused during the entrance so the two never fight over the same property.
    const el = root.current!
    el.classList.add('entering')
    const tl = gsap.timeline({ defaults: { ease: 'power3.out', clearProps: 'transform,opacity,visibility' }, onComplete: () => el.classList.remove('entering') })
    tl.from('[data-hero]', { y: 28, autoAlpha: 0, duration: 0.6 })
      .from('[data-hero-text] > *', { y: 14, autoAlpha: 0, duration: 0.5, stagger: 0.08 }, '-=0.35')
      .from('[data-side]', { y: 24, autoAlpha: 0, duration: 0.5, stagger: 0.07 }, '-=0.4')
      .from('[data-card]', { y: 32, autoAlpha: 0, duration: 0.55, stagger: 0.09 }, '-=0.35')
      .from('[data-bar-fill]', { scaleX: 0, duration: 1, ease: 'power2.out', stagger: 0.1 }, 0.35)
    gsap.utils.toArray<HTMLElement>('[data-count]').forEach((num) => {
      const counter = { v: 0 }
      tl.to(counter, { v: Number(num.dataset.count), duration: 1, ease: 'power2.out', clearProps: '', onUpdate: () => { num.textContent = `${Math.round(counter.v)}% read` } }, 0.35)
    })
    return () => el.classList.remove('entering')
  }, { scope: root, dependencies: [loaded] })
  const saved = rows?.filter((r) => r.downloaded) ?? []
  const resume = rows?.filter((r) => r.position).sort((a, b) => b.position!.at.localeCompare(a.position!.at))[0]
  const toReview = rows?.reduce((n, r) => n + r.doc.review_count, 0) ?? 0
  const lead = !rows
    ? 'Loading your chapters…'
    : !online
      ? `Offline. Showing the ${rows.length} ${rows.length === 1 ? 'chapter' : 'chapters'} downloaded to this device.`
      : 'Read or listen to your textbook chapters, and check anything the scanner was unsure about.'

  return (
    <Shell title="Library" lead={lead}>
      <div ref={root}>
      {failed && (
        <div className="card mb-4 flex flex-wrap items-center justify-between gap-3 px-5 py-4" role="alert">
          <p className="m-0">Couldn't load the chapter list from the server. Downloaded chapters are shown below.</p>
          <button className="btn" onClick={() => void reload()}>Retry</button>
        </div>
      )}

      {resume && (
        <section data-hero aria-labelledby="resume-title" className="mb-4 flex items-center gap-10 overflow-hidden rounded-card bg-primary px-6 py-6 text-on-primary sm:px-9 sm:py-8">
          <div data-hero-text className="min-w-0 flex-1">
            <h2 id="resume-title" className="m-0 text-sm font-medium opacity-85">Continue reading</h2>
            <p className="m-0 mt-1 text-3xl font-bold leading-tight tracking-tight sm:text-4xl" lang={resume.doc.languages[0]}>{resume.doc.title}</p>
            <p className="m-0 mt-2 text-base" lang={resume.doc.languages[0]}>{resume.position!.label}</p>
            <div className="mt-4 flex max-w-md items-center gap-3">
              <div className="flex-1"><Bar value={resume.position!.progress} onPrimary /></div>
              <span data-count={Math.round(resume.position!.progress * 100)} className="flex-none text-sm">{Math.round(resume.position!.progress * 100)}% read</span>
            </div>
            <Link viewTransition to={`/read/${resume.doc.id}`} className="btn mt-6 min-h-11 border-transparent bg-on-primary px-5 text-base text-primary hover:bg-on-primary hover:opacity-90">
              Resume reading <ArrowRight size={18} aria-hidden />
            </Link>
          </div>
          <ReadingPage />
        </section>
      )}

      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <Tile to="/review" icon={<ClipboardCheck size={20} />} label="Review desk"
          value={!rows ? '–' : toReview ? `${toReview} to check` : 'All checked'}
          note={toReview ? 'Passages the scanner was unsure about' : 'Every passage has been reviewed'} />
        <Tile to="/downloads" icon={<HardDriveDownload size={20} />} label="On this device"
          value={rows ? `${saved.length} of ${rows.length} chapters` : '–'}
          note={saved.length ? `${formatBytes(saved.reduce((n, r) => n + r.downloaded!.bytes, 0))}, opens without internet` : 'Download a chapter to read offline'} />
        <Tile to="/settings" icon={<Type size={20} />} label="Reading setup"
          value={`${prefs.size} px · ${prefs.theme === 'contrast' ? 'High contrast' : prefs.theme === 'dark' ? 'Dark' : 'Light'}`}
          note={`Speaking speed ${prefs.rate.toFixed(1)}×, highlight ${prefs.highlight ? 'on' : 'off'}`} />
      </div>

      <section aria-labelledby="chapters-title">
        <h2 id="chapters-title" className="m-0 mb-3 text-xl font-bold tracking-tight">Your chapters</h2>
        {!rows && (
          <div className="grid gap-4 md:grid-cols-2" aria-hidden>
            {[0, 1].map((i) => (
              <div key={i} className="card flex gap-4 p-4">
                <div className="skeleton h-36 w-28 flex-none rounded-[10px]">.</div>
                <div className="flex-1"><div className="skeleton h-6 w-4/5">.</div><div className="skeleton mt-2 h-4 w-3/5">.</div></div>
              </div>
            ))}
          </div>
        )}
        {rows?.length === 0 && !online && (
          <div className="card px-5 py-10">
            <p className="m-0 text-base font-medium">No chapters are downloaded to this device.</p>
            <p className="m-0 mt-1 text-muted">Connect to the internet, then download a chapter to read it offline.</p>
          </div>
        )}
        <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2 xl:grid-cols-3">
          {rows?.map((row, i) => (
            <li key={row.doc.id} data-card className="card book flex flex-col p-4">
              <div className="mb-4 flex gap-4">
              <Cover doc={row.doc} index={i} />
              <div className="flex min-w-0 flex-1 flex-col">
                <h3 className="m-0 text-lg font-bold leading-snug" lang={row.doc.languages[0]}>
                  <Link viewTransition to={`/read/${row.doc.id}`} className="hover:underline">{row.doc.title}</Link>
                </h3>
                <p className="m-0 mt-0.5 text-muted">
                  {row.doc.subject && <><span lang={row.doc.languages[0]}>{row.doc.subject}</span> · </>}{row.doc.languages.map((l) => (l === 'hi' ? 'Hindi' : 'English')).join(' and ')}
                </p>
                <p className="m-0 mt-2 flex flex-wrap items-center gap-2">
                  {row.doc.review_count > 0 ? <span className="pill pill-warn">{row.doc.review_count} to review</span> : row.doc.needs_review ? <span className="pill pill-warn">Needs review</span> : <span className="pill pill-ok">Reviewed</span>}
                  <span className="pill">Revision {row.doc.current_revision}</span>
                </p>
                {row.position ? (
                  <div className="mt-3">
                    <Bar value={row.position.progress} />
                    <p className="m-0 mt-1 text-xs text-muted">{Math.round(row.position.progress * 100)}% read · <span lang={row.doc.languages[0]}>{row.position.label}</span></p>
                  </div>
                ) : (
                  <p className="m-0 mt-3 text-xs text-muted">Not started</p>
                )}
              </div>
              </div>
              <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-rule pt-3">
                  <Link viewTransition to={`/read/${row.doc.id}`} className="btn btn-primary" aria-label={`${row.position ? 'Continue' : 'Open'} ${row.doc.title}`}>
                    {row.position ? 'Continue' : 'Open'}
                  </Link>
                  <Link viewTransition to={`/chapter/${row.doc.id}`} className="btn" aria-label={`Details of ${row.doc.title}`}>Details</Link>
                  <span className="ml-auto"><Status row={row} busy={busy === row.doc.id} online={online} onDownload={() => void download(row.doc.id)} /></span>
              </div>
            </li>
          ))}
          {rows && online && (
            <li data-card className="flex">
              <Link to="/add" viewTransition className="tile flex min-h-44 flex-1 flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed border-control px-5 py-6 text-center">
                <span className="grid size-11 place-items-center rounded-full bg-primary text-on-primary" aria-hidden><Plus size={22} /></span>
                <span className="text-base font-bold">Add a chapter</span>
                <span className="text-muted">Upload a PDF or a photo of the pages</span>
              </Link>
            </li>
          )}
        </ul>
      </section>
      </div>
    </Shell>
  )
}
