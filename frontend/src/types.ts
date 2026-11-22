// Shared content contract (report p.16). Role 1 produces blocks, Role 3 versions and serves them,
// this reader only consumes them. Keep this file in sync with the team's JSON schema.

export type Lang = 'en' | 'hi'
export type BlockType = 'heading' | 'paragraph' | 'list_item' | 'table' | 'equation' | 'figure'
export type BlockStatus = 'trusted' | 'needs_review' | 'reviewed' | 'unsupported'

export type PageStatus = 'ok' | 'blank' | 'needs_ocr' | 'partial' | 'failed'

export interface Confidence {
  engine: string
  /** null means "not scored" (e.g. native PDF text). Never shown as 100%. */
  score: number | null
  /** Machine codes from Role 1's checks, e.g. possible_missing_minus. */
  flags: string[]
}

export interface Provenance {
  parser: string
  version: string
  reviewer?: string
  changed_at?: string
}

export interface TableData {
  caption?: string
  columns: string[]
  /** First cell of each row is the row header. */
  rows: string[][]
  numeric?: boolean[]
}

export interface Block {
  id: string
  page_id: string
  type: BlockType
  level?: 1 | 2
  order_key: number
  /** Normalised top-left page space, 0..1: [x0, y0, x1, y1]. */
  bbox: [number, number, number, number]
  text_raw: string
  text_current: string
  /** Narration voice. Always en or hi. */
  lang: Lang
  /** Role 1's own language tag when it is not en or hi ("mul" or "und"), kept so it is never lost. */
  source_lang?: string
  /** Sentence starts in text_current (JavaScript string offsets) from the backend segmenter.
   *  Absent means the reader splits the text itself. */
  sentence_starts?: number[]
  revision: number
  status: BlockStatus
  confidence: Confidence
  provenance: Provenance
  table?: TableData
  /** Reviewed MathML markup plus a spoken fallback. */
  mathml?: string
  spoken?: string
  figure?: { caption: string; alt: string; description: string; description_origin: 'teacher' | 'generated_draft' }
}

export interface Page {
  id: string
  pdf_index_0: number
  printed_label: string
  /** True when the book page had no printed number, so printed_label is only its position in the file. */
  label_missing?: boolean
  /** How completely Role 1 could read the page (contract 1.1.0). Absent means ok. */
  status?: PageStatus
  /** Processing notes from Role 1, for teachers and reviewers. */
  warnings?: { stage: string; code: string; message: string }[]
  /** Original scan/PDF page image, when the backend provides one. */
  source_asset?: string
}

export interface DocumentSummary {
  id: string
  title: string
  subject: string
  languages: Lang[]
  page_count: number
  printed_range: string
  current_revision: number
  review_count: number
  /** Set when the backend says review is pending but gives no count. */
  needs_review?: boolean
  rights_note: string
  updated_at: string
}

export interface ChapterPackage {
  document: DocumentSummary
  revision: number
  pages: Page[]
  blocks: Block[]
  /** Prepared sentence audio from the backend. Empty means the reader uses the device voice. */
  audio: { key: string; url: string; bytes: number; sha256?: string }[]
  /** Role 3 is still building audio for this revision; earlier clips that still match may be kept. */
  audio_pending?: boolean
  /** Name of the voice that made the clips, shown to the student. */
  audio_voice?: string
  bytes: number
}

export interface CorrectionRequest {
  block_id: string
  base_revision: number
  text: string
  reason: string
  /** Optional structure fixes (Role 1 applies them): the passage's language, its kind, or its place in the reading order. */
  lang?: Lang
  block_type?: 'heading' | 'paragraph' | 'list_item'
  move?: 'earlier' | 'later'
}

/** One published correction, as the backend records it (Role 3). */
export interface RevisionEntry {
  revision: number
  block_id: string
  at: string
  by: string
  reason: string
  before: string
  after: string
  /** Plain-language list of what changed besides the words, e.g. "Language set to Hindi". */
  changes: string[]
}

/** How many questions the student may still ask today (Role 3's usage limit). */
export interface Usage {
  remaining: number
  limit: number
}

export type CorrectionResult =
  | { ok: true; block: Block; document_revision: number }
  | { ok: false; conflict: true; current: Block }

export interface Evidence {
  block_id: string
  rev: number
  quote: string
}

export type Answer =
  | {
      abstain: false
      origin: 'evidence_passages' | 'ai_explanation'
      document_revision: number
      claims: { text: string; evidence: Evidence[] }[]
      usage?: Usage
    }
  | {
      abstain: true
      reason: 'no_support' | 'source_needs_review'
      document_revision: number
      evidence_candidates: string[]
      usage?: Usage
    }

export interface AnswerRecord {
  id: string
  doc_id: string
  question: string
  asked_at: string
  answer: Answer
}

export interface Bookmark {
  id: string
  doc_id: string
  block_id: string
  label: string
  created_at: string
}

export interface PendingCorrection extends CorrectionRequest {
  id: string
  doc_id: string
  queued_at: string
  state: 'queued' | 'conflict'
}

export interface Pronunciation {
  id: string
  term: string
  spoken: string
  lang: Lang
  /** 'all' or a document id, so "lead" in chemistry need not change another book. */
  scope: string
}

export const FLAG_REASONS: Record<string, string> = {
  possible_missing_minus: 'A minus sign may be missing. The numbers around it suggest a negative value.',
  low_ocr_confidence: 'The scanner was unsure about some characters in this passage.',
  column_order_uncertain: 'This passage sits between two columns, so its position in the reading order may be wrong.',
  script_mixing: 'Hindi and English letters are mixed inside one word, which usually means a misread character.',
  unreviewed_figure: 'This figure description is a generated draft that no teacher has checked yet.',
  merged_headers: 'This table has merged header cells, which the reader cannot yet present reliably.',
  figure_not_described: 'This picture has no description yet.',
  // A sign, decimal point, exponent or unit that changes the meaning may be wrong (name still to be agreed).
  critical_symbol_uncertain: 'A sign, decimal point or other symbol that changes the meaning may be wrong here.',
  critical_minus_sign_uncertain: 'A minus sign may be missing or wrong here, which would change the meaning.',
  // Role 1 contract 1.1.0 quality flags.
  low_confidence: 'The scanner was unsure about some characters in this passage.',
  possible_ocr_error: 'Some characters in this passage may have been misread.',
  mixed_script: 'Hindi and English letters are mixed in this passage, which can mean a misread character.',
  language_uncertain: 'The language of this passage could not be worked out, so the wrong voice may read it.',
  reading_order_uncertain: 'The position of this passage in the reading order may be wrong.',
  geometry_uncertain: 'The place of this passage on the printed page is uncertain.',
  table_structure_uncertain: 'The rows and columns of this table could not be worked out, so it is shown as plain text.',
  math_needs_review: 'This equation has not been checked, so its symbols may be wrong.',
  unsupported_content: 'This kind of content cannot be shown reliably yet.',
  empty_text: 'No text could be read in this part of the page.',
  block_type_uncertain: 'It is unclear whether this is a heading, a paragraph or something else.',
  missing_geometry: 'Part of this passage could not be placed on the printed page.',
  overlapping_regions: 'This passage overlaps another one on the page, so some text may be repeated or missing.',
  orphan_caption: 'This caption could not be matched to a figure or table.',
  duplicate_content: 'This text was read twice in two different ways, so some of it may be repeated.',
}
