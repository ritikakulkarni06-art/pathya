import type { Block } from '../types'

const STOP = new Set('a an the is are was were of in on at to for and or it its this that what which who how why does do did be by with from as can could will would should when where find state using i me my explain define'.split(' ').concat(['क्या', 'है', 'हैं', 'का', 'की', 'के', 'को', 'में', 'से', 'पर', 'और', 'किसे', 'कहते', 'यह', 'वह']))

export function tokens(text: string): string[] {
  return text
    .toLowerCase()
    .normalize('NFC')
    .split(/[^\p{L}\p{M}\p{N}]+/u)
    .filter((w) => w && !STOP.has(w))
}

export function blockText(b: Block): string {
  if (b.table) return [b.table.caption, ...b.table.columns, ...b.table.rows.flat()].join(' ')
  if (b.figure) return `${b.figure.caption} ${b.figure.description}`
  return b.text_current
}

export interface Hit {
  block: Block
  snippet: string
}

/** Chapter search that runs entirely on the device, so it works offline. */
export function searchBlocks(blocks: Block[], query: string): Hit[] {
  const q = query.trim().toLowerCase().normalize('NFC')
  if (q.length < 2) return []
  const words = tokens(q)
  return blocks
    .map((block) => {
      const text = blockText(block)
      const low = text.toLowerCase().normalize('NFC')
      const at = low.indexOf(q)
      const set = tokens(low)
      const wordHits = words.filter((w) => set.some((t) => t.startsWith(w))).length
      const score = (at >= 0 ? 10 : 0) + wordHits
      if (at < 0 && (!words.length || wordHits < words.length)) return null
      const from = Math.max(0, (at >= 0 ? at : low.indexOf(words[0])) - 40)
      const snippet = (from > 0 ? '…' : '') + text.slice(from, from + 140).trim() + (from + 140 < text.length ? '…' : '')
      return { block, snippet, score }
    })
    .filter((h): h is Hit & { score: number } => h !== null)
    .sort((a, b) => b.score - a.score || a.block.order_key - b.block.order_key)
}
