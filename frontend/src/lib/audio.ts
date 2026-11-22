// Role 3 prepared narration: which backend clips the reader may play for a passage.
import type { Block, ChapterPackage } from '../types'
import { clipKey, sha256 } from './hash'
import { toSentenceStarts } from './sentences'

/** One passage's audio file from Role 3: a clip per sentence, offsets in code points of the current text. */
export interface AudioUnits {
  status: string
  block_id: string
  text_sha256: string
  language: string
  synthetic?: boolean
  units: { text_offset_start: number; text_offset_end: number; clip_asset_id: string; hash: string; bytes: number }[]
}

/** Clips for one passage, or nothing when they do not match exactly what the reader will say:
 *  same passage, same text (SHA-256), same voice language (a mul/und passage matches by its source tag too),
 *  and the same sentence boundaries the reader highlights. Silent test clips are never used.
 *  May set `block.sentence_starts` from the clips when the backend sent no separate ranges. */
export async function clipsFor(block: Block, a: AudioUnits, assetUrl: (id: string) => string): Promise<ChapterPackage['audio']> {
  if (a.status !== 'ready' || a.synthetic || a.block_id !== block.id || !a.units.length) return []
  if (block.type !== 'paragraph' && block.type !== 'heading' && block.type !== 'list_item') return []
  if (a.language !== block.lang && a.language !== block.source_lang) return []
  const textSha = await sha256(block.text_current)
  if (a.text_sha256 !== textSha) return []
  const starts = toSentenceStarts(block.text_current, a.units.map((u) => ({ start: u.text_offset_start, end: u.text_offset_end })))
  if (!starts || (block.sentence_starts && block.sentence_starts.join() !== starts.join())) return []
  block.sentence_starts ??= starts
  return a.units.map((u, i) => ({ key: clipKey(block.id, textSha, i, block.lang), url: assetUrl(u.clip_asset_id), bytes: u.bytes, sha256: u.hash }))
}
