import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowLeft, Check, Info, CornerDownLeft, Download, FileSearch, Flag, List, Loader2, MessageCircleQuestion, Type, X } from 'lucide-react'
import { api, LimitError, OfflineError } from '../api/client'
import { store, uid } from '../lib/db'
import { blockText } from '../lib/search'
import { pageNotice } from '../lib/sentences'
import { say, submitCorrection, syncPending, useChapter, useOnline, type SubmitOutcome } from '../state/app'
import { useNarration } from '../state/narration'
import { readingVars, usePrefs } from '../state/prefs'
import { OfflinePill } from '../components/Shell'
import { DisplayControls, Presets } from '../components/PrefsControls'
import { BlockView, type BlockActions } from '../components/reader/BlockView'
import { NavPanel } from '../components/reader/NavPanel'
import { ReviewPanel } from '../components/reader/ReviewPanel'
import { AskPanel } from '../components/reader/AskPanel'
import { SourcePanel } from '../components/reader/SourcePanel'
import { Player } from '../components/reader/Player'
import type { AnswerRecord, Block, Bookmark, CorrectionRequest, PendingCorrection, Usage } from '../types'
import type { Fixes } from '../components/CorrectionForm'

type Side = 'review' | 'ask' | 'source'
type Sheet = 'nav' | 'side' | 'display' | null

function useMedia(query: string) {
  const mq = useMemo(() => window.matchMedia(query), [query])
  return useSyncExternalStore((cb) => { mq.addEventListener('change', cb); return () => mq.removeEventListener('change', cb) }, () => mq.matches)
}

const day = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

export default function Reader() {
  const { docId = '' } = useParams()
  const chapter = useChapter(docId)
  const { pkg } = chapter
  const online = useOnline()
  const prefs = usePrefs()
  const wide = useMedia('(min-width: 1280px)')
  const nar = useNarration()

  const [side, setSide] = useState<Side>('review')
  const [sheet, setSheet] = useState<Sheet>(null)
  const [correcting, setCorrecting] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const [returnTo, setReturnTo] = useState<string | null>(null)
  const [focusAnswer, setFocusAnswer] = useState<{ id: string; t: number } | null>(null)
  const [visibleId, setVisibleId] = useState<string | null>(null)
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([])
  const [answers, setAnswers] = useState<AnswerRecord[]>([])
  const [pending, setPending] = useState<PendingCorrection[]>([])
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)
  const [usage, setUsage] = useState<Usage | null>(null)
  useEffect(() => void api.getUsage().then(setUsage).catch(() => {}), [])
  const [downloading, setDownloading] = useState(false)
  const pendingGoto = useRef<{ id: string; flash: boolean } | null>(null)
  const restored = useRef<string | null>(null)
  const progressBar = useRef<HTMLDivElement>(null)
  const ready = !!pkg
  useEffect(() => {
    if (!ready) return
    const update = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      if (progressBar.current) progressBar.current.style.scale = `${max > 0 ? Math.min(1, window.scrollY / max) : 0} 1`
    }
    update()
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [ready])
  const pkgRef = useRef(pkg)
  pkgRef.current = pkg
  /** Save where the student is, with a label the library can show: "Acceleration, page 38". */
  const savePos = useCallback((blockId: string) => {
    const p = pkgRef.current
    const i = p ? p.blocks.findIndex((b) => b.id === blockId) : -1
    if (!p || i < 0) return
    const heading = [...p.blocks.slice(0, i + 1)].reverse().find((b) => b.type === 'heading')
    const page = p.pages.find((pg) => pg.id === p.blocks[i].page_id)
    void store.setPosition(docId, blockId, `${heading?.text_current ?? 'Start'}, page ${page?.printed_label}`, i / Math.max(1, p.blocks.length - 1))
  }, [docId])

  const refresh = useCallback(async () => {
    const [b, a, p] = await Promise.all([store.listBookmarks(docId), store.listAnswers(docId), store.listPending(docId)])
    setBookmarks(b)
    setAnswers(a)
    setPending(p)
  }, [docId])
  useEffect(() => void refresh(), [refresh])

  // ---- narration follows the current revision ----
  const loadNarration = nar.load
  const stopNarration = nar.stop
  useEffect(() => {
    if (pkg) loadNarration(pkg)
  }, [pkg, prefs.announceFlags, loadNarration])
  useEffect(() => () => stopNarration(), [stopNarration])
  useEffect(() => {
    if (pkg) document.title = `${pkg.document.title} · Pathya`
    return () => { document.title = 'Pathya textbook reader' }
  }, [pkg])

  const setAnchor = nar.setAnchor
  useEffect(() => setAnchor(visibleId), [visibleId, setAnchor])
  const unit = nar.status !== 'idle' ? nar.units[nar.index] : undefined
  const activeId = unit?.block_id ?? visibleId
  const smooth = prefs.reduceMotion ? 'auto' : 'smooth'

  useEffect(() => {
    if (!unit || nar.status !== 'playing') return
    const el = document.getElementById(unit.block_id)
    if (!el) return
    const r = el.getBoundingClientRect()
    if (r.top < 80 || r.bottom > window.innerHeight - 170) el.scrollIntoView({ block: 'center', behavior: smooth })
  }, [unit?.block_id, nar.status]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---- reading position: restore once, then keep saving the top visible passage ----
  const hasPkg = !!pkg
  useEffect(() => {
    if (!hasPkg) return
    let live = true
    let timer = 0
    const els = [...document.querySelectorAll<HTMLElement>('.passage')]
    const order = new Map(els.map((el, i) => [el.id, i]))
    // The passage being read is the first one whose bottom edge is below the sticky header.
    const io = new IntersectionObserver(() => {
      const top = els.find((el) => el.getBoundingClientRect().bottom > 110)?.id
      if (!top || restored.current !== docId) return
      setVisibleId(top)
      clearTimeout(timer)
      timer = window.setTimeout(() => savePos(top), 600)
    }, { rootMargin: '-72px 0px -55% 0px', threshold: [0, 0.5, 1] })
    void (async () => {
      if (restored.current !== docId) {
        const pos = await store.getPosition(docId)
        if (!live) return
        // A link from the review desk or chapter page names the passage to open: /read/<chapter>?at=<passage>.
        const at = new URLSearchParams(window.location.search).get('at')
        const target = at ?? pos?.block_id
        const el = target && document.getElementById(target)
        if (el && (at || order.get(el.id)! > 0)) {
          el.scrollIntoView({ block: 'start' })
          setVisibleId(el.id)
          if (at) {
            el.focus({ preventScroll: true })
            setFlash(el.id)
            window.setTimeout(() => setFlash((f) => (f === el.id ? null : f)), 3000)
          } else say('Resumed where you stopped reading.')
        }
        restored.current = docId
      }
      els.forEach((el) => io.observe(el))
    })()
    return () => {
      live = false
      clearTimeout(timer)
      io.disconnect()
    }
  }, [hasPkg, docId])

  // ---- moving around ----
  const jump = useCallback((id: string, doFlash: boolean) => {
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ block: 'start', behavior: smooth })
    el.focus({ preventScroll: true })
    setVisibleId(id)
    savePos(id)
    if (doFlash) {
      setFlash(id)
      window.setTimeout(() => setFlash((f) => (f === id ? null : f)), 3000)
    }
  }, [smooth, docId])
  const goTo = useCallback((id: string, doFlash = false) => {
    if (sheet) {
      pendingGoto.current = { id, flash: doFlash }
      setSheet(null)
    } else jump(id, doFlash)
  }, [sheet, jump])
  const openSide = useCallback((s: Side) => {
    setSide(s)
    if (!wide) setSheet('side')
  }, [wide])

  // ---- bookmarks ----
  const toggleBookmark = useCallback(async (block: Block) => {
    const existing = bookmarks.find((b) => b.block_id === block.id)
    if (existing) {
      await store.deleteBookmark(existing.id)
      say('Bookmark removed.')
    } else {
      await store.putBookmark({ id: uid(), doc_id: docId, block_id: block.id, label: blockText(block).slice(0, 90), created_at: new Date().toISOString() })
      say('Bookmark added. Find it under Contents, then Bookmarks.', 'ok')
    }
    void refresh()
  }, [bookmarks, docId, refresh])

  const narPlay = nar.play
  const actions: BlockActions = useMemo(() => ({
    listen: (id, sentence) => narPlay(id, sentence),
    toggleBookmark: (b) => void toggleBookmark(b),
    showSource: (id) => { setVisibleId(id); openSide('source') },
    correct: (id) => { setCorrecting(id); openSide('review') },
  }), [narPlay, toggleBookmark, openSide])

  // ---- corrections ----
  const { reload, downloaded, source, setDownloaded } = chapter
  const settle = useCallback(async (outcome: SubmitOutcome, req: CorrectionRequest) => {
    if (outcome.kind === 'published') {
      setCorrecting(null)
      say(`Revision ${outcome.revision} published. Narration, search and answer evidence now use the corrected text.`, 'ok')
      reload()
    } else if (outcome.kind === 'queued') {
      setCorrecting(null)
      say('You are offline. Your correction is saved on this device and will be sent when you reconnect.')
    } else {
      await store.putPending({ ...req, id: uid(), doc_id: docId, queued_at: new Date().toISOString(), state: 'conflict' })
      say('This passage was changed on the server while you were editing. Compare the two versions under Review.', 'bad')
      reload()
    }
    void refresh()
  }, [docId, refresh, reload])

  const submit = async (block: Block, text: string, reason: string, fixes: Fixes = {}) => {
    const req: CorrectionRequest = { block_id: block.id, base_revision: block.revision, text, reason, ...fixes }
    setBusy(true)
    try {
      await settle(await submitCorrection(docId, req), req)
    } catch {
      say('The correction could not be published. Nothing was changed. Try again.', 'bad')
    }
    setBusy(false)
  }
  const resolve = async (p: PendingCorrection, action: 'send' | 'discard') => {
    await store.deletePending(p.id)
    const block = pkg?.blocks.find((b) => b.id === p.block_id)
    if (action === 'send' && block) await submit(block, p.text, p.reason, { lang: p.lang, block_type: p.block_type, move: p.move })
    else say('Your version was discarded. The server text is kept.')
    void refresh()
  }

  // Send what was written offline as soon as the connection returns.
  useEffect(() => {
    if (!online) return
    void syncPending(docId).then(({ sent, conflicts }) => {
      if (sent) say(`${sent} ${sent === 1 ? 'correction' : 'corrections'} written offline ${sent === 1 ? 'was' : 'were'} sent and published.`, 'ok')
      if (conflicts) say(`${conflicts} ${conflicts === 1 ? 'correction needs' : 'corrections need'} your decision. Open Review.`, 'bad')
      if (sent || conflicts) {
        reload()
        void refresh()
      }
    })
  }, [online, docId, reload, refresh])

  // Keep the downloaded copy on the current revision when that costs no audio download.
  useEffect(() => {
    if (source !== 'network' || !pkg || !downloaded || downloaded.revision >= pkg.revision || pkg.audio.length) return
    void store.savePackage(pkg).then(setDownloaded)
  }, [source, pkg, downloaded, setDownloaded])

  const download = async () => {
    setDownloading(true)
    try {
      const stored = await store.savePackage(await api.getPackage(docId))
      setDownloaded(stored)
      say(stored.missing_assets.length ? `Downloaded, but ${stored.missing_assets.length} files could not be saved. They are listed under Downloads.` : 'Chapter downloaded. It will open without internet, at the place you stopped.', stored.missing_assets.length ? 'bad' : 'ok')
    } catch {
      say('The download did not finish. Any earlier copy is unchanged.', 'bad')
    }
    setDownloading(false)
  }

  // ---- questions ----
  const ask = async (question: string) => {
    setAsking(true)
    try {
      const answer = await api.ask(docId, question)
      if (answer.usage) setUsage(answer.usage)
      await store.putAnswer({ id: uid(), doc_id: docId, question, asked_at: new Date().toISOString(), answer })
      say(answer.abstain ? 'No supported answer was found.' : `Found ${answer.claims.length} supporting ${answer.claims.length === 1 ? 'passage' : 'passages'}.`)
    } catch (e) {
      if (e instanceof LimitError) setUsage({ remaining: 0, limit: e.limit })
      say(e instanceof LimitError ? 'You have used all of today\'s questions. Reading, search and your earlier answers still work.' : e instanceof OfflineError ? 'You went offline before the answer arrived.' : 'The assistant did not respond. Try again in a moment.', 'bad')
    }
    setAsking(false)
    void refresh()
  }

  // ---- states before content ----
  if (!pkg) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <Link to="/" className="btn mb-6"><ArrowLeft size={16} aria-hidden /> Library</Link>
        {chapter.loading ? (
          <div role="status" aria-label="Opening chapter">
            <div className="skeleton h-8 w-2/3">.</div>
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton mt-4 h-5 w-full">.</div>)}
          </div>
        ) : chapter.error === 'offline_not_downloaded' ? (
          <main id="main" tabIndex={-1}>
            <h1 className="m-0 text-2xl font-bold">This chapter is not on this device</h1>
            <p className="mt-2 text-base">You are offline and this chapter was not downloaded, so it cannot be opened right now. Connect to the internet and download it to read it anywhere.</p>
            <Link to="/downloads" className="btn btn-primary mt-3">See downloaded chapters</Link>
          </main>
        ) : (
          <main id="main" tabIndex={-1}>
            <h1 className="m-0 text-2xl font-bold">Couldn't open this chapter</h1>
            <p className="mt-2 text-base">The server did not return the chapter. Your downloads and bookmarks are not affected.</p>
            <button className="btn btn-primary mt-3" onClick={reload}>Try again</button>
          </main>
        )}
      </div>
    )
  }

  const doc = pkg.document
  const activeBlock = pkg.blocks.find((b) => b.id === activeId)
  const activeHeading = activeBlock ? [...pkg.blocks.filter((b) => b.order_key <= activeBlock.order_key)].reverse().find((b) => b.type === 'heading')?.id ?? null : null
  const reviewCount = pkg.blocks.filter((b) => b.status === 'needs_review').length + pending.length
  const pendingIds = new Set(pending.map((p) => p.block_id))
  const bookmarkIds = new Set(bookmarks.map((b) => b.block_id))
  const upToDate = downloaded && downloaded.revision >= pkg.revision

  const navPanel = <NavPanel pkg={pkg} bookmarks={bookmarks} activeHeadingId={activeHeading} onGoTo={(id) => goTo(id)} onRemoveBookmark={(id) => void store.deleteBookmark(id).then(refresh)} onMiss={(m) => say(m, 'bad')} />
  const sidePanel = (
    <>
      <div role="group" aria-label="Study tools" className="mb-4 grid grid-cols-3 gap-1 rounded-control bg-raised p-1">
        {([['review', `Review${reviewCount ? ` ${reviewCount}` : ''}`], ['ask', 'Ask'], ['source', 'Source']] as [Side, string][]).map(([s, label]) => (
          <button key={s} type="button" aria-pressed={side === s} className={`min-h-9 rounded-[4px] px-2 font-medium ${side === s ? 'bg-surface text-ink' : 'text-muted'}`} onClick={() => setSide(s)}>{label}</button>
        ))}
      </div>
      {side === 'review' && <ReviewPanel pkg={pkg} pending={pending} correcting={correcting} busy={busy} setCorrecting={setCorrecting} onGoTo={(id) => goTo(id, true)} onListen={(id) => nar.play(id)} onSubmit={(b, t, r, f) => void submit(b, t, r, f)} onResolve={(p, a) => void resolve(p, a)} />}
      {side === 'ask' && <AskPanel pkg={pkg} answers={answers} online={online} asking={asking} focus={focusAnswer} usage={usage} onAsk={(q) => void ask(q)} onOpenEvidence={(answerId, blockId) => { setReturnTo(answerId); goTo(blockId, true) }} onOpenReview={(id) => { setCorrecting(id); setSide('review') }} onSearchInstead={() => setSheet(wide ? null : 'nav')} />}
      {side === 'source' && <SourcePanel pkg={pkg} activeBlockId={activeId} onGoTo={(id) => goTo(id, true)} />}
    </>
  )
  const sheetTitle = sheet === 'nav' ? 'Contents' : sheet === 'display' ? 'Display' : side === 'review' ? 'Review' : side === 'ask' ? 'Ask' : 'Source page'
  let sheetBody: ReactNode = null
  if (sheet === 'nav') sheetBody = navPanel
  else if (sheet === 'side') sheetBody = sidePanel
  else if (sheet === 'display') sheetBody = (
    <div className="grid gap-6">
      <Presets />
      <DisplayControls />
      <Link to="/settings" className="btn">Speech, pronunciation and all settings</Link>
      <section aria-labelledby="keys-title">
        <h3 id="keys-title" className="m-0 font-medium">Keyboard</h3>
        <dl className="m-0 mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-muted">
          <dt><kbd className="font-mono text-ink">Alt+Shift+P</kbd></dt><dd className="m-0">Play or pause narration</dd>
          <dt><kbd className="font-mono text-ink">Alt+Shift+→</kbd></dt><dd className="m-0">Next sentence</dd>
          <dt><kbd className="font-mono text-ink">Alt+Shift+←</kbd></dt><dd className="m-0">Previous sentence</dd>
          <dt><kbd className="font-mono text-ink">Esc</kbd></dt><dd className="m-0">Close a panel or menu</dd>
          <dt><kbd className="font-mono text-ink">Tab</kbd></dt><dd className="m-0">First stop on every screen is “Skip to content”</dd>
        </dl>
      </section>
    </div>
  )

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-border bg-ground">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-2 px-3 sm:gap-3 sm:px-6">
          <Link to="/" viewTransition className="btn btn-ghost px-2" aria-label="Back to library"><ArrowLeft size={18} aria-hidden /> <span className="hidden sm:inline">Library</span></Link>
          <div className="min-w-0 flex-1">
            <h1 className="m-0 truncate text-base font-bold" lang={doc.languages[0]}>{doc.title}</h1>
            <p className="m-0 truncate text-xs text-muted">Pages {doc.printed_range} · Revision {pkg.revision}{source === 'device' ? ` · copy saved ${day(downloaded!.downloaded_at)}` : ''}</p>
          </div>
          <OfflinePill />
          <Link to={`/chapter/${docId}`} viewTransition className="btn btn-ghost btn-icon" aria-label="Chapter details: quality, history and removal"><Info size={18} aria-hidden /></Link>
          <button className="btn" onClick={() => setSheet('display')}><Type size={16} aria-hidden /> <span className="hidden sm:inline">Display</span><span className="sr-only sm:hidden">Display</span></button>
          {upToDate ? (
            <span className="hidden items-center gap-1.5 text-muted sm:inline-flex"><Check size={16} aria-hidden /> Downloaded</span>
          ) : (
            <button className="btn" onClick={() => void download()} disabled={!online || downloading}>
              {downloading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Download size={16} aria-hidden />}
              <span className="hidden sm:inline">{downloading ? 'Downloading…' : downloaded ? 'Update download' : 'Download'}</span><span className="sr-only sm:hidden">{downloaded ? 'Update download' : 'Download chapter'}</span>
            </button>
          )}
        </div>
        <div ref={progressBar} aria-hidden className="-mb-[3px] h-[3px] origin-left bg-primary" style={{ scale: '0 1' }} />
      </header>

      {source === 'device' && (
        <p className="m-0 border-b border-warn-border bg-warn-bg px-4 py-2 text-center text-warn-ink" role="status">
          {online ? 'The server could not be reached, so this is your downloaded copy. ' : 'You are offline, reading your downloaded copy. '}
          Reading, search and bookmarks work. The assistant and new downloads wait for a connection.
          {online && <button className="ml-2 font-medium underline" onClick={reload}>Retry</button>}
        </p>
      )}

      <div className="mx-auto grid max-w-[1440px] xl:grid-cols-[288px_minmax(0,1fr)_392px]">
        {wide && <aside aria-label="Contents and search" className="sticky top-14 h-[calc(100dvh-7.5rem)] overflow-y-auto p-4 pl-6">{navPanel}</aside>}
        <main id="main" tabIndex={-1} className="min-w-0 px-0 pb-52 pt-0 outline-none sm:px-6 sm:pt-6 xl:px-3 xl:pb-32">
          <article aria-label={doc.title} className="reading mx-auto border-border bg-surface px-5 py-6 sm:rounded-card sm:border sm:px-12 sm:py-10" style={readingVars(prefs)} data-focus={prefs.focusMode} data-reading={nar.status === 'playing'}>
            {pkg.pages.map((page) => (
              <section key={page.id} aria-label={`Printed page ${page.printed_label}`}>
                <p className="page-mark first:mt-0" id={`page-${page.printed_label}`} lang="en">Page {page.printed_label}{page.label_missing && <span className="font-normal">no printed number, counted from the start of the file</span>}</p>
                {pageNotice(page) && (
                  <div role="note" lang="en" data-page-status={page.status} className={`mb-4 rounded-control border px-3 py-2.5 font-sans text-sm tracking-normal [word-spacing:0] ${page.status === 'blank' ? 'border-border text-muted' : 'border-warn-border bg-warn-bg text-warn-ink'}`}>
                    <p className="m-0 font-medium">{pageNotice(page)}</p>
                  </div>
                )}
                {!!page.warnings?.length && (
                  <details lang="en" className="mb-4 font-sans text-sm tracking-normal text-muted [word-spacing:0]">
                    <summary className="cursor-pointer">Notes from the scanner for this page ({page.warnings.length})</summary>
                    <ul className="m-0 mt-1 pl-5">{page.warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul>
                  </details>
                )}
                {pkg.blocks.filter((b) => b.page_id === page.id).map((b) => (
                  <BlockView key={b.id} block={b} actions={actions} highlight={prefs.highlight} active={b.id === activeId} flash={flash === b.id}
                    current={unit?.block_id === b.id ? unit.sentence : null} bookmarked={bookmarkIds.has(b.id)} pending={pendingIds.has(b.id)} />
                ))}
              </section>
            ))}
            <p className="page-mark" lang="en">End of chapter</p>
          </article>
        </main>
        {wide && <aside aria-label="Study tools" className="sticky top-14 h-[calc(100dvh-7.5rem)] overflow-y-auto p-4 pr-6">{sidePanel}</aside>}
      </div>

      {returnTo && (
        <button className="btn btn-primary sheet-in fixed bottom-36 right-4 z-30 shadow-lg xl:bottom-20 xl:right-6" onClick={() => { setFocusAnswer({ id: returnTo, t: Date.now() }); setReturnTo(null); openSide('ask') }}>
          <CornerDownLeft size={16} aria-hidden /> Back to your answer
        </button>
      )}

      <footer className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)]">
        <Player />
        {!wide && (
          <nav aria-label="Chapter tools" className="grid grid-cols-4 border-t border-rule">
            {([
              ['Contents', List, () => setSheet('nav')],
              [`Review${reviewCount ? ` ${reviewCount}` : ''}`, Flag, () => openSide('review')],
              ['Ask', MessageCircleQuestion, () => openSide('ask')],
              ['Source', FileSearch, () => openSide('source')],
            ] as [string, typeof List, () => void][]).map(([label, Icon, run]) => (
              <button key={label} type="button" className="flex min-h-12 flex-col items-center justify-center gap-0.5 text-xs font-medium" onClick={run}>
                <Icon size={18} aria-hidden /> {label}
              </button>
            ))}
          </nav>
        )}
      </footer>

      <Dialog.Root open={sheet !== null} onOpenChange={(o) => !o && setSheet(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fade-in fixed inset-0 z-40 bg-black/45" />
          <Dialog.Content
            aria-describedby={undefined}
            className="sheet-in fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-ground shadow-2xl"
            onOpenAutoFocus={(e) => { if (focusAnswer && sheet === 'side' && side === 'ask') e.preventDefault() }}
            onCloseAutoFocus={(e) => {
              const target = pendingGoto.current
              if (!target) return
              e.preventDefault()
              pendingGoto.current = null
              jump(target.id, target.flash)
            }}
          >
            <div className="flex h-14 flex-none items-center justify-between border-b border-border px-4">
              <Dialog.Title className="m-0 text-base font-bold">{sheetTitle}</Dialog.Title>
              <Dialog.Close className="btn btn-ghost btn-icon" aria-label={`Close ${sheetTitle.toLowerCase()}`}><X size={20} aria-hidden /></Dialog.Close>
            </div>
            <div className="flex-1 overflow-y-auto p-4">{sheetBody}</div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
