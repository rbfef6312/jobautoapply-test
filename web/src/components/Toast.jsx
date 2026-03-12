import { useEffect, useState } from 'react'

const TYPE_STYLES = {
  success: 'bg-emerald-600',
  error: 'bg-red-600',
  warning: 'bg-amber-600',
  info: 'bg-slate-800',
}

export function ToastHost() {
  const [toast, setToast] = useState(null)

  useEffect(() => {
    const handler = (e) => {
      const { message, type = 'info', duration = 2500 } = e.detail || {}
      if (!message) return
      setToast({ message, type })
      if (duration > 0) {
        const timer = setTimeout(() => setToast(null), duration)
        return () => clearTimeout(timer)
      }
    }
    window.addEventListener('app-toast', handler)
    return () => window.removeEventListener('app-toast', handler)
  }, [])

  if (!toast) return null

  const cls = TYPE_STYLES[toast.type] || TYPE_STYLES.info

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      <div className={`px-4 py-3 rounded-xl shadow-lg text-sm text-white ${cls}`}>
        {toast.message}
      </div>
    </div>
  )
}

