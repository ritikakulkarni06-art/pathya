// Turns a Role 1 document (content contract 1.0.0 / 1.1.0, docs/p1_contract.md in the team repo)
// into the package this reader displays and narrates. Every place where the reader has to guess,
// because the contract does not say, is marked "GAP" and listed in README.
import type { Block, BlockStatus, ChapterPackage, Lang, Page, TableData } from '../types'

interface P1Annotation { text: string; language: string; origin: 'source' | 'human' | 'model_generated'; review_status: string }
interface P1Block {
  id: string
  page_id: string
  parent_id: string | null
  block_type: 'heading' | 'paragraph' | 'list_item' | 'table' | 'table_cell' | 'equation' | 'figure' | 'caption'
  reading_order: number
  bbox: [number, number, number, number]
  raw_text: string | null
  current_text: string | null
  language: string
  revision: number
  review_status: 'unreviewed' | 'needs_review' | 'approved' | 'rejected'
  confidence: { score: number | null; origin: string; reason: string | null }
  quality_flags: string[]
  provenance: { method: string; engine: string | null; engine_version: string | null; parameters: Record<string, unknown> }
  table: { row_count: number | null; column_count: number | null; cell_ids: string[] } | null
  table_cell: { row_index: number; column_index: number; row_span: number; column_span: number; is_header: boolean } | null
  equation: { source_text: string | null; mathml: string | null; mathml_review_status: string; spoken_fallback: string | null; spoken_fallback_review_status: string } | null
  figure: { source_caption: string | null; caption_block_id: string | null; alt_text: P1Annotation | null; extended_description: P1Annotation | null } | null
}
export interface P1Document {
  schema_version: string
  id: string
  title: string | null
  languages: string[]
  pages: { id: string; page_index: number; page_label: string | null }[]
  blocks: P1Block[]
  edges: { edge_type: string; source_id: string; target_id: string }[]
  corrections: { block_id: string; author_ref: string | null; created_at: string }[]
  created_at: string
}

export const P1_VERSIONS = ['1.0.0', '1.1.0']

/** GAP: speech needs one voice per passage, but the contract allows "mul" and "und". Pick by script. */
function voiceLang(tag: string, text: string, fallback: Lang): Lang {
  if (tag === 'en' || tag === 'hi') return tag
  const hi = (text.match(/[ऀ-ॿ]/g) ?? []).length
  const en = (text.match(/[A-Za-z]/g) ?? []).length
  return hi + en === 0 ? fallback : hi >= en ? 'hi' : 'en'
}

export function fromP1(input: unknown, extra: { subject: string; rights_note: string }): ChapterPackage {
  const doc = input as P1Document
  if (!P1_VERSIONS.includes(doc.schema_version)) throw new Error(`Unsupported content contract version ${doc.schema_version}`)
  const byId = new Map(doc.blocks.map((b) => [b.id, b]))
  const main: Lang = doc.languages.includes('hi') && !doc.languages.includes('en') ? 'hi' : 'en'
  const pageIndex = new Map(doc.pages.map((p) => [p.id, p.page_index]))
  const pages: Page[] = [...doc.pages].sort((a, b) => a.page_index - b.page_index)
    // GAP: page_label may be null. The physical page number is shown instead.
    .map((p) => ({ id: p.id, pdf_index_0: p.page_index, printed_label: p.page_label ?? String(p.page_index + 1) }))

  // A caption that belongs to a figure or table is shown with it, not read a second time on its own.
  const captionFor = new Map<string, string>()
  const linked = new Set<string>()
  const link = (captionId: string, targetId: string) => {
    const c = byId.get(captionId)
    if (c?.block_type !== 'caption' || !byId.has(targetId)) return
    captionFor.set(targetId, c.current_text ?? '')
    linked.add(captionId)
  }
  for (const e of doc.edges) if (e.edge_type === 'caption_of') link(e.source_id, e.target_id)
  for (const b of doc.blocks) if (b.figure?.caption_block_id) link(b.figure.caption_block_id, b.id)

  const blocks: Block[] = []
  let headings = 0
  const top = doc.blocks
    .filter((b) => !b.parent_id && b.block_type !== 'table_cell' && !linked.has(b.id))
    .sort((a, b) => (pageIndex.get(a.page_id)! - pageIndex.get(b.page_id)!) || a.reading_order - b.reading_order)

  for (const b of top) {
    const label = String(b.provenance.parameters.layout_label ?? '')
    // GAP: running page headers and footers arrive as paragraphs. Only the layout label tells them apart.
    if (label === 'page_header' || label === 'page_footer') continue
    const text = b.current_text ?? ''
    const flags = [...b.quality_flags]
    let type: Block['type'] = b.block_type === 'caption' ? 'paragraph' : (b.block_type as Block['type'])
    let level: 1 | 2 | undefined
    let table: TableData | undefined
    let figure: Block['figure']
    let mathml: string | undefined
    let spoken: string | undefined
    let shown = text
    let say = text

    if (type === 'heading') {
      // GAP: the contract has no heading level. Use the layout label, else treat the first heading as the title.
      level = label === 'title' || (!label && headings === 0) ? 1 : 2
      headings++
    } else if (b.block_type === 'table') {
      const cells = b.table!.cell_ids.map((id) => byId.get(id)).filter((c): c is P1Block => !!c?.table_cell)
      if (!cells.length) {
        // 1.1.0 uncertain table: no cells, so the region's text is read as a plain passage.
        type = 'paragraph'
        if (!flags.includes('table_structure_uncertain')) flags.push('table_structure_uncertain')
      } else {
        const grid = Array.from({ length: b.table!.row_count! }, () => Array<string>(b.table!.column_count!).fill(''))
        for (const c of cells) grid[c.table_cell!.row_index][c.table_cell!.column_index] = c.current_text ?? ''
        if (cells.some((c) => c.table_cell!.row_span > 1 || c.table_cell!.column_span > 1)) flags.push('merged_headers')
        // GAP: the reader needs one header row. A table without one is sent to review.
        if (!cells.filter((c) => c.table_cell!.row_index === 0).every((c) => c.table_cell!.is_header)) flags.push('table_structure_uncertain')
        table = { caption: captionFor.get(b.id), columns: grid[0], rows: grid.slice(1) }
        say = cells.map((c) => c.current_text ?? '').join(' ')
      }
    } else if (b.equation) {
      const q = b.equation
      shown = text || q.source_text || ''
      if (q.mathml && q.mathml_review_status === 'approved') mathml = q.mathml
      else if (!flags.includes('math_needs_review')) flags.push('math_needs_review')
      // Contract rule: the spoken form is read only once a person has approved it.
      if (q.spoken_fallback && q.spoken_fallback_review_status === 'approved') spoken = q.spoken_fallback
      say = spoken ?? shown
    } else if (b.figure) {
      const f = b.figure
      const d = f.extended_description ?? f.alt_text
      figure = {
        caption: f.source_caption ?? captionFor.get(b.id) ?? '',
        alt: f.alt_text?.text ?? '',
        description: d?.text ?? '',
        description_origin: d && d.origin === 'model_generated' && d.review_status !== 'approved' ? 'generated_draft' : 'teacher',
      }
      if (!d) flags.push('figure_not_described')
      else if (figure.description_origin === 'generated_draft') flags.push('unreviewed_figure')
      say = figure.description || figure.caption
    } else if (!text.trim()) continue // empty_text passages have nothing to show or read

    // GAP: the pipeline leaves review_status at "unreviewed" and expects the reader to look at the flags.
    const status: BlockStatus =
      b.review_status === 'approved' ? 'reviewed'
      : b.review_status === 'rejected' ? 'unsupported'
      : b.review_status === 'needs_review' || flags.length ? 'needs_review'
      : 'trusted'
    const fix = [...doc.corrections].reverse().find((c) => c.block_id === b.id)
    blocks.push({
      id: b.id,
      page_id: b.page_id,
      type,
      level,
      order_key: blocks.length + 1,
      bbox: b.bbox,
      text_raw: b.raw_text ?? shown,
      text_current: shown,
      lang: voiceLang(b.language, say, main),
      revision: b.revision,
      status,
      confidence: { engine: b.provenance.engine ?? b.provenance.method, score: b.confidence.score, flags },
      provenance: { parser: b.provenance.engine ?? b.provenance.method, version: b.provenance.engine_version ?? '', reviewer: fix?.author_ref ?? undefined, changed_at: fix?.created_at },
      table,
      mathml,
      spoken,
      figure,
    })
  }

  const langs = doc.languages.filter((l): l is Lang => l === 'en' || l === 'hi')
  return {
    document: {
      id: doc.id,
      title: doc.title ?? 'Untitled chapter',
      subject: extra.subject,
      languages: langs.length ? langs : [main],
      page_count: pages.length,
      printed_range: `${pages[0].printed_label}–${pages[pages.length - 1].printed_label}`,
      // GAP: the contract has no document-level revision. Role 3 has to supply one.
      current_revision: 1,
      review_count: 0,
      rights_note: extra.rights_note,
      updated_at: doc.created_at,
    },
    revision: 1,
    pages,
    blocks,
    audio: [],
    bytes: 0,
  }
}
