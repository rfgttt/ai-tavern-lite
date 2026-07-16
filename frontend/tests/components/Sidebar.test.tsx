import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Sidebar from '@/components/Sidebar'
import { useAppStore } from '@/stores/appStore'
import { resetAppStore, renderWithRouter } from '../testUtils'

describe('Sidebar', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('loads characters and lets the user select one', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    const characterButton = await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(characterButton)

    await waitFor(() => {
      expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅')
      expect(useAppStore.getState().sessions).toHaveLength(1)
    })
  })

  it('explains that a character is required before starting a chat', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await user.click(screen.getByTitle('新建对话'))

    expect(await screen.findByText('请先选择一个角色')).toBeInTheDocument()
  })

  it('opens the built-in character creator', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await user.click(screen.getByTitle('新建角色'))

    expect(screen.getByRole('dialog', { name: '新建角色' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建角色' })).toBeDisabled()
  })

  it('opens edit and delete actions from the character menu', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /编辑角色/ }))

    expect(screen.getByRole('dialog', { name: /编辑角色：林雅/ })).toBeInTheDocument()
    expect(screen.getByLabelText('角色名称 *')).toHaveValue('林雅')
  })
  it('deletes a character only after explicit confirmation', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /删除角色/ }))

    expect(screen.getByRole('dialog', { name: '删除角色' })).toHaveTextContent('相关会话、消息和角色记忆')
    await user.click(screen.getByRole('button', { name: '删除角色' }))

    await waitFor(() => expect(useAppStore.getState().characters.some((item) => item.id === 'character-linya')).toBe(false))
    expect(await screen.findByText('角色“林雅”已删除')).toBeInTheDocument()
  })

  it('exports a character from its action menu', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:character-export')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    renderWithRouter(<Sidebar />)
    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /导出角色/ }))

    expect(await screen.findByText('角色“林雅”已导出')).toBeInTheDocument()
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:character-export')
  })

})
