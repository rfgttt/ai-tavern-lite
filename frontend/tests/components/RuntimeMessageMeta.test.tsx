import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RuntimeMessageMeta from '@/components/runtime/RuntimeMessageMeta'
import type { TurnRuntime } from '@/types'

const turn = (overrides: Partial<TurnRuntime> = {}): TurnRuntime => ({
  id: 'turn-1',
  message_id: 'message-1',
  state_before: {},
  patch: [],
  state_after: {},
  events: [],
  choices: [],
  dice: [],
  battle_checks: [],
  battle: null,
  expression: '',
  triggered_lorebook: [],
  rejected_patch: [],
  parser_errors: [],
  decision_trace: [],
  created_at: null,
  ...overrides,
})

describe('RuntimeMessageMeta decision trace correctness', () => {
  it('unwraps rejected patch operations instead of showing an unknown field', () => {
    render(<RuntimeMessageMeta turn={turn({
      rejected_patch: [{
        operation: { op: 'replace', path: '/custom/世界信息/时间/0', value: '16:00' },
        error: '替换值与当前状态相同，已忽略无效操作',
      }],
    })}/>)

    fireEvent.click(screen.getByText('本轮动态数据'))
    expect(screen.getByText('custom › 世界信息 › 时间 › 0')).toBeInTheDocument()
    expect(screen.queryByText('未知字段')).not.toBeInTheDocument()
  })

  it('normalizes legacy applied traces that were stored with POLICY_REJECTED', () => {
    render(<RuntimeMessageMeta turn={turn({
      decision_trace: [{
        operation_id: 'op-001',
        raw_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 1 },
        normalized_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 1 },
        policy: {
          decision: 'accepted',
          reason_code: 'POLICY_REJECTED',
          reason: '操作通过状态引擎并已应用',
        },
        apply: { decision: 'applied', before: 7, after: 8, changed: true },
      }],
    })}/>)

    fireEvent.click(screen.getByText('状态决策链'))
    expect(screen.getByText('已应用')).toBeInTheDocument()
    expect(screen.getByText('POLICY_PASSED')).toBeInTheDocument()
    expect(screen.getByText('APPLIED')).toBeInTheDocument()
    expect(screen.queryByText('POLICY_REJECTED')).not.toBeInTheDocument()
  })

  it('shows policy and engine decisions as separate stages', () => {
    render(<RuntimeMessageMeta turn={turn({
      decision_trace: [{
        operation_id: 'op-001',
        outcome: 'adjusted_applied',
        raw_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 5 },
        normalized_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 2 },
        field: { classification: 'existing', path: '/custom/穗秋生/好感度/0' },
        policy: {
          decision: 'adjusted',
          reason_code: 'RELATION_DELTA_LIMIT',
          reason: '按角色卡声明的每轮/每日关系变化上限调整',
        },
        apply: {
          decision: 'applied',
          reason_code: 'APPLIED',
          reason: '操作通过状态引擎并已应用',
          before: 7,
          after: 9,
          changed: true,
        },
      }],
    })}/>)

    fireEvent.click(screen.getByText('状态决策链'))
    expect(screen.getByText('调整后已应用')).toBeInTheDocument()
    expect(screen.getByText('现有字段')).toBeInTheDocument()
    expect(screen.getByText('RELATION_DELTA_LIMIT')).toBeInTheDocument()
    expect(screen.getByText('APPLIED')).toBeInTheDocument()
    expect(screen.getByText(/最终操作:/)).toBeInTheDocument()
  })
  it('shows formal schema metadata for declared decision-trace fields', () => {
    render(<RuntimeMessageMeta turn={turn({
      decision_trace: [{
        operation_id: 'op-001',
        outcome: 'applied',
        raw_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 1 },
        normalized_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 1 },
        field: {
          classification: 'existing',
          path: '/custom/穗秋生/好感度/0',
          declared: true,
          schema_type: 'integer',
          semantic: 'relationship.affection',
          minimum: 0,
          maximum: 100,
          update_modes: ['replace', 'increment', 'delta'],
        },
        policy: { decision: 'passed', reason_code: 'POLICY_PASSED', reason: '状态规则允许该操作' },
        apply: { decision: 'applied', reason_code: 'APPLIED', before: 5, after: 6, changed: true },
      }],
    })}/>)

    fireEvent.click(screen.getByText('状态决策链'))
    expect(screen.getByText('已声明字段')).toBeInTheDocument()
    expect(screen.getByText('integer')).toBeInTheDocument()
    expect(screen.getByText('relationship.affection')).toBeInTheDocument()
    expect(screen.getByText('0…100')).toBeInTheDocument()
    expect(screen.getByText('replace · increment · delta')).toBeInTheDocument()
  })

  it('shows Formal State Schema as a separate adjustment stage', () => {
    render(<RuntimeMessageMeta turn={turn({
      decision_trace: [{
        operation_id: 'op-001',
        outcome: 'adjusted_applied',
        raw_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 500 },
        normalized_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 95 },
        field: { classification: 'existing', declared: true, path: '/custom/穗秋生/好感度/0' },
        policy: { decision: 'passed', reason_code: 'POLICY_PASSED', reason: '状态规则允许该操作' },
        schema: {
          decision: 'adjusted',
          reason_code: 'SCHEMA_RANGE_CLAMPED',
          reason: '按 Formal State Schema 数值范围调整操作',
        },
        apply: { decision: 'applied', reason_code: 'APPLIED', before: 5, after: 100, changed: true },
      }],
    })}/>)

    fireEvent.click(screen.getByText('状态决策链'))
    expect(screen.getByText('Schema')).toBeInTheDocument()
    expect(screen.getByText('SCHEMA_RANGE_CLAMPED')).toBeInTheDocument()
    expect(screen.getByText('调整后已应用')).toBeInTheDocument()
    expect(screen.getByText(/最终操作:/)).toBeInTheDocument()
  })

  it('shows a confirmed card-scoped alias before policy and schema stages', () => {
    render(<RuntimeMessageMeta turn={turn({
      decision_trace: [{
        operation_id: 'op-001',
        outcome: 'adjusted_applied',
        raw_operation: { op: 'increment', path: '/custom/穗秋生/favor/0', value: 1 },
        normalized_operation: { op: 'increment', path: '/custom/穗秋生/好感度/0', value: 1 },
        field: { classification: 'existing', declared: true, path: '/custom/穗秋生/好感度/0' },
        alias: {
          decision: 'confirmed',
          reason_code: 'ALIAS_CONFIRMED',
          reason: '当前角色卡已确认别名 favor，写入唯一路径 /custom/穗秋生/好感度/0',
        },
        policy: { decision: 'passed', reason_code: 'POLICY_PASSED', reason: '状态规则允许该操作' },
        schema: { decision: 'passed', reason_code: 'SCHEMA_PASSED', reason: 'Formal State Schema 允许该操作' },
        apply: { decision: 'applied', reason_code: 'APPLIED', before: 5, after: 6, changed: true },
      }],
    })}/>)

    fireEvent.click(screen.getByText('状态决策链'))
    expect(screen.getByText('Alias')).toBeInTheDocument()
    expect(screen.getByText('ALIAS_CONFIRMED')).toBeInTheDocument()
    expect(screen.getByText(/已确认别名 favor/)).toBeInTheDocument()
    expect(screen.getByText('调整后已应用')).toBeInTheDocument()
  })

})
