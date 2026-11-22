import type { Block } from '../types'

/** A small drawing of the printed page, with one passage marked, so a reviewer can find it in the book. */
export function PageThumb({ blocks, activeId, label }: { blocks: Block[]; activeId: string; label: string }) {
  const W = 100
  const H = 141
  const n = blocks.findIndex((b) => b.id === activeId) + 1
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full rounded-[6px] border border-border bg-surface" role="img" aria-label={`Printed page ${label}. This passage is number ${n} of ${blocks.length} from the top.`}>
      {blocks.map((b) => {
        const [x0, y0, x1, y1] = b.bbox
        const x = x0 * W, y = y0 * H, w = (x1 - x0) * W, h = (y1 - y0) * H
        const on = b.id === activeId
        return (
          <g key={b.id}>
            {on && <rect x={x - 1} y={y - 1} width={w + 2} height={h + 2} rx="1.5" fill="var(--warn-bg)" stroke="var(--warn-ink)" strokeWidth="0.9" />}
            {[...Array(Math.max(1, Math.floor(h / 3.2))).keys()].map((i, _n, all) => (
              <rect key={i} x={x + 1} y={y + 1 + i * 3.2} width={(w - 2) * (i === all.length - 1 && all.length > 1 ? 0.6 : 1)} height={b.type === 'heading' ? 2.2 : 1.2} rx="0.6" fill={on ? 'var(--warn-ink)' : b.type === 'heading' ? 'var(--muted)' : 'var(--control)'} />
            ))}
          </g>
        )
      })}
    </svg>
  )
}
