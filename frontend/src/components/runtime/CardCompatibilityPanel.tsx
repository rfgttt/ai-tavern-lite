import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleMinus, Puzzle, ShieldAlert } from 'lucide-react'
import { getCharacterCompatibility } from '@/api'
import type { CardCompatibilityDetail, CardCompatibilityReport, CardRuntimeCheck } from '@/types'

const STATUS_LABELS: Record<string, string> = {
  supported: '可用', partial: '部分兼容', isolated: '已隔离', absent: '未检测到',
}

const fallbackDetails = (report: CardCompatibilityReport): CardCompatibilityDetail[] =>
  Object.entries(report.capabilities).map(([key, enabled]) => ({
    key,
    label: key,
    status: enabled ? 'supported' : 'absent',
    summary: enabled ? '已识别并可由安全运行时处理' : '角色卡未声明该能力',
  }))

const RUNTIME_LABELS: Record<string, string> = {
  initial_variables: '初始变量',
  patch_paths: '变量更新路径',
  read_only_macros: '只读酒馆宏',
  dynamic_templates: '动态模板',
  status_placeholder: '状态栏投影',
  external_javascript: '外部 JavaScript',
}

const StatusIcon = ({ status }: { status: CardRuntimeCheck['status'] }) =>
  status === 'supported' ? <CheckCircle2 size={13}/> :
    status === 'partial' ? <AlertTriangle size={13}/> :
      status === 'isolated' ? <ShieldAlert size={13}/> : <CircleMinus size={13}/>

export default function CardCompatibilityPanel({ characterId, onLoaded }: { characterId: string; onLoaded?: (report: CardCompatibilityReport) => void }) {
  const [report, setReport] = useState<CardCompatibilityReport | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let active = true
    void getCharacterCompatibility(characterId).then((response) => {
      if (!active) return
      setReport(response.data)
      onLoaded?.(response.data)
    }).catch(() => undefined)
    return () => { active = false }
  }, [characterId, onLoaded])

  const details = useMemo(() => report ? (report.details?.length ? report.details : fallbackDetails(report)) : [], [report])
  const runtimeChecks = useMemo(() => report ? Object.entries(report.runtime_checks || {}) : [], [report])
  if (!report) return null
  const usable = details.filter((item) => item.status === 'supported' || item.status === 'partial').length

  return (
    <section className="runtime-card compatibility-card">
      <button className="runtime-section-title w-full" onClick={() => setOpen((value) => !value)}>
        <Puzzle size={15}/><span>角色卡兼容情况</span><span className="tag ml-auto">{usable} 项可用</span>
      </button>
      <div className="compatibility-summary">
        <CheckCircle2 size={13}/><span>{report.card_format} {report.card_format_version}</span><span>·</span><span>{report.counts.enabled_lorebook_entries || 0} 条世界书</span>
      </div>
      {open ? <div className="compatibility-details">
        <div className="compatibility-capability-list">
          {details.map((item) => (
            <div key={item.key} className={`compatibility-capability is-${item.status}`}>
              <StatusIcon status={item.status}/>
              <span><strong>{item.label}</strong><small>{item.summary}</small></span>
              <i>{STATUS_LABELS[item.status] || item.status}</i>
            </div>
          ))}
        </div>
        {runtimeChecks.length ? <>
          <h4 className="compatibility-runtime-title">运行级验证</h4>
          <div className="compatibility-capability-list">
            {runtimeChecks.map(([key, check]) => (
              <div key={key} className={`compatibility-capability is-${check.status}`}>
                <StatusIcon status={check.status}/>
                <span>
                  <strong>{RUNTIME_LABELS[key] || key}</strong>
                  <small>{check.summary}</small>
                  {check.source && check.source !== 'none' ? <small>来源：{check.source}</small> : null}
                  {check.warnings?.map((warning) => <small key={warning}>⚠ {warning}</small>)}
                </span>
                <i>{STATUS_LABELS[check.status] || check.status}</i>
              </div>
            ))}
          </div>
        </> : null}
        {report.unknown_extensions.length ? <p><AlertTriangle size={12}/> 未识别扩展已原样保留：{report.unknown_extensions.join('、')}</p> : null}
        {report.unsupported.length ? <p><ShieldAlert size={12}/> 隔离能力：{report.unsupported.join('、')}</p> : null}
        {report.warnings.map((warning) => <p key={warning}>{warning}</p>)}
      </div> : null}
    </section>
  )
}
