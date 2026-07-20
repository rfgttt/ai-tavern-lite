import { ChevronLeft, ChevronRight, Heart, MapPin, Moon, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { RuntimeState } from '@/types'
import GenericDataPanel from '../runtime/GenericDataPanel'
import { hasContent, isRecord, sanitizedCustom } from '../runtime/runtimePresentation'

const numberValue = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

const Meter = ({ label, value, tone }: { label: string; value: number; tone: string }) => {
  const percent = Math.max(0, Math.min(100, value))
  return (
    <div className={`card-emulation-meter card-emulation-meter--${tone}`}>
      <div><span>{label}</span><strong>{value}</strong></div>
      <i><b style={{ width: `${percent}%` }}/></i>
    </div>
  )
}

export default function InlineCardState({ state }: { state?: RuntimeState }) {
  const runtimeState = state || {}
  const relationship = isRecord(runtimeState.relationship) ? runtimeState.relationship : {}
  const scene = isRecord(runtimeState.scene) ? runtimeState.scene : {}
  const character = isRecord(runtimeState.character) ? runtimeState.character : {}
  const characterName = hasContent(character.name) ? String(character.name) : '角色'
  const affection = numberValue(relationship.affection)
  const fear = numberValue(relationship.fear)
  const dependence = numberValue(relationship.dependence ?? relationship.dependency)
  const injuries = Array.isArray(character.injuries) ? character.injuries.filter(hasContent).map(String) : []
  const memories = Array.isArray(character.important_memories)
    ? character.important_memories.filter(hasContent).map(String)
    : []
  const [memoryIndex, setMemoryIndex] = useState(0)
  const safeMemoryIndex = Math.min(memoryIndex, Math.max(0, memories.length - 1))

  const hasNativeCardShape = Boolean(
    affection != null || fear != null || dependence != null || injuries.length || memories.length || hasContent(scene)
  )
  const fallback = useMemo(() => {
    const custom = sanitizedCustom(runtimeState.custom)
    return hasContent(custom) ? custom : {
      ...(hasContent(runtimeState.scene) ? { 场景: runtimeState.scene } : {}),
      ...(hasContent(runtimeState.relationship) ? { 关系: runtimeState.relationship } : {}),
      ...(hasContent(runtimeState.character) ? { 角色: runtimeState.character } : {}),
    }
  }, [runtimeState])

  if (!hasNativeCardShape && !hasContent(fallback)) {
    return (
      <div data-testid="inline-card-state" className="inline-card-state inline-card-state--empty">
        <Moon size={14}/>
        <span>角色卡状态尚未初始化；等待变量协议或剧情更新。</span>
      </div>
    )
  }

  if (!hasNativeCardShape) {
    return (
      <div data-testid="inline-card-state" className="inline-card-state">
        <GenericDataPanel title="角色卡状态栏" subtitle="原生安全模式" icon={<Moon size={15}/>} value={fallback}/>
      </div>
    )
  }

  return (
    <section data-testid="inline-card-state" className="inline-card-state card-emulation-status">
      <header>
        <span className="card-emulation-moon"><Moon size={18}/></span>
        <div><strong>{characterName} · 状态栏</strong><small>原生安全还原 · 不执行卡片脚本</small></div>
      </header>

      {hasContent(scene) ? (
        <div className="card-emulation-scene">
          <MapPin size={14}/>
          <span>{String(scene.date || '日期未记录')}</span>
          <span>{String(scene.time || '时间未记录')}</span>
          <strong>{String(scene.location || '地点未记录')}</strong>
        </div>
      ) : null}

      <div className="card-emulation-meters">
        {affection != null ? <Meter label="好感度" value={affection} tone="affection"/> : null}
        {fear != null ? <Meter label="害怕值" value={fear} tone="fear"/> : null}
        {dependence != null ? <Meter label="依赖值" value={dependence} tone="dependence"/> : null}
      </div>

      {injuries.length ? (
        <div className="card-emulation-section">
          <div className="card-emulation-title"><ShieldAlert size={13}/><span>身上的伤</span><small>{injuries.length}</small></div>
          <div className="card-emulation-injuries">{injuries.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}</div>
        </div>
      ) : null}

      {memories.length ? (
        <div className="card-emulation-section">
          <div className="card-emulation-title">
            <Heart size={13}/><span>重要记忆</span>
            <div className="card-emulation-pages">
              <button aria-label="上一条记忆" disabled={safeMemoryIndex === 0} onClick={() => setMemoryIndex((value) => Math.max(0, value - 1))}><ChevronLeft size={13}/></button>
              <small>{safeMemoryIndex + 1} / {memories.length}</small>
              <button aria-label="下一条记忆" disabled={safeMemoryIndex >= memories.length - 1} onClick={() => setMemoryIndex((value) => Math.min(memories.length - 1, value + 1))}><ChevronRight size={13}/></button>
            </div>
          </div>
          <p className="card-emulation-memory">{memories[safeMemoryIndex]}</p>
        </div>
      ) : null}
    </section>
  )
}
