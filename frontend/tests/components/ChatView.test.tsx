import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import ChatView from '@/components/ChatView'
import { useAppStore } from '@/stores/appStore'
import type { Message } from '@/types'
import { appSettingsFixture, charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { server } from '../mocks/server'
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


describe('ChatView paged history', () => {
  const message = (id: string, sequence: number, content: string): Message => ({
    id,
    session_id: sessionsFixture[0].id,
    role: sequence % 2 === 0 ? 'assistant' : 'user',
    content,
    sequence,
    generation_status: 'complete',
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
  })

  beforeEach(() => {
    resetAppStore()
    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: sessionsFixture[0],
      sessions: sessionsFixture,
      settings: appSettingsFixture,
      messages: [message('message-3', 3, '第三条'), message('message-4', 4, '第四条')],
      hasMoreMessages: true,
      oldestMessageSequence: 3,
    })
  })

  it('prepends older messages and preserves the visible scroll anchor', async () => {
    let scrollHeight = 300
    server.use(
      http.get('*/api/sessions/:sessionId/messages/page', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('before_sequence')).toBe('3')
        scrollHeight = 500
        return HttpResponse.json({
          items: [message('message-1', 1, '第一条'), message('message-2', 2, '第二条')],
          has_more: false,
          oldest_sequence: 1,
          newest_sequence: 2,
        })
      }),
    )

    const user = userEvent.setup()
    renderWithRouter(<ChatView />)
    const list = screen.getByTestId('message-list')
    Object.defineProperty(list, 'scrollHeight', { configurable: true, get: () => scrollHeight })
    Object.defineProperty(list, 'clientHeight', { configurable: true, value: 100 })
    list.scrollTop = 20

    await user.click(screen.getByRole('button', { name: '加载更早消息' }))

    expect(await screen.findByText('第一条')).toBeInTheDocument()
    await waitFor(() => expect(list.scrollTop).toBe(220))
    expect(useAppStore.getState().scrollPositions[sessionsFixture[0].id]).toBe(220)
    expect(screen.getByText('已到达会话开头')).toBeInTheDocument()
  })
})
