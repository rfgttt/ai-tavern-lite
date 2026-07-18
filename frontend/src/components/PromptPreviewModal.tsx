import { useEffect, useState } from 'react'
import {
  BookOpen,
  Brain,
  Check,
  Copy,
  FileText,
  History,
  Maximize2,
  Minimize2,
  X,
} from 'lucide-react'
import { previewPrompt } from '@/api'
import type { PromptPreview } from '@/types'

interface Props {
  sessionId: string
  message: string
  onClose: () => void
}

interface TextViewerProps {
  content: string
  ariaLabel: string
  compact?: boolean
}

const reasonLabels: Record<string, string> = {
  included: '已注入',
  included_partial: '部分注入',
  context_budget: '上下文预算不足',
  empty: '内容为空',
  already_in_history_or_empty: '已在历史中或内容为空',
  disabled: '已禁用',
  entry_limit: '超过记忆条数上限',
  memory_budget_partial: '记忆预算内部分注入',
  memory_budget: '记忆预算不足',
  not_rendered: '未进入渲染结果',
  empty_content: '内容为空',
  no_primary_match: '关键词未命中',
  no_secondary_match: '次级关键词未命中',
  probability_or_duplicate_filter: '概率检查或重复内容过滤',
}

const scopeLabels: Record<string, string> = {
  global: '全局',
  character: '角色共享',
  session: '会话专属',
}

const loreKindLabels: Record<string, string> = {
  character_core: '角色核心',
  runtime_protocol: '运行协议',
  world: '世界书',
}

function reasonLabel(reason: string) {
  return reasonLabels[reason] || reason || '未知'
}

function ScrollableText({ content, ariaLabel, compact = false }: TextViewerProps) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyContent = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  if (!content) {
    return <p className="text-xs text-tavern-text-muted italic py-1">（空）</p>
  }

  return (
    <div className="rounded-lg border border-tavern-border-subtle/50 bg-tavern-bg-deepest/60 overflow-hidden">
      <div className="flex items-center justify-end gap-1 px-2 py-1 border-b border-tavern-border-subtle/40 bg-tavern-bg-deepest/35">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="btn-icon p-1"
          aria-label={`${expanded ? '收起' : '展开'}${ariaLabel}`}
          title={expanded ? '恢复默认高度' : '展开内容区域'}
        >
          {expanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </button>
        <button
          type="button"
          onClick={() => void copyContent()}
          className="btn-icon p-1"
          aria-label={`复制${ariaLabel}`}
          title="复制完整内容"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
      </div>
      <pre
        className={`scrollbar-thin overflow-auto whitespace-pre-wrap break-words text-xs text-tavern-text-secondary leading-relaxed p-3 ${
          expanded ? 'max-h-[62vh]' : compact ? 'max-h-44' : 'max-h-72'
        }`}
        aria-label={ariaLabel}
      >
        {content}
      </pre>
    </div>
  )
}

export default function PromptPreviewModal({ sessionId, message, onClose }: Props) {
  const [data, setData] = useState<PromptPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void loadPreview()
  }, [sessionId, message])

  const loadPreview = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await previewPrompt(sessionId, message)
      setData(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const summary = data?.inspection?.summary
  const usagePercent = data
    ? summary?.usage_percent
      ?? Math.min(100, (data.total_estimated_tokens / Math.max(1, data.context_budget)) * 100)
    : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 md:p-5 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-tavern-bg-secondary/95 backdrop-blur-md border border-tavern-border-subtle rounded-2xl w-full max-w-6xl max-h-[92vh] flex flex-col shadow-large animate-slide-up">
        <div className="flex items-center justify-between px-5 py-4 border-b border-tavern-border-subtle">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-tavern-gold-900/30 flex items-center justify-center">
              <FileText size={16} className="text-tavern-gold-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-tavern-text-primary">Prompt 上下文检查器</h3>
              <p className="text-[11px] text-tavern-text-muted">只读解释当前 Prompt，不改变实际生成行为</p>
            </div>
          </div>
          <button onClick={onClose} className="btn-icon p-1.5" aria-label="关闭 Prompt 检查器">
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 md:p-5 space-y-4 scrollbar-thin">
          {loading && (
            <div className="text-center py-12">
              <div className="generating-dots justify-center mb-3"><span /><span /><span /></div>
              <p className="text-sm text-tavern-text-muted">正在检查 Prompt...</p>
            </div>
          )}

          {error && <div className="text-center py-8"><p className="text-tavern-rose-400 text-sm">{error}</p></div>}

          {data && (
            <>
              <section className="card-parchment" aria-label="Prompt Token 摘要">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm mb-3">
                  <div><p className="text-[11px] text-tavern-text-muted">上下文窗口</p><p className="font-semibold">{(summary?.context_window ?? data.context_budget).toLocaleString()}</p></div>
                  <div><p className="text-[11px] text-tavern-text-muted">预留输出</p><p className="font-semibold">{(summary?.reserved_output_tokens ?? 0).toLocaleString()}</p></div>
                  <div><p className="text-[11px] text-tavern-text-muted">输入预算</p><p className="font-semibold">{(summary?.input_budget ?? data.context_budget).toLocaleString()}</p></div>
                  <div><p className="text-[11px] text-tavern-text-muted">预估输入</p><p className="font-semibold">{data.total_estimated_tokens.toLocaleString()}</p></div>
                  <div><p className="text-[11px] text-tavern-text-muted">剩余预算</p><p className="font-semibold">{(summary?.remaining_tokens ?? Math.max(0, data.context_budget - data.total_estimated_tokens)).toLocaleString()}</p></div>
                </div>
                <div className="w-full h-1.5 bg-tavern-bg-tertiary/60 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(100, usagePercent)}%`,
                      background: usagePercent > 80
                        ? 'linear-gradient(90deg, #b85c6e, #d47a8a)'
                        : 'linear-gradient(90deg, #c47424, #e6a94a)',
                    }}
                  />
                </div>
                <p className="text-[11px] text-tavern-text-muted mt-1.5 text-right">已使用 {usagePercent.toFixed(1)}%</p>
              </section>

              {data.section_content_complete === false && (
                <div className="rounded-lg border border-tavern-gold-700/40 bg-tavern-gold-900/15 px-3 py-2 text-xs text-tavern-text-secondary">
                  当前为生产环境安全预览，最终区块只返回前 500 个字符。开发模式会返回完整内容。
                </div>
              )}

              {data.inspection && (
                <>
                  <section className="card-parchment" aria-label="Prompt 区块预算">
                    <div className="flex items-center gap-2 mb-3"><FileText size={15} /><h4 className="text-sm font-semibold">区块预算与裁剪</h4></div>
                    <div className="grid md:grid-cols-2 gap-2">
                      {data.inspection.sections.map((section) => (
                        <div key={section.key} className="rounded-lg border border-tavern-border-subtle/60 bg-tavern-bg-deepest/35 p-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-sm text-tavern-text-primary">{section.name}</span>
                            <span className="text-[11px] text-tavern-text-muted">{section.estimated_tokens} / {section.budget_tokens || '动态'} tokens</span>
                          </div>
                          <p className="text-[11px] mt-1 text-tavern-text-muted">{reasonLabel(section.reason)}{section.source ? ` · ${section.source}` : ''}</p>
                        </div>
                      ))}
                    </div>
                  </section>

                  <section className="card-parchment" aria-label="聊天历史检查">
                    <div className="flex items-center gap-2 mb-3"><History size={15} /><h4 className="text-sm font-semibold">聊天历史</h4></div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
                      <div><p className="text-tavern-text-muted">总消息</p><p className="text-sm font-medium">{data.inspection.history.total_messages}</p></div>
                      <div><p className="text-tavern-text-muted">本轮保留</p><p className="text-sm font-medium">{data.inspection.history.included_messages}</p></div>
                      <div><p className="text-tavern-text-muted">被裁剪</p><p className="text-sm font-medium">{data.inspection.history.trimmed_messages}</p></div>
                      <div><p className="text-tavern-text-muted">历史预算</p><p className="text-sm font-medium">{data.inspection.history.budget_tokens}</p></div>
                      <div><p className="text-tavern-text-muted">最早序号</p><p className="text-sm font-medium">{data.inspection.history.earliest_included_sequence ?? '—'}</p></div>
                    </div>
                  </section>

                  <details className="card-parchment" open={data.inspection.memories.length > 0}>
                    <summary className="cursor-pointer flex items-center gap-2 text-sm font-semibold"><Brain size={15} />长期记忆明细（{data.inspection.memories.length}）</summary>
                    <div className="mt-3 space-y-2">
                      {data.inspection.memories.length === 0 && <p className="text-xs text-tavern-text-muted">当前作用域没有记忆。</p>}
                      {data.inspection.memories.map((memory) => (
                        <div key={memory.id} className="rounded-lg border border-tavern-border-subtle/60 bg-tavern-bg-deepest/35 p-3">
                          <div className="flex flex-wrap items-center gap-2 text-[11px] text-tavern-text-muted mb-2">
                            <span>{scopeLabels[memory.scope] || memory.scope}</span><span>·</span><span>{memory.category}</span><span>·</span><span>重要度 {memory.importance.toFixed(2)}</span><span>·</span><span>{reasonLabel(memory.reason)}</span>
                          </div>
                          <ScrollableText content={memory.content} ariaLabel={`记忆 ${memory.id}`} compact />
                        </div>
                      ))}
                    </div>
                  </details>

                  <details className="card-parchment" open={data.inspection.lorebook.some((entry) => entry.triggered)}>
                    <summary className="cursor-pointer flex items-center gap-2 text-sm font-semibold"><BookOpen size={15} />世界书检查（{data.inspection.lorebook.length}）</summary>
                    <div className="mt-3 space-y-3">
                      {data.inspection.lorebook.length === 0 && <p className="text-xs text-tavern-text-muted">角色卡没有世界书条目。</p>}
                      {data.inspection.lorebook.map((entry, index) => (
                        <div key={`${entry.id}-${index}`} className="rounded-lg border border-tavern-border-subtle/60 bg-tavern-bg-deepest/35 p-3 space-y-2.5">
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-xs font-medium text-tavern-text-primary">{entry.title}</p>
                            <span className="text-[11px] text-tavern-text-muted shrink-0">{reasonLabel(entry.reason)}</span>
                          </div>
                          <p className="text-[11px] text-tavern-text-muted">
                            {loreKindLabels[entry.kind] || entry.kind} · {entry.constant ? '常驻' : '关键词触发'} · 概率 {entry.probability}% · 原文 {entry.content_characters} 字符 · 实际注入 {entry.injected_characters} 字符
                          </p>
                          {entry.matched_keys.length > 0 && <p className="text-[11px] text-tavern-text-muted">命中关键词：{entry.matched_keys.join('、')}</p>}
                          <div>
                            <p className="text-[11px] text-tavern-text-muted mb-1">条目原文</p>
                            <ScrollableText content={entry.content} ariaLabel={`${entry.title}条目原文`} compact />
                          </div>
                          {entry.resolved_content !== entry.content && (
                            <div>
                              <p className="text-[11px] text-tavern-text-muted mb-1">宏替换后内容</p>
                              <ScrollableText content={entry.resolved_content} ariaLabel={`${entry.title}宏替换后内容`} compact />
                            </div>
                          )}
                          {entry.injected_content && (
                            <div>
                              <p className="text-[11px] text-tavern-text-muted mb-1">本轮实际注入片段</p>
                              <ScrollableText content={entry.injected_content} ariaLabel={`${entry.title}实际注入片段`} compact />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </details>
                </>
              )}

              <details className="card-parchment" open>
                <summary className="cursor-pointer text-sm font-semibold">查看最终 Prompt 区块内容</summary>
                <p className="text-[11px] text-tavern-text-muted mt-2">
                  每个区块独立滚动；“聊天历史”中的方括号角色和序号仅用于检查器展示，不会作为额外文本发送给模型。
                </p>
                <div className="space-y-3 mt-3">
                  {data.sections.map((section, idx) => (
                    <div key={`${section.name}-${idx}`} className="rounded-lg border border-tavern-border-subtle/60 bg-tavern-bg-deepest/35 p-3.5">
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <h4 className="text-sm font-medium text-tavern-gold-300/90">{section.name}</h4>
                        <div className="flex items-center gap-2 text-[11px] text-tavern-text-muted">
                          <span>{section.estimated_tokens} tokens</span>
                          {section.source && <><span>·</span><span>{section.source}</span></>}
                        </div>
                      </div>
                      <ScrollableText content={section.content} ariaLabel={`${section.name}完整内容`} />
                    </div>
                  ))}
                </div>
              </details>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
