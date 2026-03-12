import { useState, useEffect, useMemo, useRef } from 'react'
import { api } from '../api'
import { PageLoading } from '../components/PageLoading'
import { showToast } from '../utils/toast'

const TABS = [
  { id: 'all', label: '全部' },
  { id: 'ops', label: '操作记录' },
  { id: 'error', label: '错误' },
  { id: 'auto', label: '自动投递' },
  { id: 'manual', label: '手动投递' },
]

const TIME_RANGES = [
  { id: 'all', label: '全部', mins: null },
  { id: '10m', label: '10分钟', mins: 10 },
  { id: '1h', label: '1小时', mins: 60 },
  { id: '24h', label: '24小时', mins: 24 * 60 },
]

function parseLogTime(line) {
  const m = line.match(/^\[(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\]/)
  if (!m) return null
  const [, y, mo, d, h, mi, s] = m.map(Number)
  return new Date(y, mo - 1, d, h, mi, s).getTime()
}

export default function Logs() {
  const [logs, setLogs] = useState([])
  const [operations, setOperations] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('all')
  const [timeRange, setTimeRange] = useState('all')
  const [keyword, setKeyword] = useState('')
  const containerRef = useRef(null)
  const [autoFollow, setAutoFollow] = useState(true)

  const refresh = () => {
    setLoading(true)
    api
      .logs(500, true)
      .then((r) => {
        setLogs(r.logs || [])
        setOperations(r.operations || [])
      })
      .catch(() => {
        setLogs([])
        setOperations([])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  // 监听滚动，用户上滑较多时关闭自动跟随；回到底部时重新开启
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const handler = () => {
      const { scrollTop, scrollHeight, clientHeight } = el
      const distanceToBottom = scrollHeight - (scrollTop + clientHeight)
      if (distanceToBottom < 80) setAutoFollow(true)
      else setAutoFollow(false)
    }
    el.addEventListener('scroll', handler)
    return () => el.removeEventListener('scroll', handler)
  }, [])

  const viewLogs = useMemo(() => {
    if (tab === 'ops') return []
    const now = Date.now()
    const range = TIME_RANGES.find((r) => r.id === timeRange)
    const since = range?.mins ? now - range.mins * 60 * 1000 : 0

    let result = logs.filter((line) => {
      if (since > 0) {
        const t = parseLogTime(line)
        if (!t || t < since) return false
      }
      if (tab === 'error') {
        const lower = line.toLowerCase()
        return lower.includes('error') || lower.includes('失败') || lower.includes('异常') || lower.includes('exception') || lower.includes('[排查]') || lower.includes('[调试]')
      }
      if (tab === 'auto') return line.includes('自动投递')
      if (tab === 'manual') return line.includes('手动投递')
      return true
    })
    if (keyword.trim()) {
      const kw = keyword.trim().toLowerCase()
      result = result.filter((l) => l.toLowerCase().includes(kw))
    }
    return result
  }, [logs, tab, timeRange, keyword])

  const viewOps = useMemo(() => {
    if (tab !== 'ops') return []
    let list = operations
    const range = TIME_RANGES.find((r) => r.id === timeRange)
    if (range?.mins) {
      const since = Date.now() - range.mins * 60 * 1000
      list = list.filter((o) => {
        try {
          const t = new Date(o.ts).getTime()
          return t >= since
        } catch { return true }
      })
    }
    if (keyword.trim()) {
      const kw = keyword.trim().toLowerCase()
      list = list.filter((o) =>
        (o.action || '').toLowerCase().includes(kw) ||
        (o.detail || '').toLowerCase().includes(kw) ||
        (o.source || '').toLowerCase().includes(kw)
      )
    }
    return list
  }, [operations, tab, timeRange, keyword])

  // 日志更新时，如开启自动跟随则滚动到底部
  useEffect(() => {
    const el = containerRef.current
    if (!el || !autoFollow) return
    el.scrollTop = el.scrollHeight
  }, [viewLogs, viewOps, autoFollow])

  const handleCopy = () => {
    const text = tab === 'ops'
      ? viewOps.map((o) => `[${o.ts}] ${o.source} | ${o.action} | ${o.detail || ''}`).join('\n')
      : viewLogs.join('\n')
    if (!text) return
    try {
      navigator.clipboard.writeText(text)
      showToast('已复制到剪贴板', 'success')
    } catch {
      showToast('复制失败', 'error')
    }
  }

  const handleExport = () => {
    const text = tab === 'ops'
      ? viewOps.map((o) => `[${o.ts}] ${o.source} | ${o.action} | ${o.detail || ''}`).join('\n')
      : viewLogs.join('\n')
    if (!text) return
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `jobsdb-logs-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
    showToast('已导出', 'success')
  }

  const isErrorLine = (line) => {
    const lower = line.toLowerCase()
    return lower.includes('error') || lower.includes('失败') || lower.includes('异常') || lower.includes('exception')
  }

  if (loading && logs.length === 0) return <PageLoading />

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">日志</h1>
        <p className="text-slate-600 dark:text-slate-200 mt-1">投递任务的运行日志</p>
        <div className="flex flex-wrap items-center gap-3 mt-4">
          <div className="glass-subtle flex rounded-lg overflow-hidden">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-2 text-sm font-medium ${
                  tab === t.id
                    ? 'bg-brand-500/90 text-white'
                    : 'bg-transparent text-slate-700 hover:bg-white/50'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-900/40 text-slate-800 dark:text-slate-100 text-sm"
          >
            {TIME_RANGES.map((r) => (
              <option key={r.id} value={r.id}>{r.label}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="关键词"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white/70 dark:bg-slate-900/40 text-slate-800 dark:text-slate-100 text-sm w-28"
          />
          <button
            onClick={refresh}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-100 hover:bg-white/60 dark:hover:bg-white/10 text-sm"
          >
            刷新
          </button>
          <button
            onClick={handleCopy}
            disabled={tab === 'ops' ? !viewOps.length : !viewLogs.length}
            className="px-3 py-2 rounded-lg border border-brand-400 text-brand-600 dark:text-brand-200 hover:bg-brand-50 dark:hover:bg-brand-500/10 disabled:opacity-40 text-sm"
          >
            复制
          </button>
          <button
            onClick={handleExport}
            disabled={tab === 'ops' ? !viewOps.length : !viewLogs.length}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-100 hover:bg-white/60 dark:hover:bg-white/10 text-sm"
          >
            导出 .txt
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="glass-card bg-slate-900/80 dark:bg-slate-950/80 font-mono text-sm text-slate-200 overflow-x-auto max-h-[70vh] overflow-y-auto"
      >
        {tab === 'ops' ? (
          viewOps.length === 0 ? (
            <p className="text-slate-500">暂无操作记录</p>
          ) : (
            viewOps.map((o, i) => (
              <div key={i} className={`py-1 border-b border-slate-700/50 last:border-0 ${o.level === 'error' ? 'text-red-400' : ''}`}>
                <span className="text-slate-500">[{o.ts}]</span>{' '}
                <span className="text-amber-400">{o.source}</span>{' '}
                <span className="text-emerald-400">{o.action}</span>
                {o.detail ? <span className="text-slate-400"> | {o.detail}</span> : ''}
              </div>
            ))
          )
        ) : viewLogs.length === 0 ? (
          <p className="text-slate-500">暂无日志</p>
        ) : (
          viewLogs.map((line, i) => (
            <div key={i} className={`py-0.5 ${isErrorLine(line) ? 'text-red-400' : ''}`}>
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
