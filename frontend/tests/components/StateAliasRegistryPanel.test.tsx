import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StateAliasRegistryPanel from '@/components/runtime/StateAliasRegistryPanel'
import type { CharacterStateAliasRegistry } from '@/types'

const getCharacterStateAliases = vi.fn()
const confirmCharacterStateAlias = vi.fn()
const deleteCharacterStateAlias = vi.fn()

vi.mock('@/api', () => ({
  getCharacterStateAliases: (...args: unknown[]) => getCharacterStateAliases(...args),
  confirmCharacterStateAlias: (...args: unknown[]) => confirmCharacterStateAlias(...args),
  deleteCharacterStateAlias: (...args: unknown[]) => deleteCharacterStateAlias(...args),
}))

const baseRegistry: CharacterStateAliasRegistry = {
  schema: 'ai-tavern-card-aliases/1',
  version: 1,
  character_id: 'char-1',
  character_name: '穗秋生',
  revision: 'empty',
  confirmed: [],
  suggestions: [{
    id: 'relationship.affection:favor',
    alias: 'favor',
    alias_key: 'favor',
    semantic: 'relationship.affection',
    canonical_path: '/custom/穗秋生/好感度/0',
    confidence: .96,
    observed: true,
    observed_paths: ['/custom/穗秋生/favor/0'],
  }],
  targets: [{
    semantic: 'relationship.affection',
    canonical_path: '/custom/穗秋生/好感度/0',
    type: 'integer',
  }],
  summary: {
    confirmed_count: 0,
    suggestion_count: 1,
    observed_suggestion_count: 1,
    semantic_target_count: 1,
  },
}

describe('StateAliasRegistryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getCharacterStateAliases.mockResolvedValue({ data: baseRegistry })
  })

  it('shows candidates without activating them automatically', async () => {
    render(<StateAliasRegistryPanel characterId="char-1"/>)

    await screen.findByText('Card-scoped Alias Registry')
    fireEvent.click(screen.getByText('Card-scoped Alias Registry'))

    expect(await screen.findByText('favor')).toBeInTheDocument()
    expect(screen.getByText(/置信度 96%/)).toBeInTheDocument()
    expect(screen.getByText(/历史未解析路径/)).toBeInTheDocument()
    expect(confirmCharacterStateAlias).not.toHaveBeenCalled()
  })

  it('confirms a suggestion only for the selected character', async () => {
    const confirmed: CharacterStateAliasRegistry = {
      ...baseRegistry,
      revision: 'confirmed',
      suggestions: [],
      confirmed: [{
        id: 'alias-1',
        alias: 'favor',
        alias_key: 'favor',
        semantic: 'relationship.affection',
        canonical_path: '/custom/穗秋生/好感度/0',
        source: 'user_confirmed',
        confidence: 1,
      }],
      summary: { ...baseRegistry.summary, confirmed_count: 1, suggestion_count: 0 },
    }
    confirmCharacterStateAlias.mockResolvedValue({ data: confirmed })

    render(<StateAliasRegistryPanel characterId="char-1"/>)
    await screen.findByText('favor')
    const confirmButtons = screen.getAllByRole('button', { name: /确认/ })
    fireEvent.click(confirmButtons[confirmButtons.length - 1])

    await waitFor(() => expect(confirmCharacterStateAlias).toHaveBeenCalledWith('char-1', {
      alias: 'favor',
      semantic: 'relationship.affection',
    }))
    expect(await screen.findByText('1 个已确认')).toBeInTheDocument()
  })
})
