import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Download, Loader2, Trash2 } from 'lucide-react'
import { Shell } from '../components/Shell'
import { useLibrary } from '../components/useLibrary'
import { formatBytes } from '../lib/db'

const date = (iso: string) => new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export default function Downloads() {
  const { rows, online, busy, download, remove } = useLibrary()
  const [quota, setQuota] = useState<{ usage: number; quota: number } | null>(null)
  const saved = rows?.filter((r) => r.downloaded) ?? []
  const rest = rows?.filter((r) => !r.downloaded) ?? []
  const total = saved.reduce((n, r) => n + r.downloaded!.bytes, 0)

  useEffect(() => {
    void navigator.storage?.estimate?.().then((e) => setQuota({ usage: e.usage ?? 0, quota: e.quota ?? 0 }))
  }, [rows])

  return (
    <Shell
      title="Downloads"
      lead={!rows ? 'Checking this device…' : saved.length ? `${saved.length} ${saved.length === 1 ? 'chapter' : 'chapters'} on this device, ${formatBytes(total)} of text and audio. They open without internet.` : 'Nothing is downloaded yet. Downloaded chapters open without internet.'}
    >
      <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section aria-labelledby="dl-saved" className="card">
          <h2 id="dl-saved" className="m-0 border-b border-rule px-5 py-3 text-base font-medium">On this device</h2>
          {rows && !saved.length && <p className="m-0 px-5 py-6 text-muted">No chapters downloaded. Choose one {rest.length ? 'from “Available to download”' : 'from the library when you are online'}.</p>}
          <ul className="m-0 list-none p-0">
            {saved.map(({ doc, downloaded, updateAvailable }) => (
              <li key={doc.id} className="border-b border-rule px-5 py-4 last:border-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="m-0 text-base font-bold" lang={doc.languages[0]}><Link to={`/read/${doc.id}`} className="hover:underline">{doc.title}</Link></h3>
                    <p className="m-0 mt-0.5 text-muted">Revision {downloaded!.revision} · {formatBytes(downloaded!.bytes)} · saved {date(downloaded!.downloaded_at)}</p>
                  </div>
                  <div className="flex gap-2">
                    {updateAvailable && (
                      <button className="btn" disabled={busy === doc.id} onClick={() => void download(doc.id)}>
                        {busy === doc.id ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Download size={16} aria-hidden />} Update to revision {doc.current_revision}
                      </button>
                    )}
                    <button className="btn" onClick={() => void remove(doc.id)} aria-label={`Remove download of ${doc.title}`}><Trash2 size={16} aria-hidden /> Remove</button>
                  </div>
                </div>
                <dl className="m-0 mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted">
                  <dt>Text and navigation</dt><dd className="m-0 text-ink">Saved, {downloaded!.blocks.length} passages on {downloaded!.pages.length} pages</dd>
                  <dt>Audio</dt><dd className="m-0 text-ink">{downloaded!.audio.length ? `${downloaded!.audio.length - downloaded!.missing_assets.length} of ${downloaded!.audio.length} sentence clips saved${downloaded!.audio_voice ? ` (voice: ${downloaded!.audio_voice})` : ''}. Sentences without a clip use a voice installed on this device.` : 'No prepared audio in this chapter. Narration uses a voice installed on this device.'}</dd>
                  <dt>Assistant</dt><dd className="m-0 text-ink">Needs internet. Search works offline.</dd>
                </dl>
                {downloaded!.missing_assets.length > 0 && <p className="pill pill-bad mt-3">{downloaded!.missing_assets.length} files missing. Update the download when online.</p>}
              </li>
            ))}
          </ul>
        </section>

        <div className="grid gap-3">
          <section aria-labelledby="dl-storage" className="card px-5 py-4">
            <h2 id="dl-storage" className="m-0 text-base font-medium">Storage</h2>
            {quota && quota.quota > 0 ? (
              <>
                <p className="m-0 mt-2 text-2xl">{formatBytes(quota.usage)}</p>
                <p className="m-0 text-muted">used by Pathya on this device, of {formatBytes(quota.quota)} the browser allows</p>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-raised" role="img" aria-label={`${((quota.usage / quota.quota) * 100).toFixed(1)}% of allowed storage used`}>
                  <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(quota.usage ? 0.5 : 0, (quota.usage / quota.quota) * 100)}%` }} />
                </div>
              </>
            ) : <p className="m-0 mt-2 text-muted">This browser does not report storage use.</p>}
            <p className="m-0 mt-3 text-xs text-muted">Browsers can clear saved data when the device runs low on space. If a chapter disappears, download it again.</p>
          </section>
          {rest.length > 0 && (
            <section aria-labelledby="dl-rest" className="card">
              <h2 id="dl-rest" className="m-0 border-b border-rule px-5 py-3 text-base font-medium">Available to download</h2>
              <ul className="m-0 list-none p-0">
                {rest.map(({ doc }) => (
                  <li key={doc.id} className="flex items-center justify-between gap-3 border-b border-rule px-5 py-3 last:border-0">
                    <span className="min-w-0 truncate font-medium" lang={doc.languages[0]}>{doc.title}</span>
                    <button className="btn" disabled={!online || busy === doc.id} onClick={() => void download(doc.id)} aria-label={`Download ${doc.title}`}>
                      {busy === doc.id ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Download size={16} aria-hidden />} Download
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </Shell>
  )
}
