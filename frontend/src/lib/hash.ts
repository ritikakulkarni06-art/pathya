// Hashes shared by the API client, narration and the clip tool.
import type { SpeechUnit } from './sentences'

/** SHA-256 of the exact UTF-8 text, as Role 3 computes `text_sha256`. */
export async function sha256(text: string | ArrayBuffer): Promise<string> {
  const data = typeof text === 'string' ? new TextEncoder().encode(text) : text
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** A prepared clip is identified by passage, exact passage text, sentence number and voice language
 *  (agreed with Role 1 and Role 3), so edited text can never play old audio. */
export const clipKey = (blockId: string, textSha: string, sentence: number, voiceLang: string) => `${blockId}|${textSha}|${sentence}|${voiceLang}`

/** Key for one narration unit. Sentences use the passage text; phrases the reader builds itself (table
 *  rows, captions, notes) have no sentence number, so their own text is hashed instead. */
export async function unitClipKey(unit: SpeechUnit, blockText: string | undefined): Promise<string> {
  if (unit.sentence >= 0 && blockText !== undefined) return clipKey(unit.block_id, await sha256(blockText), unit.sentence, unit.lang)
  return clipKey(unit.block_id, await sha256(unit.text), unit.sentence, unit.lang)
}
