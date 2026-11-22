import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { Check, FileUp, Loader2, RotateCcw, X } from 'lucide-react'
import { Shell } from '../components/Shell'
import { api, usingMock, type Job, type JobState } from '../api/client'
import { say, useOnline } from '../state/app'
import { formatBytes } from '../lib/db'
import type { Lang } from '../types'

const MAX_BYTES = 25 * 1024 * 1024
const STOPPED: JobState[] = ['ready', 'failed', 'cancelled', 'review_required']
const STATE_WORDS: Record<JobState, string> = { queued: 'Waiting', validating: 'Checking the file', extracting: 'Reading pages', building: 'Preparing audio', review_required: 'Ready, with passages to review', ready: 'Ready', failed: 'Stopped', cancelled: 'Cancelled' }
const STEPS: { state: JobState; label: string; doing: string }[] = [
  { state: 'queued', label: 'Uploaded', doing: 'Waiting for its turn' },
  { state: 'validating', label: 'File checked', doing: 'Checking the file' },
  { state: 'extracting', label: 'Pages read', doing: 'Reading the pages' },
  { state: 'building', label: 'Audio and search prepared', doing: 'Preparing audio and search' },
  { state: 'ready', label: 'Ready to read', doing: 'Ready to read' },
]

/** Look at the first bytes, not the file name, to decide what the file really is. */
async function sniff(file: File): Promise<'pdf' | 'jpeg' | 'png' | null> {
  const b = new Uint8Array(await file.slice(0, 8).arrayBuffer())
  if (b[0] === 0x25 && b[1] === 0x50 && b[2] === 0x44 && b[3] === 0x46) return 'pdf'
  if (b[0] === 0xff && b[1] === 0xd8) return 'jpeg'
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return 'png'
  return null
}

export default function AddChapter() {
  const online = useOnline()
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [langs, setLangs] = useState<Lang[]>(['en'])
  const [rights, setRights] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [job, setJob] = useState<Job | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const status = useRef<HTMLHeadingElement>(null)
  const errorBox = useRef<HTMLParagraphElement>(null)

  // Follow the job until it stops.
  const jobId = job?.id
  const running = job && !STOPPED.includes(job.state)
  useEffect(() => {
    if (!jobId || !running) return
    const t = setInterval(() => void api.getJob(jobId).then(setJob).catch(() => {}), 700)
    return () => clearInterval(t)
  }, [jobId, running])

  // Earlier uploads, so a student can come back to one, cancel it or try it again.
  const loadJobs = () => void api.listJobs().then(setJobs).catch(() => {})
  const anyRunning = jobs.some((j) => !STOPPED.includes(j.state))
  useEffect(loadJobs, [online, job?.state])
  useEffect(() => {
    if (!anyRunning) return
    const t = setInterval(loadJobs, 1000)
    return () => clearInterval(t)
  }, [anyRunning])
  const act = async (id: string, what: 'cancel' | 'retry') => {
    try {
      const next = what === 'cancel' ? await api.cancelJob(id) : await api.retryJob(id)
      if (job?.id === id) setJob(next)
      say(what === 'cancel' ? 'Upload cancelled. Nothing was stored.' : 'Trying again. Preparing the chapter.')
      loadJobs()
    } catch {
      say('That did not work. Check the connection and try again.', 'bad')
    }
  }

  const fail = (message: string) => {
    setError(message)
    setTimeout(() => errorBox.current?.focus())
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!file) return fail('Choose a PDF or a photo of the page first.')
    if (file.size > MAX_BYTES) return fail(`This file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_BYTES)}. Split the chapter or lower the scan quality.`)
    if (!(await sniff(file))) return fail('This does not look like a PDF, JPEG or PNG file, so it was not uploaded. Password-protected and other formats are not supported.')
    if (!langs.length) return fail('Choose at least one language used in the chapter.')
    if (!rights) return fail('Confirm that you are allowed to use this chapter before uploading.')
    setSending(true)
    try {
      const { job_id } = await api.createDocument({ file, title: title.trim() || file.name, languages: langs, rights_note: 'Uploaded by the student, who confirmed permission to use it for study.' })
      setJob(await api.getJob(job_id))
      say('Upload finished. Preparing the chapter.')
      setTimeout(() => status.current?.focus())
    } catch {
      fail(navigator.onLine ? 'The upload did not finish. Check the connection and try again.' : 'You are offline. Uploading needs internet.')
    }
    setSending(false)
  }

  const stepIndex = job ? STEPS.findIndex((s) => s.state === job.state) : -1
  const reached = job?.state === 'review_required' ? 3 : job?.state === 'failed' || job?.state === 'cancelled' ? STEPS.findIndex((s) => s.state === job.failed_at) : stepIndex
  const line = !job
    ? ''
    : job.state === 'extracting'
      ? `Reading page ${Math.min(job.pages_done + 1, job.pages_total)} of ${job.pages_total}`
      : job.state === 'failed'
        ? 'Preparation stopped'
        : job.state === 'cancelled'
        ? 'Upload cancelled'
        : job.state === 'review_required'
          ? 'Prepared, with passages to review'
          : STEPS[stepIndex]?.doing

  return (
    <Shell title="Add a chapter" lead="Upload a chapter you are allowed to use. Pathya reads the pages, then shows you anything it was unsure about.">
      <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        {!job ? (
          <form onSubmit={submit} className="card grid gap-5 p-5" noValidate aria-describedby={error ? 'add-error' : undefined}>
            {!online && <p className="pill pill-warn m-0 justify-self-start">Offline. Uploading needs internet; your downloaded chapters still open.</p>}
            {error && <p id="add-error" ref={errorBox} tabIndex={-1} role="alert" className="m-0 rounded-control bg-bad-bg px-3 py-2.5 text-bad-ink">{error}</p>}
            <div className="grid gap-1.5">
              <label htmlFor="add-file" className="font-medium">Chapter file</label>
              <input id="add-file" type="file" accept="application/pdf,image/jpeg,image/png" className="field file:mr-3 file:rounded file:border-0 file:bg-raised file:px-3 file:py-1.5 file:font-medium file:text-ink" aria-describedby="add-file-help"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null
                  setFile(f)
                  if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' '))
                }} />
              <p id="add-file-help" className="m-0 text-xs text-muted">PDF, JPEG or PNG, up to {formatBytes(MAX_BYTES)}. For photos: flat page, good light, all four corners visible.{file ? ` Chosen: ${file.name}, ${formatBytes(file.size)}.` : ''}</p>
            </div>
            <div className="grid gap-1.5">
              <label htmlFor="add-title" className="font-medium">Chapter title</label>
              <input id="add-title" className="field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="For example: Motion in a straight line" />
            </div>
            <fieldset className="m-0 border-0 p-0">
              <legend className="mb-1.5 p-0 font-medium">Languages in the chapter</legend>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {([['en', 'English'], ['hi', 'Hindi']] as [Lang, string][]).map(([code, name]) => (
                  <label key={code} className="flex min-h-9 items-center gap-2">
                    <input type="checkbox" className="size-5 accent-[var(--primary)]" checked={langs.includes(code)} onChange={(e) => setLangs((l) => (e.target.checked ? [...l, code] : l.filter((x) => x !== code)))} /> {name}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="flex items-start gap-2.5">
              <input type="checkbox" className="mt-0.5 size-5 flex-none accent-[var(--primary)]" checked={rights} onChange={(e) => setRights(e.target.checked)} />
              <span>I am allowed to use this chapter for my own study. <span className="text-muted">It stays private to you and anyone you ask to review it.</span></span>
            </label>
            <div>
              <button className="btn btn-primary" type="submit" disabled={!online || sending}>
                {sending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <FileUp size={16} aria-hidden />} {sending ? 'Uploading…' : 'Upload and prepare'}
              </button>
            </div>
          </form>
        ) : (
          <section className="card p-5" aria-labelledby="job-title">
            <h2 id="job-title" ref={status} tabIndex={-1} className="m-0 text-xl font-bold outline-none">{job.title || title || file?.name}</h2>
            <p className="m-0 mt-1 text-base" role="status" aria-live="polite">{line}</p>
            {job.state === 'extracting' && (
              <progress className="mt-3 h-2 w-full accent-[var(--primary)]" max={job.pages_total} value={job.pages_done} aria-label="Pages read">{job.pages_done} of {job.pages_total}</progress>
            )}
            <ol className="m-0 mt-4 grid list-none gap-0 p-0">
              {STEPS.map((s, i) => {
                const done = job.state === 'ready' ? true : i < reached || (job.state === 'review_required' && i <= 3)
                const now = i === reached && running
                return (
                  <li key={s.state} aria-current={now ? 'step' : undefined} className={`flex min-h-10 items-center gap-3 border-b border-rule last:border-0 ${done || now ? '' : 'text-muted'}`}>
                    <span className="grid size-5 flex-none place-items-center" aria-hidden>
                      {done ? <Check size={16} /> : now ? <Loader2 size={16} className="animate-spin" /> : <span className="size-1.5 rounded-full bg-control" />}
                    </span>
                    <span className={now ? 'font-medium' : ''}>{now ? s.doing : s.label}</span>
                    <span className="sr-only">{done ? ', done' : now ? ', in progress' : ', not started'}</span>
                  </li>
                )
              })}
            </ol>
            {job.state === 'failed' && (
              <div className="mt-4 rounded-control bg-bad-bg px-3 py-2.5 text-bad-ink" role="alert">
                <p className="m-0 font-medium">This file could not be prepared.</p>
                <p className="m-0 mt-1">{job.reason}</p>
              </div>
            )}
            {job.state === 'cancelled' && <p className="m-0 mt-4 rounded-control bg-raised px-3 py-2.5">{job.reason}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              {(job.state === 'ready' || job.state === 'review_required') && <Link to={`/read/${job.document_id}`} className="btn btn-primary">{job.state === 'ready' ? 'Open the chapter' : 'Open and review flagged passages'}</Link>}
              {running && <button className="btn" onClick={() => void act(job.id, 'cancel')}><X size={16} aria-hidden /> Cancel upload</button>}
              {(job.state === 'failed' || job.state === 'cancelled') && <button className="btn btn-primary" disabled={!online} onClick={() => void act(job.id, 'retry')}><RotateCcw size={16} aria-hidden /> Try again</button>}
              {!running && <button className="btn" onClick={() => { setJob(null); setFile(null); setTitle(''); setRights(false) }}>Add another file</button>}
              <Link to="/" className="btn">Back to library</Link>
            </div>
          </section>
        )}
        <div className="grid gap-3">
        {jobs.length > 0 && (
          <section aria-labelledby="add-jobs" className="card">
            <h2 id="add-jobs" className="m-0 border-b border-rule px-5 py-3 text-base font-medium">Your uploads</h2>
            <ul className="m-0 list-none p-0">
              {jobs.map((j) => {
                const live = !STOPPED.includes(j.state)
                return (
                  <li key={j.id} className="border-b border-rule px-5 py-3 last:border-0">
                    <p className="m-0 truncate font-medium">{j.title}</p>
                    <p className="m-0 flex items-center gap-1.5 text-xs text-muted">
                      {live && <Loader2 size={12} className="animate-spin" aria-hidden />}
                      {STATE_WORDS[j.state]}{j.state === 'extracting' ? `, page ${Math.min(j.pages_done + 1, j.pages_total)} of ${j.pages_total}` : ''}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {job?.id !== j.id && <button className="btn" onClick={() => setJob(j)} aria-label={`Show progress of ${j.title}`}>Show</button>}
                      {live && <button className="btn" onClick={() => void act(j.id, 'cancel')} aria-label={`Cancel upload of ${j.title}`}>Cancel</button>}
                      {(j.state === 'failed' || j.state === 'cancelled') && <button className="btn" disabled={!online} onClick={() => void act(j.id, 'retry')} aria-label={`Try ${j.title} again`}>Try again</button>}
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        )}
        <aside aria-labelledby="add-what" className="card px-5 py-4">
          <h2 id="add-what" className="m-0 text-base font-medium">What happens to the file</h2>
          <ul className="m-0 mt-2 grid list-disc gap-1.5 pl-5 text-muted">
            <li>The pages are read on the preparation server, one at a time.</li>
            <li>Anything the scanner was unsure about is flagged for you or a helper to check.</li>
            <li>A page that cannot be read is reported honestly. Pathya does not guess.</li>
            <li>You can remove the chapter and everything made from it later.</li>
          </ul>
          {usingMock && <p className="m-0 mt-3 text-xs text-muted">Sample build: no preparation server is connected, so uploads are checked and then stop.</p>}
        </aside>
        </div>
      </div>
    </Shell>
  )
}
