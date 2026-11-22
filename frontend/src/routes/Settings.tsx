import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { useAuth } from '../state/auth'
import { Trash2 } from 'lucide-react'
import { Shell } from '../components/Shell'
import { DisplayControls, Presets, Row, SpeechControls } from '../components/PrefsControls'
import { readingVars, usePrefs } from '../state/prefs'
import { store, uid } from '../lib/db'
import { say } from '../state/app'
import { usingMock } from '../api/client'
import type { Lang, Pronunciation } from '../types'

function Section({ title, about, children }: { title: string; about: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-x-10 gap-y-4 border-t border-border py-8 first:border-0 first:pt-0 lg:grid-cols-[360px_minmax(0,1fr)]">
      <div>
        <h2 className="m-0 text-base font-medium">{title}</h2>
        <div className="mt-1 text-muted [&_p]:m-0 [&_p+p]:mt-2">{about}</div>
      </div>
      <div className="card p-5">{children}</div>
    </section>
  )
}

function Pronunciations() {
  const [list, setList] = useState<Pronunciation[]>([])
  const [term, setTerm] = useState('')
  const [spoken, setSpoken] = useState('')
  const [lang, setLang] = useState<Lang>('en')
  const load = () => store.listPronunciations().then(setList)
  useEffect(() => void load(), [])

  const add = async (e: FormEvent) => {
    e.preventDefault()
    if (!term.trim() || !spoken.trim()) return
    await store.putPronunciation({ id: uid(), term: term.trim(), spoken: spoken.trim(), lang, scope: 'all' })
    say(`“${term.trim()}” will now be spoken as “${spoken.trim()}”.`, 'ok')
    setTerm('')
    setSpoken('')
    void load()
  }
  return (
    <div className="grid gap-5">
      {list.length === 0 ? (
        <p className="m-0 rounded-control border border-dashed border-control px-3 py-2.5 text-muted">No overrides yet. Add one when the voice mispronounces a term, for example “m/s” spoken as “metres per second”.</p>
      ) : (
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">Pronunciation overrides</caption>
          <thead>
            <tr className="text-xs text-muted"><th className="py-2 font-normal" scope="col">Written</th><th className="py-2 font-normal" scope="col">Spoken as</th><th className="py-2 font-normal" scope="col">Language</th><th scope="col"><span className="sr-only">Remove</span></th></tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.id} className="border-t border-rule">
                <td className="py-2 font-medium" lang={p.lang}>{p.term}</td>
                <td className="py-2" lang={p.lang}>{p.spoken}</td>
                <td className="py-2 text-muted">{p.lang === 'hi' ? 'Hindi' : 'English'}</td>
                <td className="py-1 text-right">
                  <button className="btn btn-ghost btn-icon" aria-label={`Remove override for ${p.term}`} onClick={() => void store.deletePronunciation(p.id).then(load)}><Trash2 size={16} aria-hidden /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={add} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto_auto]">
        <Row label="Written in the book">{(id) => <input id={id} className="field" value={term} onChange={(e) => setTerm(e.target.value)} required />}</Row>
        <Row label="Say it as">{(id) => <input id={id} className="field" value={spoken} onChange={(e) => setSpoken(e.target.value)} required />}</Row>
        <Row label="Language">{(id) => (
          <select id={id} className="field" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
            <option value="en">English</option>
            <option value="hi">Hindi</option>
          </select>
        )}</Row>
        <button className="btn btn-primary" type="submit">Add</button>
      </form>
    </div>
  )
}

export default function Settings() {
  const user = useAuth((x) => x.user)
  const logout = useAuth((x) => x.logout)
  const prefs = usePrefs()
  return (
    <Shell title="Settings" lead="Set up reading and listening the way that works for you. Changes apply at once and are remembered on this device.">
      <Section
        title="Reading display"
        about={<><p>Each control works on its own. Start from a preset if you like, then change anything.</p><p>The textbook's words are never rewritten by these settings.</p></>}
      >
        <div className="grid gap-6">
          <Presets />
          <DisplayControls />
          <div>
            <h3 className="m-0 mb-2 text-xs font-normal text-muted">Preview</h3>
            <div className="reading rounded-control border border-border bg-ground p-4" style={readingVars(prefs)}>
              <p>Acceleration is the rate at which <span className="sentence" data-current={prefs.highlight}>velocity changes with time.</span></p>
              <p lang="hi" className="mt-[var(--read-para)]">बल वस्तु की विराम अवस्था या गति की अवस्था को बदल सकता है।</p>
            </div>
          </div>
        </div>
      </Section>
      <Section title="Speech" about={<p>Narration uses voices installed on this device. A voice marked “works offline” keeps reading without internet.</p>}>
        <SpeechControls />
      </Section>
      <Section title="Pronunciation" about={<p>Teach the narrator how to say a term. The spelling shown on the page stays exactly as the textbook has it.</p>}>
        <Pronunciations />
      </Section>
      <Section title="Reset" about={<p>Return every display and speech setting to its starting value. Downloads, bookmarks and pronunciations are kept.</p>}>
        <button className="btn" onClick={() => { prefs.reset(); say('Display and speech settings were reset.') }}>Reset display and speech settings</button>
      </Section>
      {user && (
        <Section title="Account" about={<p>Signing out does not remove chapters you downloaded to this device. On a shared computer, remove them under Downloads first.</p>}>
          <p className="m-0">Signed in as <strong className="break-all">{user.email}</strong></p>
          <p className="m-0 mt-2 text-sm text-muted">Signing out deletes this account's downloaded chapters, bookmarks and saved places from this device.</p>
          <button className="btn mt-3" onClick={() => void logout()}>Sign out</button>
        </Section>
      )}
      {usingMock && (
        <Section title="Sample data" about={<p>This build has no server, so the two sample chapters live in this browser. Restoring them undoes every correction, removal and upload made here.</p>}>
          <button className="btn" onClick={() => { ['pathya.mock.server.v1', 'pathya.mock.jobs.v1', 'pathya.mock.usage.v1'].forEach((k) => localStorage.removeItem(k)); say('The sample chapters are back as they first were.', 'ok') }}>Restore the sample chapters</button>
        </Section>
      )}
    </Shell>
  )
}
