import { useState, useEffect } from 'react'
import { api } from '../api'
import { PageLoading } from '../components/PageLoading'
import { showToast } from '../utils/toast'

export default function ExcludedCompanies() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [companies, setCompanies] = useState([])
  const [inputValue, setInputValue] = useState('')

  const fetchList = () => {
    api.excludedCompanies
      .get()
      .then((r) => {
        const list = r.companies || []
        setCompanies(list)
        setInputValue(list.join('\n'))
      })
      .catch(() => {
        setCompanies([])
        setInputValue('')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchList()
  }, [])

  const handleSave = async () => {
    const items = inputValue
      .split(/[\n,，；;]+/)
      .map((x) => x.trim())
      .filter(Boolean)
    setSaving(true)
    try {
      await api.excludedCompanies.update(items.length ? items : ['MOMAX', 'AIA', 'Prudential'])
      fetchList()
      showToast('保存成功', 'success')
    } catch (e) {
      showToast(e.message || '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleLoad = () => {
    setInputValue(companies.join('\n'))
  }

  const handleAddFromText = () => {
    const items = inputValue
      .split(/[\n,，；;]+/)
      .map((x) => x.trim())
      .filter(Boolean)
    const merged = [...new Set([...companies, ...items])]
    setCompanies(merged)
    setInputValue(merged.join('\n'))
  }

  if (loading) return <PageLoading />

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="mb-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">排除公司</h1>
        <p className="text-slate-600 dark:text-slate-200 mt-1">
          填入公司名称后，自动投递与手动投递均会跳过这些公司，每行一个或逗号分隔
        </p>
      </div>

      <div className="glass-card p-6 space-y-6">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">黑名单公司</label>
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="MOMAX&#10;AIA&#10;Prudential&#10;..."
            rows={12}
            className="w-full px-4 py-3 rounded-lg border border-slate-300 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-brand-500 font-mono text-sm"
          />
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
            支持换行、逗号、分号分隔。留空保存将恢复默认：MOMAX, AIA, Prudential
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white font-medium"
          >
            {saving ? '保存中…' : '保存'}
          </button>
          <button
            onClick={() => setInputValue(companies.join('\n'))}
            className="px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            恢复已保存
          </button>
          <button
            onClick={handleAddFromText}
            className="px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
          >
            合并到当前列表
          </button>
        </div>
      </div>
    </div>
  )
}
