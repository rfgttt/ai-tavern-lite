import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import NewSessionWizard from '@/components/NewSessionWizard'
import { charactersFixture } from '../mocks/fixtures'
import { renderWithRouter } from '../testUtils'

describe('NewSessionWizard', () => {
  it('creates a single-character session with the selected Persona and alternate greeting', async () => {
    const user = userEvent.setup()
    const onCreate = vi.fn().mockResolvedValue(undefined)
    renderWithRouter(
      <NewSessionWizard
        open
        characters={charactersFixture}
        initialCharacterId="character-linya"
        onClose={vi.fn()}
        onCreate={onCreate}
      />,
    )

    expect(await screen.findByRole('dialog', { name: '新建会话' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    const title = screen.getByPlaceholderText('例如：钟楼下的第一次见面')
    await user.clear(title)
    await user.type(title, '酒馆里的第二次相遇')
    await user.selectOptions(screen.getByRole('combobox', { name: /玩家 Persona/ }), 'persona-traveler')
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.click(await screen.findByText('备用开场白 1'))
    await user.click(screen.getByRole('button', { name: /创建会话/ }))

    await waitFor(() => expect(onCreate).toHaveBeenCalledOnce())
    expect(onCreate).toHaveBeenCalledWith('character-linya', expect.objectContaining({
      title: '酒馆里的第二次相遇',
      persona_id: 'persona-traveler',
      use_default_persona: false,
      opening_message: '你终于来了。',
      skip_opening_message: false,
    }))
  })

  it('starts from a selected group and can explicitly avoid Persona and greeting bindings', async () => {
    const user = userEvent.setup()
    const onCreate = vi.fn().mockResolvedValue(undefined)
    renderWithRouter(
      <NewSessionWizard
        open
        characters={charactersFixture}
        initialGroupId="group-tavern"
        onClose={vi.fn()}
        onCreate={onCreate}
      />,
    )

    await screen.findByRole('dialog', { name: '新建会话' })
    expect(screen.getByRole('button', { name: /多角色编组/ })).toHaveClass('is-selected')
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.selectOptions(screen.getByRole('combobox', { name: /玩家 Persona/ }), 'none')
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.click(await screen.findByText('空白开始'))
    await user.click(screen.getByRole('button', { name: /创建会话/ }))

    await waitFor(() => expect(onCreate).toHaveBeenCalledOnce())
    expect(onCreate).toHaveBeenCalledWith('character-linya', expect.objectContaining({
      group_id: 'group-tavern',
      use_default_persona: false,
      persona_id: undefined,
      skip_opening_message: true,
    }))
  })

  it('rejects malformed custom initial-state JSON before creating the session', async () => {
    const user = userEvent.setup()
    const onCreate = vi.fn().mockResolvedValue(undefined)
    renderWithRouter(
      <NewSessionWizard
        open
        characters={charactersFixture}
        onClose={vi.fn()}
        onCreate={onCreate}
      />,
    )

    await screen.findByRole('dialog', { name: '新建会话' })
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await screen.findByText('默认开场白')
    await user.click(screen.getByText('高级：初始运行时状态'))
    await user.click(screen.getByLabelText('自定义本会话的初始状态'))
    const editor = screen.getByLabelText('初始运行时状态 JSON')
    fireEvent.change(editor, { target: { value: '{broken' } })
    await user.click(screen.getByRole('button', { name: /创建会话/ }))

    expect(await screen.findByText('初始状态不是有效的 JSON')).toBeInTheDocument()
    expect(onCreate).not.toHaveBeenCalled()
  })
})
