import { useEffect, useState, type FormEvent } from 'react'
import { usingMock } from '../../api/client'
import type { AnswerRecord, ChapterPackage, Usage } from '../../types'

export function AskPanel({ pkg, answers, online, asking, focus, usage, onAsk, onOpenEvidence, onOpenReview, onSearchInstead }: {
  pkg: ChapterPackage
  answers: AnswerRecord[]
  online: boolean
  asking: boolean
  /** Answer to bring back into view when the student returns from an evidence passage. */
  focus: { id: string; t: number } | null
  /** Questions left today, when the backend sets a limit. */
  usage: Usage | null
  onAsk: (question: string) => void
  onOpenEvidence: (answerId: string, blockId: string) => void
  onOpenReview: (blockId: string) => void
  onSearchInstead: () => void
}) {
  const [q, setQ] = useState('')
  const blockOf = (id: string) => pkg.blocks.find((b) => b.id === id)
  const pageOf = (id: string) => pkg.pages.find((p) => p.id === blockOf(id)?.page_id)?.printed_label

  useEffect(() => {
    if (!focus) return
    const el = document.getElementById(`answer-${focus.id}`)
    el?.scrollIntoView({ block: 'nearest' })
    el?.focus()
  }, [focus])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!q.trim() || !online || asking || usage?.remaining === 0) return
    onAsk(q.trim())
    setQ('')
  }

  return (
    <div className="grid gap-4">
      <form onSubmit={submit} className="grid gap-2">
        <label htmlFor="ask-q" className="font-medium">Ask about this chapter</label>
        <textarea id="ask-q" className="field min-h-20" value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: What is displacement?" aria-describedby="ask-help" />
        <p id="ask-help" className="m-0 text-xs text-muted">
          {online
            ? usingMock
              ? 'Answers are passages quoted from this chapter, each linked to where it appears. Flagged passages are left out.'
              : 'Answers use only this chapter. Each statement links to the passage that supports it.'
            : 'The assistant needs internet. Reading, search, bookmarks and your earlier answers still work.'}
        </p>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-primary" type="submit" disabled={!online || asking || !q.trim() || usage?.remaining === 0}>{asking ? 'Looking in the chapter…' : 'Ask'}</button>
          {!online && <button className="btn" type="button" onClick={onSearchInstead}>Search the chapter instead</button>}
          {usage && online && (
            <span className={`pill self-center ${usage.remaining <= 3 ? 'pill-warn' : ''}`} role="status">
              {usage.remaining ? `${usage.remaining} of ${usage.limit} questions left today` : `Today's ${usage.limit} questions are used. Search still works.`}
            </span>
          )}
        </div>
      </form>

      {answers.length === 0 && !asking && <p className="m-0 rounded-control border border-dashed border-control px-3 py-2.5 text-muted">No questions asked in this chapter yet.</p>}

      <ol className="m-0 grid list-none gap-3 p-0" aria-label="Your questions, newest first">
        {asking && <li className="card p-4" role="status"><div className="skeleton h-5 w-3/4">.</div><div className="skeleton mt-2 h-4 w-full">.</div><span className="sr-only">Looking for supporting passages…</span></li>}
        {answers.map((rec) => {
          const a = rec.answer
          return (
            <li key={rec.id} id={`answer-${rec.id}`} tabIndex={-1} className="card p-4">
              <h3 className="m-0 text-base font-bold">{rec.question}</h3>
              {a.abstain ? (
                <>
                  <p className="m-0 mt-2">
                    {a.reason === 'no_support'
                      ? 'This chapter does not seem to cover that, so there is no answer to give. Try the words the textbook uses, or search the chapter.'
                      : 'The passage that would answer this is flagged for review, so it is not used as evidence yet.'}
                  </p>
                  {a.evidence_candidates.map((id) => blockOf(id) && (
                    <button key={id} className="btn mt-2" onClick={() => onOpenReview(id)}>Review the passage on page {pageOf(id)}</button>
                  ))}
                </>
              ) : (
                <>
                  <p className="m-0 mt-1 text-xs text-muted">{a.origin === 'ai_explanation' ? 'AI explanation' : 'Passages from the chapter'} · revision {a.document_revision}</p>
                  <ul className="m-0 mt-2 grid list-none gap-3 p-0">
                    {a.claims.map((c, i) => {
                      const ev = c.evidence[0]
                      const block = blockOf(ev.block_id)
                      const stale = !block || block.revision !== ev.rev
                      return (
                        <li key={i}>
                          <p className={`m-0 text-base ${stale ? 'text-muted line-through' : ''}`} lang={block?.lang}>{c.text}</p>
                          {stale ? (
                            <p className="m-0 mt-1"><span className="pill pill-warn">Out of date</span> <span className="text-muted">This passage was corrected after the answer was given. Ask again for a current answer.</span></p>
                          ) : null}
                          {block && (
                            <button className="mt-1 font-medium text-mark underline" onClick={() => onOpenEvidence(rec.id, ev.block_id)}>
                              {stale ? 'Open the corrected passage' : 'Open the passage'}, page {pageOf(ev.block_id)}
                            </button>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                </>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
