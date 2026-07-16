import { useState, useEffect } from 'react'
import { X, FileText } from 'lucide-react'
import { previewPrompt } from '@/api'
import type { PromptPreview } from '@/types'

interface Props {
  sessionId: string
  message: string
  onClose: () => void
}

export default function PromptPreviewModal({ sessionId, message, onClose }: Props) {
  const [data, setData] = useState<PromptPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadPreview()
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

  const usagePercent = data
    ? Math.min(100, (data.total_estimated_tokens / data.context_budget) * 100)
    : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-tavern-bg-secondary/95 backdrop-blur-md border border-tavern-border-subtle rounded-2xl w-full max-w-3xl max-h-[80vh] flex flex-col shadow-large animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-tavern-border-subtle">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-tavern-gold-900/30 flex items-center justify-center">
              <FileText size={16} className="text-tavern-gold-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-tavern-text-primary">Prompt 构成预览</h3>
              <p className="text-[11px] text-tavern-text-muted">查看当前发送的完整提示词结构</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="btn-icon p-1.5"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 scrollbar-thin">
          {loading && (
            <div className="text-center py-12">
              <div className="generating-dots justify-center mb-3">
                <span /><span /><span />
              </div>
              <p className="text-sm text-tavern-text-muted">正在构建 Prompt...</p>
            </div>
          )}

          {error && (
            <div className="text-center py-8">
              <p className="text-tavern-rose-400 text-sm">{error}</p>
            </div>
          )}

          {data && (
            <>
              {/* Token summary */}
              <div className="card-parchment">
                <div className="flex items-center justify-between text-sm mb-3">
                  <div>
                    <span className="text-tavern-text-muted">预估 Token</span>
                    <span className="text-tavern-text-primary font-semibold ml-2">
                      {data.total_estimated_tokens.toLocaleString()}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-tavern-text-muted">上下文预算</span>
                    <span className="text-tavern-text-primary font-semibold ml-2">
                      {data.context_budget.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="w-full h-1.5 bg-tavern-bg-tertiary/60 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${usagePercent}%`,
                      background: usagePercent > 80
                        ? 'linear-gradient(90deg, #b85c6e, #d47a8a)'
                        : 'linear-gradient(90deg, #c47424, #e6a94a)',
                    }}
                  />
                </div>
                <p className="text-[11px] text-tavern-text-muted mt-1.5 text-right">
                  已使用 {usagePercent.toFixed(1)}%
                </p>
              </div>

              {/* Sections */}
              <div className="space-y-2.5">
                {data.sections.map((section, idx) => (
                  <div key={idx} className="card-parchment !p-3.5">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-medium text-tavern-gold-300/90">
                        {section.name}
                      </h4>
                      <div className="flex items-center gap-2 text-[11px] text-tavern-text-muted">
                        <span>{section.estimated_tokens} tokens</span>
                        {section.source && (
                          <>
                            <span className="text-tavern-border-default">·</span>
                            <span className="text-tavern-text-muted/70">{section.source}</span>
                          </>
                        )}
                      </div>
                    </div>
                    {section.content ? (
                      <pre className="text-xs text-tavern-text-secondary bg-tavern-bg-deepest/60 p-2.5 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed border border-tavern-border-subtle/50">
                        {section.content}
                      </pre>
                    ) : (
                      <p className="text-xs text-tavern-text-muted italic py-1">（空）</p>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
