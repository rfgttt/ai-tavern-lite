import { AlertTriangle, ExternalLink, ShieldAlert, ShieldCheck, X } from 'lucide-react'
import type { CharacterCardSecurityScan, CharacterSecurityRiskLevel } from '@/types'

interface CharacterSecurityDialogProps {
  open: boolean
  scan: CharacterCardSecurityScan | null
  busy?: boolean
  existingCharacter?: boolean
  onCancel: () => void
  onSafeCopy: () => void
  onQuarantine?: () => void
  onOriginal?: () => void
}

const riskPresentation: Record<CharacterSecurityRiskLevel, { label: string; className: string }> = {
  safe: { label: '安全', className: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10' },
  notice: { label: '需要确认', className: 'text-amber-200 border-amber-500/30 bg-amber-500/10' },
  high: { label: '高风险', className: 'text-orange-200 border-orange-500/30 bg-orange-500/10' },
  blocked: { label: '已阻止危险内容', className: 'text-red-200 border-red-500/30 bg-red-500/10' },
}

const findingTone = {
  info: 'border-slate-500/20 bg-slate-500/5',
  warning: 'border-amber-500/20 bg-amber-500/5',
  high: 'border-orange-500/25 bg-orange-500/5',
  blocked: 'border-red-500/25 bg-red-500/5',
}

export default function CharacterSecurityDialog({
  open,
  scan,
  busy = false,
  existingCharacter = false,
  onCancel,
  onSafeCopy,
  onQuarantine,
  onOriginal,
}: CharacterSecurityDialogProps) {
  if (!open || !scan) return null

  const { report } = scan
  const risk = riskPresentation[report.risk_level]
  const totalFindings = report.findings.length

  return (
    <div className="manager-scrim" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onCancel()
    }}>
      <section
        className="confirm-dialog max-w-3xl w-[min(94vw,760px)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="character-security-title"
      >
        <header>
          <div>
            {report.risk_level === 'safe' ? <ShieldCheck size={18}/> : <ShieldAlert size={18}/>} 
            <span id="character-security-title">角色卡安全检查</span>
          </div>
          <button type="button" aria-label="关闭安全检查" disabled={busy} onClick={onCancel}><X size={18}/></button>
        </header>

        <div className="confirm-dialog__body space-y-4 max-h-[75vh] overflow-y-auto scrollbar-thin">
          <div className="rounded-xl border border-tavern-border-subtle bg-tavern-bg-tertiary/30 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-tavern-text-primary">{scan.card_name}</strong>
              <span className={`text-xs px-2 py-0.5 rounded-full border ${risk.className}`}>{risk.label}</span>
            </div>
            <p className="mt-2 text-sm text-tavern-text-secondary">{report.summary}</p>
            <p className="mt-1 text-[11px] text-tavern-text-muted break-all">SHA-256：{report.card_sha256}</p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            <div className="rounded-lg border border-tavern-border-subtle p-2"><strong>{report.counts.blocked ?? 0}</strong><small className="block text-tavern-text-muted">阻止</small></div>
            <div className="rounded-lg border border-tavern-border-subtle p-2"><strong>{report.counts.high ?? 0}</strong><small className="block text-tavern-text-muted">高风险</small></div>
            <div className="rounded-lg border border-tavern-border-subtle p-2"><strong>{report.counts.warning ?? 0}</strong><small className="block text-tavern-text-muted">注意</small></div>
            <div className="rounded-lg border border-tavern-border-subtle p-2"><strong>{report.counts.external_urls ?? 0}</strong><small className="block text-tavern-text-muted">外部网址</small></div>
          </div>

          {report.prompt_injection_detected ? (
            <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100">
              <div className="flex items-center gap-2 font-medium"><AlertTriangle size={16}/>检测到 AI 提示词注入</div>
              <p className="mt-1 text-xs text-red-100/80">卡片尝试覆盖系统指令、索取敏感信息、调用工具或向外发送数据。原样导入已禁用。</p>
            </div>
          ) : null}

          {report.external_hosts.length > 0 ? (
            <div className="rounded-lg border border-tavern-border-subtle p-3">
              <div className="flex items-center gap-2 text-sm font-medium"><ExternalLink size={15}/>外部主机</div>
              <p className="mt-1 text-xs text-tavern-text-muted">扫描器没有访问这些网址。安全副本会移除可主动加载的远程资源。</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {report.external_hosts.map((host) => <code key={host} className="text-[11px] rounded bg-black/20 px-1.5 py-0.5">{host}</code>)}
              </div>
            </div>
          ) : null}

          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium">检测详情</h3>
              <span className="text-xs text-tavern-text-muted">{totalFindings} 项</span>
            </div>
            {totalFindings === 0 ? (
              <p className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm text-emerald-200">未发现主动代码、外部资源或提示词注入。</p>
            ) : (
              <div className="space-y-2">
                {report.findings.map((finding) => (
                  <article key={finding.id} className={`rounded-lg border p-3 ${findingTone[finding.severity]}`}>
                    <div className="flex items-start justify-between gap-3">
                      <strong className="text-sm">{finding.title}</strong>
                      <span className="text-[10px] uppercase text-tavern-text-muted">{finding.severity}</span>
                    </div>
                    <p className="mt-1 text-xs text-tavern-text-secondary">{finding.message}</p>
                    <code className="mt-1 block text-[10px] text-tavern-text-muted break-all">{finding.path}</code>
                    {finding.evidence ? <pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap break-words rounded bg-black/20 p-2 text-[10px] text-tavern-text-muted">{finding.evidence}</pre> : null}
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-tavern-border-subtle p-3">
            <h3 className="text-sm font-medium">扫描器保证</h3>
            <ul className="mt-1 space-y-1 text-xs text-tavern-text-muted">
              {report.scanner_guarantees.map((item) => <li key={item}>• {item}</li>)}
            </ul>
          </div>

          <div className="confirm-dialog__actions flex-wrap">
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={onCancel}>取消</button>
            {!existingCharacter && onQuarantine ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy || !report.can_import_safe}
                title={report.can_import_safe ? '保留原卡数据，但禁止创建会话' : '角色卡结构过深或过大，不能保存'}
                onClick={onQuarantine}
              >隔离保存</button>
            ) : null}
            {!existingCharacter && onOriginal ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy || !report.can_import_original}
                title={report.can_import_original ? '保留原卡数据；平台仍不会执行脚本' : '高风险卡片不能原样导入'}
                onClick={onOriginal}
              >原样导入</button>
            ) : null}
            <button type="button" className="btn btn-primary" disabled={busy || !report.can_import_safe} onClick={onSafeCopy}>
              {busy ? '处理中…' : existingCharacter ? '生成安全副本' : '安全导入（推荐）'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
