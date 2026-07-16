import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import ChatView from '@/components/ChatView'
import { useAppStore } from '@/stores/appStore'
import { appSettingsFixture, charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { renderWithRouter, resetAppStore } from '../testUtils'

describe('ChatView model configuration guard', () => {
  beforeEach(() => {
    resetAppStore()
    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: sessionsFixture[0],
      sessions: sessionsFixture,
      settings: {
        ...appSettingsFixture,
        mock_llm: false,
        api_key_configured: false,
      },
    })
  })

  it('does not submit a message and offers to open settings', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ChatView />)

    await user.type(screen.getByTestId('chat-composer'), '你好')
    await user.click(screen.getByTitle('发送'))

    expect(await screen.findByText(/真实模型配置不完整：缺少API Key/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开设置' })).toBeInTheDocument()
    expect(useAppStore.getState().messages).toHaveLength(0)
    expect(useAppStore.getState().generatingMessageId).toBeNull()
  })
})
