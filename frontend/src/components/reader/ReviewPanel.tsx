import { CorrectionForm, movable, type Fixes } from '../CorrectionForm'
import { FLAG_REASONS, type Block, type ChapterPackage, type PendingCorrection } from '../../types'

export function ReviewPanel({ pkg, pending, correcting, busy, setCorrecting, onGoTo, onListen, onSubmit, onResolve }: {
  pkg: ChapterPackage
  pending: PendingCorrection[]
  correcting: string | null
  busy: boolean
  setCorrecting: (id: string | null) => void
  onGoTo: (blockId: string) => void
  onListen: (blockId: string) => void
  onSubmit: (block: Block, text: string, reason: string, fixes: Fixes) => void
  onResolve: (p: PendingCorrection, action: 'send' | 'discard') => void
}) {
  const flagged = pkg.blocks.filter((b) => b.status === 'needs_review')
  const extra = correcting && !flagged.some((b) => b.id === correcting) ? pkg.blocks.find((b) => b.id === correcting) : undefined
  const list = extra ? [extra, ...flagged] : flagged
  const pageOf = (b: Block) => pkg.pages.find((p) => p.id === b.page_id)?.printed_label

  return (
    <div className="grid gap-3">
      <p className="m-0 text-muted">
        {flagged.length
          ? `${flagged.length} ${flagged.length === 1 ? 'passage needs' : 'passages need'} a check against the printed page. Until then they are not used as evidence for answers.`
          : 'No passages are waiting for review in this chapter.'}
      </p>

      {pending.length > 0 && (
        <section aria-label="Corrections waiting to send" className="rounded-card border border-warn-border bg-warn-bg p-3 text-warn-ink">
          <h3 className="m-0 font-medium">{pending.length} {pending.length === 1 ? 'correction' : 'corrections'} waiting to send</h3>
          <ul className="m-0 mt-2 grid list-none gap-3 p-0">
            {pending.map((p) => {
              const block = pkg.blocks.find((b) => b.id === p.block_id)
              return (
                <li key={p.id}>
                  <p className="m-0" lang={block?.lang}>“{p.text}”</p>
                  {p.state === 'queued' ? (
                    <p className="m-0 text-xs">Written offline. It will be sent when you reconnect.</p>
                  ) : (
                    <>
                      <p className="m-0 mt-1 text-xs">This passage changed on the server after you wrote your correction. The server now has:</p>
                      <p className="m-0 mt-1" lang={block?.lang}>“{block?.text_current}”</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button className="btn" onClick={() => onResolve(p, 'send')}>Replace it with mine</button>
                        <button className="btn" onClick={() => onResolve(p, 'discard')}>Keep the server's text</button>
                      </div>
                    </>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      <ul className="m-0 grid list-none gap-3 p-0">
        {list.map((b) => (
          <li key={b.id} className="card p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`pill ${b.status === 'needs_review' ? 'pill-warn' : ''}`}>{b.status === 'needs_review' ? 'Needs review' : 'Your correction'}</span>
              <span className="text-muted">Page {pageOf(b)}</span>
              <span className="ml-auto text-xs text-muted">{b.confidence.score === null ? 'Not scored' : `Scanner confidence ${Math.round(b.confidence.score * 100)}%`}</span>
            </div>
            {b.confidence.flags[0] && <p className="m-0 mt-2 font-medium">{FLAG_REASONS[b.confidence.flags[0]] ?? b.confidence.flags[0]}</p>}
            <blockquote className="m-0 mt-2 border-l-2 border-control pl-3 text-base" lang={b.lang}>{b.figure ? b.figure.description : b.text_current}</blockquote>
            {correcting === b.id ? (
              b.figure || b.table || b.type === 'equation' ? (
                <div className="mt-3">
                  <p className="m-0 text-muted">Figures, tables and equations are corrected by a teacher, because they need the original picture. Ask your teacher to check this one against the printed page.</p>
                  <button className="btn mt-2" onClick={() => setCorrecting(null)}>Close</button>
                </div>
              ) : (
                <CorrectionForm block={b} busy={busy} canMove={movable(pkg.blocks, b)} onSubmit={(t, r, f) => onSubmit(b, t, r, f)} onCancel={() => setCorrecting(null)} />
              )
            ) : (
              <div className="mt-3 flex flex-wrap gap-2">
                <button className="btn btn-primary" onClick={() => setCorrecting(b.id)}>{b.figure ? 'How to fix' : 'Correct'}</button>
                <button className="btn" onClick={() => onGoTo(b.id)}>Show in text</button>
                <button className="btn" onClick={() => onListen(b.id)}>Listen</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
