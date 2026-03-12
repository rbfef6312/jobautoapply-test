export function PageLoading() {
  return (
    <div className="min-h-[200px] flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-slate-500">
        <div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full" />
        <span className="text-sm">加载中…</span>
      </div>
    </div>
  )
}

