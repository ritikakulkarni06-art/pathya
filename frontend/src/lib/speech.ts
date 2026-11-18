// Speech adapter. The reader talks to this interface only, so the device voice used today
// can be swapped for prepared sentence clips from the backend without touching the UI.
import type { Lang } from '../types'

export interface VoiceInfo {
  id: string
  name: string
  lang: string
  offline: boolean
}

export interface SpeakRequest {
  text: string
  lang: Lang
  rate: number
  voiceId?: string
  /** Prepared clip for this sentence, if the chapter package has one. */
  clipUrl?: string
}

export interface SpeechAdapter {
  readonly available: boolean
  voices(): Promise<VoiceInfo[]>
  /** Resolves when the unit finishes; rejects with 'cancelled' if stopped. */
  speak(req: SpeakRequest): Promise<void>
  pause(): void
  resume(): void
  cancel(): void
}

/** Clips are named by a hash of language and sentence, so changed text never matches old audio. */
export async function clipKey(lang: Lang, text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(`${lang}|${text}`))
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16)
}

/** Use the downloaded copy of a clip when there is one, so narration keeps working offline. */
async function clipSource(url: string): Promise<string> {
  try {
    const hit = 'caches' in window ? await caches.match(url) : undefined
    if (hit) return URL.createObjectURL(await hit.blob())
  } catch {
    // fall through to the network
  }
  return url
}

const BCP: Record<Lang, string> = { en: 'en-IN', hi: 'hi-IN' }

class BrowserSpeech implements SpeechAdapter {
  private audio: HTMLAudioElement | null = null
  private rejectCurrent: ((r: unknown) => void) | null = null
  readonly available = typeof window !== 'undefined' && 'speechSynthesis' in window

  voices(): Promise<VoiceInfo[]> {
    if (!this.available) return Promise.resolve([])
    const read = () => speechSynthesis.getVoices().map((v) => ({ id: v.voiceURI, name: v.name, lang: v.lang, offline: v.localService }))
    const now = read()
    if (now.length) return Promise.resolve(now)
    return new Promise((resolve) => {
      const done = () => resolve(read())
      speechSynthesis.addEventListener('voiceschanged', done, { once: true })
      setTimeout(done, 1200)
    })
  }

  speak(req: SpeakRequest): Promise<void> {
    this.cancel()
    return new Promise((resolve, reject) => {
      this.rejectCurrent = reject
      if (req.clipUrl) {
        void clipSource(req.clipUrl).then((src) => {
          if (this.rejectCurrent !== reject) return // cancelled while the clip was being looked up
          const a = new Audio(src)
          a.playbackRate = req.rate
          const done = () => src.startsWith('blob:') && URL.revokeObjectURL(src)
          a.onended = () => { done(); resolve() }
          a.onerror = () => { done(); reject(new Error('clip_failed')) }
          this.audio = a
          void a.play().catch(reject)
        })
        return
      }
      if (!this.available) return reject(new Error('no_voice'))
      const u = new SpeechSynthesisUtterance(req.text)
      const all = speechSynthesis.getVoices()
      const chosen = all.find((v) => v.voiceURI === req.voiceId && v.lang.startsWith(req.lang))
      // No voice chosen: prefer natural-sounding voices and Indian English over the old robotic defaults.
      const score = (v: SpeechSynthesisVoice) =>
        (/natural|neural/i.test(v.name) ? 8 : 0) + (/google/i.test(v.name) ? 4 : 0) + (/online/i.test(v.name) ? 2 : 0) + (v.lang.endsWith('-IN') ? 3 : 0) - (/david|zira|mark|desktop/i.test(v.name) ? 4 : 0)
      const fallback = all.filter((v) => v.lang.startsWith(req.lang)).sort((a, b) => score(b) - score(a))[0]
      u.voice = chosen ?? fallback ?? null
      u.lang = (chosen ?? fallback)?.lang ?? BCP[req.lang]
      u.rate = req.rate
      u.onend = () => resolve()
      u.onerror = (e) => reject(new Error(e.error === 'canceled' || e.error === 'interrupted' ? 'cancelled' : e.error))
      speechSynthesis.speak(u)
    })
  }
  pause() {
    this.audio ? this.audio.pause() : this.available && speechSynthesis.pause()
  }
  resume() {
    this.audio ? void this.audio.play() : this.available && speechSynthesis.resume()
  }
  cancel() {
    this.rejectCurrent?.(new Error('cancelled'))
    this.rejectCurrent = null
    if (this.audio) {
      this.audio.pause()
      this.audio = null
    }
    if (this.available) speechSynthesis.cancel()
  }
}

export const speech: SpeechAdapter = new BrowserSpeech()

export async function hasVoiceFor(lang: Lang): Promise<boolean> {
  return (await speech.voices()).some((v) => v.lang.startsWith(lang))
}
