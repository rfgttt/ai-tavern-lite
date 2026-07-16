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

    const characterButton = await screen.findByRole('button', { name: /林雅/ })
    await user.click(characterButton)

    await waitFor(() => {
      expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅')
      expect(useAppStore.getState().sessions).toHaveLength(1)
    })
  })

  it('explains that a character is required before starting a chat', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => undefined)
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await user.click(screen.getByTitle('新建对话'))

    expect(alertSpy).toHaveBeenCalledWith('请先选择一个角色')
  })

  it('exposes the new-character control for the upcoming management workflow', async () => {
    renderWithRouter(<Sidebar />)

    expect(screen.getByTitle('新建角色')).toBeInTheDocument()
  })
})
