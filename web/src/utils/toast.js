export function showToast(message, type = 'info', duration = 2500) {
  if (!message || typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent('app-toast', {
      detail: { message, type, duration },
    }),
  )
}

