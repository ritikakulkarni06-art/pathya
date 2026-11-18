import { create } from 'zustand'
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { api, OfflineError } from '../api/client'
import { store, uid, type StoredPackage } from '../lib/db'
import type { Block, ChapterPackage, CorrectionRequest } from '../types'
export type { Block }

// ---- screen-reader announcements and visible toasts (one polite live region) ----
interface Notice {
  id: number
  text: string
  tone: 'info' | 'ok' | 'bad'
}
export const useNotices = create<{ items: Notice[]; say: (text: string, tone?: Notice['tone']) => void; dismiss: (id: number) => void }>((set) => ({
  items: [],
  say(text, tone = 'info') {
    const id = Date.now() + Math.random()
    set((s) => ({ items: [...s.items.slice(-2), { id, text, tone }] }))
    setTimeout(() => set((s) => ({ items: s.items.filter((n) => n.id !== id) })), 7000)
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((n) => n.id !== id) })),
}))
export const say = (text: string, tone?: Notice['tone']) => useNotices.getState().say(text, tone)

// ---- passages waiting for review, shown beside "Review desk" in the menu ----
export const useReviewCount = create<{ count: number }>(() => ({ count: 0 }))
export async function refreshReviewCount() {
  let count: number
  try {
    count = (await api.listDocuments()).reduce((n, d) => n + d.review_count, 0)
  } catch {
    count = (await store.listPackages()).reduce((n, p) => n + p.blocks.filter((b) => b.status === 'needs_review').length, 0)
  }
  useReviewCount.setState({ count })
}

// ---- connectivity ----
const subscribe = (cb: () => void) => {
  window.addEventListener('online', cb)
  window.addEventListener('offline', cb)
  return () => {
    window.removeEventListener('online', cb)
    window.removeEventListener('offline', cb)
  }
}
export const useOnline = () => useSyncExternalStore(subscribe, () => navigator.onLine)

// ---- chapter loading: network first, the downloaded copy when offline ----
export interface ChapterState {
  pkg: ChapterPackage | null
  /** Where the content on screen came from. */
  source: 'network' | 'device' | null
  downloaded: StoredPackage | null
  error: 'offline_not_downloaded' | 'failed' | null
  loading: boolean
}

export function useChapter(docId: string) {
  const online = useOnline()
  const [state, setState] = useState<ChapterState>({ pkg: null, source: null, downloaded: null, error: null, loading: true })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let live = true
    ;(async () => {
      const downloaded = (await store.getPackage(docId)) ?? null
      // Show the device copy at once so reading resumes without waiting for the network.
      if (downloaded && live) setState({ pkg: downloaded, source: 'device', downloaded, error: null, loading: false })
      try {
        const pkg = await api.getPackage(docId)
        if (live) setState({ pkg, source: 'network', downloaded, error: null, loading: false })
      } catch (e) {
        if (!live) return
        if (downloaded) setState({ pkg: downloaded, source: 'device', downloaded, error: null, loading: false })
        else setState({ pkg: null, source: null, downloaded: null, error: e instanceof OfflineError ? 'offline_not_downloaded' : 'failed', loading: false })
      }
    })()
    return () => {
      live = false
    }
  }, [docId, online, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const setDownloaded = useCallback((d: StoredPackage | null) => setState((s) => ({ ...s, downloaded: d })), [])
  return { ...state, reload, setDownloaded }
}

// ---- corrections: send now, or queue with the base revision while offline ----
export type SubmitOutcome = { kind: 'published'; block: Block; revision: number } | { kind: 'queued' } | { kind: 'conflict'; current: Block }

export async function submitCorrection(docId: string, req: CorrectionRequest): Promise<SubmitOutcome> {
  try {
    const res = await api.patchBlock(docId, req)
    if (res.ok) {
      void refreshReviewCount()
      return { kind: 'published', block: res.block, revision: res.document_revision }
    }
    return { kind: 'conflict', current: res.current }
  } catch (e) {
    if (!(e instanceof OfflineError)) throw e
    await store.putPending({ ...req, id: uid(), doc_id: docId, queued_at: new Date().toISOString(), state: 'queued' })
    return { kind: 'queued' }
  }
}

/** Send queued corrections after reconnecting. Conflicts stay in the queue for the student to resolve. */
let syncing = false
export async function syncPending(docId: string): Promise<{ sent: number; conflicts: number }> {
  if (syncing) return { sent: 0, conflicts: 0 }
  syncing = true
  try {
    return await runSync(docId)
  } finally {
    syncing = false
  }
}

async function runSync(docId: string): Promise<{ sent: number; conflicts: number }> {
  let sent = 0
  let conflicts = 0
  for (const p of await store.listPending(docId)) {
    if (p.state === 'conflict') continue // already shown to the student, waiting for their decision
    try {
      const res = await api.patchBlock(docId, p)
      if (res.ok) {
        await store.deletePending(p.id)
        sent++
      } else {
        await store.putPending({ ...p, state: 'conflict' })
        conflicts++
      }
    } catch {
      break
    }
  }
  return { sent, conflicts }
}
