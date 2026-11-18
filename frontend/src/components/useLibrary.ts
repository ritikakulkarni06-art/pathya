import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { store, type Position, type StoredPackage } from '../lib/db'
import { say, useOnline } from '../state/app'
import type { Block, DocumentSummary } from '../types'

export interface LibraryRow {
  doc: DocumentSummary
  downloaded: StoredPackage | null
  /** True when the server has a newer revision than the downloaded copy. */
  updateAvailable: boolean
  position: (Position & { label: string; progress: number }) | null
}

function positionLabel(pkg: StoredPackage | null, pos?: Position) {
  if (!pos) return null
  if (pos.label) return { ...pos, label: pos.label, progress: pos.progress ?? 0 }
  // Older saved positions have no label: work it out from the downloaded copy if there is one.
  const blocks: Block[] = pkg?.blocks ?? []
  const i = blocks.findIndex((b) => b.id === pos.block_id)
  if (i < 0) return { ...pos, label: 'Part-way through', progress: 0 }
  const heading = [...blocks.slice(0, i + 1)].reverse().find((b) => b.type === 'heading')
  const page = pkg!.pages.find((p) => p.id === blocks[i].page_id)
  return { ...pos, label: `${heading?.text_current ?? 'Start'}, page ${page?.printed_label}`, progress: i / Math.max(1, blocks.length - 1) }
}

/** Chapters from the server when online, merged with what is on this device. Offline: device only. */
export function useLibrary() {
  const online = useOnline()
  const [rows, setRows] = useState<LibraryRow[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [local, positions] = await Promise.all([store.listPackages(), store.listPositions()])
    let docs: DocumentSummary[]
    let fromServer = true
    try {
      docs = await api.listDocuments()
      setFailed(false)
    } catch {
      fromServer = false
      docs = local.map((p) => p.document)
      setFailed(navigator.onLine)
    }
    setRows(
      docs.map((doc) => {
        const downloaded = local.find((p) => p.document.id === doc.id) ?? null
        return {
          doc,
          downloaded,
          updateAvailable: fromServer && !!downloaded && downloaded.revision < doc.current_revision,
          position: positionLabel(downloaded, positions.find((p) => p.doc_id === doc.id)),
        }
      }),
    )
  }, [])

  useEffect(() => {
    void load()
  }, [load, online])

  const download = async (id: string) => {
    setBusy(id)
    try {
      const pkg = await api.getPackage(id)
      const stored = await store.savePackage(pkg)
      say(stored.missing_assets.length ? `Downloaded, but ${stored.missing_assets.length} audio or image files could not be saved.` : `“${pkg.document.title}” is downloaded and can be read offline.`, stored.missing_assets.length ? 'bad' : 'ok')
    } catch {
      say('The download did not finish. Your previous copy, if any, is unchanged.', 'bad')
    }
    setBusy(null)
    await load()
  }
  const remove = async (id: string) => {
    await store.deletePackage(id)
    say('Download removed from this device.')
    await load()
  }

  return { rows, online, failed, busy, download, remove, reload: load }
}
