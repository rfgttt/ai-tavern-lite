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
  it('reorders alternate greetings and saves them with the character', async () => {
    const user = userEvent.setup()
    let savedBody: Record<string, unknown> | null = null
    server.use(http.put('*/api/characters/:characterId', async ({ request }) => {
      savedBody = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ...charactersFixture[0], ...savedBody })
    }))

    renderWithRouter(
      <CharacterManager open mode="edit" character={charactersFixture[0]} onSaved={vi.fn()} onClose={vi.fn()} />,
    )

    await user.click(screen.getByRole('tab', { name: /开场白/ }))
    expect(screen.getByLabelText('默认开场白')).toHaveValue('晚上好。')
    expect(screen.getByLabelText('备用开场白 1')).toHaveValue('你终于来了。')
    expect(screen.getByLabelText('备用开场白 2')).toHaveValue('雨还没有停。')

    await user.click(screen.getByRole('button', { name: '下移备用开场白 1' }))
    await user.click(screen.getByRole('button', { name: '保存角色' }))

    await waitFor(() => expect(savedBody).toMatchObject({
      first_message: '晚上好。',
      alternate_greetings: ['雨还没有停。', '你终于来了。'],
    }))
    expect(await screen.findByText('角色资料与开场白已保存')).toBeInTheDocument()
  })

  it('blocks blank and duplicate alternate greetings before saving', async () => {
    const user = userEvent.setup()
    let putCount = 0
    server.use(http.put('*/api/characters/:characterId', () => {
      putCount += 1
      return HttpResponse.json(charactersFixture[0])
    }))

    renderWithRouter(
      <CharacterManager open mode="edit" character={charactersFixture[0]} onSaved={vi.fn()} onClose={vi.fn()} />,
    )
    await user.click(screen.getByRole('tab', { name: /开场白/ }))
    const firstAlternate = screen.getByLabelText('备用开场白 1')
    await user.clear(firstAlternate)
    await user.type(firstAlternate, '晚上好。')
    await user.click(screen.getByRole('button', { name: '保存角色' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('开场白内容重复')
    expect(putCount).toBe(0)

    await user.clear(firstAlternate)
    await user.click(screen.getByRole('button', { name: '保存角色' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('不能为空')
    expect(putCount).toBe(0)
  })

  it('updates the selected greeting preview while editing', async () => {
    const user = userEvent.setup()
    renderWithRouter(
      <CharacterManager open mode="create" character={null} onSaved={vi.fn()} onClose={vi.fn()} />,
    )

    await user.click(screen.getByRole('tab', { name: /开场白/ }))
    await user.click(screen.getByRole('button', { name: /添加备用开场白/ }))
    await user.type(screen.getByLabelText('备用开场白 1'), '雨夜里，角色推开酒馆的门。')

    expect(screen.getByText('实时预览 · 备用开场白 1')).toBeInTheDocument()
    expect(screen.getAllByText('雨夜里，角色推开酒馆的门。').length).toBeGreaterThanOrEqual(1)
  })

  it('keeps the action bar outside the scrollable editor body', () => {
    renderWithRouter(
      <CharacterManager open mode="edit" character={charactersFixture[0]} onSaved={vi.fn()} onClose={vi.fn()} />,
    )

    const dialog = screen.getByRole('dialog', { name: /编辑角色/ })
    const body = dialog.querySelector('.manager-body')
    const footer = dialog.querySelector('.character-manager__footer')
    const saveButton = screen.getByRole('button', { name: '保存角色' })

    expect(body).not.toContainElement(saveButton)
    expect(footer).toContainElement(saveButton)
  })

})
