import { create } from 'zustand'
import { clipKey, speech, hasVoiceFor } from '../lib/speech'
import { applyPronunciations, unitsFor, type SpeechUnit } from '../lib/sentences'
import { store } from '../lib/db'
import { usePrefs } from './prefs'
import type { ChapterPackage } from '../types'

interface NarrationState {
  docId: string | null
  units: SpeechUnit[]
  index: number
  status: 'idle' | 'playing' | 'paused'
  /** Plain-language problem shown in the player, e.g. no Hindi voice on this device. */
  problem: string | null
  /** The passage on screen, so "Listen" starts where the student is reading. */
  anchor: string | null
  setAnchor: (blockId: string | null) => void
  load: (pkg: ChapterPackage) => void
  play: (fromBlockId?: string, sentence?: number) => void
  pause: () => void
  toggle: () => void
  step: (by: number) => void
  stop: () => void
}

let run = 0
/** Identity of the loaded content, so re-fetching the same revision never interrupts playback. */
let loadedKey = ''
let clips = new Map<string, string>()

export const useNarration = create<NarrationState>((set, get) => {
  async function speakFrom(i: number) {
    const mine = ++run
    const { units, docId } = get()
    const pronunciations = await store.listPronunciations()
    for (let idx = i; idx < units.length; idx++) {
      if (mine !== run) return
      const unit = units[idx]
      set({ index: idx, status: 'playing', problem: null })
      const prefs = usePrefs.getState()
      const text = applyPronunciations(unit.text, unit.lang, docId ?? '', pronunciations)
      // A prepared clip is used only for the exact, unmodified sentence it was made from.
      const clipUrl = text === unit.text ? clips.get(await clipKey(unit.lang, unit.text)) : undefined
      if (clipUrl) {
        try {
          await speech.speak({ text, lang: unit.lang, rate: prefs.rate, clipUrl })
          continue
        } catch (e) {
          if ((e as Error).message === 'cancelled') return
          // clip missing or unplayable: fall through to the device voice
        }
        if (mine !== run) return
      }
      if (!(await hasVoiceFor(unit.lang))) {
        set({ status: 'paused', problem: unit.lang === 'hi' ? 'This device has no Hindi voice installed. The text is still readable; install a Hindi voice in your system settings to listen.' : 'This device has no English voice installed.' })
        return
      }
      try {
        await speech.speak({
          text,
          lang: unit.lang,
          rate: prefs.rate,
          voiceId: unit.lang === 'hi' ? prefs.voiceHi : prefs.voiceEn,
        })
      } catch (e) {
        if ((e as Error).message === 'cancelled') return
        set({ status: 'paused', problem: 'Speech stopped unexpectedly. Press play to try again.' })
        return
      }
    }
    if (mine === run) set({ status: 'idle', index: 0 })
  }

  return {
    docId: null,
    units: [],
    index: 0,
    status: 'idle',
    problem: null,
    anchor: null,
    setAnchor: (anchor) => set({ anchor }),
    load(pkg) {
      const key = `${pkg.document.id}:${pkg.revision}:${usePrefs.getState().announceFlags}`
      if (key === loadedKey) return
      loadedKey = key
      clips = new Map(pkg.audio.map((a) => [a.key, a.url]))
      const keep = get().docId === pkg.document.id ? get().units[get().index] : undefined
      const units = pkg.blocks.flatMap((b) => unitsFor(b, usePrefs.getState().announceFlags))
      // After a correction the text changed: stop so old audio is never played as current.
      if (get().status !== 'idle') {
        run++
        speech.cancel()
      }
      const index = keep ? Math.max(0, units.findIndex((u) => u.block_id === keep.block_id && u.sentence === keep.sentence)) : 0
      set({ docId: pkg.document.id, units, index, status: get().status === 'idle' ? 'idle' : 'paused' })
    },
    play(fromBlockId, sentence) {
      const { units, index } = get()
      let i = index
      if (fromBlockId) {
        const exact = units.findIndex((u) => u.block_id === fromBlockId && (sentence === undefined || u.sentence === sentence))
        i = exact >= 0 ? exact : Math.max(0, units.findIndex((u) => u.block_id === fromBlockId))
      }
      void speakFrom(i)
    },
    pause() {
      run++
      speech.cancel()
      set({ status: 'paused' })
    },
    toggle() {
      const { status, anchor } = get()
      if (status === 'playing') get().pause()
      else if (status === 'idle' && anchor) get().play(anchor)
      else get().play()
    },
    step(by) {
      const { units, index, status } = get()
      const i = Math.min(units.length - 1, Math.max(0, index + by))
      if (status === 'playing') void speakFrom(i)
      else set({ index: i, status: 'paused' })
    },
    stop() {
      run++
      speech.cancel()
      loadedKey = ''
      set({ status: 'idle', index: 0, problem: null })
    },
  }
})
