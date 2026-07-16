import { useCallback, useEffect, useState } from 'react'
import {
  Activity,
  Bot,
  CheckCircle2,
  Database,
  Download,
  Eraser,
  FileClock,
  Monitor,
  RefreshCw,
  Server,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react'

import {
  clearDiagnosticsLogs,
  exportDiagnostics,
  getDiagnosticsHealth,
  getLatestDiagnostics,
} from '@/api'
import type {
  DiagnosticComponents,
  DiagnosticHealth,
  DiagnosticRequestSummary,
} from '@/types'

const componentLabels: Array<{
  key: keyof DiagnosticComponents
  label: string
  icon: typeof Server
}> = [
  { key: 'backend', label: '后端服务', icon: Server },
  { key: 'database', label: '数据库', icon: Database },
  { key: 'frontend_build', label: '前端构建', icon: Monitor },
  { key: 'provider_configured', label: '模型配置', icon: Bot },
  { key: 'state_engine', label: '状态引擎', icon: Activity },
  { key: 'log_writable', label: '日志目录', icon: FileClock },
]

function formatDuration(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(2)} 秒`
}

function HealthItem({
  label,
  healthy,
  icon: Icon,
}: {
  label: string
  healthy: boolean
  icon: typeof Server
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-tavern-border-subtle bg-tavern-bg-tertiary/30 px-3 py-2.5">
      <div className="flex items-center gap-2 text-xs text-tavern-text-secondary">
        <Icon size={14} className="text-tavern-gold-400" />
        {label}
      </div>
      <span className={`flex items-center gap-1 text-[11px] ${healthy ? 'text-emerald-300' : 'text-amber-300'}`}>
        {healthy ? <CheckCircle2 size={13} /> : <TriangleAlert size={13} />}
        {healthy ? '正常' : '需检查'}
      </span>
    </div>
  )
}

export default function DiagnosticsPanel() {
  const [health, setHealth] = useState<DiagnosticHealth | null>(null)
  const [latest, setLatest] = useState<DiagnosticRequestSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setMessage('')
    try {
      const [healthResponse, latestResponse] = await Promise.all([
        getDiagnosticsHealth(),
        getLatestDiagnostics(),
      ])
      setHealth(healthResponse.data)
      setLatest(latestResponse.data)
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || '健康检查失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleExport = async () => {
    setExporting(true)
    setMessage('')
    try {
      const response = await exportDiagnostics()
      const disposition = response.headers['content-disposition'] || ''
      const matched = disposition.match(/filename="?([^";]+)"?/i)
      const filename = matched?.[1] || `ai-tavern-diagnostics-${Date.now()}.zip`
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setMessage('诊断包已导出。可以直接把 ZIP 发给排查人员。')
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || '导出诊断包失败')
    } finally {
      setExporting(false)
    }
  }

  const handleClear = async () => {
    if (!window.confirm('清空本地诊断日志和最近请求摘要？聊天记录不会被删除。')) return
    try {
      await clearDiagnosticsLogs()
      setLatest(null)
      setMessage('诊断日志已清空。')
      await refresh()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || '清空日志失败')
    }
  }

  return (
    <section className="card-parchment mb-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-3 border-b border-tavern-border-subtle/50">
        <div className="flex items-center gap-2.5">
          <ShieldCheck size={16} className="text-tavern-gold-400" />
          <div>
            <h2 className="text-sm font-semibold text-tavern-text-primary">开发者与诊断</h2>
            <p className="text-[11px] text-tavern-text-muted mt-0.5">安全健康检查与一键诊断包</p>
          </div>
        </div>
        <button onClick={refresh} disabled={loading} className="btn btn-secondary px-3">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {health ? (
        <>
          <div className={`mb-4 rounded-xl border p-3.5 ${
            health.status === 'ok'
              ? 'border-emerald-700/30 bg-emerald-900/15'
              : 'border-amber-700/30 bg-amber-900/15'
          }`}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {health.status === 'ok' ? (
                  <CheckCircle2 size={17} className="text-emerald-300" />
                ) : (
                  <TriangleAlert size={17} className="text-amber-300" />
                )}
                <span className="text-sm text-tavern-text-primary">
                  {health.status === 'ok' ? '核心服务运行正常' : '部分项目需要检查'}
                </span>
              </div>
              <span className="text-[11px] text-tavern-text-muted">v{health.version}</span>
            </div>
            <p className="mt-2 text-[11px] text-tavern-text-muted">
              {health.mock_mode
                ? '当前使用 Mock 模式，模型请求不会产生费用。'
                : `当前服务：${health.provider || 'OpenAI Compatible'} / ${health.model || '未填写模型'}`}
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
            {componentLabels.map(({ key, label, icon }) => (
              <HealthItem key={key} label={label} healthy={health.components[key]} icon={icon} />
            ))}
          </div>
        </>
      ) : (
        <div className="mb-4 rounded-lg border border-tavern-border-subtle p-4 text-xs text-tavern-text-muted">
          {loading ? '正在检查运行状态…' : '尚未取得健康检查结果。'}
        </div>
      )}

      <div className="rounded-xl border border-tavern-border-subtle bg-tavern-bg-tertiary/20 p-3.5 mb-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <h3 className="text-xs font-semibold text-tavern-text-primary">最近一次模型请求</h3>
          {latest?.request_id && (
            <code className="text-[10px] text-tavern-gold-300">#{latest.request_id}</code>
          )}
        </div>
        {latest ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3 text-[11px]">
            <div><span className="block text-tavern-text-muted">状态</span><b className="text-tavern-text-primary">{latest.status}</b></div>
            <div><span className="block text-tavern-text-muted">首字延迟</span><b className="text-tavern-text-primary">{formatDuration(latest.timing?.first_token_ms)}</b></div>
            <div><span className="block text-tavern-text-muted">总耗时</span><b className="text-tavern-text-primary">{formatDuration(latest.timing?.total_ms)}</b></div>
            <div><span className="block text-tavern-text-muted">Prompt 估算</span><b className="text-tavern-text-primary">{latest.prompt?.estimated_tokens?.toLocaleString() || 0} tokens</b></div>
            <div><span className="block text-tavern-text-muted">世界书</span><b className="text-tavern-text-primary">{latest.prompt?.worldbook_entries || 0} 条</b></div>
            <div><span className="block text-tavern-text-muted">状态更新</span><b className="text-tavern-text-primary">{latest.state?.applied_operations || 0} 项</b></div>
            <div><span className="block text-tavern-text-muted">历史裁剪</span><b className="text-tavern-text-primary">{latest.prompt?.history_trimmed || 0} 条</b></div>
            <div><span className="block text-tavern-text-muted">流式分片</span><b className="text-tavern-text-primary">{latest.generation?.chunks || 0}</b></div>
            <div><span className="block text-tavern-text-muted">解析错误</span><b className={latest.state?.parser_errors ? 'text-amber-300' : 'text-tavern-text-primary'}>{latest.state?.parser_errors || 0}</b></div>
          </div>
        ) : (
          <p className="text-[11px] text-tavern-text-muted">还没有模型请求记录。完成一次对话后再刷新即可查看。</p>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <button onClick={handleExport} disabled={exporting} className="btn btn-primary">
          <Download size={15} />
          {exporting ? '正在生成…' : '一键导出诊断包'}
        </button>
        <button onClick={handleClear} className="btn btn-secondary text-tavern-rose-400">
          <Eraser size={14} />
          清空诊断日志
        </button>
      </div>

      <p className="mt-3 text-[10px] leading-5 text-tavern-text-muted">
        诊断包不包含完整聊天、完整 Prompt、角色卡正文、API Key 或自定义请求头值。默认仅保存运行元数据与脱敏日志。
      </p>

      {message && (
        <div className="mt-3 rounded-lg border border-tavern-border-subtle bg-tavern-bg-tertiary/30 px-3 py-2 text-[11px] text-tavern-text-secondary">
          {message}
        </div>
      )}
    </section>
  )
}
