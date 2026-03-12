import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from 'recharts'
import { api } from '../api'
import { formatNextRunBeijing } from '../utils/format'
import { showToast } from '../utils/toast'


export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [dailyStats, setDailyStats] = useState([])
  const [monitor, setMonitor] = useState(null)
  const [running, setRunning] = useState(false)
  const [taskState, setTaskState] = useState('idle')
  const [progress, setProgress] = useState(null)
  const [blacklistCount, setBlacklistCount] = useState(0)

  const fetchAll = useCallback(() => {
    api.stats().then(setStats).catch(() => setStats({ today: 0, last7: 0, last30: 0 }))
    api.statsDaily(14).then((r) => setDailyStats(r.items || [])).catch(() => setDailyStats([]))
    api.monitor.get().then(setMonitor).catch(() => setMonitor(null))
    api.excludedCompanies.get().then((r) => setBlacklistCount((r.companies || []).length)).catch(() => setBlacklistCount(0))
    api.apply.status().then((r) => {
      setRunning(r.running)
      setTaskState(r.state || 'idle')
      setProgress(r.progress || null)
    }).catch(() => {
      setRunning(false)
      setTaskState('idle')
      setProgress(null)
    })
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  useEffect(() => {
    const poll = () => {
      api.monitor.get().then(setMonitor).catch(() => {})
      api.apply.status()
        .then((r) => {
          setRunning(r.running)
          setTaskState(r.state || 'idle')
          setProgress(r.progress || null)
        })
        .catch(() => {})
    }
    poll()
    const t = setInterval(poll, running ? 2000 : 5000)
    return () => clearInterval(t)
  }, [running])

  const [starting, setStarting] = useState(false)
  const handleManualApply = async () => {
    if (running || starting) return
    setStarting(true)
    try {
      const status = await api.jobsdb.status().catch(() => null)
      if (!status?.logged_in) {
        showToast('请先在 JobsDB 登录页完成登录', 'error')
        return
      }
      const m = monitor || {}
      const mode = m.mode ?? 1
      await api.apply.run({
        mode1: mode === 1,
        mode2: mode === 2,
        mode2_keywords: m.mode2_keywords ?? '',
        mode3: mode === 3,
        mode3_category: m.mode3_category ?? '',
        max_pages: m.max_pages ?? 3,
        experience_years: m.experience_years ?? 3,
        expected_salary: m.expected_salary ?? '16K',
      })
      setRunning(true)
      fetchAll()
    } catch (e) {
      showToast(e.message || '启动失败', 'error')
      fetchAll()
    } finally {
      setStarting(false)
    }
  }

  const handleMonitorToggle = async (enabled) => {
    if (!enabled && !window.confirm('确定关闭自动投递？')) return
    try {
      await api.monitor.update({ enabled })
      fetchAll()
    } catch (e) {
      showToast(e.message || '操作失败', 'error')
    }
  }

  const today = stats?.today ?? 0
  const d7 = stats?.last7 ?? 0
  const d30 = stats?.last30 ?? 0
  const autoTodayRuns = stats?.auto_today_runs ?? 0
  const autoTodaySuccess = stats?.auto_today_success ?? 0
  const autoFailStreak = stats?.auto_fail_streak ?? 0
  const lastAuto = stats?.auto_last

  const statCards = [
    { label: '今日投递', value: today, color: 'text-brand-600' },
    { label: '近 7 天', value: d7, color: 'text-emerald-600' },
    { label: '近 30 天', value: d30, color: 'text-violet-600' },
  ]

  const nextRunText = formatNextRunBeijing(monitor?.next_run_at)
  // 自动投递状态文案和样式：
  // 1) 运行中：绿色「自动投递运行中」
  // 2) 最近一次自动投递已完成（有进度但未在运行）
  // 3) 已开启，等待下次自动投递（开关开但无进度且未在运行）
  // 4) 已关闭
  let autoStatusLabel = '未在运行'
  let badgeCls = 'bg-slate-600/40 text-slate-200'
  let dotCls = 'bg-slate-400'
  const hasProgress = !!progress && (progress.total ?? 0) > 0
  if (running) {
    autoStatusLabel = '自动投递运行中'
    badgeCls = 'bg-emerald-500/20 text-emerald-700'
    dotCls = 'bg-emerald-500 animate-pulse'
  } else if (hasProgress) {
    autoStatusLabel = '最近一次自动投递已完成'
    badgeCls = 'bg-blue-100 text-blue-700'
    dotCls = 'bg-blue-500'
  } else if (monitor?.enabled) {
    autoStatusLabel = '已开启，等待下次自动投递'
    badgeCls = 'bg-slate-200 text-slate-700'
    dotCls = 'bg-slate-500'
  } else {
    autoStatusLabel = '已关闭'
    badgeCls = 'bg-slate-200 text-slate-600'
    dotCls = 'bg-slate-400'
  }

  const [onboardingDismissed, setOnboardingDismissed] = useState(() => {
    try { return localStorage.getItem('jobsdb_onboarding_done') === '1' } catch { return true }
  })
  const dismissOnboarding = () => {
    setOnboardingDismissed(true)
    try { localStorage.setItem('jobsdb_onboarding_done', '1') } catch {}
  }

  const chartData = dailyStats.map(({ date, count }) => ({
    date: date.slice(5),
    count,
    full: date,
  }))

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {!onboardingDismissed && (
        <div className="mb-6 p-4 rounded-xl bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800">
          <div className="flex justify-between items-start">
            <div>
              <p className="font-medium text-brand-800 dark:text-brand-200">首次使用？请按以下步骤操作：</p>
              <ol className="mt-2 text-sm text-brand-700 dark:text-brand-300 list-decimal list-inside space-y-1">
                <li>JobsDB 登录 / 绑定账号</li>
                <li>在「排除公司」配置黑名单</li>
                <li>在「自动投递」配置模式与间隔</li>
                <li>点击「立即投递」试运行一次</li>
              </ol>
            </div>
            <button onClick={dismissOnboarding} className="text-brand-600 dark:text-brand-400 hover:underline text-sm">我知道了</button>
          </div>
        </div>
      )}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">概览</h1>
        <div className="flex flex-wrap items-center gap-4 mt-1 text-sm text-slate-600 dark:text-slate-300/80">
          <span>{stats?.jobsdb_email ? `JobsDB：${stats.jobsdb_email}` : '请先完成 JobsDB 登录'}</span>
          <Link to="/excluded-companies" className="text-brand-600 dark:text-brand-400 hover:underline">
            排除公司 {blacklistCount} 家 →
          </Link>
          {stats?.jobsdb_email ? (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              已登录 JobsDB
            </span>
          ) : (
            <Link
              to="/jobsdb-login"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 text-xs hover:bg-amber-100"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              未登录，去登录 →
            </Link>
          )}
        </div>
        {autoFailStreak >= 3 && lastAuto && (
          <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">
            <p className="font-medium mb-1">最近自动投递连续 {autoFailStreak} 次异常</p>
            <p>
              上次任务：共 {lastAuto.total ?? 0} 个，成功 {lastAuto.success ?? 0}，失败 {lastAuto.failed ?? 0}，跳过 {lastAuto.skip ?? 0}
            </p>
            {lastAuto.reason && <p className="mt-1 opacity-80">原因：{lastAuto.reason}</p>}
          </div>
        )}
        {autoTodayRuns > 0 && autoFailStreak < 3 && (
          <div className="mt-3 text-xs text-slate-500">
            今日自动投递 {autoTodayRuns} 次 · 成功 {autoTodaySuccess} 个
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {statCards.map(({ label, value, color }) => (
          <div key={label} className="glass-card p-6">
            <p className="text-sm font-medium text-slate-600 dark:text-slate-200/80">{label}</p>
            <p className={`text-3xl font-bold mt-2 ${color.replace('text-', 'text-')}`}>{value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-3">快捷操作</h2>
          <div className="glass-subtle p-4 mb-4 text-sm text-slate-700 space-y-2">
            <p className="font-medium text-slate-800">使用流程：</p>
            <ol className="list-decimal list-inside space-y-1 text-slate-700">
              <li>JobsDB 登录 / 绑定账号</li>
              <li>在「自动投递」中配置模式与间隔</li>
              <li>启动自动投递，系统将按间隔定时运行</li>
            </ol>
          </div>
          <button
            onClick={handleManualApply}
            disabled={running || starting}
            className="w-full py-3 rounded-lg bg-gradient-to-r from-brand-500 to-indigo-500 hover:from-brand-600 hover:to-indigo-600 disabled:opacity-50 text-white font-medium shadow-lg shadow-indigo-500/30"
          >
            {running ? '投递中…' : '立即投递'}
          </button>
          <div className="mt-4 space-y-2">
            <Link
              to="/jobsdb-login"
              className="block py-2 px-4 rounded-lg bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors"
            >
              JobsDB 登录 / 绑定
            </Link>
            <Link
              to="/monitor"
              className="block py-2 px-4 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
            >
              自动投递配置
            </Link>
            <Link
              to="/jobs"
              className="block py-2 px-4 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
            >
              职位列表
            </Link>
            <Link
              to="/logs"
              className="block py-2 px-4 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
            >
              日志
            </Link>
          </div>
        </div>

        <div className="glass-card p-6">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">自动投递状态</h2>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${badgeCls}`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${dotCls}`}
                />
                {autoStatusLabel}
              </span>
              <button
                onClick={() => handleMonitorToggle(true)}
                disabled={monitor?.enabled}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium"
              >
                启用自动投递
              </button>
              <button
                onClick={() => handleMonitorToggle(false)}
                disabled={!monitor?.enabled}
                className="px-4 py-2 rounded-lg bg-slate-600 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium"
              >
                关闭
              </button>
            </div>
            <p className="text-sm text-slate-600">
              下次启动：
              {monitor?.enabled && nextRunText
                ? nextRunText + '（北京时间）'
                : monitor?.enabled
                  ? '即将运行'
                  : '已关闭'}
            </p>
            {(progress || (running && true)) && (
              <div>
                <div className="flex justify-between text-sm text-slate-600 dark:text-slate-400 mb-1">
                  <span>
                    {progress?.total === 0 && running ? '加载中…' : `进度：共 ${progress?.total ?? 0} · 已投递 ${progress?.success ?? 0} · 失败 ${progress?.failed ?? 0} · 跳过 ${progress?.skip ?? 0} · 待投递 ${progress?.pending ?? 0}`}
                  </span>
                  <span>{progress?.total > 0 ? Math.round(((progress.success || 0) + (progress.failed || 0) + (progress.skip || 0)) / progress.total * 100) : 0}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-600 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-brand-500 transition-all"
                    style={{ width: `${progress?.total > 0 ? Math.round(((progress.success || 0) + (progress.failed || 0) + (progress.skip || 0)) / progress.total * 100) : 0}%` }}
                  />
                </div>
              </div>
            )}
            <Link
              to="/monitor"
              className="block text-sm text-brand-600 hover:text-brand-700"
            >
              前往自动投递页配置模式与间隔 →
            </Link>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-600 p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4">每日投递量（近 14 天）</h2>
        {chartData.length > 0 ? (
          <div className="glass-card p-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v) => v.replace('-', '/')}
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} width={28} />
                <Tooltip
                  formatter={([v]) => [v, '投递数']}
                  labelFormatter={(_, items) => items?.[0]?.payload?.full ?? ''}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]} name="投递数">
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.date === chartData[chartData.length - 1]?.date ? '#6366f1' : '#94a3b8'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-slate-500 text-center py-12">暂无投递记录</p>
        )}
      </div>
    </div>
  )
}
