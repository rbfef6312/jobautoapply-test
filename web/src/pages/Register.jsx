import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Register() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const { register } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!email || !password) {
      setError('请填写邮箱和密码')
      return
    }
    try {
      await register(email, password, name)
      navigate('/')
    } catch (err) {
      setError(err.message || '注册失败')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <h1 className="text-2xl font-bold text-slate-800 text-center">创建账号</h1>
          <p className="text-slate-500 text-center mt-1 text-sm">加入 JobsDB 自动投递</p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            {error && (
              <div className="p-3 rounded-lg bg-red-50 text-red-600 text-sm">{error}</div>
            )}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">邮箱</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">昵称（选填）</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-3 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition"
                placeholder="你的名字"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">密码</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 rounded-lg border border-slate-300 focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              className="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium transition-colors"
            >
              注册
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            已有账号？{' '}
            <Link to="/login" className="text-brand-600 hover:underline font-medium">
              登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
