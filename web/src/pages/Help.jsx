import { Link } from 'react-router-dom'

export default function Help() {
  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">使用说明</h1>
      <div className="glass-card mt-2 p-6 space-y-6 text-slate-700 dark:text-slate-200/80">
        <section>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">使用流程</h2>
          <ol className="list-decimal list-inside space-y-2">
            <li>JobsDB 登录 / 绑定账号</li>
            <li>在「排除公司」中配置黑名单</li>
            <li>在「自动投递」中配置模式与间隔</li>
            <li>启动自动投递，或点击「立即投递」手动运行</li>
            <li>在「职位列表」查看结果</li>
          </ol>
        </section>
        <section>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">投递模式</h2>
          <ul className="space-y-1">
            <li>• 模式一：推荐岗位，投递 JobsDB 首页推荐</li>
            <li>• 模式二：关键词，按关键词搜索</li>
            <li>• 模式三：职位类别，按 JobsDB 分类</li>
          </ul>
        </section>
        <section>
          <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">常见问题</h2>
          <dl className="space-y-2">
            <dt className="font-medium text-slate-700 dark:text-slate-300">为什么有职位被跳过？</dt>
            <dd>可能是：已投递过、公司被加入黑名单、或链接指向外部站点（需手动投递）</dd>
            <dt className="font-medium text-slate-700 dark:text-slate-300">外部投递待办是什么？</dt>
            <dd>跳转到非 JobsDB 站点的职位会记录在此，需要手动打开链接投递</dd>
          </dl>
        </section>
        <p className="pt-4">
          <Link to="/" className="text-brand-600 dark:text-brand-400 hover:underline">← 返回概览</Link>
        </p>
      </div>
    </div>
  )
}
