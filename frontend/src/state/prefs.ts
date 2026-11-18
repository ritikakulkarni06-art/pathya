import type React from 'react'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'contrast'
export type ReadFont = 'hyperlegible' | 'sans' | 'serif'

export interface Prefs {
  theme: Theme
  font: ReadFont
  /** Reading text size in px. Independent of browser zoom. */
  size: number
  leading: number
  /** Letter spacing in em. */
  tracking: number
  /** Word spacing in em. */
  wordSpacing: number
  paragraphGap: number
  measure: 'narrow' | 'medium' | 'wide'
  focusMode: boolean
  highlight: boolean
  reduceMotion: boolean
  rate: number
  voiceEn: string
  voiceHi: string
  announceFlags: boolean
}

export const DEFAULT_PREFS: Prefs = {
  theme: 'light',
  font: 'hyperlegible',
  size: 18,
  leading: 1.7,
  tracking: 0,
  wordSpacing: 0,
  paragraphGap: 0.6,
  measure: 'medium',
  focusMode: false,
  highlight: true,
  reduceMotion: false,
  rate: 1,
  voiceEn: '',
  voiceHi: '',
  announceFlags: true,
}

// Named starting points. They only set values; nothing is locked and no diagnosis is asked for.
export const PRESETS: { id: string; name: string; note: string; values: Partial<Prefs> }[] = [
  { id: 'default', name: 'Standard', note: 'Medium text on a light page.', values: DEFAULT_PREFS },
  { id: 'large', name: 'Large and clear', note: 'Bigger text, dark page, wide lines.', values: { size: 26, leading: 1.6, theme: 'dark', measure: 'wide', font: 'hyperlegible' } },
  { id: 'spaced', name: 'Spaced and focused', note: 'More space between letters, words and lines; one paragraph in focus.', values: { size: 20, leading: 2, tracking: 0.06, wordSpacing: 0.2, paragraphGap: 1.2, measure: 'narrow', focusMode: true } },
  { id: 'listen', name: 'Listening first', note: 'Screen-reader friendly: no visual highlight, flags spoken aloud.', values: { highlight: false, focusMode: false, announceFlags: true } },
]

interface PrefsStore extends Prefs {
  set: (p: Partial<Prefs>) => void
  reset: () => void
}

export const usePrefs = create<PrefsStore>()(
  persist(
    (set) => ({
      ...DEFAULT_PREFS,
      set: (p) => set(p),
      reset: () => set(DEFAULT_PREFS),
    }),
    { name: 'pathya.prefs.v1' },
  ),
)

const FONTS: Record<ReadFont, string> = {
  hyperlegible: "'Atkinson Hyperlegible'",
  sans: "'Space Grotesk Variable'",
  serif: "Georgia, 'Times New Roman'",
}
const MEASURE = { narrow: '32rem', medium: '42rem', wide: '56rem' }

/** CSS variables for the reading surface. */
export function readingVars(p: Prefs): React.CSSProperties {
  return {
    '--read-font': FONTS[p.font],
    '--read-size': `${p.size / 16}rem`,
    '--read-leading': String(p.leading),
    '--read-tracking': `${p.tracking}em`,
    '--read-word': `${p.wordSpacing}em`,
    '--read-para': `${p.paragraphGap}em`,
    '--read-measure': MEASURE[p.measure],
  } as React.CSSProperties
}

export function applyRootPrefs(p: Pick<Prefs, 'theme' | 'reduceMotion'>) {
  const r = document.documentElement
  r.dataset.theme = p.theme
  r.dataset.motion = p.reduceMotion ? 'reduce' : 'auto'
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', p.theme === 'light' ? '#f4f1ea' : p.theme === 'dark' ? '#15140f' : '#000000')
}
