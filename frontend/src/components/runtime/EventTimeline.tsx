import { BookMarked, History, RotateCcw, SlidersHorizontal } from 'lucide-react'
import type { TurnRuntime } from '@/types'
import { humanPath } from './runtimePresentation'

export default function EventTimeline({ timeline, disabled, onRollback }: { timeline: TurnRuntime[]; disabled?: boolean; onRollback: (messageId: string) => void }) {
  const items = timeline.filter((turn) =>
    turn.events.length || turn.expression || turn.dice.length || turn.battle_checks.length || turn.patch.length || turn.triggered_lorebook.length
  ).slice(-10).reverse()

  return (
    <section className="runtime-card">
      <div className="runtime-section-title"><History size={15}/><span>剧情时间线</span><span className="tag ml-auto">{timeline.length} 回合</span></div>
      <p className="runtime-section-help">记录每轮真正发生的事件、变量变化和世界书触发；右侧按钮可以回滚到该轮。</p>
      {items.length ? (
        <div className="runtime-timeline">
          {items.map((turn) => {
            const headline = turn.events[0] || (turn.patch.length ? `更新了 ${turn.patch.length} 项状态` : turn.expression || '完成一次行动')
            return (
              <div key={turn.id} className="runtime-timeline__item">
                <i/>
                <div>
                  <strong>{headline}</strong>
                  {turn.events.length > 1 ? <p>{turn.events.slice(1).join(' · ')}</p> : null}
                  {turn.patch.length ? <span className="runtime-timeline-meta"><SlidersHorizontal size={10}/>{turn.patch.slice(0, 2).map((item) => humanPath(item.path)).join('、')}{turn.patch.length > 2 ? ` 等 ${turn.patch.length} 项` : ''}</span> : null}
                  {turn.triggered_lorebook.length ? <span className="runtime-timeline-meta"><BookMarked size={10}/>{turn.triggered_lorebook.map((entry) => entry.title || entry.comment || entry.keys?.[0] || '未命名条目').slice(0, 2).join('、')}</span> : null}
                </div>
                <button disabled={disabled} onClick={() => onRollback(turn.message_id)} title="删除此处之后的剧情并恢复状态"><RotateCcw size={12}/></button>
              </div>
            )
          })}
        </div>
      ) : <p className="runtime-empty">目前还没有可记录的剧情事件或状态变化。</p>}
    </section>
  )
}
