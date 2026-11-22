import { useEffect } from 'react'
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react'
import { useNarration } from '../../state/narration'
import { usePrefs } from '../../state/prefs'
import { speech } from '../../lib/speech'

const RATES = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]

/** Narration controls. Shortcuts use Alt+Shift so they do not collide with screen-reader keys. */
export function Player() {
  const { status, index, units, problem, toggle, step } = useNarration()
  const rate = usePrefs((p) => p.rate)
  const setPrefs = usePrefs((p) => p.set)
  const unit = units[index]
  const playing = status === 'playing'

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || !e.shiftKey) return
      if (e.code === 'KeyP') toggle()
      else if (e.code === 'ArrowRight') step(1)
      else if (e.code === 'ArrowLeft') step(-1)
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle, step])

  return (
    <section aria-label="Narration" className="mx-auto flex w-full max-w-[1440px] items-center gap-2 px-3 py-2 sm:gap-3 sm:px-6">
      <button className="btn btn-ghost btn-icon" aria-label="Previous sentence" aria-keyshortcuts="Alt+Shift+ArrowLeft" onClick={() => step(-1)} disabled={!units.length || index === 0}><SkipBack size={18} aria-hidden /></button>
      <button className="btn btn-primary min-w-28" aria-keyshortcuts="Alt+Shift+P" onClick={toggle} disabled={!units.length || !speech.available}>
        {playing ? <Pause size={18} aria-hidden /> : <Play size={18} aria-hidden />} {playing ? 'Pause' : status === 'paused' ? 'Resume' : 'Listen'}
      </button>
      <button className="btn btn-ghost btn-icon" aria-label="Next sentence" aria-keyshortcuts="Alt+Shift+ArrowRight" onClick={() => step(1)} disabled={!units.length || index >= units.length - 1}><SkipForward size={18} aria-hidden /></button>
      <span className="wave hidden sm:flex" data-on={playing} aria-hidden><i /><i /><i /><i /></span>
      <div className="min-w-0 flex-1">
        {problem ? (
          <p className="m-0 line-clamp-2 text-warn-ink" role="alert">{problem}</p>
        ) : !speech.available ? (
          <p className="m-0 text-muted">This browser cannot speak text aloud. The chapter is still fully readable.</p>
        ) : (
          <>
            <p className="m-0 hidden truncate sm:block" lang={unit?.lang} aria-hidden>{status === 'idle' ? 'Narration is ready' : unit?.text}</p>
            <p className="m-0 text-xs text-muted">{units.length ? <><span className="hidden sm:inline">Sentence </span>{index + 1} of {units.length}</> : 'Nothing to read'}</p>
          </>
        )}
      </div>
      <label htmlFor="rate" className="sr-only">Speaking speed</label>
      <select id="rate" className="field w-auto flex-none" value={RATES.includes(rate) ? rate : ''} onChange={(e) => setPrefs({ rate: Number(e.target.value) })}>
        {!RATES.includes(rate) && <option value="">{rate.toFixed(1)}×</option>}
        {RATES.map((r) => <option key={r} value={r}>{r}×</option>)}
      </select>
    </section>
  )
}
