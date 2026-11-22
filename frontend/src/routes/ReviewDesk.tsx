import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { BookOpen, CircleCheckBig, PencilLine } from 'lucide-react'
import { Shell } from '../components/Shell'
import { PageThumb } from '../components/PageThumb'
import { CorrectionForm, movable, type Fixes } from '../components/CorrectionForm'
import { api } from '../api/client'
import { store, uid } from '../lib/db'
import { say, submitCorrection, useOnline } from '../state/app'
import { FLAG_REASONS, type Block, type ChapterPackage, type CorrectionRequest } from '../types'

const SHORT: Record<string, string> = {
  possible_missing_minus: 'Missing minus sign',
  low_ocr_confidence: 'Unclear characters',
  column_order_uncertain: 'Reading order',
  script_mixing: 'Mixed scripts',
  unreviewed_figure: 'Figure description',
  merged_headers: 'Table headers',
  figure_not_described: 'Figure description',
  low_confidence: 'Unclear characters',
  possible_ocr_error: 'Possible misread',
  mixed_script: 'Mixed scripts',
  language_uncertain: 'Language',
  reading_order_uncertain: 'Reading order',
  geometry_uncertain: 'Place on page',
  table_structure_uncertain: 'Table layout',
  math_needs_review: 'Equation',
  unsupported_content: 'Not supported',
  empty_text: 'No text',
  block_type_uncertain: 'Kind of passage',
  missing_geometry: 'Place on page',
  overlapping_regions: 'Overlap',
  orphan_caption: 'Loose caption',
  duplicate_content: 'Repeated text',
}
const day = (iso?: string) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '')

/** Every chapter the student can open: from the server when online, else the downloaded copies. */
function usePackages() {
  const online = useOnline()
  const [pkgs, setPkgs] = useState<ChapterPackage[] | null>(null)
  const load = useCallback(async () => {
    const local = await store.listPackages()
    try {
      const docs = await api.listDocuments()
      setPkgs(await Promise.all(docs.map((d) => api.getPackage(d.id))))
    } catch {
      setPkgs(local)
    }
  }, [])
  useEffect(() => void load(), [load, online])
  return { pkgs, online, reload: load }
}

export default function ReviewDesk() {
  const { pkgs, online, reload } = usePackages()
  const [filter, setFilter] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const all = pkgs?.flatMap((pkg) => pkg.blocks.map((block) => ({ pkg, block }))) ?? []
  const waiting = all.filter((x) => x.block.status === 'needs_review')
  const checked = all.filter((x) => x.block.status === 'reviewed').sort((a, b) => (b.block.provenance.changed_at ?? '').localeCompare(a.block.provenance.changed_at ?? ''))
  const reasons = [...new Set(waiting.map((x) => x.block.confidence.flags[0]).filter(Boolean))]
  // A filter whose last passage was just checked falls back to showing everything.
  const active = filter && reasons.includes(filter) ? filter : null
  const shown = active ? waiting.filter((x) => x.block.confidence.flags[0] === active) : waiting
  const total = waiting.length + checked.length
  const pageOf = (pkg: ChapterPackage, b: Block) => pkg.pages.find((p) => p.id === b.page_id)?.printed_label ?? ''

  const submit = async (pkg: ChapterPackage, block: Block, text: string, reason: string, fixes: Fixes) => {
    const req: CorrectionRequest = { block_id: block.id, base_revision: block.revision, text, reason, ...fixes }
    setBusy(true)
    try {
      const out = await submitCorrection(pkg.document.id, req)
      if (out.kind === 'published') say(`Revision ${out.revision} of “${pkg.document.title}” published. Narration, search and answers now use the corrected text.`, 'ok')
      else if (out.kind === 'queued') say('You are offline. Your correction is saved on this device and will be sent when you reconnect.')
      else {
        await store.putPending({ ...req, id: uid(), doc_id: pkg.document.id, queued_at: new Date().toISOString(), state: 'conflict' })
        say('This passage was changed on the server while you were editing. Open the chapter and compare the two versions under Review.', 'bad')
      }
      setOpen(null)
      await reload()
    } catch {
      say('The correction could not be published. Nothing was changed. Try again.', 'bad')
    }
    setBusy(false)
  }

  return (
    <Shell title="Review desk" lead="Passages the scanner was unsure about, from all your chapters. Check each one against the printed book. Until then it is not used as evidence for answers.">
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="grid gap-4">
          {reasons.length > 1 && (
            <div role="group" aria-label="Show passages by problem" className="flex flex-wrap gap-2">
              <button className={`btn ${active === null ? 'btn-primary' : ''}`} aria-pressed={active === null} onClick={() => setFilter(null)}>All {waiting.length}</button>
              {reasons.map((r) => (
                <button key={r} className={`btn ${active === r ? 'btn-primary' : ''}`} aria-pressed={active === r} onClick={() => setFilter(r)}>
                  {SHORT[r] ?? r} {waiting.filter((x) => x.block.confidence.flags[0] === r).length}
                </button>
              ))}
            </div>
          )}

          {!pkgs && <div className="card p-5" role="status"><div className="skeleton h-5 w-2/3">.</div><div className="skeleton mt-2 h-4 w-full">.</div><span className="sr-only">Loading passages…</span></div>}

          {pkgs && waiting.length === 0 && (
            <div className="card flex flex-col items-center px-6 py-12 text-center">
              <CircleCheckBig size={44} className="text-primary" aria-hidden />
              <p className="m-0 mt-3 text-xl font-bold">Nothing is waiting for a check</p>
              <p className="m-0 mt-1 max-w-[50ch] text-muted">{pkgs.length ? 'Every passage in your chapters is either trusted or already checked. New flags appear here when a chapter is added.' : online ? 'There are no chapters yet. Flags appear here after a chapter is added.' : 'You are offline and no chapter is downloaded, so there is nothing to show.'}</p>
            </div>
          )}

          <ul className="m-0 grid list-none gap-4 p-0" aria-label="Passages waiting for a check">
            {shown.map(({ pkg, block: b }) => {
              const flag = b.confidence.flags[0]
              const special = !!(b.figure || b.table || b.type === 'equation')
              const score = b.confidence.score
              return (
                <li key={pkg.document.id + b.id} className="card grid gap-4 p-4 sm:grid-cols-[104px_minmax(0,1fr)] sm:p-5">
                  <div className="hidden sm:block">
                    <PageThumb blocks={pkg.blocks.filter((x) => x.page_id === b.page_id)} activeId={b.id} label={pageOf(pkg, b)} />
                    <p className="m-0 mt-1.5 text-center text-xs text-muted">Printed page {pageOf(pkg, b)}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="m-0 flex flex-wrap items-center gap-2">
                      <span className="pill pill-warn">{SHORT[flag] ?? 'Needs review'}</span>
                      <span className="text-muted"><span lang={pkg.document.languages[0]}>{pkg.document.title}</span>, page {pageOf(pkg, b)}</span>
                    </p>
                    <h2 className="m-0 mt-2 text-base font-bold">{FLAG_REASONS[flag] ?? 'This passage needs a check against the printed page.'}</h2>
                    <blockquote className="m-0 mt-2 border-l-[3px] border-warn-border pl-3 text-base leading-relaxed" lang={b.lang}>{b.figure ? b.figure.description : b.text_current}</blockquote>
                    <div className="mt-3 flex items-center gap-3 text-xs text-muted">
                      {score === null ? <span>The scanner gave no confidence score for this passage.</span> : (
                        <>
                          <span className="flex-none">Scanner confidence {Math.round(score * 100)}%</span>
                          <span className="meter max-w-40 flex-1" aria-hidden><span className="bg-primary" style={{ width: `${score * 100}%` }} /></span>
                        </>
                      )}
                    </div>
                    {open === b.id ? (
                      special ? (
                        <div className="mt-3 rounded-control bg-raised px-3 py-2.5">
                          <p className="m-0">Figures, tables and equations are corrected by a teacher, because they need the original picture. Ask your teacher to check this one against the printed page.</p>
                          <button className="btn mt-2" onClick={() => setOpen(null)}>Close</button>
                        </div>
                      ) : (
                        <CorrectionForm block={b} busy={busy} canMove={movable(pkg.blocks, b)} onSubmit={(t, r, f) => void submit(pkg, b, t, r, f)} onCancel={() => setOpen(null)} />
                      )
                    ) : (
                      <div className="mt-4 flex flex-wrap gap-2">
                        <button className="btn btn-primary" onClick={() => setOpen(b.id)}><PencilLine size={16} aria-hidden /> {special ? 'How to fix' : 'Check and correct'}</button>
                        <Link className="btn" to={`/read/${pkg.document.id}?at=${b.id}`}><BookOpen size={16} aria-hidden /> Open in the chapter</Link>
                      </div>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        <div className="grid gap-4">
          <section aria-labelledby="rd-effort" className="card px-5 py-4">
            <h2 id="rd-effort" className="m-0 text-base font-medium">Review progress</h2>
            <p className="m-0 mt-2 text-3xl font-bold">{pkgs ? checked.length : '–'} <span className="text-base font-normal text-muted">of {pkgs ? total : '–'} checked</span></p>
            <div className="meter mt-3" role="img" aria-label={`${checked.length} of ${total} flagged passages checked`}>
              <span className="bg-primary" style={{ width: `${total ? (checked.length / total) * 100 : 0}%` }} />
            </div>
            <p className="m-0 mt-3 text-xs text-muted">Counts passages that were flagged or corrected, across {pkgs?.length ?? 0} {pkgs?.length === 1 ? 'chapter' : 'chapters'}.</p>
          </section>
          {checked.length > 0 && (
            <section aria-labelledby="rd-done" className="card">
              <h2 id="rd-done" className="m-0 border-b border-rule px-5 py-3 text-base font-medium">Recently checked</h2>
              <ul className="m-0 list-none p-0">
                {checked.slice(0, 6).map(({ pkg, block: b }) => (
                  <li key={pkg.document.id + b.id} className="border-b border-rule px-5 py-3 last:border-0">
                    <Link to={`/read/${pkg.document.id}?at=${b.id}`} className="line-clamp-2 font-medium hover:underline" lang={b.lang}>{b.text_current}</Link>
                    <p className="m-0 mt-0.5 text-xs text-muted">Page {pageOf(pkg, b)} · revision {b.revision}{b.provenance.changed_at ? ` · ${day(b.provenance.changed_at)}` : ''}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </Shell>
  )
}
