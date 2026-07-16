import { useMemo, useState } from 'react'
import { Code2, ShieldCheck, X } from 'lucide-react'
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
import { battleFromState } from './utils'
import { changedFromInitial, hasContent } from './runtimePresentation'
import type { CardCompatibilityReport } from '@/types'

export default function RuntimePanel() {
  const {
    selectedCharacter,
    currentSession,
    runtime,
    timeline,
    activeLorebook,
    runtimeLoading,
    runtimeDrawerOpen,
    generatingMessageId,
    replaceRuntimeState,
    rollbackToMessage,
    toggleRuntimeDrawer,
  } = useAppStore()
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
          <ManifestPanel manifest={compatibility?.ui_manifest} state={state}/>

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
