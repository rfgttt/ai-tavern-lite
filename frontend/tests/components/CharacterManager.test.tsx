import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CharacterManager from '@/components/CharacterManager'
import { useAppStore } from '@/stores/appStore'
import { charactersFixture } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { renderWithRouter, resetAppStore } from '../testUtils'

describe('CharacterManager', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('creates a character and selects it through the callback', async () => {
    const user = userEvent.setup()
    const onSaved = vi.fn()
    const onClose = vi.fn()
    renderWithRouter(<CharacterManager open mode="create" character={null} onSaved={onSaved} onClose={onClose} />)

    await user.type(screen.getByLabelText('角色名称 *'), '雾叶泠')
    await user.type(screen.getByLabelText('性格'), '冷静而温柔')
    await user.click(screen.getByRole('button', { name: '创建角色' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ name: '雾叶泠' })))
    expect(useAppStore.getState().characters[0].name).toBe('雾叶泠')
    expect(onClose).toHaveBeenCalled()
    expect(await screen.findByText('角色已创建')).toBeInTheDocument()
  })

  it('loads and saves lorebook entries without losing their structured fields', async () => {
    const user = userEvent.setup()
    let savedBody: unknown = null
    server.use(http.put('*/api/characters/:characterId/lorebook', async ({ request }) => {
      savedBody = await request.json()
      return HttpResponse.json(savedBody as Record<string, unknown>)
    }))

    renderWithRouter(
      <CharacterManager open mode="edit" character={charactersFixture[0]} onSaved={vi.fn()} onClose={vi.fn()} />,
    )

    await user.click(screen.getByRole('tab', { name: /世界书/ }))
    expect(await screen.findByDisplayValue('古老图书馆')).toBeInTheDocument()
    await user.clear(screen.getByDisplayValue('图书馆'))
    await user.type(screen.getByPlaceholderText('魔法, 图书馆'), '魔法, 禁书区')
    await user.click(screen.getByRole('button', { name: '保存世界书' }))

    await waitFor(() => expect(savedBody).toMatchObject({
      entries: [expect.objectContaining({ keys: ['魔法', '禁书区'], enabled: true, probability: 100 })],
    }))
    expect(await screen.findByText('世界书已保存')).toBeInTheDocument()
  })
})
