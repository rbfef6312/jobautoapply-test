import { useState, useEffect } from 'react'
import { api } from '../api'
import { showToast } from '../utils/toast'

export default function JobsDBLogin() {
  const [step, setStep] = useState(1)
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState(null)

  useEffect(() => {
    api.jobsdb.status().then(setStatus).catch(() => setStatus({ logged_in: false, email: '' }))
  }, [step])

  const handleSendCode = async () => {
    if (!email.trim()) return
    setError('')
    setLoading(true)
    try {
      api.logReport('jobsdb_send_code', `email=${email.trim().slice(0, 5)}***`).catch(() => {})
      await api.jobsdb.loginStart(email.trim())
      setStep(2)
    } catch (e) {
      setError(e.message || '发送失败')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async () => {
    if (!code.trim()) return
    setError('')
    setLoading(true)
    try {
      api.logReport('jobsdb_verify_code', '输入验证码').catch(() => {})
      await api.jobsdb.loginVerify(code.trim())
      const s = await api.jobsdb.status()
      setStatus(s)
      setStep(1)
      setEmail('')
      setCode('')
    } catch (e) {
      setError(e.message || '验证失败')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    if (!confirm('确定注销当前 JobsDB 账号？注销后可切换到其他账号登录。')) return
    try {
      await api.jobsdb.logout()
      setStatus({ logged_in: false, email: '' })
      setStep(1)
      setEmail('')
      setCode('')
    } catch (e) {
      showToast(e.message || '注销失败', 'error')
    }
  }

  const isLoggedIn = status?.logged_in && status?.email

  return (
    <div className="p-8 max-w-md mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800">JobsDB 登录</h1>
        <p className="text-slate-500 mt-1">
          通过邮箱验证码登录 JobsDB，系统将保存登录状态用于自动投递
        </p>
      </div>

      {isLoggedIn && (
        <div className="mb-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center text-white">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </span>
            <div>
              <p className="font-medium text-emerald-800">JobsDB 账号已登录</p>
              <p className="text-sm text-emerald-600">{status.email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 text-sm font-medium"
          >
            注销
          </button>
        </div>
      )}

      {!isLoggedIn && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          {step === 1 ? (
            <>
              <label className="block text-sm font-medium text-slate-700 mb-2">JobsDB 注册邮箱</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full px-4 py-3 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none"
              />
              {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
              <button
                onClick={handleSendCode}
                disabled={loading || !email.trim()}
                className="mt-4 w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium transition-colors"
              >
                {loading ? '正在发送验证码…' : '发送验证码'}
              </button>
            </>
          ) : (
            <>
              <p className="text-sm text-slate-600 mb-2">
                验证码已发送至 <strong>{email}</strong>，请查收后输入 6 位验证码
              </p>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode((e.target.value || '').replace(/\D/g, '').slice(0, 6))}
                placeholder="请输入 6 位数字验证码"
                maxLength={6}
                className="w-full px-4 py-3 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none text-center text-lg tracking-widest"
              />
              {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
              <div className="mt-4 flex gap-2">
                <button
                  onClick={() => { setStep(1); setError(''); }}
                  className="flex-1 py-3 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  更换邮箱
                </button>
                <button
                  onClick={handleVerify}
                  disabled={loading || code.length < 6}
                  className="flex-1 py-3 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium transition-colors"
                >
                  {loading ? '登录中…' : '完成登录'}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
