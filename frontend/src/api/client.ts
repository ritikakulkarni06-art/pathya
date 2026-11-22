// The reader's only door to Role 3's backend. Set VITE_API_URL to use the real API;
// without it the app runs on a mock that imitates the same contract (revisions, 409 conflicts,
// evidence answers, abstention) using the sample chapters.
import { SAMPLE_PACKAGES } from '../data/chapters'
import { csrfHeader, SIGNED_OUT_EVENT } from './auth'
import { fromP1 } from '../lib/p1'
import type { Answer, Block, ChapterPackage, CorrectionRequest, CorrectionResult, DocumentSummary, Lang, RevisionEntry, Usage } from '../types'
import { splitSentences, toSentenceStarts } from '../lib/sentences'
import { tokens } from '../lib/search'

export class OfflineError extends Error {
  constructor() {
    super('You are offline.')
  }
}

/** The chapter was removed, or this account may no longer open it. Copies on this device must be deleted. */
export class GoneError extends Error {
  constructor() {
    super('This chapter is no longer available to you.')
  }
}

/** The daily question limit is used up. */
export class LimitError extends Error {
  limit: number
  constructor(limit: number) {
    super('The daily question limit is reached.')
    this.limit = limit
  }
}

export type JobState = 'queued' | 'validating' | 'extracting' | 'review_required' | 'building' | 'ready' | 'failed' | 'cancelled'
export interface Job {
  id: string
  document_id: string
  title: string
  created_at: string
  state: JobState
  pages_done: number
  pages_total: number
  /** Plain-language reason when the job failed. */
  reason?: string
  /** The step that was running when the job failed. */
  failed_at?: JobState
}
export interface NewDocument {
  file: File
  title: string
  languages: string[]
  rights_note: string
}

export interface PathyaApi {
  createDocument(input: NewDocument): Promise<{ document_id: string; job_id: string }>
  getJob(jobId: string): Promise<Job>
  listDocuments(): Promise<DocumentSummary[]>
  getPackage(docId: string): Promise<ChapterPackage>
  patchBlock(docId: string, req: CorrectionRequest): Promise<CorrectionResult>
  ask(docId: string, question: string): Promise<Answer>
  /** Questions left today, without asking one. */
  getUsage(): Promise<Usage>
  /** Every published correction of a chapter, newest first. */
  getHistory(docId: string): Promise<RevisionEntry[]>
  /** Remove a chapter and everything made from it from the server. */
  deleteDocument(docId: string): Promise<void>
  listJobs(): Promise<Job[]>
  cancelJob(jobId: string): Promise<Job>
  retryJob(jobId: string): Promise<Job>
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
const online = () => {
  if (!navigator.onLine) throw new OfflineError()
}

// ---------- mock ----------
const KEY = 'pathya.mock.server.v1'
type Overrides = Record<string, { revision: number; blocks: Record<string, Partial<Block>>; history?: RevisionEntry[]; deleted?: boolean }>

function loadOverrides(): Overrides {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}')
  } catch {
    return {}
  }
}

function current(docId: string): ChapterPackage {
  const base = SAMPLE_PACKAGES.find((p) => p.document.id === docId)
  const o = loadOverrides()[docId]
  if (!base || o?.deleted) throw new Error('This chapter does not exist.')
  const blocks = base.blocks.map((b) => (o?.blocks[b.id] ? { ...b, ...o.blocks[b.id] } : b)).sort((a, b) => a.order_key - b.order_key)
  const revision = o?.revision ?? 1
  const pkg: ChapterPackage = {
    ...base,
    revision,
    blocks,
    document: {
      ...base.document,
      current_revision: revision,
      review_count: blocks.filter((b) => b.status === 'needs_review').length,
    },
  }
  pkg.bytes = new Blob([JSON.stringify(pkg)]).size
  return pkg
}

// The mock cannot read a file, so its jobs walk through the real states and then stop honestly.
interface MockJob { id: string; title: string; created: number; started: number; pages: number; cancelled?: boolean }
const JOBS = 'pathya.mock.jobs.v1'
const loadJobs = (): MockJob[] => {
  try {
    return JSON.parse(localStorage.getItem(JOBS) ?? '[]')
  } catch {
    return []
  }
}
const saveJobs = (list: MockJob[]) => localStorage.setItem(JOBS, JSON.stringify(list.slice(-8)))
function mockJob(id: string): Job {
  const j = loadJobs().find((x) => x.id === id)
  if (!j) throw new Error('This job does not exist.')
  const t = (Date.now() - j.started) / 1000
  const base = { id, document_id: 'upload-' + id, title: j.title, created_at: new Date(j.created).toISOString(), pages_done: 0, pages_total: j.pages }
  if (j.cancelled) return { ...base, state: 'cancelled', failed_at: 'queued', reason: 'You cancelled this upload. Nothing was stored.' }
  if (t < 1) return { ...base, state: 'queued' }
  if (t < 2.2) return { ...base, state: 'validating' }
  const read = Math.floor((t - 2.2) / 0.6)
  if (read < j.pages) return { ...base, state: 'extracting', pages_done: read }
  return {
    ...base,
    state: 'failed',
    failed_at: 'building',
    pages_done: j.pages,
    reason: 'This is the sample build, with no preparation server connected. The file was checked and its pages counted, but no text was extracted. Nothing was stored.',
  }
}

// The sample build allows 20 questions a day, so the limit can be seen and tested.
const USAGE = 'pathya.mock.usage.v1'
function mockUsage(spend = 0): Usage {
  const today = new Date().toISOString().slice(0, 10)
  let used = 0
  try {
    const u = JSON.parse(localStorage.getItem(USAGE) ?? '{}')
    if (u.day === today) used = u.used
  } catch {
    // start from zero
  }
  used += spend
  if (spend) localStorage.setItem(USAGE, JSON.stringify({ day: today, used }))
  return { limit: 20, remaining: Math.max(0, 20 - used) }
}

const mock: PathyaApi = {
  async createDocument(input) {
    online()
    await wait(700)
    const id = Math.random().toString(36).slice(2, 10)
    saveJobs([...loadJobs(), { id, title: input.title, created: Date.now(), started: Date.now(), pages: Math.max(2, Math.min(12, Math.round(input.file.size / 150_000))) }])
    return { document_id: 'upload-' + id, job_id: id }
  },
  async getJob(jobId) {
    online()
    return mockJob(jobId)
  },
  async listDocuments() {
    online()
    await wait(250)
    const gone = loadOverrides()
    return SAMPLE_PACKAGES.filter((p) => !gone[p.document.id]?.deleted).map((p) => current(p.document.id).document)
  },
  async getPackage(docId) {
    online()
    await wait(350)
    if (loadOverrides()[docId]?.deleted) throw new GoneError()
    const pkg = current(docId)
    // Prepared narration clips, if tools/make-audio.mjs has produced them for this chapter.
    try {
      const res = await fetch(`/audio/${docId}.json`)
      if (res.ok && res.headers.get('content-type')?.includes('json')) {
        const { voice, audio } = await res.json()
        pkg.audio = audio
        pkg.audio_voice = voice
        pkg.bytes += audio.reduce((n: number, a: { bytes: number }) => n + a.bytes, 0)
      }
    } catch {
      // no prepared audio: the reader falls back to the device voice
    }
    return pkg
  },
  async patchBlock(docId, req) {
    online()
    await wait(400)
    const pkg = current(docId)
    const block = pkg.blocks.find((b) => b.id === req.block_id)
    if (!block) throw new Error('This passage no longer exists.')
    if (block.revision !== req.base_revision) return { ok: false, conflict: true, current: block }
    const all = loadOverrides()
    const doc = all[docId] ?? { revision: 1, blocks: {} }
    doc.revision += 1
    const changes: string[] = []
    const patch: Partial<Block> = {
      text_current: req.text,
      revision: block.revision + 1,
      status: 'reviewed' as const,
      provenance: { ...block.provenance, reviewer: 'student', changed_at: new Date().toISOString() },
    }
    if (req.lang && req.lang !== block.lang) {
      patch.lang = req.lang
      changes.push(`Language set to ${req.lang === 'hi' ? 'Hindi' : 'English'}`)
    }
    if (req.block_type && req.block_type !== block.type) {
      patch.type = req.block_type
      if (req.block_type === 'heading') patch.level = 2
      changes.push(`Marked as a ${req.block_type === 'list_item' ? 'list item' : req.block_type}`)
    }
    if (req.move) {
      // Swap places with the neighbouring passage on the same page.
      const i = pkg.blocks.indexOf(block)
      const other = pkg.blocks[i + (req.move === 'earlier' ? -1 : 1)]
      if (other && other.page_id === block.page_id) {
        patch.order_key = other.order_key
        doc.blocks[other.id] = { ...doc.blocks[other.id], order_key: block.order_key }
        changes.push(`Moved ${req.move} in the reading order`)
      }
    }
    doc.blocks[block.id] = { ...doc.blocks[block.id], ...patch }
    doc.history = [{ revision: doc.revision, block_id: block.id, at: new Date().toISOString(), by: 'student', reason: req.reason, before: block.text_current, after: req.text, changes }, ...(doc.history ?? [])]
    all[docId] = doc
    localStorage.setItem(KEY, JSON.stringify(all))
    return { ok: true, block: { ...block, ...patch }, document_revision: doc.revision }
  },
  // Base mode from the report: extractive evidence passages, no generated prose.
  async ask(docId, question) {
    online()
    await wait(600)
    const before = mockUsage()
    if (before.remaining <= 0) throw new LimitError(before.limit)
    const usage = mockUsage(1)
    return { ...mockAnswer(docId, question), usage }
  },
  async getUsage() {
    return mockUsage()
  },
  async getHistory(docId) {
    online()
    await wait(200)
    return loadOverrides()[docId]?.history ?? []
  },
  async deleteDocument(docId) {
    online()
    await wait(400)
    const all = loadOverrides()
    all[docId] = { revision: 1, blocks: {}, deleted: true }
    localStorage.setItem(KEY, JSON.stringify(all))
  },
  async listJobs() {
    online()
    return loadJobs().map((j) => mockJob(j.id)).reverse()
  },
  async cancelJob(jobId) {
    online()
    saveJobs(loadJobs().map((j) => (j.id === jobId ? { ...j, cancelled: true } : j)))
    return mockJob(jobId)
  },
  async retryJob(jobId) {
    online()
    saveJobs(loadJobs().map((j) => (j.id === jobId ? { ...j, cancelled: false, started: Date.now() } : j)))
    return mockJob(jobId)
  },
}

// Base mode from the report: extractive evidence passages, no generated prose.
function mockAnswer(docId: string, question: string): Answer {
  {
    const pkg = current(docId)
    const q = tokens(question)
    const scored = pkg.blocks
      .filter((b) => b.type === 'paragraph' || b.type === 'list_item')
      .map((b) => {
        const t = new Set(tokens(b.text_current))
        const hits = q.filter((w) => t.has(w)).length
        return { b, hits }
      })
      .filter((s) => q.length > 0 && s.hits >= (q.length <= 2 ? q.length : Math.max(2, Math.ceil(q.length * 0.5))))
      .sort((a, b) => b.hits - a.hits)
      .slice(0, 3)
    if (!scored.length) return { abstain: true, reason: 'no_support', document_revision: pkg.revision, evidence_candidates: [] }
    const unsafe = scored.filter((s) => s.b.status === 'needs_review')
    if (unsafe.length && unsafe[0].b.id === scored[0].b.id)
      return { abstain: true, reason: 'source_needs_review', document_revision: pkg.revision, evidence_candidates: unsafe.map((s) => s.b.id) }
    return {
      abstain: false as const,
      origin: 'evidence_passages',
      document_revision: pkg.revision,
      claims: scored
        .filter((s) => s.b.status !== 'needs_review')
        .map(({ b }) => {
          const best = splitSentences(b.text_current, b.lang)
            .map((s) => ({ s, n: q.filter((w) => tokens(s).includes(w)).length }))
            .sort((x, y) => y.n - x.n)[0].s
          return { text: best, evidence: [{ block_id: b.id, rev: b.revision, quote: best }] }
        }),
    }
  }
}

// ---------- real backend (Role 3) ----------
/** A library entry as Role 3 sends it (GET /documents and GET /documents/{id}). */
interface BackendDocument {
  id: string
  title: string
  rights_note: string
  current_revision: number
  state: string
  updated_at: string
  languages: Lang[]
  counts: { pages: number; blocks: number; review?: number }
}
// Role 3 has no subject or printed page range in the list, so those stay empty here.

/** SHA-256 of the exact UTF-8 text, as Role 3 sends it with each block's sentence ranges. */
const sha256 = async (text: string) =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map((b) => b.toString(16).padStart(2, '0')).join('')

interface SentenceRanges {
  document_revision: number
  blocks: { block_id: string; text_sha256: string; segmenter: string; ranges: { start: number; end: number }[] }[]
}
const summary = (d: BackendDocument): DocumentSummary => ({
  id: d.id, title: d.title, subject: '', languages: d.languages, page_count: d.counts.pages, printed_range: '',
  current_revision: d.current_revision, review_count: d.counts.review ?? 0, needs_review: d.counts.review === undefined && d.state === 'review_required',
  rights_note: d.rights_note, updated_at: d.updated_at,
})
function http(base: string): PathyaApi {
  const call = async <T,>(path: string, init?: RequestInit): Promise<T> => {
    online()
    // Role 3 requires the CSRF token on every write; it is harmless on reads.
    const res = await fetch(base + path, { credentials: 'include', headers: { 'Content-Type': 'application/json', ...csrfHeader() }, ...init })
    if (res.status === 401) {
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT))
      throw new Error('Your session has ended. Sign in again.')
    }
    if (res.status === 409) return { ok: false, conflict: true, current: (await res.json()).current } as T
    if (res.status === 429) throw new LimitError((await res.json().catch(() => ({}))).limit ?? 0)
    if (res.status === 204) return undefined as T
    if (!res.ok) throw new Error(`The server answered ${res.status}.`)
    return res.json()
  }
  return {
    async createDocument(input) {
      online()
      const body = new FormData()
      body.set('file', input.file)
      body.set('title', input.title)
      body.set('languages', input.languages.join(','))
      body.set('rights_note', input.rights_note)
      const res = await fetch(base + '/documents', { method: 'POST', body, credentials: 'include', headers: csrfHeader() })
      if (!res.ok) throw new Error(`The server answered ${res.status}.`)
      return res.json()
    },
    getJob: (id) => call(`/jobs/${id}`),
    listDocuments: async () => (await call<{ documents: BackendDocument[] }>('/documents')).documents.map(summary),
    // Role 3 returns Role 1's Document unchanged; the document revision travels in a header.
    async getPackage(id) {
      online()
      const res = await fetch(`${base}/documents/${id}/content`, { credentials: 'include' })
      if (res.status === 401) {
        window.dispatchEvent(new Event(SIGNED_OUT_EVENT))
        throw new Error('Your session has ended. Sign in again.')
      }
      // 403/404: access was taken away. 410: the owner deleted it and asks for local copies to be purged.
      if ([403, 404, 410].includes(res.status)) throw new GoneError()
      if (!res.ok) throw new Error(`The server answered ${res.status}.`)
      const meta = await call<BackendDocument>(`/documents/${id}`).catch(() => null)
      const pkg = fromP1(await res.json(), { subject: '', rights_note: meta?.rights_note ?? '' })
      if (meta) pkg.document.title = meta.title
      const revision = Number(res.headers.get('X-Document-Revision')) || 1
      pkg.revision = pkg.document.current_revision = revision
      for (const p of pkg.pages) p.source_asset = `${base}/documents/${id}/pages/${p.pdf_index_0}/image`
      // Sentence ranges from the backend segmenter, used only when they belong to this exact revision and
      // text. Anything that does not match falls back to the reader's own splitter, so reading never breaks.
      try {
        const sr = await call<SentenceRanges>(`/documents/${id}/sentence-ranges`)
        if (sr.document_revision === revision) {
          const byId = new Map(sr.blocks.map((b) => [b.block_id, b]))
          for (const b of pkg.blocks) {
            const r = byId.get(b.id)
            if (!r?.ranges.length || r.text_sha256 !== (await sha256(b.text_current))) continue
            const starts = toSentenceStarts(b.text_current, r.ranges)
            if (starts) b.sentence_starts = starts
          }
        }
      } catch (e) {
        if (e instanceof OfflineError) throw e
      }
      return pkg
    },
    patchBlock: (_doc, req) =>
      call(`/blocks/${req.block_id}`, { method: 'PATCH', body: JSON.stringify({ base_revision: req.base_revision, reason: req.reason, operations: [
        { op: 'replace_text', text: req.text },
        ...(req.lang ? [{ op: 'set_language', lang: req.lang }] : []),
        ...(req.block_type ? [{ op: 'set_type', type: req.block_type }] : []),
        ...(req.move ? [{ op: 'move', direction: req.move }] : []),
      ] }) }),
    ask: (id, question) => call('/questions', { method: 'POST', body: JSON.stringify({ document_id: id, question }) }),
    getUsage: () => call('/usage'),
    getHistory: (id) => call(`/documents/${id}/revisions`),
    deleteDocument: (id) => call(`/documents/${id}`, { method: 'DELETE' }),
    listJobs: () => call('/jobs'),
    // Role 3 answers 204 with no body, so the job is read again to get its new state.
    cancelJob: async (id) => {
      await call(`/jobs/${id}/cancel`, { method: 'POST' })
      return call(`/jobs/${id}`)
    },
    retryJob: (id) => call(`/jobs/${id}/retry`, { method: 'POST' }),
  }
}

const url = import.meta.env.VITE_API_URL as string | undefined
export const api: PathyaApi = url ? http(url) : mock
export const usingMock = !url
