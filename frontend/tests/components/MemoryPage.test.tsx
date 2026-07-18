import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import MemoryPage from '@/pages/MemoryPage'
import { useAppStore } from '@/stores/appStore'
import type { Memory } from '@/types'
import { charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { renderWithRouter, resetAppStore } from '../testUtils'

const memoryFixture: Memory = {
  id: 'memory-global',
  character_id: null,
  session_id: null,
  category: 'general',
  content: '全局测试记忆',
  importance: 0.5,
  keywords: '',
  enabled: true,
  created_at: '2026-07-18T00:00:00Z',
  updated_at: '2026-07-18T00:00:00Z',
}

describe('MemoryPage scope handling', () => {
  beforeEach(() => {
    resetAppStore()
    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: sessionsFixture[0],
    })
  })

  it('loads the effective context and creates session memory with both ids', async () => {
    const listRequests: URL[] = []
    let createdBody: Record<string, unknown> | null = null

    server.use(
      http.get('*/api/memories', ({ request }) => {
        listRequests.push(new URL(request.url))
        return HttpResponse.json([memoryFixture])
      }),
      http.post('*/api/memories', async ({ request }) => {
        createdBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...memoryFixture,
          id: 'memory-session',
          content: String(createdBody.content),
          character_id: String(createdBody.character_id),
          session_id: String(createdBody.session_id),
        })
      }),
    )

    renderWithRouter(<MemoryPage />)

    await screen.findByText('全局测试记忆')
    expect(listRequests[0].searchParams.get('scope')).toBe('effective')
    expect(listRequests[0].searchParams.get('character_id')).toBe('character-linya')
    expect(listRequests[0].searchParams.get('session_id')).toBe('session-linya-1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '添加记忆' }))
    expect(screen.getByLabelText('作用范围')).toHaveValue('session')
    await user.type(screen.getByLabelText('记忆内容'), '当前会话中的秘密')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(createdBody).not.toBeNull())
    expect(createdBody).toMatchObject({
      content: '当前会话中的秘密',
      character_id: 'character-linya',
      session_id: 'session-linya-1',
    })
  })

  it('requests an exact global scope when the scope filter changes', async () => {
    const listRequests: URL[] = []
    server.use(
      http.get('*/api/memories', ({ request }) => {
        listRequests.push(new URL(request.url))
        return HttpResponse.json([memoryFixture])
      }),
    )

    renderWithRouter(<MemoryPage />)
    await screen.findByText('全局测试记忆')

    const user = userEvent.setup()
    await user.selectOptions(screen.getByDisplayValue('当前上下文'), 'global')

    await waitFor(() => {
      expect(listRequests.some((url) => url.searchParams.get('scope') === 'global')).toBe(true)
    })
  })
})
