import { Sparkles } from 'lucide-react'
import type { RuntimeState } from '@/types'
import GenericDataPanel from '../runtime/GenericDataPanel'
import { hasContent, sanitizedCustom } from '../runtime/runtimePresentation'

export default function InlineCardState({ state }: { state?: RuntimeState }) {
  const runtimeState = state || {}
  const custom = sanitizedCustom(runtimeState.custom)
  const fallback = {
    ...(hasContent(runtimeState.scene) ? { 场景: runtimeState.scene } : {}),
    ...(hasContent(runtimeState.relationship) ? { 关系: runtimeState.relationship } : {}),
    ...(hasContent(runtimeState.character) ? { 角色: runtimeState.character } : {}),
  }
  const value = hasContent(custom) ? custom : fallback

  if (!hasContent(value)) {
    return (
      <div data-testid="inline-card-state" className="inline-card-state inline-card-state--empty">
        <Sparkles size={14}/>
        <span>角色卡状态尚未初始化；等待变量协议或剧情更新。</span>
      </div>
    )
  }

  return (
    <div data-testid="inline-card-state" className="inline-card-state">
      <GenericDataPanel
        title="角色卡状态栏"
        subtitle="原生安全模式"
        icon={<Sparkles size={15}/>}
        value={value}
      />
    </div>
  )
}
