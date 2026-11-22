import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import type { Block, CorrectionRequest, Lang } from '../types'

/** What a correction may change besides the words. Role 1 applies these as content operations. */
export type Fixes = Pick<CorrectionRequest, 'lang' | 'block_type' | 'move'>
type Kind = NonNullable<CorrectionRequest['block_type']>

/** Labeled form for fixing one passage: its words and, if needed, its language, kind and reading order. */
export function CorrectionForm({ block, busy, canMove, onSubmit, onCancel }: {
  block: Block
  busy: boolean
  /** Whether a neighbouring passage exists on the same page to swap places with. */
  canMove?: { earlier: boolean; later: boolean }
  onSubmit: (text: string, reason: string, fixes: Fixes) => void
  onCancel: () => void
}) {
  const [text, setText] = useState(block.text_current)
  const [reason, setReason] = useState('')
  const [lang, setLang] = useState<Lang>(block.lang)
  const kind0: Kind = block.type === 'heading' || block.type === 'list_item' ? block.type : 'paragraph'
  const [kind, setKind] = useState<Kind>(kind0)
  const [move, setMove] = useState<Fixes['move']>()
  const area = useRef<HTMLTextAreaElement>(null)
  useEffect(() => area.current?.focus(), [])
  const fixes: Fixes = { lang: lang !== block.lang ? lang : undefined, block_type: kind !== kind0 ? kind : undefined, move }
  const unchanged = text.trim() === block.text_current && !fixes.lang && !fixes.block_type && !move
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim()) onSubmit(text.trim(), reason.trim(), fixes)
  }
  const id = block.id
  return (
    <form onSubmit={submit} className="mt-3 grid gap-3" aria-label="Correct this passage">
      <div>
        <label htmlFor={`fix-${id}`} className="mb-1 block font-medium">Corrected text</label>
        <textarea ref={area} id={`fix-${id}`} className="field min-h-32 text-base leading-relaxed" lang={lang} value={text} onChange={(e) => setText(e.target.value)} required aria-describedby={`fix-help-${id}`} />
        <p id={`fix-help-${id}`} className="m-0 mt-1 text-xs text-muted">Type the words exactly as the printed page has them. This fixes the transcription; it should not rephrase the textbook.</p>
      </div>
      <details className="rounded-control border border-border px-3 py-2">
        <summary className="cursor-pointer font-medium">Language, kind and reading order</summary>
        <div className="mt-3 grid gap-3 pb-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor={`lang-${id}`} className="mb-1 block font-medium">Language</label>
              <select id={`lang-${id}`} className="field" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                <option value="en">English</option>
                <option value="hi">Hindi</option>
              </select>
            </div>
            <div>
              <label htmlFor={`kind-${id}`} className="mb-1 block font-medium">This passage is a</label>
              <select id={`kind-${id}`} className="field" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
                <option value="paragraph">Paragraph</option>
                <option value="heading">Heading</option>
                <option value="list_item">List item</option>
              </select>
            </div>
          </div>
          {canMove && (
            <fieldset className="m-0 border-0 p-0">
              <legend className="mb-1 p-0 font-medium">Reading order on this page</legend>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn" aria-pressed={move === 'earlier'} disabled={!canMove.earlier} onClick={() => setMove(move === 'earlier' ? undefined : 'earlier')}><ArrowUp size={16} aria-hidden /> Read it one passage earlier</button>
                <button type="button" className="btn" aria-pressed={move === 'later'} disabled={!canMove.later} onClick={() => setMove(move === 'later' ? undefined : 'later')}><ArrowDown size={16} aria-hidden /> Read it one passage later</button>
              </div>
            </fieldset>
          )}
        </div>
      </details>
      <div>
        <label htmlFor={`why-${id}`} className="mb-1 block font-medium">What was wrong? <span className="font-normal text-muted">(optional)</span></label>
        <input id={`why-${id}`} className="field" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="For example: minus sign missing" />
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Publishing…' : unchanged ? 'Confirm text is correct' : 'Publish correction'}</button>
        <button className="btn" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

/** Can this passage swap places with the one before or after it on the same page? */
export function movable(blocks: Block[], block: Block) {
  const i = blocks.findIndex((b) => b.id === block.id)
  return { earlier: blocks[i - 1]?.page_id === block.page_id, later: blocks[i + 1]?.page_id === block.page_id }
}
