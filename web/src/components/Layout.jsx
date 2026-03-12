import { useState, useEffect } from 'react'
import { Outlet, NavLink, Link } from 'react-router-dom'
import { api } from '../api'

const navGroups = [
  { label: '概览', items: [{ to: '/', label: '概览' }] },
  { label: '配置', items: [
    { to: '/monitor', label: '自动投递' },
    { to: '/excluded-companies', label: '排除公司' },
    { to: '/jobsdb-login', label: 'JobsDB 登录' },
  ]},
  { label: '运行', items: [{ to: '/manual-apply', label: '手动投递' }] },
  { label: '结果', items: [
    { to: '/jobs', label: '职位列表' },
    { to: '/external', label: '外部投递待办' },
    { to: '/logs', label: '日志' },
  ]},
  { label: '帮助', items: [{ to: '/help', label: '使用说明' }] },
]

export default function Layout({ user, onLogout }) {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem('theme') === 'dark' || (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches)
    } catch { return false }
  })
  const [running, setRunning] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [prevRunning, setPrevRunning] = useState(false)

  useEffect(() => {
    if (dark) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [dark])

  useEffect(() => {
    const refresh = async () => {
      try {
        const r = await api.apply.status()
        const nowRunning = r.running
        setPrevRunning((prev) => {
          if (prev && !nowRunning) {
            try {
              window.dispatchEvent(new CustomEvent('app-toast', { detail: { message: '投递任务已完成', type: 'success', duration: 3000 } }))
            } catch {}
          }
          return nowRunning
        })
        setRunning(nowRunning)
      } catch {
        setPrevRunning(false)
        setRunning(false)
      }
    }
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [])

  return (
    <div className="min-h-screen flex bg-[radial-gradient(circle_at_top_left,_#e0f2ff_0,_#f5e9ff_40%,_#ffffff_100%)] dark:bg-[radial-gradient(circle_at_top,_#020617_0,_#020617_40%,_#000000_100%)]">
      <aside className="w-56 min-w-[200px] glass-card border-r border-white/60 dark:border-slate-700 flex flex-col shrink-0">
        <div className="p-5 border-b border-white/60 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">JobsDB 投递</h1>
            {running && (
              <Link
                to="/jobs"
                className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"
                title="任务运行中，点击查看"
              />
            )}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 truncate">{user?.email}</p>
          <div className="flex gap-2 mt-2">
            <button
              type="button"
              onClick={() => setDark((d) => !d)}
              className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            >
              {dark ? '浅色' : '深色'}
            </button>
            <button
              type="button"
              onClick={() => setShowHelp((h) => !h)}
              className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            >
              {showHelp ? '收起说明' : '使用说明'}
            </button>
          </div>
          {showHelp && (
            <div className="mt-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50 text-xs text-slate-600 dark:text-slate-400 space-y-2">
              <p>1. JobsDB 登录后，配置自动投递模式与排除公司</p>
              <p>2. 开启自动投递，或手动立即投递</p>
              <p>3. 职位列表查看结果，需关注的可加入黑名单</p>
              <p>4. 外部链接职位会出现在外部投递待办</p>
            </div>
          )}
        </div>
        <nav className="flex-1 p-2 overflow-y-auto">
          {navGroups.map((group) => (
            <div key={group.label} className="mb-3">
              <p className="px-4 py-1 text-xs font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                {group.label}
              </p>
              {group.items.map(({ to, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    `block px-4 py-2 rounded-2xl text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-white/80 text-brand-600 shadow-sm'
                        : 'text-slate-600 hover:bg-white/50 hover:text-slate-900'
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={onLogout}
            className="w-full px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
          >
            退出登录
          </button>
        </div>
      </aside>
      <main className="flex-1 min-w-0 overflow-auto px-4 py-6 md:px-10 md:py-10">
        <div className="max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
