import { Backpack, CircleDotDashed, ScrollText, Sparkles, UserRound } from 'lucide-react'
import type { RuntimeState, TurnRuntime } from '@/types'
import GenericDataPanel from './GenericDataPanel'
import {
  activityForRoots,
  activityLabel,
  changedFromInitial,
  hasContent,
  isRecord,
  pickAlias,
  sanitizedCustom,
  sectionValue,
} from './runtimePresentation'

const SectionHeader = ({ icon, title, activity }: { icon: React.ReactNode; title: string; activity: string }) => (
  <div className="runtime-section-title">{icon}<span>{title}</span><span className="tag ml-auto">{activity}</span></div>
)

const taskTitle = (value: unknown, index: number) => {
  if (!isRecord(value)) return String(value || `任务 ${index + 1}`)
  return String(value.title ?? value.name ?? value['名称'] ?? value['任务'] ?? `任务 ${index + 1}`)
}

const taskStatus = (value: unknown) => {
  if (!isRecord(value)) return ''
  return String(value.status ?? value.stage ?? value.progress ?? value['状态'] ?? value['进度'] ?? '')
}

export default function CardStateSections({
  state,
  initialState,
  timeline,
}: {
  state: RuntimeState
  initialState: RuntimeState
  timeline: TurnRuntime[]
}) {
  const custom = isRecord(state.custom) ? state.custom : {}
  const initialCustom = isRecord(initialState.custom) ? initialState.custom : {}

  const quests = sectionValue(state, 'quests', ['quest', 'tasks', 'task', '任务', '目标', '委托'])
  const clues = pickAlias(custom, ['线索', 'clues', 'clue', '调查记录', '案件线索', '谜题'])
  const inventory = sectionValue(state, 'inventory', ['items', 'item', '背包', '物品', '道具'])
  const character = sectionValue(state, 'character', ['角色', '角色状态'])
  const meaningfulCharacter = isRecord(character)
    ? Object.fromEntries(Object.entries(character).filter(([key, value]) => key !== 'name' && hasContent(value)))
    : character

  const questActivity = activityForRoots(timeline, ['quests', 'quest', 'tasks', 'task', '任务', '目标', '线索', 'clues'])
  const inventoryActivity = activityForRoots(timeline, ['inventory', 'items', '背包', '物品', '道具'])
  const characterActivity = activityForRoots(timeline, ['character', '角色', '角色状态'])

  const questItems = Array.isArray(quests) ? quests : isRecord(quests) ? Object.values(quests) : []
  const clueItems = Array.isArray(clues) ? clues : isRecord(clues) ? Object.values(clues) : hasContent(clues) ? [clues] : []
  const showQuests = questItems.some(hasContent) || clueItems.some(hasContent)
  const showInventory = hasContent(inventory) && changedFromInitial(inventory, initialState.inventory)
  const showCharacter = hasContent(meaningfulCharacter)

  const meaningfulCustom = sanitizedCustom(custom)
  const initialMeaningfulCustom = sanitizedCustom(initialCustom)
  const customChanged = changedFromInitial(meaningfulCustom, initialMeaningfulCustom)
  const showCustom = hasContent(meaningfulCustom)

  return (
    <>
      {showQuests ? (
        <section className="runtime-card">
          <SectionHeader icon={<ScrollText size={15}/>} title="任务与线索" activity={activityLabel(questActivity)}/>
          {questItems.length ? <div className="runtime-list">{questItems.slice(0, 10).map((item, index) => (
            <div key={`quest-${index}`}><ScrollText size={13}/><span><strong>{taskTitle(item, index)}</strong>{taskStatus(item) ? <small>{taskStatus(item)}</small> : null}</span></div>
          ))}</div> : null}
          {clueItems.length ? <div className="runtime-clue-list">{clueItems.slice(0, 12).map((item, index) => <span key={`clue-${index}`}><CircleDotDashed size={11}/>{isRecord(item) ? JSON.stringify(item) : String(item)}</span>)}</div> : null}
        </section>
      ) : null}

      {showInventory ? <GenericDataPanel icon={<Backpack size={15}/>} title="物品与资源" subtitle={activityLabel(inventoryActivity)} value={inventory}/> : null}
      {showCharacter ? <GenericDataPanel icon={<UserRound size={15}/>} title="角色状态" subtitle={characterActivity.changed ? activityLabel(characterActivity) : '角色卡初始状态'} value={meaningfulCharacter}/> : null}
      {showCustom ? <GenericDataPanel icon={<Sparkles size={15}/>} title="角色卡变量" subtitle={customChanged ? '本轮或历史已更新' : '角色卡初始状态'} value={meaningfulCustom}/> : null}
    </>
  )
}
