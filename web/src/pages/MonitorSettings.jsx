import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { formatNextRunBeijing } from '../utils/format'
import { PageLoading } from '../components/PageLoading'
import { showToast } from '../utils/toast'

const MODES = [
  { id: 1, name: '模式一：推荐岗位', desc: '投递 JobsDB 推荐岗位' },
  { id: 2, name: '模式二：关键词', desc: '按关键词搜索并投递' },
  { id: 3, name: '模式三：职位类别', desc: '按 JobsDB 分类投递' },
]

const INTERVAL_OPTIONS = [6, 12, 24, 36, 48]
const EXPERIENCE_OPTS = [
  { val: 0, label: '0 年（无经验）' },
  { val: 1, label: '1 年' },
  { val: 2, label: '2 年' },
  { val: 3, label: '3 年' },
  { val: 4, label: '4 年' },
  { val: 5, label: '5 年' },
]
const SALARY_OPTS = ['16K', '17K', '18K', '19K', '20K', '22K', '25K', '28K', '30K']

export default function MonitorSettings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [mode, setMode] = useState(1)
  const [intervalHours, setIntervalHours] = useState(6)
  const [maxPages, setMaxPages] = useState(3)
  const [mode2Keywords, setMode2Keywords] = useState('')
  const [mode3Category, setMode3Category] = useState('')
  const [experienceYears, setExperienceYears] = useState(3)
  const [expectedSalary, setExpectedSalary] = useState('16K')
  const [nextRunAt, setNextRunAt] = useState(null)
  const [lastRunStartedAt, setLastRunStartedAt] = useState(null)
  const [categories, setCategories] = useState([])
  const [running, setRunning] = useState(false)
  const [taskState, setTaskState] = useState('idle')  // idle | running | paused
  const [progress, setProgress] = useState(null)     // { total, success, failed, skip, pending }
  const [blacklistCount, setBlacklistCount] = useState(0)

  const fetchMonitor = useCallback(() => {
    api.monitor.get().then((data) => {
      setEnabled(data.enabled)
      setMode(data.mode ?? 1)
      setIntervalHours(INTERVAL_OPTIONS.includes(data.interval_hours) ? data.interval_hours : 6)
      setMaxPages(data.max_pages ?? 3)
      setMode2Keywords(data.mode2_keywords || '')
      setMode3Category(data.mode3_category || '')
      setExperienceYears(EXPERIENCE_OPTS.some((o) => o.val === data.experience_years) ? data.experience_years : 3)
      setExpectedSalary(SALARY_OPTS.includes(data.expected_salary) ? data.expected_salary : '16K')
      setNextRunAt(data.next_run_at)
      setLastRunStartedAt(data.last_run_started_at)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    fetchMonitor()
    api.classifications().then(setCategories).catch(() => setCategories([]))
    api.excludedCompanies.get().then((r) => setBlacklistCount((r.companies || []).length)).catch(() => {})
  }, [fetchMonitor])

  useEffect(() => {
    setLoading(false)
  }, [])

  // 挂载时立即请求 status 和 monitor，再启动轮询
  useEffect(() => {
    const refresh = () => {
      api.apply.status()
        .then((r) => {
          setRunning(r.running)
          setTaskState(r.state || 'idle')
          setProgress(r.progress || null)
        })
        .catch(() => {})
      fetchMonitor()
    }
    refresh()  // 立即执行一次
    const interval = setInterval(refresh, running ? 1000 : 5000)
    return () => clearInterval(interval)
  }, [fetchMonitor, running])

  const handleSave = async () => {
    if (mode === 2 && !mode2Keywords.trim()) {
      showToast('模式二请填写关键词', 'error')
      return
    }
    if (mode === 3 && !mode3Category.trim()) {
      showToast('模式三请选择职位类别', 'error')
      return
    }
    setSaving(true)
    try {
      await api.monitor.update({
        enabled,
        mode,
        interval_hours: intervalHours,
        max_pages: maxPages,
        mode2_keywords: mode2Keywords,
        mode3_category: mode3Category,
        experience_years: experienceYears,
        expected_salary: expectedSalary,
      })
      fetchMonitor()
      showToast('保存成功', 'success')
    } catch (e) {
      showToast(e.message || '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleStop = async () => {
    try {
      await api.apply.stop()
      setRunning(false)
      setTaskState('idle')
      setProgress(null)
      fetchMonitor()
    } catch (e) {
      showToast(e.message || '停止失败', 'error')
    }
  }

  const handlePause = async () => {
    try {
      await api.apply.pause()
      setTaskState('paused')
    } catch (e) {
      showToast(e.message || '暂停失败', 'error')
    }
  }

  const handleResume = async () => {
    try {
      await api.apply.resume()
      setTaskState('running')
    } catch (e) {
      showToast(e.message || '恢复失败', 'error')
    }
  }

  const nextRunText = formatNextRunBeijing(nextRunAt)
  const lastRunText = formatNextRunBeijing(lastRunStartedAt)
  const p = progress || {}
  const total = p.total || 0
  const done = (p.success || 0) + (p.failed || 0) + (p.skip || 0)
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const hasProgress = running || total > 0 || lastRunText || nextRunText
  if (loading) return <PageLoading />

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">自动投递</h1>
        <p className="text-slate-600 dark:text-slate-200 mt-1">配置定时任务与投递模式</p>
        <p className="text-sm text-slate-600 dark:text-slate-300 mt-1">
          <Link to="/excluded-companies" className="text-brand-600 dark:text-brand-400 hover:underline">排除公司 {blacklistCount} 家</Link>
        </p>
      </div>

      <div className="space-y-6">
        <section className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-200 mb-4">自动投递开关</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-slate-700 dark:text-slate-300">定时自动投递</p>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                按选定间隔自动检查新岗位并投递
              </p>
            </div>
            <button
              onClick={() => setEnabled(!enabled)}
              className={`relative w-14 h-8 rounded-full transition-colors ${
                enabled ? 'bg-brand-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <span
                className={`absolute top-1 w-6 h-6 rounded-full bg-white shadow transition-transform ${
                  enabled ? 'left-7' : 'left-1'
                }`}
              />
            </button>
          </div>
          {enabled && nextRunText && !running && (
            <p className="text-sm text-slate-600 dark:text-slate-400 mt-3">
              下次自动投递：{nextRunText}（北京时间）
            </p>
          )}
          {/* 进度条与运行状态合并到开关区域 */}
          {hasProgress && (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-600 space-y-3">
              {(lastRunText || nextRunText) && (
                <div className="flex flex-wrap gap-4 text-sm text-slate-600 dark:text-slate-400">
                  {lastRunText && <span>本次启动：{lastRunText}</span>}
                  {nextRunText && running && <span>下次启动：{nextRunText}</span>}
                </div>
              )}
              {(total > 0 || running) && (
                <div>
                  <div className="flex justify-between text-sm text-slate-600 dark:text-slate-400 mb-1">
                    <span>
                      {total === 0 && running ? '加载中…' : `共 ${total} · 已投递 ${p.success || 0} · 失败 ${p.failed || 0} · 跳过 ${p.skip || 0} · 待投递 ${p.pending || 0}`}
                    </span>
                    <span>{pct}%</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-600 overflow-hidden">
                    <div className="h-full rounded-full bg-brand-500 transition-all duration-300" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )}
              {running && (
                <div className="flex gap-2">
                  {taskState === 'paused' ? (
                    <button onClick={handleResume} className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium">恢复</button>
                  ) : (
                    <button onClick={handlePause} className="px-4 py-2 rounded-lg bg-slate-600 hover:bg-slate-700 text-white font-medium">暂停</button>
                  )}
                  <button onClick={async () => { if (window.confirm('确定停止当前投递任务？')) await handleStop() }} className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-medium">停止</button>
                </div>
              )}
            </div>
          )}
          {!hasProgress && enabled && (
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-3">暂无运行任务</p>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
            当前配置：{MODES.find((m) => m.id === mode)?.name}，间隔 {intervalHours} 小时，每模式最多 {maxPages} 页，经验 {experienceYears} 年，期望 {expectedSalary}
          </p>
        </section>

        <section className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">投递间隔</h2>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">
              间隔时间（小时）
            </label>
            <select
              value={intervalHours}
              onChange={(e) => setIntervalHours(Number(e.target.value))}
              className="w-32 px-3 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
            >
              {INTERVAL_OPTIONS.map((h) => (
                <option key={h} value={h}>
                  {h} 小时
                </option>
              ))}
            </select>
          </div>
        </section>

        <section className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">投递模式</h2>
          <p className="text-sm text-slate-500 mb-4">选择一种模式用于定时投递</p>

          <div className="space-y-5">
            {MODES.map((m) => (
              <label key={m.id} className="flex items-start gap-3 cursor-pointer">
                <input
                  type="radio"
                  name="mode"
                  checked={mode === m.id}
                  onChange={() => setMode(m.id)}
                  className="mt-1 w-4 h-4 border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <div className="flex-1">
                  <span className="font-medium text-slate-800">{m.name}</span>
                  <p className="text-sm text-slate-500 mb-2">{m.desc}</p>
                  {m.id === 2 && (
                    <input
                      type="text"
                      value={mode2Keywords}
                      onChange={(e) => setMode2Keywords(e.target.value)}
                      placeholder="例如：shopify, admin, digital marketing"
                      disabled={mode !== 2}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 disabled:opacity-50 disabled:bg-slate-100"
                    />
                  )}
                  {m.id === 3 && (
                    <select
                      value={mode3Category}
                      onChange={(e) => setMode3Category(e.target.value)}
                      disabled={mode !== 3}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 disabled:opacity-50 disabled:bg-slate-100"
                    >
                      <option value="">-- 请选择 --</option>
                      {categories.map((c) => (
                        <option key={c.slug} value={c.slug}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </label>
            ))}
          </div>
        </section>

        <section className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">填表偏好</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">申请表单中的经验年限、期望薪酬会使用以下设置</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">经验年限</label>
              <select
                value={experienceYears}
                onChange={(e) => setExperienceYears(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 focus:ring-2 focus:ring-brand-500"
              >
                {EXPERIENCE_OPTS.map((o) => (
                  <option key={o.val} value={o.val}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-600 dark:text-slate-300 mb-1">期望薪酬（月薪）</label>
              <select
                value={expectedSalary}
                onChange={(e) => setExpectedSalary(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 focus:ring-2 focus:ring-brand-500"
              >
                {SALARY_OPTS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
        </section>

        <section className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">最大页数</h2>
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1">
              每模式最多爬取页数（1–8）
            </label>
            <input
              type="number"
              min={1}
              max={8}
              value={maxPages}
              onChange={(e) => setMaxPages(Math.max(1, Math.min(8, Number(e.target.value) || 1)))}
              className="w-24 px-3 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </section>

        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium transition-colors"
          >
            {saving ? '保存中…' : '保存设置'}
          </button>
        </div>
      </div>
    </div>
  )
}
