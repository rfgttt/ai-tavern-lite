import { Clock3, CloudSun, Compass, MapPin, Sparkles } from 'lucide-react'
import type { RuntimeState, TurnRuntime } from '@/types'
import { activityForRoots, activityLabel, hasContent, isRecord, PLACEHOLDER_TEXT } from './runtimePresentation'

const text = (value: unknown): string => typeof value === 'string' ? value.trim() : ''
const visibleText = (value: unknown): string => {
  const result = text(value)
  return result && !PLACEHOLDER_TEXT.has(result) ? result : ''
}

export default function SceneStatus({
  state,
  initialState,
  timeline,
  scenario,
}: {
  state: RuntimeState
  initialState: RuntimeState
  timeline: TurnRuntime[]
  scenario?: string
}) {
  const scene = isRecord(state.scene) ? state.scene : {}
  const initialScene = isRecord(initialState.scene) ? initialState.scene : {}
  const activity = activityForRoots(timeline, ['scene', '场景', '环境'])

  const location = visibleText(scene.location ?? scene['地点'] ?? scene['位置'])
  const time = visibleText(scene.time ?? scene['时间'])
  const weather = visibleText(scene.weather ?? scene['天气'] ?? scene['环境'])
  const atmosphere = visibleText(scene.atmosphere ?? scene['氛围'] ?? scene['气氛'])
  const objective = visibleText(scene.objective ?? scene['目标'] ?? scene['当前目标'])
  const scenarioText = visibleText(scenario)
  const hasRuntimeScene = hasContent(scene) && JSON.stringify(scene) !== JSON.stringify(initialScene)
  const established = Boolean(location || time || weather || atmosphere || objective || scenarioText)

  return (
    <section className={`runtime-scene-card ${established ? '' : 'runtime-scene-card--empty'}`}>
      <div className="runtime-scene-card__eyebrow">
        <Compass size={13}/>
        <span>当前场景</span>
        <span className={`runtime-activity-pill ${activity.changed ? 'is-active' : ''}`}>
          {activity.changed ? activityLabel(activity) : hasRuntimeScene ? '已有场景数据' : scenarioText ? '来自角色卡场景' : '尚未建立'}
        </span>
      </div>

      {established ? (
        <>
          <h3>{location || scenarioText}</h3>
          <div className="runtime-scene-facts">
            {location && scenarioText && location !== scenarioText ? <span><MapPin size={12}/>{location}</span> : null}
            {time ? <span><Clock3 size={12}/>{time}</span> : null}
            {weather ? <span><CloudSun size={12}/>{weather}</span> : null}
          </div>
          {atmosphere ? <p>{atmosphere}</p> : null}
          {objective ? <div className="runtime-scene-character"><Sparkles size={13}/><span>当前目标：{objective}</span></div> : null}
          {!activity.changed ? (
            <p className="runtime-note mt-2">本轮没有收到新的场景变化；当前显示的是最近一次可靠场景信息。</p>
          ) : activity.event ? (
            <p className="runtime-note mt-2">变化原因：{activity.event}</p>
          ) : null}
        </>
      ) : (
        <div className="runtime-uninitialized">
          <strong>当前场景尚未建立</strong>
          <p>等待角色卡开场内容或后续剧情提供地点、时间和环境信息。系统不会再用“环境平稳”之类的占位文字冒充真实状态。</p>
        </div>
      )}
    </section>
  )
}
