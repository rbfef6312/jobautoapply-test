/**
 * 将 UTC ISO 时间格式化为北京时间 (UTC+8)
 * @param {string} isoStr - ISO 时间字符串，如 "2025-03-10T12:00:00"
 * @returns {string|null} "3 月 10 日 20:00" 或 null
 */
export function formatNextRunBeijing(isoStr) {
  if (!isoStr) return null
  try {
    const utc = isoStr.endsWith('Z') ? isoStr : isoStr + 'Z'
    const d = new Date(utc)
    const fmt = new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    const parts = fmt.formatToParts(d)
    const get = (t) => parts.find((p) => p.type === t)?.value ?? ''
    const m = get('month')
    const day = get('day')
    const h = get('hour').padStart(2, '0')
    const min = get('minute').padStart(2, '0')
    if (m && day) return `${m} 月 ${day} 日 ${h}:${min}`
    return null
  } catch {
    return null
  }
}

/**
 * 将 UTC ISO 时间格式化为北京时间 (UTC+8)，用于投递时间等
 * @param {string} isoStr - ISO 时间字符串
 * @returns {string|null} "3 月 10 日 20:00" 或 null
 */
export function formatDateTimeBeijing(isoStr) {
  return formatNextRunBeijing(isoStr)
}
