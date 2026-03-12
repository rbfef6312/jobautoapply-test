import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { PageLoading } from '../components/PageLoading'
import { formatDateTimeBeijing } from '../utils/format'
import { showToast } from '../utils/toast'

const PAGE_SIZE_OPTS = [16, 32, 64]
const SORT_OPTIONS = [
  { value: 'default', label: '默认' },
  { value: 'company', label: '按公司' },
  { value: 'company-desc', label: '按公司 Z-A' },
  { value: 'appliedAt', label: '按投递时间' },
  { value: 'appliedAt-desc', label: '按投递时间倒序' },
  { value: 'date', label: '按日期' },
  { value: 'date-desc', label: '按日期倒序' },
]

const loadPref = (key, defaultVal) => {
  try {
    const v = localStorage.getItem(`jobs_pref_${key}`)
    if (v != null) return JSON.parse(v)
  } catch {}
  return defaultVal
}
const savePref = (key, val) => {
  try { localStorage.setItem(`jobs_pref_${key}`, JSON.stringify(val)) } catch {}
}

export default function JobList() {
  const [jobs, setJobs] = useState([])
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [statusFilter, setStatusFilter] = useState(() => loadPref('statusFilter', 'all'))
  const [companySearch, setCompanySearch] = useState('')
  const [blacklistFilter, setBlacklistFilter] = useState('all')  // all | blacklist | notBlacklist
  const [hasErrorFilter, setHasErrorFilter] = useState(false)
  const [blacklist, setBlacklist] = useState([])
  const [pageSize, setPageSize] = useState(() => loadPref('pageSize', 32))
  const [pageIndex, setPageIndex] = useState(0)
  const [sortBy, setSortBy] = useState(() => loadPref('sortBy', 'appliedAt-desc'))
  const [selected, setSelected] = useState(new Set())
  const [detailJob, setDetailJob] = useState(null)

  useEffect(() => {
    savePref('statusFilter', statusFilter)
  }, [statusFilter])
  useEffect(() => {
    savePref('pageSize', pageSize)
  }, [pageSize])
  useEffect(() => {
    savePref('sortBy', sortBy)
  }, [sortBy])

  useEffect(() => {
    let timer
    let cancelled = false

    const refresh = async () => {
      if (cancelled) return
      setRefreshing(true)
      try {
        const r = await api.jobs()
        const list = r.jobs || []
        setJobs(list)
        const hasRunning = (list || []).some((j) => {
          const raw = j.job?.status ?? j.status
          return raw === '投递中'
        })
        const delay = hasRunning ? 2000 : 8000
        if (!cancelled) {
          timer = setTimeout(refresh, delay)
        }
      } catch {
        if (!cancelled) {
          timer = setTimeout(refresh, 5000)
        }
      } finally {
        if (!cancelled) {
          setInitialLoading(false)
          setRefreshing(false)
        }
      }
    }

    refresh()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    api.excludedCompanies.get().then((r) => setBlacklist(r.companies || [])).catch(() => setBlacklist([]))
  }, [])

  const list = useMemo(() => {
    const blacklistLower = (blacklist || []).map((x) => x.toLowerCase().trim()).filter(Boolean)
    const statusMap = {
      投递中: { label: '投递中', cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' },
      成功: { label: '已投递', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' },
      失败: { label: '需关注', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' },
      跳过: { label: '跳过', cls: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400' },
    }
    return jobs.map((j, i) => {
      const raw = j.job?.status ?? j.status
      const msg = j.job?.message ?? j.message ?? ''
      let key = raw
      if (raw === '失败' && (msg.includes('已投递') || msg.includes('外部站点'))) key = '跳过'
      const st = key ? (statusMap[key] || { label: key, cls: 'bg-slate-100 text-slate-600' }) : null
      const company = j.job?.company ?? j.company ?? '-'
      const isBlacklisted = blacklistLower.some((kw) => (company || '').toLowerCase().includes(kw))
      return {
        id: i,
        page: j.page ?? 1,
        idx: i + 1,
        title: j.job?.title ?? j.title ?? '-',
        company,
        isBlacklisted,
        date: j.job?.date ?? j.date ?? '-',
        appliedAt: j.job?.applied_at,
        appliedAtFormatted: j.job?.applied_at ? formatDateTimeBeijing(j.job.applied_at) : null,
        statusNote: st,
        message: msg,
        url: j.job?.url ?? j.job?.link ?? j.url ?? j.link,
        statusKey: key || 'pending',
      }
    })
  }, [jobs, blacklist])

  const filteredList = useMemo(() => {
    let result = list.filter((job) => {
      if (statusFilter !== 'all' && job.statusKey !== statusFilter) return false
      if (blacklistFilter === 'blacklist' && !job.isBlacklisted) return false
      if (blacklistFilter === 'notBlacklist' && job.isBlacklisted) return false
      if (hasErrorFilter && !job.message) return false
      if (companySearch.trim()) {
        const kw = companySearch.trim().toLowerCase()
        if (!(job.company || '').toLowerCase().includes(kw)) return false
      }
      return true
    })
    if (sortBy !== 'default') {
      const [field, dir] = sortBy.split('-')
      const desc = dir === 'desc'
      result = [...result].sort((a, b) => {
        let va = field === 'company' ? (a.company || '').toLowerCase() : (a[field] || '')
        let vb = field === 'company' ? (b.company || '').toLowerCase() : (b[field] || '')
        if (field === 'appliedAt' || field === 'date') {
          va = va || '0'
          vb = vb || '0'
        }
        const cmp = va < vb ? -1 : va > vb ? 1 : 0
        return desc ? -cmp : cmp
      })
    }
    return result
  }, [list, statusFilter, blacklistFilter, hasErrorFilter, companySearch, sortBy])

  const totalPages = Math.max(1, Math.ceil(filteredList.length / pageSize))
  const safePageIndex = Math.min(pageIndex, totalPages - 1)
  const pageList = filteredList.slice(safePageIndex * pageSize, (safePageIndex + 1) * pageSize)

  useEffect(() => {
    if (pageIndex >= totalPages && totalPages > 0) setPageIndex(0)
  }, [pageIndex, totalPages])

  const handleAddToBlacklist = async (company) => {
    if (!company || company === '-') return
    try {
      const cur = await api.excludedCompanies.get()
      const companies = cur.companies || []
      if (companies.some((c) => c.toLowerCase() === company.toLowerCase())) {
        showToast('该公司已在黑名单中', 'info')
        return
      }
      await api.excludedCompanies.update([...companies, company])
      setBlacklist([...companies, company])
      showToast(`已添加「${company}」到黑名单`, 'success')
    } catch (e) {
      showToast(e.message || '添加失败', 'error')
    }
  }

  const handleBatchAddToBlacklist = async () => {
    const companies = [...selected]
      .map((id) => list[id]?.company)
      .filter((c) => c && c !== '-')
    const unique = [...new Set(companies.map((c) => c.toLowerCase()))]
    if (unique.length === 0) {
      showToast('请先勾选职位', 'info')
      return
    }
    try {
      const cur = await api.excludedCompanies.get()
      const existing = (cur.companies || []).map((c) => c.toLowerCase())
      const toAdd = unique.filter((c) => !existing.includes(c))
      if (toAdd.length === 0) {
        showToast('所选公司均已在黑名单中', 'info')
        setSelected(new Set())
        return
      }
      const names = toAdd.map((l) => companies.find((c) => c.toLowerCase() === l))
      await api.excludedCompanies.update([...(cur.companies || []), ...names])
      setBlacklist(await api.excludedCompanies.get().then((r) => r.companies || []))
      showToast(`已添加 ${toAdd.length} 家公司到黑名单`, 'success')
      setSelected(new Set())
    } catch (e) {
      showToast(e.message || '添加失败', 'error')
    }
  }

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selected.size >= pageList.length) setSelected(new Set())
    else setSelected(new Set(pageList.map((j) => j.id)))
  }

  const exportCsv = (scope) => {
    const data = scope === 'all' ? filteredList : pageList
    if (data.length === 0) {
      showToast('无数据可导出', 'info')
      return
    }
    const headers = ['页码', '序号', '职位', '公司', '日期', '投递时间', '备注']
    const rows = data.map((j) => [
      j.page,
      j.idx,
      `"${(j.title || '').replace(/"/g, '""')}"`,
      `"${(j.company || '').replace(/"/g, '""')}"`,
      j.date,
      j.appliedAtFormatted ?? '—',
      j.statusNote?.label ?? '待投递',
    ])
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `jobs-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    showToast(`已导出 ${data.length} 条`, 'success')
  }

  if (initialLoading) return <PageLoading />

  return (
    <div className="space-y-6">
      <div className="mb-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">职位列表</h1>
        <p className="text-slate-600 dark:text-slate-200 mt-1">本次任务发现的职位及投递状态（仅显示最近一次投递任务）</p>
        <div className="glass-subtle mt-4 inline-flex flex-wrap items-center gap-3 px-4 py-3">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPageIndex(0) }}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 text-sm focus:ring-2 focus:ring-brand-500"
          >
            <option value="all">全部状态</option>
            <option value="成功">已投递</option>
            <option value="失败">需关注</option>
            <option value="pending">待投递</option>
            <option value="跳过">跳过</option>
          </select>
          <select
            value={blacklistFilter}
            onChange={(e) => { setBlacklistFilter(e.target.value); setPageIndex(0) }}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 text-sm focus:ring-2 focus:ring-brand-500"
          >
            <option value="all">全部公司</option>
            <option value="blacklist">仅黑名单</option>
            <option value="notBlacklist">非黑名单</option>
          </select>
          <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-400">
            <input
              type="checkbox"
              checked={hasErrorFilter}
              onChange={(e) => { setHasErrorFilter(e.target.checked); setPageIndex(0) }}
              className="rounded border-slate-300 text-brand-600"
            />
            有备注
          </label>
          <input
            type="text"
            placeholder="按公司名搜索"
            value={companySearch}
            onChange={(e) => { setCompanySearch(e.target.value); setPageIndex(0) }}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 text-sm w-40 focus:ring-2 focus:ring-brand-500"
          />
          <select
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value); setPageIndex(0) }}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 text-sm focus:ring-2 focus:ring-brand-500"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            每页
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPageIndex(0) }}
              className="mx-1 px-2 py-1 rounded border border-slate-300 dark:border-slate-600 dark:bg-slate-800 text-sm"
            >
              {PAGE_SIZE_OPTS.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            条
          </span>
          <button
            onClick={() => exportCsv('page')}
            disabled={filteredList.length === 0}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 text-sm disabled:opacity-50"
          >
            导出本页 CSV
          </button>
          <button
            onClick={() => exportCsv('all')}
            disabled={filteredList.length === 0}
            className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 text-sm disabled:opacity-50"
          >
            导出全部 CSV
          </button>
          {refreshing && (
            <span className="text-xs text-slate-400">
              刷新中…
            </span>
          )}
          {selected.size > 0 && (
            <button
              onClick={handleBatchAddToBlacklist}
              className="px-3 py-2 rounded-lg bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-400 hover:bg-rose-200 dark:hover:bg-rose-800 text-sm font-medium"
            >
              将选中公司加入黑名单 ({selected.size})
            </button>
          )}
        </div>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full table-fixed">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-700/50 border-b border-slate-200 dark:border-slate-600">
                <th className="w-10 px-2 py-3 text-left">
                  {pageList.length > 0 && (
                    <input
                      type="checkbox"
                      checked={selected.size === pageList.length && pageList.length > 0}
                      onChange={toggleSelectAll}
                      className="rounded border-slate-300 text-brand-600"
                    />
                  )}
                </th>
                <th className="w-14 px-2 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">页码</th>
                <th className="w-12 px-2 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">序号</th>
                <th className="min-w-[160px] w-[22%] px-3 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">职位标题</th>
                <th className="min-w-[120px] w-[18%] px-3 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">公司</th>
                <th className="w-20 px-2 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">日期</th>
                <th className="w-32 px-3 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">投递时间</th>
                <th className="min-w-[120px] w-[16%] px-3 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">备注</th>
                <th className="w-20 px-2 py-3 text-left text-sm font-semibold text-slate-700 dark:text-slate-300">操作</th>
              </tr>
            </thead>
            <tbody>
              {pageList.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-16 text-center">
                    {list.length === 0 ? (
                      <div className="text-slate-500 dark:text-slate-400 space-y-3">
                        <p className="font-medium">暂无职位数据</p>
                        <p className="text-sm">请先在「手动投递」或「自动投递」中运行一次投递任务</p>
                        <Link to="/manual-apply" className="inline-block text-brand-600 dark:text-brand-400 hover:underline">去手动投递 →</Link>
                      </div>
                    ) : (
                      <p className="text-slate-500 dark:text-slate-400">无匹配结果，请调整筛选条件</p>
                    )}
                  </td>
                </tr>
              ) : (
                pageList.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => setDetailJob(job)}
                    className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/30 cursor-pointer"
                  >
                    <td className="px-2 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(job.id)}
                        onChange={() => toggleSelect(job.id)}
                        className="rounded border-slate-300 text-brand-600"
                      />
                    </td>
                    <td className="px-2 py-3 text-sm text-slate-600 dark:text-slate-400">{job.page}</td>
                    <td className="px-2 py-3 text-sm text-slate-600 dark:text-slate-400">{job.idx}</td>
                    <td className="px-3 py-3 text-sm font-medium text-slate-800 dark:text-slate-200 truncate" title={job.title}>
                      {job.url ? (
                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="text-brand-600 dark:text-brand-400 hover:underline truncate block">{job.title}</a>
                      ) : (
                        job.title
                      )}
                    </td>
                    <td className="px-3 py-3 text-sm text-slate-600 dark:text-slate-400">
                      <span className="truncate block" title={job.company}>
                        {job.company}
                        {job.isBlacklisted && (
                          <span className="ml-1 inline-flex px-2 py-0.5 rounded text-xs font-medium bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-400 shrink-0">
                            黑
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-2 py-3 text-sm text-slate-500 dark:text-slate-400">{job.date}</td>
                    <td className="px-3 py-3 text-sm text-slate-500 dark:text-slate-400">{job.appliedAtFormatted ?? '—'}</td>
                    <td className="px-3 py-3">
                      {job.statusNote ? (
                        <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium truncate max-w-full ${job.statusNote.cls}`} title={job.message}>
                          {job.statusNote.label}{job.message ? `: ${job.message}` : ''}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-sm">待投递</span>
                      )}
                    </td>
                    <td className="px-2 py-3">
                      <div className="flex flex-col gap-1">
                        {job.url && (
                          <a href={job.url} target="_blank" rel="noopener noreferrer" className="text-brand-600 dark:text-brand-400 text-xs hover:underline">查看</a>
                        )}
                        {job.company && job.company !== '-' && (
                          <button
                            onClick={() => handleAddToBlacklist(job.company)}
                            className="text-xs text-rose-600 dark:text-rose-400 hover:underline text-left"
                          >
                            加黑名单
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {filteredList.length > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/30">
            <span className="text-sm text-slate-600 dark:text-slate-400">
              共 {filteredList.length} 条 · 第 {safePageIndex + 1} / {totalPages} 页
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPageIndex(0)}
                disabled={safePageIndex === 0}
                className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 text-sm disabled:opacity-50"
              >
                首页
              </button>
              <button
                onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                disabled={safePageIndex === 0}
                className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 text-sm disabled:opacity-50"
              >
                上一页
              </button>
              <span className="px-2 text-sm text-slate-600 dark:text-slate-400">
                {safePageIndex + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPageIndex((p) => Math.min(totalPages - 1, p + 1))}
                disabled={safePageIndex >= totalPages - 1}
                className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 text-sm disabled:opacity-50"
              >
                下一页
              </button>
              <button
                onClick={() => setPageIndex(totalPages - 1)}
                disabled={safePageIndex >= totalPages - 1}
                className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 text-sm disabled:opacity-50"
              >
                末页
              </button>
            </div>
          </div>
        )}
      </div>

      {detailJob && (
        <div
          className="fixed inset-0 bg-black/40 z-40 flex justify-end"
          onClick={() => setDetailJob(null)}
        >
          <div
            className="w-full max-w-md bg-white dark:bg-slate-800 shadow-xl overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 space-y-4">
              <div className="flex justify-between items-start">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">职位详情</h2>
                <button onClick={() => setDetailJob(null)} className="text-slate-500 hover:text-slate-700">✕</button>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">职位</p>
                <p className="font-medium text-slate-800 dark:text-slate-200">{detailJob.title}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">公司</p>
                <p className="text-slate-700 dark:text-slate-300">{detailJob.company}{detailJob.isBlacklisted && <span className="ml-2 text-rose-600 text-sm">(黑名单)</span>}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">日期</p>
                <p className="text-slate-600 dark:text-slate-400">{detailJob.date}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">投递时间</p>
                <p className="text-slate-600 dark:text-slate-400">{detailJob.appliedAtFormatted ?? '—'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">状态</p>
                <span className={detailJob.statusNote?.cls || 'bg-slate-100'}>{detailJob.statusNote?.label || '待投递'}</span>
              </div>
              {detailJob.message && (
                <div>
                  <p className="text-xs text-slate-500 mb-1">备注</p>
                  <p className="text-sm text-slate-600 dark:text-slate-400">{detailJob.message}</p>
                </div>
              )}
              {detailJob.url && (
                <a href={detailJob.url} target="_blank" rel="noopener noreferrer" className="block py-2 text-brand-600 dark:text-brand-400 hover:underline">查看职位链接 →</a>
              )}
              {detailJob.company && detailJob.company !== '-' && (
                <button onClick={() => handleAddToBlacklist(detailJob.company)} className="px-4 py-2 rounded-lg bg-rose-100 text-rose-700 dark:bg-rose-900/50 hover:bg-rose-200 text-sm">加入黑名单</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
