import { AlertTriangle, BookMarked, ChevronRight, History, Sparkles } from 'lucide-react'
import type { RuntimeDecisionTrace, TurnRuntime } from '@/types'
import BattleCheckCard from './BattleCheckCard'
import BattleMap from './BattleMap'
import DiceCard from './DiceCard'

const formatValue = (value: unknown) => {
  if (value === undefined) return '未记录'
  if (value === null) return '空'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}

const readablePath = (value: unknown) => {
  const path = typeof value === 'string' ? value : ''
  if (!path) return '未提供路径'
  return path
    .split('/')
    .filter(Boolean)
    .map((part) => decodeURIComponent(part.replace(/~1/g, '/').replace(/~0/g, '~')))
    .join(' › ')
}

const rejectedOperation = (entry: Record<string, unknown>) => {
  const nested = asRecord(entry.operation)
  return Object.keys(nested).length ? nested : entry
}

const fieldLabel = (entry: RuntimeDecisionTrace, path: unknown) => {
  const classification = String(entry.field?.classification || '')
  if (classification === 'existing' && entry.field?.declared === true) return '已声明字段'
  if (classification === 'existing' && entry.field?.declared === false) return '兼容字段'
  if (classification === 'existing') return '现有字段'
  if (classification === 'created') return '本轮新建字段'
  if (classification === 'unresolved') return path ? '未解析字段' : '未提供路径'
  return path ? '状态字段' : '未提供路径'
}

const normalizedOutcome = (entry: RuntimeDecisionTrace) => {
  const aliasDecision = String(entry.alias?.decision || '')
  const policyDecision = String(entry.policy?.decision || '')
  const schemaDecision = String(entry.schema?.decision || '')
  const applyDecision = String(entry.apply?.decision || '')
  if (aliasDecision === 'invalid' || policyDecision === 'rejected' || schemaDecision === 'rejected' || applyDecision === 'rejected') return 'rejected'
  if (applyDecision === 'applied' || applyDecision === 'adjusted') {
    return aliasDecision === 'confirmed' || policyDecision === 'adjusted' || schemaDecision === 'adjusted' || applyDecision === 'adjusted' ? 'adjusted_applied' : 'applied'
  }
  if (applyDecision === 'not_attempted') return 'rejected'
  return String(entry.outcome || applyDecision || 'not_applied')
}

const outcomeLabel = (outcome: string) => {
  if (outcome === 'applied') return '已应用'
  if (outcome === 'adjusted_applied') return '调整后已应用'
  if (outcome === 'rejected') return '已拒绝'
  if (outcome === 'not_applied') return '未应用'
  return outcome || '未知'
}

const policyPresentation = (entry: RuntimeDecisionTrace, outcome: string) => {
  const policy = entry.policy || {}
  const decision = String(policy.decision || '')
  let code = String(policy.reason_code || '')
  let reason = String(policy.reason || '')

  // P0 traces stored the successful engine message in the policy stage and
  // generated POLICY_REJECTED from that text. Normalize historical snapshots
  // in the UI instead of rewriting the database.
  if ((outcome === 'applied' || outcome === 'adjusted_applied') && decision !== 'rejected') {
    if (!code || code === 'POLICY_REJECTED' || code === 'UNKNOWN') {
      code = decision === 'adjusted' ? 'POLICY_ADJUSTED' : 'POLICY_PASSED'
    }
    if (!reason || reason === '操作通过状态引擎并已应用') {
      reason = decision === 'adjusted' ? '状态规则调整了操作' : '状态规则允许该操作'
    }
  }
  return { decision, code, reason }
}

const applyPresentation = (entry: RuntimeDecisionTrace, outcome: string) => {
  const apply = entry.apply || {}
  let decision = String(apply.decision || '')
  let code = String(apply.reason_code || '')
  let reason = String(apply.reason || '')

  if (outcome === 'applied' || outcome === 'adjusted_applied') {
    decision = 'applied'
    code = 'APPLIED'
    reason ||= '操作通过状态引擎并已应用'
  } else if (String(entry.policy?.decision || '') === 'rejected') {
    decision = 'not_attempted'
    code ||= 'NOT_ATTEMPTED_POLICY_REJECTED'
    reason ||= '状态规则已拒绝该操作，未进入状态引擎'
  }
  return { decision, code, reason }
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
        {turn.rejected_patch.map((entry, index) => {
          const wrapper = asRecord(entry)
          const operation = rejectedOperation(wrapper)
          return (
            <div className="runtime-state-change runtime-state-change-rejected" key={`rejected-${index}`}>
              <AlertTriangle size={13}/>
              <div>
                <strong>{readablePath(operation.path)}</strong>
                <span>{String(wrapper.reason || wrapper.error || operation.reason || operation.error || '该变量更新不符合当前状态规则')}</span>
              </div>
            </div>
          )
        })}
      </div>
    </details>
  )
}

function DecisionTrace({ turn }: { turn: TurnRuntime }) {
  if (!turn.decision_trace?.length) return null
  return (
    <details className="runtime-decision-trace">
      <summary><ChevronRight size={13}/><span>状态决策链</span><strong>{turn.decision_trace.length}</strong></summary>
      <div className="runtime-state-diff-list">
        {turn.decision_trace.map((entry, index) => {
          const raw = asRecord(entry.raw_operation)
          const normalized = asRecord(entry.normalized_operation)
          const apply = entry.apply || {}
          const path = normalized.path || raw.path || entry.field?.path
          const outcome = normalizedOutcome(entry)
          const policyView = policyPresentation(entry, outcome)
          const applyView = applyPresentation(entry, outcome)
          const operationChanged = JSON.stringify(raw) !== JSON.stringify(normalized)
          const rejected = outcome === 'rejected'
          return (
            <div className={`runtime-state-change runtime-decision-entry ${rejected ? 'runtime-state-change-rejected' : ''}`} key={String(entry.operation_id || index)}>
              <span className={`runtime-state-operation runtime-decision-outcome runtime-decision-outcome--${outcome}`}>{outcomeLabel(outcome)}</span>
              <div>
                <div className="runtime-decision-heading">
                  <strong>{readablePath(path)}</strong>
                  <small>{fieldLabel(entry, path)}</small>
                </div>
                {entry.field?.schema_type ? <div className="runtime-decision-schema">
                  <code>{entry.field.schema_type}</code>
                  {entry.field.semantic ? <span>{entry.field.semantic}</span> : null}
                  {entry.field.minimum !== undefined || entry.field.maximum !== undefined ? <span>{entry.field.minimum ?? '−∞'}…{entry.field.maximum ?? '+∞'}</span> : null}
                  {entry.field.update_modes?.length ? <small>{entry.field.update_modes.join(' · ')}</small> : null}
                </div> : null}
                {entry.alias ? <div className="runtime-decision-stage">
                  <b>Alias</b>
                  <code>{entry.alias.reason_code || 'ALIAS_UNKNOWN'}</code>
                  <span>{entry.alias.reason || '未记录别名决策'}</span>
                </div> : null}
                <div className="runtime-decision-stage">
                  <b>规则</b>
                  <code>{policyView.code || 'UNKNOWN'}</code>
                  <span>{policyView.reason || '未记录规则决策'}</span>
                </div>
                {entry.schema ? <div className="runtime-decision-stage">
                  <b>Schema</b>
                  <code>{entry.schema.reason_code || 'UNKNOWN'}</code>
                  <span>{entry.schema.reason || '未记录 Schema 决策'}</span>
                </div> : null}
                <div className="runtime-decision-stage">
                  <b>合并</b>
                  <code>{applyView.code || 'UNKNOWN'}</code>
                  <span>{applyView.reason || '未记录合并决策'}</span>
                </div>
                <pre>{[
                  `原始操作: ${formatValue(raw)}`,
                  operationChanged ? `最终操作: ${formatValue(normalized)}` : '',
                  'before' in apply ? `前值: ${formatValue(apply.before)}` : '',
                  'after' in apply ? `后值: ${formatValue(apply.after)}` : '',
                ].filter(Boolean).join('\n')}</pre>
              </div>
            </div>
          )
        })}
      </div>
    </details>
  )
}

export default function RuntimeMessageMeta({ turn, canRollback, onRollback }: { turn?: TurnRuntime; canRollback?: boolean; onRollback?: () => void }) {
  if (!turn) return null
  const hasContent = turn.events.length || turn.dice.length || turn.battle_checks.length || turn.battle || turn.expression || turn.triggered_lorebook.length || turn.patch.length || turn.rejected_patch.length || turn.decision_trace?.length
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
      <DecisionTrace turn={turn}/>
      <div className="runtime-message-footer">
        {turn.expression ? <span className="tag"><Sparkles size={10}/>{turn.expression}</span> : null}
        {turn.triggered_lorebook.length ? <span className="tag"><BookMarked size={10}/>{turn.triggered_lorebook.length} 条设定生效</span> : null}
        {canRollback && onRollback ? <button onClick={onRollback}><History size={11}/>回到此处</button> : null}
      </div>
    </div>
  )
}
