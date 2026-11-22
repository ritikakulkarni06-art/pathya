import { useState } from 'react'
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react'
import type { ChapterPackage } from '../../types'

/** The printed page beside the reflowed text, zoomable on its own.
 *  Shows the scan when the backend supplies one; otherwise a layout sketch from block geometry. */
export function SourcePanel({ pkg, activeBlockId, onGoTo }: { pkg: ChapterPackage; activeBlockId: string | null; onGoTo: (blockId: string) => void }) {
  const active = pkg.blocks.find((b) => b.id === activeBlockId)
  const [manual, setManual] = useState<{ page: number; for: string | null } | null>(null)
  const [zoom, setZoom] = useState(1)
  const follow = Math.max(0, pkg.pages.findIndex((p) => p.id === active?.page_id))
  // Follow the reading position until the student pages by hand; follow again when the passage changes.
  const index = manual && manual.for === activeBlockId ? manual.page : follow
  const page = pkg.pages[index]
  const blocks = pkg.blocks.filter((b) => b.page_id === page.id)
  const W = 100
  const H = 141

  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <button className="btn btn-icon" aria-label="Previous page" disabled={index === 0} onClick={() => setManual({ page: index - 1, for: activeBlockId })}><ChevronLeft size={18} aria-hidden /></button>
        <p className="m-0 flex-1 text-center font-medium" aria-live="polite">Printed page {page.printed_label} <span className="font-normal text-muted">({index + 1} of {pkg.pages.length})</span></p>
        <button className="btn btn-icon" aria-label="Next page" disabled={index === pkg.pages.length - 1} onClick={() => setManual({ page: index + 1, for: activeBlockId })}><ChevronRight size={18} aria-hidden /></button>
      </div>
      <div className="flex items-center gap-2">
        <button className="btn btn-icon" aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom((z) => Math.max(1, z - 0.5))}><ZoomOut size={18} aria-hidden /></button>
        <span className="w-14 text-center text-muted" aria-live="polite">{Math.round(zoom * 100)}%</span>
        <button className="btn btn-icon" aria-label="Zoom in" disabled={zoom >= 4} onClick={() => setZoom((z) => Math.min(4, z + 0.5))}><ZoomIn size={18} aria-hidden /></button>
      </div>
      <div className="max-h-[60dvh] overflow-auto rounded-control border border-border bg-raised p-2" tabIndex={0} role="group" aria-label="Source page, scrollable">
        <div style={{ width: `${zoom * 100}%` }} className="relative">
          {page.source_asset && <img src={page.source_asset} alt={`Scan of printed page ${page.printed_label}`} className="block w-full" />}
          <svg viewBox={`0 0 ${W} ${H}`} className={page.source_asset ? 'absolute inset-0 h-full w-full' : 'block w-full bg-surface'} role="img"
            aria-label={`Layout of printed page ${page.printed_label} with ${blocks.length} passages.${active && active.page_id === page.id ? ` The passage you are reading is number ${blocks.indexOf(active) + 1} from the top.` : ''}`}>
            {blocks.map((b) => {
              const [x0, y0, x1, y1] = b.bbox
              const on = b.id === activeBlockId
              const x = x0 * W, y = y0 * H, w = (x1 - x0) * W, h = (y1 - y0) * H
              return (
                <g key={b.id} onClick={() => onGoTo(b.id)} className="cursor-pointer">
                  <rect x={x} y={y} width={w} height={h} rx="0.8" fill={on ? 'var(--mark-bg)' : 'transparent'} stroke={on ? 'var(--mark)' : b.status === 'needs_review' ? 'var(--warn-ink)' : 'transparent'} strokeWidth={on ? 0.6 : 0.4} strokeDasharray={!on && b.status === 'needs_review' ? '1.2 1' : undefined} />
                  {!page.source_asset && (b.type === 'heading' ? (
                    <rect x={x + 1} y={y + h / 2 - 1.1} width={Math.min(w - 2, b.text_current.length * 1.5)} height="2.2" rx="0.5" fill="var(--text)" />
                  ) : b.type === 'table' || b.type === 'figure' ? (
                    <rect x={x + 1} y={y + 1} width={w - 2} height={h - 2} fill="none" stroke="var(--control)" strokeWidth="0.4" />
                  ) : (
                    [...Array(Math.max(1, Math.floor((h - 1.5) / 2.4))).keys()].map((i, _n, all) => (
                      <rect key={i} x={x + 1} y={y + 1.2 + i * 2.4} width={(w - 2) * (i === all.length - 1 && all.length > 1 ? 0.6 : 1)} height="0.9" rx="0.4" fill="var(--control)" />
                    ))
                  ))}
                </g>
              )
            })}
          </svg>
        </div>
      </div>
      <p className="m-0 text-xs text-muted">
        {page.source_asset
          ? 'The highlighted box is the passage you are reading. The scan is extra context; the reflowed text is the accessible version.'
          : 'No scan of this page is stored with the chapter, so this is a sketch of where each passage sits on the printed page. Dashed boxes need review.'}
      </p>
    </div>
  )
}
