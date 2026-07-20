import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StateSchemaPanel from '@/components/runtime/StateSchemaPanel'
import type { RuntimeSchemaValidation, RuntimeStateSchema } from '@/types'

const schema: RuntimeStateSchema = {
  schema: 'ai-tavern-state-schema/1',
  version: 1,
  source: 'runtime_and_card',
  fields: {
    '/custom/穗秋生/好感度/0': {
      path: '/custom/穗秋生/好感度/0',
      type: 'integer',
      declared: true,
      source: 'card_initial_variables',
      mutable: true,
      required: true,
      semantic: 'relationship.affection',
      minimum: 0,
      maximum: 100,
      update_modes: ['replace', 'increment', 'delta'],
    },
    '/character/name': {
      path: '/character/name',
      type: 'string',
      declared: true,
      source: 'runtime_core',
      mutable: false,
      update_modes: [],
    },
  },
  containers: {},
  summary: {
    field_count: 2,
    declared_count: 2,
    numeric_count: 1,
    constrained_count: 1,
    semantic_count: 1,
    strict_container_count: 1,
  },
}

const valid: RuntimeSchemaValidation = {
  valid: true,
  errors: [],
  warnings: [],
  error_count: 0,
  warning_count: 0,
}

describe('StateSchemaPanel', () => {
  it('shows declared field types, ranges and update modes', () => {
    render(<StateSchemaPanel schema={schema} validation={valid}/>)
    fireEvent.click(screen.getByText('Formal State Schema'))

    expect(screen.getByText('当前状态与 Schema 一致')).toBeInTheDocument()
    expect(screen.getByText('custom › 穗秋生 › 好感度 › 0')).toBeInTheDocument()
    expect(screen.getByText('relationship.affection')).toBeInTheDocument()
    expect(screen.getByText('0…100')).toBeInTheDocument()
    expect(screen.getByText('replace · increment · delta')).toBeInTheDocument()
    expect(screen.getByText('character › name')).toBeInTheDocument()
  })

  it('surfaces schema validation errors without hiding the field registry', () => {
    render(<StateSchemaPanel schema={schema} validation={{
      ...valid,
      valid: false,
      errors: [{ path: '/custom/穗秋生/好感度/0', code: 'TYPE_MISMATCH', message: '期望 integer，实际 string' }],
      error_count: 1,
    }}/>)
    fireEvent.click(screen.getByText('Formal State Schema'))

    expect(screen.getByText('当前状态未通过 Schema 校验')).toBeInTheDocument()
    expect(screen.getByText('TYPE_MISMATCH')).toBeInTheDocument()
    expect(screen.getByText('期望 integer，实际 string')).toBeInTheDocument()
    expect(screen.getAllByText('custom › 穗秋生 › 好感度 › 0')).toHaveLength(2)
  })

  it('shows projected semantic aliases and their canonical write path', () => {
    const projected: RuntimeStateSchema = {
      ...schema,
      fields: {
        ...schema.fields,
        '/relationship/affection': {
          path: '/relationship/affection',
          type: 'integer',
          declared: true,
          source: 'runtime_core',
          mutable: true,
          semantic: 'relationship.affection',
          semantic_role: 'projection',
          canonical_path: '/custom/穗秋生/好感度/0',
          derived: true,
          minimum: 0,
          maximum: 100,
          update_modes: ['replace', 'increment', 'delta'],
        },
      },
      summary: { ...schema.summary, field_count: 3 },
    }

    render(<StateSchemaPanel schema={projected} validation={valid}/>)
    fireEvent.click(screen.getByText('Formal State Schema'))

    expect(screen.getByText('relationship › affection')).toBeInTheDocument()
    expect(screen.getByText(/投影写入 → custom › 穗秋生 › 好感度 › 0/)).toBeInTheDocument()
  })

})
