import { useLiveData } from '../hooks/useLiveData'

const COLORS = { success: '#10b981', info: '#6366f1', danger: '#ef4444' }

export default function Toasts() {
  const { toasts, dismissToast } = useLiveData()
  return (
    <div className="fixed right-4 bottom-4 z-50 space-y-2 w-96">
      {toasts.map((t) => (
        <button key={t.id} onClick={() => dismissToast(t.id)}
          className="glass w-full text-left px-4 py-3 text-sm animate-slide-in border-l-4" style={{ borderLeftColor: COLORS[t.kind] }}>
          {t.text}
        </button>
      ))}
    </div>
  )
}
