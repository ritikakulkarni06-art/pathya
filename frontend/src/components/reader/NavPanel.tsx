import { useMemo, useState, type FormEvent } from 'react'
import { Trash2 } from 'lucide-react'
import { searchBlocks } from '../../lib/search'
import type { Bookmark, ChapterPackage } from '../../types'

type View = 'contents' | 'bookmarks' | 'search'

export function NavPanel({ pkg, bookmarks, activeHeadingId, onGoTo, onRemoveBookmark, onMiss }: {
  pkg: ChapterPackage
  bookmarks: Bookmark[]
  activeHeadingId: string | null
  onGoTo: (blockId: string) => void
  onRemoveBookmark: (id: string) => void
  onMiss: (message: string) => void
}) {
  const [view, setView] = useState<View>('contents')
  const [page, setPage] = useState('')
  const [query, setQuery] = useState('')
  const pageOf = (pageId: string) => pkg.pages.find((p) => p.id === pageId)?.printed_label
  const headings = pkg.blocks.filter((b) => b.type === 'heading')
  const hits = useMemo(() => searchBlocks(pkg.blocks, query), [pkg.blocks, query])

  const goPage = (e: FormEvent) => {
    e.preventDefault()
    const p = pkg.pages.find((x) => x.printed_label === page.trim())
    const first = p && pkg.blocks.find((b) => b.page_id === p.id)
    if (first) onGoTo(first.id)
    else onMiss(`There is no page ${page.trim() || 'with that number'} in this chapter. It covers pages ${pkg.document.printed_range}.`)
  }

  return (
    <div className="grid gap-4">
      <form onSubmit={goPage} className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <label htmlFor="goto-page" className="mb-1 block font-medium">Go to printed page</label>
          <input id="goto-page" className="field" inputMode="numeric" placeholder={pkg.document.printed_range} value={page} onChange={(e) => setPage(e.target.value)} />
        </div>
        <button className="btn" type="submit">Go</button>
      </form>

      <div role="group" aria-label="Find in this chapter" className="grid grid-cols-3 gap-1 rounded-control bg-raised p-1">
        {(['contents', 'bookmarks', 'search'] as View[]).map((v) => (
          <button key={v} type="button" aria-pressed={view === v} className={`min-h-9 whitespace-nowrap rounded-[4px] px-1 text-[13px] font-medium capitalize ${view === v ? 'bg-surface text-ink' : 'text-muted'}`} onClick={() => setView(v)}>
            {v}{v === 'bookmarks' && bookmarks.length ? ` ${bookmarks.length}` : ''}
          </button>
        ))}
      </div>

      {view === 'contents' && (
        <nav aria-label="Chapter contents">
          <ol className="m-0 list-none p-0">
            {headings.map((h) => (
              <li key={h.id}>
                <button type="button" lang={h.lang} aria-current={activeHeadingId === h.id ? 'location' : undefined} onClick={() => onGoTo(h.id)}
                  className={`flex min-h-10 w-full items-baseline justify-between gap-3 rounded-control px-2.5 py-2 text-left hover:bg-raised ${h.level === 2 ? 'pl-6' : 'font-bold'} ${activeHeadingId === h.id ? 'bg-raised font-medium text-ink' : h.level === 2 ? 'text-muted' : ''}`}>
                  <span>{h.text_current}</span>
                  <span className="flex-none text-xs text-muted" lang="en"><span className="sr-only">page </span>{pageOf(h.page_id)}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
      )}

      {view === 'bookmarks' && (
        bookmarks.length === 0 ? (
          <p className="m-0 rounded-control border border-dashed border-control px-3 py-2.5 text-muted">No bookmarks in this chapter. Open “Options for this passage” beside any paragraph and choose “Add bookmark”.</p>
        ) : (
          <ul className="m-0 list-none p-0" aria-label="Bookmarks">
            {bookmarks.map((b) => {
              const block = pkg.blocks.find((x) => x.id === b.block_id)
              return (
                <li key={b.id} className="flex items-start gap-1 border-b border-rule py-1 last:border-0">
                  <button type="button" className="min-w-0 flex-1 rounded-control px-2.5 py-2 text-left hover:bg-raised" onClick={() => onGoTo(b.block_id)} disabled={!block}>
                    <span className="line-clamp-2" lang={block?.lang}>{b.label}</span>
                    <span className="text-xs text-muted">{block ? `Page ${pageOf(block.page_id)}` : 'This passage is no longer in the chapter'}</span>
                  </button>
                  <button type="button" className="btn btn-ghost btn-icon flex-none text-muted" aria-label={`Remove bookmark: ${b.label.slice(0, 40)}`} onClick={() => onRemoveBookmark(b.id)}><Trash2 size={16} aria-hidden /></button>
                </li>
              )
            })}
          </ul>
        )
      )}

      {view === 'search' && (
        <div className="grid gap-2">
          <div>
            <label htmlFor="chapter-search" className="mb-1 block font-medium">Search this chapter</label>
            <input id="chapter-search" type="search" className="field" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Word or phrase" autoComplete="off" />
          </div>
          <p className="m-0 text-xs text-muted" role="status">
            {query.trim().length < 2 ? 'Search runs on this device, so it also works offline.' : hits.length ? `${hits.length} ${hits.length === 1 ? 'passage' : 'passages'} found` : `No passage contains “${query.trim()}”.`}
          </p>
          <ul className="m-0 list-none p-0">
            {hits.map((h) => (
              <li key={h.block.id} className="border-b border-rule last:border-0">
                <button type="button" className="w-full rounded-control px-2.5 py-2 text-left hover:bg-raised" onClick={() => onGoTo(h.block.id)}>
                  <span className="line-clamp-3" lang={h.block.lang}>{h.snippet}</span>
                  <span className="text-xs text-muted">Page {pageOf(h.block.page_id)}{h.block.status === 'needs_review' ? ' · needs review' : ''}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
