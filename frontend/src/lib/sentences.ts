import type { Block, Lang, Pronunciation, Page } from '../types'

// Abbreviations that end in a full stop but do not end a sentence.
const ABBREV = /\b(?:e\.g|i\.e|etc|vs|Fig|Eq|No|Dr|Mr|Mrs|Ms|approx|cf)\.$/i

/** Split text into sentence units for narration and highlighting. Handles the Hindi danda (।). */
export function splitSentences(text: string, _lang: Lang): string[] {
  const out: string[] = []
  let start = 0
  const re = /[.!?।॥]+["')\]]*\s+/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    const end = m.index + m[0].length
    const piece = text.slice(start, end)
    const head = piece.trimEnd()
    // Keep going when the stop belongs to an abbreviation, a decimal or a list number like "1."
    if (ABBREV.test(head) || /^\s*\d+\.$/.test(head) || /\d\.$/.test(head) && /^\d/.test(text.slice(end))) continue
    out.push(piece)
    start = end
  }
  if (start < text.length) out.push(text.slice(start))
  return out.filter((s) => s.trim())
}

export interface SpeechUnit {
  block_id: string
  /** Index of the sentence inside the block, or -1 when the unit covers the whole block. */
  sentence: number
  text: string
  lang: Lang
}

/** What the student is told about a page that Role 1 could not read completely, in the page's language.
 *  Null when the page is fine. */
export function pageNotice(page: Page, lang: Lang = 'en'): string | null {
  if (lang === 'hi') {
    const name = page.label_missing ? `फ़ाइल का पृष्ठ ${page.pdf_index_0 + 1}` : `पृष्ठ ${page.printed_label}`
    switch (page.status) {
      case 'failed': return `${name} पढ़ा नहीं जा सका। इसकी सामग्री इस अध्याय में नहीं है। इस पृष्ठ के लिए छपी हुई किताब देखें।`
      case 'needs_ocr': return `${name} एक स्कैन की हुई तस्वीर है जिसे अभी पढ़ा नहीं गया है। इसका कुछ या पूरा पाठ यहाँ नहीं है।`
      case 'partial': return `${name} आंशिक रूप से ही पढ़ा गया। पाठ यहाँ है, पर शीर्षक, तालिकाएँ और पढ़ने का क्रम गलत हो सकते हैं।`
      case 'blank': return `${name} किताब में खाली है।`
      default: return null
    }
  }
  const name = page.label_missing ? `Page ${page.pdf_index_0 + 1} of the file` : `Page ${page.printed_label}`
  switch (page.status) {
    case 'failed': return `${name} could not be read. Its content is missing from this chapter. Use the printed book for this page.`
    case 'needs_ocr': return `${name} is a scanned picture that has not been read yet. Some or all of its text is missing here.`
    case 'partial': return `${name} was only partly read. The text is here, but headings, tables and the reading order may be wrong.`
    case 'blank': return `${name} is blank in the book.`
    default: return null
  }
}

/** The language of each page: most of its passages, else the passage that follows it, else the one before. */
export function pageLanguages(pages: Page[], blocks: Block[]): Map<string, Lang> {
  const out = new Map<string, Lang>()
  const order = new Map(pages.map((p, i) => [p.id, i]))
  for (const page of pages) {
    const own = blocks.filter((b) => b.page_id === page.id)
    const hi = own.filter((b) => b.lang === 'hi').length
    if (own.length) { out.set(page.id, hi * 2 > own.length ? 'hi' : 'en'); continue }
    const i = order.get(page.id)!
    const next = blocks.find((b) => (order.get(b.page_id) ?? -1) > i)
    const prev = [...blocks].reverse().find((b) => (order.get(b.page_id) ?? Infinity) < i)
    out.set(page.id, next?.lang ?? prev?.lang ?? 'en')
  }
  return out
}

export interface PageNote { text: string; lang: Lang }

/** Page notices as narration: spoken before the first passage that follows, or after the last passage of the chapter. */
export function pageAnnouncements(pages: Page[], blocks: Block[]): { before: Map<string, PageNote[]>; after: Map<string, PageNote[]> } {
  const langs = pageLanguages(pages, blocks)
  const before = new Map<string, PageNote[]>()
  const after = new Map<string, PageNote[]>()
  let waiting: PageNote[] = []
  for (const page of pages) {
    const lang = langs.get(page.id) ?? 'en'
    const text = pageNotice(page, lang)
    if (text) waiting.push({ text, lang })
    const first = blocks.find((b) => b.page_id === page.id)
    if (first && waiting.length) { before.set(first.id, waiting); waiting = [] }
  }
  const last = blocks[blocks.length - 1]
  if (last && waiting.length) after.set(last.id, waiting)
  return { before, after }
}

/** The sentences of a passage as they are shown and read. With backend ranges the pieces run from one
 *  sentence start to the next, so joining them gives back the exact text. Otherwise the reader splits it. */
export function sentencesOf(block: Block): string[] {
  const starts = block.sentence_starts
  if (!starts?.length) return splitSentences(block.text_current, block.lang)
  const t = block.text_current
  return starts.map((s, i) => t.slice(i === 0 ? 0 : s, starts[i + 1] ?? t.length)).filter((s) => s.trim())
}

/** Backend ranges count Unicode code points; JavaScript strings count UTF-16 units. Returns UTF-16 starts,
 *  or null when the ranges do not fit the text (they are then ignored and the reader splits the text). */
export function toSentenceStarts(text: string, ranges: { start: number; end: number }[]): number[] | null {
  const cps = [...text]
  const offset: number[] = [0]
  for (const c of cps) offset.push(offset[offset.length - 1] + c.length)
  let last = -1
  for (const r of ranges) {
    if (!(r.start >= 0 && r.end > r.start && r.end <= cps.length && r.start >= last)) return null
    last = r.end
  }
  return ranges.length ? ranges.map((r) => offset[r.start]) : null
}

/** What the narrator says for each block, in reading order. Display text is never changed. */
export function unitsFor(block: Block, announceFlags: boolean): SpeechUnit[] {
  const u = (text: string, sentence = -1, lang: Lang = block.lang): SpeechUnit => ({ block_id: block.id, sentence, text, lang })
  const units: SpeechUnit[] = []
  if (announceFlags && block.status === 'needs_review')
    units.push(u(block.lang === 'hi' ? 'ध्यान दें: इस अंश की जाँच बाकी है।' : 'Note: this passage is flagged for review.'))
  switch (block.type) {
    case 'table': {
      const t = block.table!
      if (t.caption) units.push(u(t.caption))
      // "row label; column label; value", as the report specifies.
      for (const row of t.rows)
        for (let c = 1; c < row.length; c++) units.push(u(`${t.columns[0]} ${row[0]}; ${t.columns[c]}; ${row[c] === '—' ? (block.lang === 'hi' ? 'कोई मान नहीं' : 'no value') : row[c]}`))
      break
    }
    case 'equation':
      // Without an approved spoken form the symbols are not guessed at (Role 1 contract rule).
      units.push(block.spoken ? u(block.spoken) : u(block.lang === 'hi' ? 'यहाँ एक समीकरण है जिसकी जाँच बाकी है। इसे स्रोत पृष्ठ पर देखें।' : 'An equation that has not been checked yet. See it on the source page.'))
      break
    case 'figure': {
      const f = block.figure!
      if (f.caption) units.push(u(f.caption))
      if (!f.description) units.push(u('This picture has no description yet.', -1, 'en'))
      else {
        if (f.description_origin === 'generated_draft') units.push(u('Draft description, not yet reviewed.', -1, 'en'))
        units.push(u(f.description))
      }
      break
    }
    default:
      sentencesOf(block).forEach((s, i) => units.push(u(s, i)))
  }
  return units
}

/** Apply the student's pronunciation overrides to spoken text only. */
export function applyPronunciations(text: string, lang: Lang, docId: string, list: Pronunciation[]): string {
  let out = text
  for (const p of list) {
    if (p.lang !== lang || (p.scope !== 'all' && p.scope !== docId) || !p.term.trim()) continue
    const esc = p.term.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    out = out.replace(new RegExp(`(?<![\\p{L}\\p{M}\\p{N}])${esc}(?![\\p{L}\\p{M}\\p{N}])`, 'giu'), p.spoken)
  }
  return out
}
