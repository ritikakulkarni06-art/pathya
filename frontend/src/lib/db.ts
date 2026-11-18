// Everything the student keeps on this device. Structured text lives in IndexedDB;
// immutable audio and page images live in Cache Storage (report p.18).
import { openDB, type IDBPDatabase } from 'idb'
import type { AnswerRecord, Bookmark, ChapterPackage, PendingCorrection, Pronunciation } from '../types'

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

let dbp: Promise<IDBPDatabase> | null = null
function db() {
  dbp ??= openDB('pathya', 1, {
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

const ASSET_CACHE = 'pathya-assets-v1'
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
  async savePackage(pkg: ChapterPackage, onProgress?: (done: number, total: number) => void): Promise<StoredPackage> {
    const urls = assetUrls(pkg)
    const missing: string[] = []
    if (urls.length && 'caches' in window) {
      const cache = await caches.open(ASSET_CACHE)
      let done = 0
      for (const url of urls) {
        try {
          const res = await fetch(url)
          if (!res.ok) throw new Error(String(res.status))
          await cache.put(url, res)
        } catch {
          missing.push(url)
        }
        onProgress?.(++done, urls.length)
      }
    }
    const stored: StoredPackage = { ...pkg, downloaded_at: new Date().toISOString(), missing_assets: missing }
    await (await db()).put('packages', stored)
    return stored
  },
  async deletePackage(id: string) {
    const d = await db()
    const pkg: StoredPackage | undefined = await d.get('packages', id)
    if (pkg && 'caches' in window) {
      const cache = await caches.open(ASSET_CACHE)
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
