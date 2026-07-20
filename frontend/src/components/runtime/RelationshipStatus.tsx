import { MessageCircleHeart } from 'lucide-react'
import type { RelationshipRuntimeState, TurnRuntime } from '@/types'
import { activityForRoots, activityLabel, changedFromInitial, hasContent, isRecord } from './runtimePresentation'

interface Props {
  relationship?: RelationshipRuntimeState
  initialRelationship?: RelationshipRuntimeState
  timeline: TurnRuntime[]
  declared?: boolean
}

const LABELS: Record<string, string> = {
  affection: '好感', trust: '信任', tension: '张力', stage: '关系阶段', attitude: '态度',
  recent_reason: '最近原因', intimacy: '亲密度', respect: '尊重', fear: '害怕值', loyalty: '忠诚',
  dependence: '依赖值', dependency: '依赖值',
}

const Meter = ({ label, value }: { label: string; value: number }) => {
  const percent = Math.max(0, Math.min(100, value))
  return (
    <div className="runtime-meter">
      <div className="runtime-meter__head"><span>{label}</span><strong>{value}</strong></div>
      <div className="runtime-meter__track"><div className="runtime-meter__fill" style={{ width: `${percent}%` }}/></div>
    </div>
  )
}

export default function RelationshipStatus({ relationship, initialRelationship, timeline, declared = false }: Props) {
  const current = isRecord(relationship) ? relationship : {}
  const initial = isRecord(initialRelationship) ? initialRelationship : {}
  const activity = activityForRoots(timeline, ['relationship', 'relation', '关系', '人际关系'])
  const changed = changedFromInitial(current, initial) || activity.changed
  if (!declared && !changed) return null

  const entries = Object.entries(current).filter(([key, value]) => key !== 'recent_reason' && hasContent(value))
  const reason = String(current.recent_reason || activity.event || '').trim()
  const cardDefined = entries.some(([key, value]) => {
    if (!['affection', 'trust', 'tension', 'stage'].includes(key)) return true
    if (key === 'stage') return String(value) !== '初识'
    return Number(value) !== 0
  })
  const initialized = changed || cardDefined

  return (
    <section className="runtime-card">
      <div className="runtime-section-title">
        <MessageCircleHeart size={15}/><span>关系状态</span>
        <span className={`tag ml-auto ${activity.changed ? 'tag-gold' : ''}`}>{activity.changed ? activityLabel(activity) : initialized ? '角色卡初始状态' : '尚未收到更新'}</span>
      </div>
      {!initialized ? (
        <div className="runtime-uninitialized compact">
          <strong>已检测到关系变量</strong>
          <p>角色卡声明了关系系统，但目前还没有收到真实关系更新。平台不会再用固定的 0/0/0 仪表盘冒充变化。</p>
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map(([key, value]) => {
            const label = LABELS[key] || key
            if (typeof value === 'number' && value >= 0 && value <= 100) return <Meter key={key} label={label} value={value}/>
            return <div className="generic-data-row" key={key}><span>{label}</span><strong>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</strong></div>
          })}
          {reason ? <p className="runtime-note">变化原因：{reason}</p> : <p className="runtime-note">来源：{changed ? '本轮结构化状态补丁' : '角色卡初始变量'}。</p>}
        </div>
      )}
    </section>
  )
}
