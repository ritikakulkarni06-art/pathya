import { X } from 'lucide-react'
import { useNotices } from '../state/app'

/** One polite live region for the whole app: toasts that screen readers also hear. */
export function Notices() {
  const { items, dismiss } = useNotices()
  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 bottom-28 z-50 flex flex-col items-center gap-2 px-4 pointer-events-none lg:bottom-24">
      {items.map((n) => (
        <div key={n.id} className={`sheet-in pointer-events-auto flex max-w-xl items-start gap-3 rounded-card border px-4 py-3 shadow-lg ${n.tone === 'ok' ? 'bg-ok-bg text-ok-ink border-transparent' : n.tone === 'bad' ? 'bg-bad-bg text-bad-ink border-transparent' : 'bg-primary text-on-primary border-primary'}`}>
          <p className="m-0">{n.text}</p>
          <button className="-mr-1 -mt-0.5 rounded p-1" aria-label="Dismiss message" onClick={() => dismiss(n.id)}>
            <X size={16} aria-hidden />
          </button>
        </div>
      ))}
    </div>
  )
}
