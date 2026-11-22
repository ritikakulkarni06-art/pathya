import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import * as Dialog from '@radix-ui/react-dialog'
import { ArrowLeft, BookOpen, Check, CircleAlert, Trash2 } from 'lucide-react'
import { Shell } from '../components/Shell'
import { Sharing } from '../components/Sharing'
import { api } from '../api/client'
import { store } from '../lib/db'
import { unitClipKey } from '../lib/hash'
import { unitsFor } from '../lib/sentences'
import { refreshReviewCount, say, useChapter, useOnline } from '../state/app'
import { FLAG_REASONS, type AnswerRecord, type BlockStatus, type ChapterPackage, type RevisionEntry } from '../types'

const when = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const STATUS: { id: BlockStatus; label: string; note: string; color: string }[] = [
  { id: 'trusted', label: 'Trusted', note: 'read cleanly', color: 'var(--primary)' },
  { id: 'reviewed', label: 'Checked by a person', note: 'corrected or confirmed', color: 'color-mix(in srgb, var(--primary) 45%, var(--surface))' },
  { id: 'needs_review', label: 'Waiting for a check', note: 'not used as evidence', color: 'var(--bad-ink)' },
  { id: 'unsupported', label: 'Not supported', note: 'shown with a notice', color: 'var(--control)' },
]
const KINDS: Record<string, string> = { heading: 'Headings', paragraph: 'Paragraphs', list_item: 'List items', table: 'Tables', equation: 'Equations', figure: 'Figures' }

function Card({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="card px-5 py-5">
      <h2 id={id} className="m-0 text-lg font-bold tracking-tight">{title}</h2>
      {children}
    </section>
  )
}

/** One line of "is this output on the current revision?" */
function Step({ ok, name, children }: { ok: boolean; name: string; children: ReactNode }) {
  return (
    <li className="flex gap-3 border-b border-rule py-3 last:border-0 last:pb-0">
      <span className={`mt-0.5 grid size-6 flex-none place-items-center rounded-full ${ok ? 'bg-ok-bg text-ok-ink' : 'bg-warn-bg text-warn-ink'}`} aria-hidden>{ok ? <Check size={14} /> : <CircleAlert size={14} />}</span>
      <div className="min-w-0">
        <p className="m-0 font-medium">{name} <span className="sr-only">{ok ? '(current)' : '(needs attention)'}</span></p>
        <p className="m-0 text-muted">{children}</p>
      </div>
    </li>
  )
}

/** How many narration sentences have a prepared clip made from the current text. */
async function audioCover(pkg: ChapterPackage) {
  const have = new Set(pkg.audio.map((a) => a.key))
  const texts = new Map(pkg.blocks.map((b) => [b.id, b.text_current]))
  const units = pkg.blocks.flatMap((b) => unitsFor(b, false))
  const keys = await Promise.all(units.map((u) => unitClipKey(u, texts.get(u.block_id))))
  return { total: units.length, ready: keys.filter((k) => have.has(k)).length }
}

export default function Chapter() {
  const { docId = '' } = useParams()
  const online = useOnline()
  const navigate = useNavigate()
  const { pkg, downloaded, error, loading } = useChapter(docId)
  const [history, setHistory] = useState<RevisionEntry[] | null>(null)
  const [answers, setAnswers] = useState<AnswerRecord[]>([])
  const [audio, setAudio] = useState<{ total: number; ready: number } | null>(null)
  const [removing, setRemoving] = useState(false)
  const revision = pkg?.revision

  useEffect(() => {
    setHistory(null)
    void api.getHistory(docId).then(setHistory).catch(() => setHistory(null))
    void store.listAnswers(docId).then(setAnswers)
  }, [docId, online, revision])
  useEffect(() => {
    if (pkg) void audioCover(pkg).then(setAudio)
  }, [pkg])

  if (!pkg) {
    return (
      <Shell title="Chapter details" lead={loading ? 'Loading…' : error === 'offline_not_downloaded' ? 'You are offline and this chapter is not downloaded, so its details cannot be shown.' : 'This chapter could not be found. It may have been removed.'}>
        <Link to="/" className="btn"><ArrowLeft size={16} aria-hidden /> Back to library</Link>
      </Shell>
    )
  }

  const doc = pkg.document
  const counts = STATUS.map((s) => ({ ...s, n: pkg.blocks.filter((b) => b.status === s.id).length })).filter((s) => s.n)
  const flags = new Map<string, number>()
  pkg.blocks.filter((b) => b.status === 'needs_review').forEach((b) => b.confidence.flags.forEach((f) => flags.set(f, (flags.get(f) ?? 0) + 1)))
  const scored = pkg.blocks.filter((b) => b.confidence.score !== null)
  const mean = scored.length ? scored.reduce((n, b) => n + b.confidence.score!, 0) / scored.length : null
  const engines = [...new Set(pkg.blocks.map((b) => b.confidence.engine))]
  const kinds = Object.entries(KINDS).map(([k, label]) => ({ label, n: pkg.blocks.filter((b) => b.type === k).length })).filter((k) => k.n)
  const stale = answers.filter((r) => !r.answer.abstain && r.answer.claims.some((c) => c.evidence.some((e) => pkg.blocks.find((b) => b.id === e.block_id)?.revision !== e.rev)))
  const pageOf = (blockId: string) => pkg.pages.find((p) => p.id === pkg.blocks.find((b) => b.id === blockId)?.page_id)?.printed_label

  const remove = async () => {
    setRemoving(true)
    try {
      await api.deleteDocument(docId)
      await store.deletePackage(docId)
      void refreshReviewCount()
      say(`“${doc.title}” and everything made from it was removed.`, 'ok')
      void navigate('/')
    } catch {
      say(online ? 'The chapter could not be removed. Nothing was changed. Try again.' : 'You are offline. Removing a chapter from the server needs internet.', 'bad')
      setRemoving(false)
    }
  }

  return (
    <Shell
      title={doc.title}
      lead={<>{doc.subject && <><span lang={doc.languages[0]}>{doc.subject}</span> · </>}{doc.printed_range ? `printed pages ${doc.printed_range}` : `${doc.page_count} pages`} · revision {pkg.revision} · updated {when(doc.updated_at)}</>}
      actions={<Link to={`/read/${docId}`} viewTransition className="btn btn-primary min-h-11 px-5 text-base"><BookOpen size={18} aria-hidden /> Read</Link>}
    >
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card id="ch-quality" title="How well the pages were read">
          <div className="meter mt-4 h-3 gap-0.5" role="img" aria-label={counts.map((c) => `${c.n} ${c.label.toLowerCase()}`).join(', ')}>
            {counts.map((c) => <span key={c.id} style={{ width: `${(c.n / pkg.blocks.length) * 100}%`, background: c.color }} />)}
          </div>
          <ul className="m-0 mt-3 grid list-none gap-1.5 p-0">
            {counts.map((c) => (
              <li key={c.id} className="flex items-center gap-2.5">
                <span className="size-3 flex-none rounded-[3px]" style={{ background: c.color }} aria-hidden />
                <span className="font-medium">{c.n} {c.label.toLowerCase()}</span>
                <span className="text-muted">{c.note}</span>
              </li>
            ))}
          </ul>
          {flags.size > 0 && (
            <>
              <h3 className="m-0 mt-5 font-medium">Why passages are waiting</h3>
              <ul className="m-0 mt-2 grid list-none gap-2 p-0">
                {[...flags].map(([f, n]) => (
                  <li key={f} className="flex gap-3"><span className="pill pill-warn mt-0.5 self-start">{n}</span><span>{FLAG_REASONS[f] ?? f}</span></li>
                ))}
              </ul>
              <Link to="/review" className="btn mt-4">Open the review desk</Link>
            </>
          )}
          <p className="m-0 mt-4 text-xs text-muted">
            {mean === null ? 'No passage has a scanner confidence score.' : `Average scanner confidence ${Math.round(mean * 100)}% over ${scored.length} scored passages. Text taken straight from a PDF has no score.`} Read by: {engines.join(', ')}.
          </p>
        </Card>

        <Card id="ch-sync" title={`Kept in step with revision ${pkg.revision}`}>
          <ul className="m-0 mt-2 list-none p-0">
            <Step ok name="Text and search">{pkg.blocks.length} passages on {pkg.pages.length} pages. Search is built on this device from the current text.</Step>
            <Step ok={!audio || !pkg.audio.length || audio.ready === audio.total} name="Narration audio">
              {!audio ? 'Checking…' : !pkg.audio.length ? 'No prepared audio. Narration uses a voice installed on this device, so it always reads the current text.'
                : audio.ready === audio.total ? `All ${audio.total} sentences have a prepared clip${pkg.audio_voice ? ` (${pkg.audio_voice})` : ''}.`
                : `${audio.ready} of ${audio.total} sentences have a prepared clip for the current text. The other ${audio.total - audio.ready} were corrected or have no clip yet, and are read by this device's voice. Old audio is never played for changed text.`}
            </Step>
            <Step ok={stale.length === 0} name="Saved answers">
              {answers.length === 0 ? 'No questions asked in this chapter yet.' : stale.length ? `${stale.length} of ${answers.length} saved answers quote a passage that was corrected later. They are marked out of date; ask again for a current answer.` : `All ${answers.length} saved answers quote the current text.`}
            </Step>
            <Step ok={!!downloaded && downloaded.revision >= pkg.revision} name="Copy on this device">
              {!downloaded ? 'Not downloaded. This chapter needs internet to open.' : downloaded.revision >= pkg.revision ? `Revision ${downloaded.revision}, saved ${when(downloaded.downloaded_at)}. Opens without internet.` : `Revision ${downloaded.revision} is saved, but revision ${pkg.revision} is current. Update it under Downloads.`}
            </Step>
          </ul>
        </Card>

        <Card id="ch-history" title="Correction history">
          {history === null ? (
            <p className="m-0 mt-2 text-muted">{online ? 'Loading…' : 'The correction history needs internet.'}</p>
          ) : history.length === 0 ? (
            <p className="m-0 mt-2 text-muted">No corrections yet. Revision 1 is the text exactly as it was first prepared.</p>
          ) : (
            <ol className="m-0 mt-3 grid list-none gap-0 p-0">
              {history.map((h) => (
                <li key={h.revision} className="relative border-l-2 border-border pb-5 pl-5 last:pb-0">
                  <span className="absolute -left-[7px] top-1 size-3 rounded-full bg-primary" aria-hidden />
                  <p className="m-0 font-medium">Revision {h.revision} <span className="font-normal text-muted">· {when(h.at)} · by {h.by === 'student' ? 'you' : h.by}</span></p>
                  {h.reason && <p className="m-0 text-muted">Reason given: {h.reason}</p>}
                  {h.before !== h.after ? (
                    <>
                      <p className="m-0 mt-1.5 text-muted line-through" lang={pkg.blocks.find((b) => b.id === h.block_id)?.lang}><span className="sr-only">Before: </span>{h.before}</p>
                      <p className="m-0 mt-1" lang={pkg.blocks.find((b) => b.id === h.block_id)?.lang}><span className="sr-only">After: </span>{h.after}</p>
                    </>
                  ) : !h.changes.length && <p className="m-0 mt-1.5">Text confirmed as correct, no words changed.</p>}
                  {h.changes.map((c) => <p key={c} className="m-0 mt-1"><span className="pill">{c}</span></p>)}
                  <Link to={`/read/${docId}?at=${h.block_id}`} className="mt-1.5 inline-block font-medium text-mark underline">Open the passage, page {pageOf(h.block_id)}</Link>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <div className="grid gap-4">
          <Card id="ch-contents" title="What is in this chapter">
            <dl className="m-0 mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5">
              {kinds.map((k) => <div key={k.label} className="contents"><dt className="text-muted">{k.label}</dt><dd className="m-0 text-right font-medium">{k.n}</dd></div>)}
              <div className="contents"><dt className="text-muted">Languages</dt><dd className="m-0 text-right font-medium">{doc.languages.map((l) => (l === 'hi' ? 'Hindi' : 'English')).join(', ')}</dd></div>
            </dl>
            <p className="m-0 mt-4 text-xs text-muted">Permission note: {doc.rights_note}</p>
          </Card>

          <Sharing docId={docId} title={doc.title} online={online} />

          <Card id="ch-remove" title="Remove this chapter">
            <p className="m-0 mt-2 text-muted">Deletes the uploaded file, the prepared text and audio, and the copy on this device. This cannot be undone.</p>
            <Dialog.Root>
              <Dialog.Trigger className="btn mt-3 border-bad-ink text-bad-ink" disabled={!online}><Trash2 size={16} aria-hidden /> Remove chapter…</Dialog.Trigger>
              {!online && <p className="m-0 mt-2 text-xs text-muted">Removing needs internet.</p>}
              <Dialog.Portal>
                <Dialog.Overlay className="fade-in fixed inset-0 z-40 bg-black/50" />
                <Dialog.Content className="sheet-in card fixed left-1/2 top-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 p-6">
                  <Dialog.Title className="m-0 text-lg font-bold">Remove “{doc.title}”?</Dialog.Title>
                  <Dialog.Description className="m-0 mt-2 text-muted">The chapter, its corrections and its audio will be deleted from the server and from this device. Your bookmarks in it will no longer open.</Dialog.Description>
                  <div className="mt-5 flex flex-wrap justify-end gap-2">
                    <Dialog.Close className="btn">Keep the chapter</Dialog.Close>
                    <button className="btn border-bad-ink bg-bad-ink text-surface hover:bg-bad-ink hover:opacity-90" disabled={removing} onClick={() => void remove()}>{removing ? 'Removing…' : 'Remove for good'}</button>
                  </div>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
          </Card>
        </div>
      </div>
    </Shell>
  )
}
