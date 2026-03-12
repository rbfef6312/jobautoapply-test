import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../api'
import { PageLoading } from '../components/PageLoading'
import { showToast } from '../utils/toast'

function getGroupKey(job) {
  try {
    const u = new URL(job.url)
    return u.hostname || '其他'
  } catch {
    return '其他'
  }
}

export default function ExternalJobs() {
  const [jobs, setJobs] = useState([])
  const [allJobs, setAllJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [showDone, setShowDone] = useState(false)

  const refresh = useCallback(() => {
    setLoading(true)
    api.external.list(showDone).then((r) => setJobs(r.jobs || [])).catch(() => setJobs([])).finally(() => setLoading(false))
  }, [showDone])

  useEffect(() => {
    refresh()
  }, [refresh])

  const grouped = useMemo(() => {
    const map = {}
    jobs.forEach((j, i) => {
      const key = getGroupKey(j)
      if (!map[key]) map[key] = []
      map[key].push({ ...j, _idx: i })
    })
    return Object.entries(map).sort((a, b) => b[1].length - a[1].length)
  }, [jobs])

  const handleMarkDone = async (url) => {
    try {
      await api.external.markDone(url)
      refresh()
      showToast('已标记为已处理', 'success')
    } catch (e) {
      showToast(e.message || '操作失败', 'error')
    }
  }

  const handleClear = async () => {
    if (!confirm('确定要清除外部投递列表吗？已处理的标记也会清除')) return
    try {
      await api.external.clear()
      refresh()
      showToast('已清除', 'success')
    } catch (e) {
      showToast(e.message || '清除失败', 'error')
    }
  }

  if (loading && jobs.length === 0) return <PageLoading />

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="mb-2 flex justify-between items-center flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">外部投递待办</h1>
          <p className="text-slate-600 dark:text-slate-200 mt-1">
            跳转到非 JobsDB 站点的职位会记录在此，需要手动去对应链接投递
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <input
              type="checkbox"
              checked={showDone}
              onChange={(e) => setShowDone(e.target.checked)}
              className="rounded border-slate-300 text-brand-600"
            />
            包含已处理
          </label>
          {jobs.length > 0 && (
            <button
              onClick={handleClear}
              className="px-4 py-2 rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              清除列表
            </button>
          )}
        </div>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="p-4 space-y-6">
          {jobs.length === 0 ? (
            <p className="text-slate-500 dark:text-slate-400 text-center py-8">暂无待办，有新的会自动出现在这里</p>
          ) : (
            grouped.map(([group, items]) => (
              <div key={group}>
                <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">{group}（{items.length} 条）</p>
                <div className="space-y-3">
                  {items.map((job, i) => (
                    <div
                      key={job.url + i}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        job.done ? 'bg-slate-50 dark:bg-slate-700/50 border-slate-200 dark:border-slate-600' : 'bg-amber-50 dark:bg-amber-900/20 border-amber-100 dark:border-amber-800/50'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-slate-800 dark:text-slate-200">{job.title}</p>
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-brand-600 dark:text-brand-400 hover:underline truncate block max-w-md"
                        >
                          {job.url}
                        </a>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {!job.done && (
                          <button
                            onClick={() => handleMarkDone(job.url)}
                            className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 text-sm"
                          >
                            已处理
                          </button>
                        )}
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-4 py-2 rounded-lg bg-amber-500/20 dark:bg-amber-500/30 text-amber-800 dark:text-amber-200 hover:bg-amber-500/30 font-medium text-sm"
                        >
                          去投递
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
