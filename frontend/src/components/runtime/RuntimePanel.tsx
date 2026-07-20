import { useMemo, useState } from 'react'
import { Code2, RefreshCcw, ShieldCheck, X } from 'lucide-react'
import { useAppStore } from '@/stores/appStore'
import AdventureSetupModal from './AdventureSetupModal'
import BattleMap from './BattleMap'
import CardCompatibilityPanel from './CardCompatibilityPanel'
import CardStateSections from './CardStateSections'
import EventTimeline from './EventTimeline'
import GenericDataPanel from './GenericDataPanel'
import LorebookActivity from './LorebookActivity'
import ManifestPanel from './ManifestPanel'
import RelationshipStatus from './RelationshipStatus'
import RpgStatus from './RpgStatus'
import SceneStatus from './SceneStatus'
import StateSchemaPanel from './StateSchemaPanel'
import StateAliasRegistryPanel from './StateAliasRegistryPanel'
import { battleFromState } from './utils'
import { changedFromInitial, hasContent } from './runtimePresentation'
import type { CardCompatibilityReport } from '@/types'

export default function RuntimePanel() {
  const selectedCharacter = useAppStore((state) => state.selectedCharacter)
  const currentSession = useAppStore((state) => state.currentSession)
  const runtime = useAppStore((state) => state.runtime)
  const timeline = useAppStore((state) => state.timeline)
  const activeLorebook = useAppStore((state) => state.activeLorebook)
  const runtimeLoading = useAppStore((state) => state.runtimeLoading)
  const runtimeDrawerOpen = useAppStore((state) => state.runtimeDrawerOpen)
  const generatingMessageId = useAppStore((state) => state.generatingMessageId)
  const replaceRuntimeState = useAppStore((state) => state.replaceRuntimeState)
  const rollbackToMessage = useAppStore((state) => state.rollbackToMessage)
  const toggleRuntimeDrawer = useAppStore((state) => state.toggleRuntimeDrawer)
  const [setupOpen, setSetupOpen] = useState(false)
  const [compatibility, setCompatibility] = useState<CardCompatibilityReport | null>(null)

  const state = runtime?.state || {}
  const initialState = runtime?.initial_state || {}
  const profile = runtime?.profile
  const battle = battleFromState(state)
  const adventure = profile?.mode === 'adventure'
  const relationshipDeclared = Boolean(
    compatibility?.capabilities.relationship_state || profile?.capabilities?.relationship_state
  )
  const showRpg = adventure && (
    changedFromInitial(state.player, initialState.player) ||
    changedFromInitial(state.custom, initialState.custom) ||
    hasContent(state.combat) && changedFromInitial(state.combat, initialState.combat)
  )
  const rawDeveloperData = useMemo(() => ({
    profile,
    revision: runtime?.revision ?? 0,
    state,
  }), [profile, runtime?.revision, state])
  const hasCardStateEmulation = Boolean(
    profile?.capabilities?.mvu_state || profile?.capabilities?.status_placeholder || profile?.emulation?.status_panel?.enabled
  )

  const restoreInitialCardState = async () => {
    if (!runtime || runtimeLoading) return
    const confirmed = window.confirm('将当前角色状态恢复为角色卡初始变量。聊天记录不会删除，但当前数值进度会被重置。继续吗？')
    if (!confirmed) return
    await replaceRuntimeState(runtime.initial_state)
  }

  if (!selectedCharacter || !currentSession) return null

  return (
    <>
      {runtimeDrawerOpen ? <button className="runtime-drawer-scrim lg:hidden" aria-label="关闭状态面板" onClick={() => toggleRuntimeDrawer(false)}/> : null}
      <aside className={`runtime-panel ${runtimeDrawerOpen ? 'runtime-panel--open' : ''}`}>
        <div className="runtime-panel__head">
          <div className="runtime-avatar">
            {selectedCharacter.avatar_path ? <img src={selectedCharacter.avatar_path} alt=""/> : <span>{selectedCharacter.name.charAt(0)}</span>}
            <i className={generatingMessageId ? 'is-generating' : ''}/>
          </div>
          <div className="min-w-0 flex-1">
            <strong className="truncate block">{selectedCharacter.name}</strong>
            <span>角色卡驱动状态 · 版本 {runtime?.revision ?? 0}</span>
          </div>
          <button className="lg:hidden" onClick={() => toggleRuntimeDrawer(false)}><X size={17}/></button>
        </div>

        <div className="runtime-panel__scroll">
          <SceneStatus state={state} initialState={initialState} timeline={timeline} scenario={selectedCharacter.scenario}/>

          <CardCompatibilityPanel characterId={selectedCharacter.id} onLoaded={setCompatibility}/>
          <StateSchemaPanel schema={profile?.state_schema} validation={runtime?.schema_validation}/>
          <StateAliasRegistryPanel characterId={selectedCharacter.id}/>
          <ManifestPanel manifest={compatibility?.ui_manifest} state={state}/>

          {hasCardStateEmulation ? (
            <section className="runtime-card runtime-native-emulation-actions">
              <div className="runtime-section-title"><RefreshCcw size={15}/><span>角色卡安全替代操作</span><span className="tag ml-auto">原生实现</span></div>
              <p>卡内脚本不会直接执行；平台以受控原生能力还原其用途。</p>
              <div className="runtime-native-emulation-actions__list">
                <span><ShieldCheck size={13}/><b>重新处理变量</b><small>每轮缺失时自动补救</small></span>
                <span><ShieldCheck size={13}/><b>快照 / 重演楼层</b><small>由下方状态时间线与回滚提供</small></span>
              </div>
              {profile?.recommended_context_window && profile.recommended_context_window > 8192 ? (
                <small>该卡建议将“上下文窗口”设为至少 {profile.recommended_context_window}，以完整载入阶段语料。</small>
              ) : null}
              <button className="runtime-primary-action" onClick={() => void restoreInitialCardState()} disabled={runtimeLoading || Boolean(generatingMessageId)}>
                <RefreshCcw size={14}/><span>重新读取初始变量</span>
              </button>
            </section>
          ) : null}

          <RelationshipStatus
            relationship={state.relationship}
            initialRelationship={initialState.relationship}
            timeline={timeline}
            declared={relationshipDeclared}
          />

          {showRpg ? <RpgStatus state={state}/> : null}
          {adventure ? (
            <button className="runtime-primary-action" onClick={() => setSetupOpen(true)} disabled={runtimeLoading}>
              <ShieldCheck size={15}/><span>创建 / 编辑冒险者</span>
            </button>
          ) : null}

          {battle ? <BattleMap battle={battle}/> : null}

          <LorebookActivity entries={activeLorebook} total={profile?.lorebook_entry_count || 0}/>
          <CardStateSections state={state} initialState={initialState} timeline={timeline}/>
          <EventTimeline timeline={timeline} disabled={Boolean(generatingMessageId || runtimeLoading)} onRollback={(messageId) => void rollbackToMessage(messageId)}/>

          <details className="runtime-developer-disclosure">
            <summary><Code2 size={14}/><span>开发者数据</span><small>原始路径、运行时和兼容调试</small></summary>
            <div className="runtime-developer-disclosure__body">
              <GenericDataPanel developer title="原始运行时" value={rawDeveloperData}/>
            </div>
          </details>
        </div>
      </aside>
      {setupOpen && runtime ? <AdventureSetupModal state={runtime.state} busy={runtimeLoading} onClose={() => setSetupOpen(false)} onSave={replaceRuntimeState}/> : null}
    </>
  )
}
