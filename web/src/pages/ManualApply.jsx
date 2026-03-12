import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { showToast } from '../utils/toast'

const MODES = [
  { id: 1, name: '推荐岗位模式', desc: '投递 /zh/jobs 最近3天职位（登录后 JobsDB 会展示个性化推荐）' },
  { id: 2, name: '职位关键词模式', desc: '按关键词搜索，如 /zh/shopify-jobs' },
  { id: 3, name: '职位类别模式', desc: '按 JobsDB 分类，如 /zh/jobs-in-information-communication-technology' },
]

const EXPERIENCE_OPTS = [
  { val: 0, label: '0 年（无经验）' },
  { val: 1, label: '1 年' },
  { val: 2, label: '2 年' },
  { val: 3, label: '3 年' },
  { val: 4, label: '4 年' },
  { val: 5, label: '5 年' },
]

const SALARY_OPTS = ['16K', '17K', '18K', '19K', '20K', '22K', '25K', '28K', '30K']

export default function ManualApply() {
  const [status, setStatus] = useState(null)
  const [applyState, setApplyState] = useState('idle')  // idle | running | paused
  const [mode, setMode] = useState(1)
  const [keywords, setKeywords] = useState('')
  const [category, setCategory] = useState('')
  const [experience, setExperience] = useState(3)
  const [salary, setSalary] = useState('16K')
  const [maxPages, setMaxPages] = useState(3)
  const [showBrowser, setShowBrowser] = useState(false)
  const [categories, setCategories] = useState([])
  const [blacklistCount, setBlacklistCount] = useState(0)

  useEffect(() => {
    api.jobsdb.status().then(setStatus).catch(() => setStatus(null))
    const refresh = () => api.apply.status().then((r) => setApplyState(r.state || (r.running ? 'running' : 'idle'))).catch(() => setApplyState('idle'))
    refresh()
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    api.classifications().then(setCategories).catch(() => setCategories([]))
    api.excludedCompanies.get().then((r) => setBlacklistCount((r.companies || []).length)).catch(() => {})
  }, [])

  const handleRun = async () => {
    if (applyState !== 'idle') return
    if (mode === 2 && !keywords.trim()) {
      showToast('请输入职位关键词', 'error')
      return
    }
    if (mode === 3 && !category.trim()) {
      showToast('请选择职位类别', 'error')
      return
    }
    try {
      await api.apply.run({
        mode1: mode === 1,
        mode2: mode === 2,
        mode2_keywords: keywords,
        mode3: mode === 3,
        mode3_category: category,
        max_pages: maxPages,
        experience_years: experience,
        expected_salary: salary,
        excluded_companies: '',
        show_browser: showBrowser,
      })
      setApplyState('running')
    } catch (e) {
      showToast(e.message || '启动失败', 'error')
    }
  }

  const canRun = status?.logged_in && applyState === 'idle'

  const handlePause = async () => {
    try {
      await api.apply.pause()
      setApplyState('paused')
    } catch (e) { showToast(e.message || '暂停失败', 'error') }
  }
  const handleResume = async () => {
    try {
      await api.apply.resume()
      setApplyState('running')
    } catch (e) { showToast(e.message || '恢复失败', 'error') }
  }
  const handleStop = async () => {
    if (!confirm('确定停止当前投递任务？')) return
    try {
      await api.apply.stop()
    } catch (e) { showToast(e.message || '停止失败', 'error') }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {!status?.logged_in && (
        <div className="glass-subtle border border-amber-300/40 dark:border-amber-500/40 text-amber-100">
          <p className="font-medium">请先完成 JobsDB 登录</p>
          <p className="text-sm mt-1 opacity-90">在左侧菜单进入「JobsDB 登录」完成登录后再进行投递</p>
          <Link to="/jobsdb-login" className="inline-block mt-3 text-sm font-medium text-amber-700 hover:text-amber-900 underline">前往登录 →</Link>
        </div>
      )}
      <div className="mb-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">手动投递</h1>
        <p className="text-slate-600 dark:text-slate-200 mt-1">
          {status?.logged_in ? `当前 JobsDB：${status.email}` : '请先在 JobsDB 登录页完成登录'}
        </p>
      </div>

      <div className="glass-card p-6 space-y-6">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">投递模式</label>
          <select
            value={mode}
            onChange={(e) => setMode(Number(e.target.value))}
            className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
          >
            {MODES.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>

        {mode === 2 && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">职位关键词</label>
            <input
              type="text"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="例如：shopify, admin, digital marketing"
              className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
            />
          </div>
        )}

        {mode === 3 && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">职位类别</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
            >
              <option value="">-- 请选择 --</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>{c.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">经验年限</label>
            <select
              value={experience}
              onChange={(e) => setExperience(Number(e.target.value))}
              className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
            >
              {EXPERIENCE_OPTS.map((o) => (
                <option key={o.val} value={o.val}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">期望月薪</label>
            <select
              value={salary}
              onChange={(e) => setSalary(e.target.value)}
              className="w-full px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
            >
              {SALARY_OPTS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="py-2 px-4 rounded-lg bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-400 text-sm">
          排除公司统一在「排除公司」页面配置，当前 {blacklistCount} 家。自动投递与手动投递均会跳过黑名单中的公司。
          <Link to="/excluded-companies" className="ml-2 text-brand-600 dark:text-brand-400 hover:underline">前往配置 →</Link>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="showBrowser"
            checked={showBrowser}
            onChange={(e) => setShowBrowser(e.target.checked)}
            className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
          />
          <label htmlFor="showBrowser" className="text-sm font-medium text-slate-700">
            调试模式：显示浏览器（便于排查「外部链接」误判等问题）
          </label>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">最大页数（1-10，默认 3）</label>
          <input
            type="number"
            min={1}
            max={10}
            value={maxPages}
            onChange={(e) => setMaxPages(Math.max(1, Math.min(10, Number(e.target.value) || 3)))}
            className="w-24 px-4 py-2 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <div className="pt-4 space-y-3">
          {applyState === 'idle' && (
            <button
              onClick={handleRun}
              disabled={!canRun}
              className="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
            >
              开始自动投递
            </button>
          )}
          {applyState === 'running' && (
            <div className="flex gap-3">
              <button onClick={handlePause} className="flex-1 py-3 rounded-lg border border-amber-500 text-amber-600 hover:bg-amber-50 font-medium">
                暂停
              </button>
              <button onClick={handleStop} className="flex-1 py-3 rounded-lg border border-red-500 text-red-600 hover:bg-red-50 font-medium">
                停止
              </button>
            </div>
          )}
          {applyState === 'paused' && (
            <div className="flex gap-3">
              <button onClick={handleResume} className="flex-1 py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium">
                恢复
              </button>
              <button onClick={handleStop} className="flex-1 py-3 rounded-lg border border-red-500 text-red-600 hover:bg-red-50 font-medium">
                停止
              </button>
            </div>
          )}
          {applyState === 'running' && <p className="text-sm text-slate-500">投递中…</p>}
          {applyState === 'paused' && <p className="text-sm text-amber-600">已暂停</p>}
          {!status?.logged_in && (
            <p className="mt-2 text-sm text-amber-600">请先在左侧 JobsDB 登录 完成登录</p>
          )}
        </div>
      </div>
    </div>
  )
}
