import { AlertTriangle, BookMarked, ChevronRight, History, Sparkles } from 'lucide-react'
import type { TurnRuntime } from '@/types'
import BattleCheckCard from './BattleCheckCard'
import BattleMap from './BattleMap'
import DiceCard from './DiceCard'

const formatValue = (value: unknown) => {
  if (value === null) return '空'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const readablePath = (value: unknown) => {
  const path = typeof value === 'string' ? value : ''
  if (!path) return '未知字段'
  return path
    .split('/')
    .filter(Boolean)
    .map((part) => decodeURIComponent(part.replace(/~1/g, '/').replace(/~0/g, '~')))
    .join(' › ')
}

function StateDiff({ turn }: { turn: TurnRuntime }) {
  if (!turn.patch.length && !turn.rejected_patch.length) return null
  return (
    <details className="runtime-state-diff">
      <summary>
        <ChevronRight size={13}/>
        <span>本轮动态数据</span>
        <strong>{turn.patch.length}</strong>
        {turn.rejected_patch.length ? <span className="runtime-rejected-count">{turn.rejected_patch.length} 项被拒绝</span> : null}
      </summary>
      <div className="runtime-state-diff-list">
        {turn.patch.map((operation, index) => (
          <div className="runtime-state-change" key={`accepted-${index}`}>
            <span className="runtime-state-operation">{String(operation.op || '更新')}</span>
            <div>
              <strong>{readablePath(operation.path)}</strong>
              {'value' in operation ? <pre>{formatValue(operation.value)}</pre> : null}
            </div>
          </div>
        ))}
        {turn.rejected_patch.map((operation, index) => (
          <div className="runtime-state-change runtime-state-change-rejected" key={`rejected-${index}`}>
            <AlertTriangle size={13}/>
            <div>
              <strong>{readablePath(operation.path)}</strong>
              <span>{String(operation.reason || operation.error || '该变量更新不符合当前状态规则')}</span>
            </div>
          </div>
        ))}
      </div>
    </details>
  )
}

export default function RuntimeMessageMeta({ turn, canRollback, onRollback }: { turn?: TurnRuntime; canRollback?: boolean; onRollback?: () => void }) {
  if (!turn) return null
  const hasContent = turn.events.length || turn.dice.length || turn.battle_checks.length || turn.battle || turn.expression || turn.triggered_lorebook.length || turn.patch.length || turn.rejected_patch.length
  if (!hasContent) return null
  return (
    <div data-testid="runtime-message-meta" className="runtime-message-meta">
      {turn.events.length ? (
        <div className="runtime-event-strip">
          <Sparkles size={13}/>{turn.events.map((event) => <span key={event}>{event}</span>)}
        </div>
      ) : null}
      {turn.dice.map((result, index) => <DiceCard key={index} result={result}/>) }
      {turn.battle_checks.map((result, index) => <BattleCheckCard key={index} result={result}/>) }
      {turn.battle ? <BattleMap battle={turn.battle}/> : null}
      <StateDiff turn={turn}/>
      <div className="runtime-message-footer">
        {turn.expression ? <span className="tag"><Sparkles size={10}/>{turn.expression}</span> : null}
        {turn.triggered_lorebook.length ? <span className="tag"><BookMarked size={10}/>{turn.triggered_lorebook.length} 条设定生效</span> : null}
        {canRollback && onRollback ? <button onClick={onRollback}><History size={11}/>回到此处</button> : null}
      </div>
    </div>
  )
}
