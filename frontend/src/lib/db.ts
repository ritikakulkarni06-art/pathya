// Everything the student keeps on this device. Structured text lives in IndexedDB;
// immutable audio and page images live in Cache Storage (report p.18).
import { deleteDB, openDB, type IDBPDatabase } from 'idb'
import type { AnswerRecord, Bookmark, ChapterPackage, PendingCorrection, Pronunciation } from '../types'
import { sha256 } from './hash'
import { withKeptClips } from './audio'

export interface StoredPackage extends ChapterPackage {
  downloaded_at: string
  /** Asset URLs that could not be cached, so the reader can say exactly what is missing. */
  missing_assets: string[]
}
export interface Position {
  doc_id: string
  block_id: string
  at: string
  /** Section and printed page, e.g. "Acceleration, page 38". */
  label?: string
  /** How far through the chapter, 0 to 1. */
  progress?: number
}

// Each account gets its own database and asset cache, so one person's downloads, bookmarks and
// queued corrections are never shown to the next person who signs in on a shared device.
// The sample student keeps the original names so existing sample data stays where it was.
let owner = ''
const scoped = (name: string) => (owner ? `${name}.${owner}` : name)
/** Point the store at one account's data. Call before anything reads or writes. */
export function setOwner(userId: string | null) {
  const next = !userId || userId === 'sample-student' ? '' : userId
  if (next === owner) return
  owner = next
  void dbp?.then((d) => d.close())
  dbp = null
}

let dbp: Promise<IDBPDatabase> | null = null
function db() {
  dbp ??= openDB(scoped('pathya'), 1, {
    upgrade(d) {
      d.createObjectStore('packages', { keyPath: 'document.id' })
      d.createObjectStore('positions', { keyPath: 'doc_id' })
      d.createObjectStore('bookmarks', { keyPath: 'id' }).createIndex('doc', 'doc_id')
      d.createObjectStore('answers', { keyPath: 'id' }).createIndex('doc', 'doc_id')
      d.createObjectStore('pending', { keyPath: 'id' }).createIndex('doc', 'doc_id')
      d.createObjectStore('pronunciations', { keyPath: 'id' })
    },
  })
  return dbp
}

const assetCache = () => scoped('pathya-assets-v1')
const assetUrls = (p: ChapterPackage) => [...p.audio.map((a) => a.url), ...p.pages.flatMap((pg) => (pg.source_asset ? [pg.source_asset] : []))]

export const store = {
  // packages
  async getPackage(id: string): Promise<StoredPackage | undefined> {
    return (await db()).get('packages', id)
  },
  async listPackages(): Promise<StoredPackage[]> {
    return (await db()).getAll('packages')
  },
  /** Download a chapter. The old package stays until every part of the new one is stored. */
  async savePackage(next: ChapterPackage, onProgress?: (done: number, total: number) => void): Promise<StoredPackage> {
    const pkg = await withKeptClips(next, await (await db()).get('packages', next.document.id))
    const urls = assetUrls(pkg)
    const hashes = new Map(pkg.audio.filter((a) => a.sha256).map((a) => [a.url, a.sha256!]))
    const missing: string[] = []
    const cache = 'caches' in window ? await caches.open(assetCache()) : null
    if (urls.length && cache) {
      let done = 0
      for (const url of urls) {
        try {
          // Files are immutable (a changed clip gets a new address), so one already saved is reused.
          if (!(await cache.match(url))) {
            const res = await fetch(url)
            if (!res.ok) throw new Error(String(res.status))
            const body = await res.arrayBuffer()
            // Role 3 lists a SHA-256 for every clip; a file that does not match is not kept.
            if (hashes.has(url) && (await sha256(body)) !== hashes.get(url)) throw new Error('hash')
            await cache.put(url, new Response(body, { headers: res.headers }))
          }
        } catch {
          missing.push(url)
        }
        onProgress?.(++done, urls.length)
      }
    }
    const d = await db()
    const old: StoredPackage | undefined = await d.get('packages', pkg.document.id)
    const stored: StoredPackage = { ...pkg, downloaded_at: new Date().toISOString(), missing_assets: missing }
    await d.put('packages', stored)
    // Files the new revision no longer uses are removed only after it is stored.
    if (old && cache) {
      const keep = new Set(urls)
      await Promise.all(assetUrls(old).filter((u) => !keep.has(u)).map((u) => cache.delete(u)))
    }
    return stored
  },
  /** Remove everything this account keeps on the device: downloads, places, bookmarks, answers, queued corrections. */
  async purgeAll() {
    const name = scoped('pathya')
    await (await dbp?.catch(() => null))?.close()
    dbp = null
    await deleteDB(name)
    if ('caches' in window) await caches.delete(assetCache())
  },
  async deletePackage(id: string) {
    const d = await db()
    const pkg: StoredPackage | undefined = await d.get('packages', id)
    if (pkg && 'caches' in window) {
      const cache = await caches.open(assetCache())
      await Promise.all(assetUrls(pkg).map((u) => cache.delete(u)))
    }
    await d.delete('packages', id)
  },

  // reading position
  async getPosition(docId: string): Promise<Position | undefined> {
    return (await db()).get('positions', docId)
  },
  async listPositions(): Promise<Position[]> {
    return (await db()).getAll('positions')
  },
  async setPosition(docId: string, blockId: string, label?: string, progress?: number) {
    await (await db()).put('positions', { doc_id: docId, block_id: blockId, at: new Date().toISOString(), label, progress })
  },

  // bookmarks
  async listBookmarks(docId: string): Promise<Bookmark[]> {
    return (await db()).getAllFromIndex('bookmarks', 'doc', docId)
  },
  async putBookmark(b: Bookmark) {
    await (await db()).put('bookmarks', b)
  },
  async deleteBookmark(id: string) {
    await (await db()).delete('bookmarks', id)
  },

  // answer history
  async listAnswers(docId: string): Promise<AnswerRecord[]> {
    const all: AnswerRecord[] = await (await db()).getAllFromIndex('answers', 'doc', docId)
    return all.sort((a, b) => b.asked_at.localeCompare(a.asked_at))
  },
  async putAnswer(a: AnswerRecord) {
    await (await db()).put('answers', a)
  },

  // corrections written while offline
  async listPending(docId?: string): Promise<PendingCorrection[]> {
    const d = await db()
    return docId ? d.getAllFromIndex('pending', 'doc', docId) : d.getAll('pending')
  },
  async putPending(p: PendingCorrection) {
    await (await db()).put('pending', p)
  },
  async deletePending(id: string) {
    await (await db()).delete('pending', id)
  },

  // pronunciation overrides
  async listPronunciations(): Promise<Pronunciation[]> {
    return (await db()).getAll('pronunciations')
  },
  async putPronunciation(p: Pronunciation) {
    await (await db()).put('pronunciations', p)
  },
  async deletePronunciation(id: string) {
    await (await db()).delete('pronunciations', id)
  },
}

export const uid = () => crypto.randomUUID()

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(1)} GB`
}
