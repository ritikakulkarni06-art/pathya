import { useEffect, useId, useState, type ReactNode } from 'react'
import { PRESETS, usePrefs, type Prefs } from '../state/prefs'
import { speech, type VoiceInfo } from '../lib/speech'

export function Row({ label, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId()
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="font-medium">{label}</label>
      {children(id)}
      {hint && <p className="m-0 text-xs text-muted">{hint}</p>}
    </div>
  )
}

function Range({ label, k, min, max, step, format }: { label: string; k: keyof Prefs; min: number; max: number; step: number; format: (v: number) => string }) {
  const value = usePrefs((p) => p[k]) as number
  const set = usePrefs((p) => p.set)
  return (
    <Row label={label}>
      {(id) => (
        <div className="flex items-center gap-3">
          <input id={id} type="range" min={min} max={max} step={step} value={value} aria-valuetext={format(value)} onChange={(e) => set({ [k]: Number(e.target.value) })} />
          <output htmlFor={id} className="w-20 flex-none text-right text-muted">{format(value)}</output>
        </div>
      )}
    </Row>
  )
}

export function Toggle({ label, hint, k }: { label: string; hint?: string; k: keyof Prefs }) {
  const value = usePrefs((p) => p[k]) as boolean
  const set = usePrefs((p) => p.set)
  const id = useId()
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <span id={id} className="font-medium">{label}</span>
        {hint && <p className="m-0 text-xs text-muted">{hint}</p>}
      </div>
      <button type="button" role="switch" aria-checked={value} aria-labelledby={id} className="switch" onClick={() => set({ [k]: !value })} />
    </div>
  )
}

function Choice<T extends string>({ label, k, options }: { label: string; k: keyof Prefs; options: { value: T; label: string }[] }) {
  const value = usePrefs((p) => p[k]) as string
  const set = usePrefs((p) => p.set)
  return (
    <fieldset className="m-0 grid gap-1.5 border-0 p-0">
      <legend className="mb-1.5 p-0 font-medium">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <label key={o.value} className={`btn has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-[var(--focus)] ${value === o.value ? 'btn-primary' : ''}`}>
            <input type="radio" className="sr-only" name={k} value={o.value} checked={value === o.value} onChange={() => set({ [k]: o.value })} />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function Presets() {
  const set = usePrefs((p) => p.set)
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {PRESETS.map((p) => (
        <button key={p.id} type="button" className="card px-3 py-2.5 text-left hover:bg-raised" onClick={() => set(p.values)}>
          <span className="block font-medium">{p.name}</span>
          <span className="block text-xs text-muted">{p.note}</span>
        </button>
      ))}
    </div>
  )
}

/** Text, spacing, contrast and focus. Every control is independent of the others. */
export function DisplayControls() {
  return (
    <div className="grid gap-5">
      <Choice label="Page colours" k="theme" options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }, { value: 'contrast', label: 'High contrast' }]} />
      <Range label="Text size" k="size" min={14} max={44} step={1} format={(v) => `${v} px`} />
      <Choice label="Typeface" k="font" options={[{ value: 'hyperlegible', label: 'Hyperlegible' }, { value: 'sans', label: 'Grotesk' }, { value: 'serif', label: 'Serif' }]} />
      <Range label="Line spacing" k="leading" min={1.2} max={2.6} step={0.1} format={(v) => `${v.toFixed(1)} lines`} />
      <Range label="Letter spacing" k="tracking" min={0} max={0.2} step={0.01} format={(v) => `${Math.round(v * 100)}%`} />
      <Range label="Word spacing" k="wordSpacing" min={0} max={0.6} step={0.02} format={(v) => `${Math.round(v * 100)}%`} />
      <Range label="Paragraph spacing" k="paragraphGap" min={0.2} max={2.4} step={0.1} format={(v) => `${v.toFixed(1)} em`} />
      <Choice label="Line length" k="measure" options={[{ value: 'narrow', label: 'Short' }, { value: 'medium', label: 'Medium' }, { value: 'wide', label: 'Long' }]} />
      <Toggle label="Focus on one passage" hint="While listening, passages other than the current one are dimmed." k="focusMode" />
      <Toggle label="Highlight the sentence being read" k="highlight" />
      <Toggle label="Reduce motion" hint="Turns off panel and scroll animation." k="reduceMotion" />
    </div>
  )
}

export function SpeechControls() {
  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const prefs = usePrefs()
  useEffect(() => {
    void speech.voices().then(setVoices)
  }, [])
  const pick = (lang: 'en' | 'hi', k: 'voiceEn' | 'voiceHi', label: string) => {
    const list = voices.filter((v) => v.lang.startsWith(lang))
    return (
      <Row label={label} hint={list.length ? undefined : `No ${lang === 'hi' ? 'Hindi' : 'English'} voice is installed on this device. Add one in your system's speech settings.`}>
        {(id) => (
          <select id={id} className="field" value={prefs[k]} disabled={!list.length} onChange={(e) => prefs.set({ [k]: e.target.value })}>
            <option value="">{list.length ? 'Device default' : 'Not available'}</option>
            {list.map((v) => (
              <option key={v.id} value={v.id}>{v.name}{v.offline ? ' (works offline)' : ' (needs internet)'}</option>
            ))}
          </select>
        )}
      </Row>
    )
  }
  return (
    <div className="grid gap-5">
      <Range label="Speaking speed" k="rate" min={0.5} max={2} step={0.1} format={(v) => `${v.toFixed(1)}×`} />
      {pick('en', 'voiceEn', 'English voice')}
      {pick('hi', 'voiceHi', 'Hindi voice')}
      <Toggle label="Say when a passage is flagged" hint="Narration pauses to tell you a passage is waiting for review before reading it." k="announceFlags" />
      <div>
        <button type="button" className="btn" disabled={!speech.available} onClick={() => void speech.speak({ text: 'This is how the narration sounds at this speed.', lang: 'en', rate: prefs.rate, voiceId: prefs.voiceEn }).catch(() => {})}>
          Play a sample
        </button>
      </div>
    </div>
  )
}
