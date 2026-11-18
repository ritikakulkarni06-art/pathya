import { memo, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Bookmark, BookmarkCheck, FileSearch, MoreHorizontal, PencilLine, Play } from 'lucide-react'
import { splitSentences } from '../../lib/sentences'
import { FLAG_REASONS, type Block } from '../../types'

export interface BlockActions {
  listen: (blockId: string, sentence?: number) => void
  toggleBookmark: (block: Block) => void
  showSource: (blockId: string) => void
  correct: (blockId: string) => void
}

const UI = 'font-sans text-sm tracking-normal [word-spacing:0]'

function PassageMenu({ block, bookmarked, actions }: { block: Block; bookmarked: boolean; actions: BlockActions }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (open) root.current?.querySelector<HTMLElement>('[role=menuitem]')?.focus()
  }, [open])
  const items = [
    { icon: Play, label: 'Listen from here', run: () => actions.listen(block.id) },
    { icon: bookmarked ? BookmarkCheck : Bookmark, label: bookmarked ? 'Remove bookmark' : 'Add bookmark', run: () => actions.toggleBookmark(block) },
    { icon: FileSearch, label: 'Show on source page', run: () => actions.showSource(block.id) },
    { icon: PencilLine, label: 'Suggest a correction', run: () => actions.correct(block.id) },
  ]
  const onKey = (e: KeyboardEvent) => {
    const list = [...(root.current?.querySelectorAll<HTMLElement>('[role=menuitem]') ?? [])]
    const i = list.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'Escape') {
      setOpen(false)
      button.current?.focus()
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      list[(i + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length]?.focus()
    }
  }
  return (
    <div ref={root} className={`absolute right-1 top-1 ${UI}`} lang="en" onKeyDown={onKey} onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && setOpen(false)}>
      <button ref={button} type="button" className="btn btn-ghost btn-icon text-muted" aria-haspopup="menu" aria-expanded={open} aria-label="Options for this passage" onClick={() => setOpen((o) => !o)}>
        <MoreHorizontal size={18} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="fade-in absolute right-0 top-full z-20 w-56 rounded-card border border-border bg-surface p-1 text-ink shadow-lg">
          {items.map((it) => (
            <button key={it.label} type="button" role="menuitem" tabIndex={-1} className="flex min-h-10 w-full items-center gap-2.5 rounded-control px-2.5 text-left hover:bg-raised focus-visible:bg-raised" onClick={() => { setOpen(false); it.run() }}>
              <it.icon size={16} aria-hidden /> {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  block: Block
  /** Sentence being narrated in this block: an index, -1 for the whole block, or null. */
  current: number | null
  active: boolean
  highlight: boolean
  flash: boolean
  bookmarked: boolean
  pending: boolean
  actions: BlockActions
}

export const BlockView = memo(function BlockView({ block, current, active, highlight, flash, bookmarked, pending, actions }: Props) {
  const review = block.status === 'needs_review'
  const whole = highlight && current === -1
  let body
  switch (block.type) {
    case 'heading': {
      const H = block.level === 1 ? 'h2' : 'h3'
      body = <H><span className="sentence" data-current={highlight && current !== null}>{block.text_current}</span></H>
      break
    }
    case 'table': {
      const t = block.table!
      body = (
        <div className="overflow-x-auto">
          <table>
            {t.caption && <caption className="mb-2 text-left font-bold"><span className="sentence" data-current={whole}>{t.caption}</span></caption>}
            <thead>
              <tr>{t.columns.map((c, i) => <th key={c} scope="col" className={t.numeric?.[i] ? 'num' : ''}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {t.rows.map((r) => (
                <tr key={r[0]}>
                  {r.map((cell, i) => i === 0
                    ? <th key={i} scope="row" className={t.numeric?.[0] ? 'num' : ''}>{cell}</th>
                    : <td key={i} className={t.numeric?.[i] ? 'num' : ''}>{cell === '—' ? <><span aria-hidden>—</span><span className="sr-only">no value</span></> : cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      break
    }
    case 'equation':
      body = (
        <div>
          {/* Reviewed MathML from the backend: screen readers with MathCAT can explore its structure. */}
          {block.mathml
            ? <div className="overflow-x-auto py-1" dangerouslySetInnerHTML={{ __html: block.mathml }} />
            : <p className="overflow-x-auto py-1"><span className="sentence" data-current={whole && !block.spoken}>{block.text_current}</span></p>}
          {block.spoken
            ? <p className={`${UI} text-muted`}><span lang="en">Read as: </span><span className="sentence" data-current={whole}>{block.spoken}</span></p>
            : <p className={`${UI} text-muted`} lang="en">Shown as the scanner read it. It is not read aloud until someone has checked it.</p>}
        </div>
      )
      break
    case 'figure': {
      const f = block.figure!
      body = (
        <figure className="m-0 rounded-control border border-border p-4">
          <figcaption className="font-bold">{f.caption || <span lang="en">Picture</span>}</figcaption>
          {f.description && <p className="mt-2"><span className="sentence" data-current={whole}>{f.description}</span></p>}
          <p className={`mt-2 ${UI} text-muted`} lang="en">
            {!f.description ? 'This picture has no description yet.' : f.description_origin === 'teacher' ? 'Description written by a teacher.' : 'Draft description made by software. No teacher has checked it yet.'} The picture itself is on the source page.
          </p>
        </figure>
      )
      break
    }
    default: {
      const sentences = splitSentences(block.text_current, block.lang).map((s, i) => (
        <span key={i} className="sentence" data-current={highlight && (current === i || current === -1)} onClick={() => actions.listen(block.id, i)}>{s}</span>
      ))
      // A list item keeps its bullet, so a screen reader announces it as part of a list.
      body = block.type === 'list_item' ? <ul className="m-0 list-disc pl-6"><li>{sentences}</li></ul> : <p>{sentences}</p>
    }
  }
  return (
    <div id={block.id} tabIndex={-1} className="passage pr-12" lang={block.lang} data-active={active} data-flash={flash} data-review={review}>
      {(review || pending || bookmarked) && (
        <p className={`mb-1 flex flex-wrap items-center gap-2 ${UI}`} lang="en">
          {bookmarked && <span className="pill"><BookmarkCheck size={12} aria-hidden /> Bookmarked</span>}
          {review && (
            <>
              <span className="pill pill-warn">Needs review</span>
              <span className="text-warn-ink">{FLAG_REASONS[block.confidence.flags[0]] ?? 'This passage has not been checked yet.'}</span>
              <button type="button" className="font-medium underline" onClick={() => actions.correct(block.id)}>Review this passage</button>
            </>
          )}
          {pending && <span className="pill">Your correction is waiting to send</span>}
        </p>
      )}
      {body}
      {block.revision > 1 && block.text_raw !== block.text_current && (
        <details className={`mt-1 ${UI} text-muted`}>
          <summary className="cursor-pointer" lang="en">Corrected in revision {block.revision}. Show what the scanner read.</summary>
          <p className="mt-1 rounded-control bg-raised p-2 text-ink">{block.text_raw}</p>
        </details>
      )}
      <PassageMenu block={block} bookmarked={bookmarked} actions={actions} />
    </div>
  )
})
