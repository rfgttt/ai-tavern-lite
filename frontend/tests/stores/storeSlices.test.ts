import { waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/appStore'
import type { Message } from '@/types'
import { charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { beginSessionListRequest, invalidateSessionListRequests, isCurrentSessionListRequest } from '@/stores/requestGuards'
import { server } from '../mocks/server'
import { resetAppStore } from '../testUtils'

const cachedMessage: Message = {
  id: 'cached-message',
  session_id: sessionsFixture[0].id,
  role: 'assistant',
  content: '缓存内容',
  sequence: 0,
  generation_status: 'complete',
  created_at: '2026-07-16T00:00:00Z',
  updated_at: '2026-07-16T00:00:00Z',
}

describe('modular app store slices', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('resets all domain state and aborts an active stream', () => {
    const controller = new AbortController()
    const abort = vi.spyOn(controller, 'abort')

    useAppStore.setState({
      characters: charactersFixture,
      selectedCharacter: charactersFixture[0],
      sessions: sessionsFixture,
      currentSession: sessionsFixture[0],
      messages: [cachedMessage],
      drafts: { [sessionsFixture[0].id]: '未发送草稿' },
      sidebarOpen: false,
      generatingMessageId: 'message-generating',
      streamController: controller,
    })

    useAppStore.getState().resetStore()

    expect(abort).toHaveBeenCalledOnce()
    expect(useAppStore.getState()).toMatchObject({
      characters: [],
      selectedCharacter: null,
      sessions: [],
      currentSession: null,
      messages: [],
      drafts: {},
      sidebarOpen: true,
      generatingMessageId: null,
      streamController: null,
    })
  })

  it('invalidates an earlier session-list request when the selection changes', () => {
    const requestId = beginSessionListRequest()
    expect(isCurrentSessionListRequest(requestId)).toBe(true)

    invalidateSessionListRequests()

    expect(isCurrentSessionListRequest(requestId)).toBe(false)
  })

  it('shows cached session data immediately and refreshes it through the session slice', async () => {
    const refreshedMessage = { ...cachedMessage, id: 'refreshed-message', content: '服务端最新内容' }
    server.use(
      http.get('*/api/sessions/:sessionId/messages', () => HttpResponse.json([refreshedMessage])),
      http.get('*/api/sessions/:sessionId/runtime', () => HttpResponse.json({
        session_id: sessionsFixture[0].id,
        profile: { mode: 'relationship' },
        initial_state: {},
        state: {},
        revision: 1,
        last_turn: null,
        updated_at: '2026-07-16T00:00:00Z',
      })),
      http.get('*/api/sessions/:sessionId/timeline', () => HttpResponse.json([])),
    )

    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      sessionCache: {
        [sessionsFixture[0].id]: {
          messages: [cachedMessage],
          runtime: null,
          timeline: [],
          activeLorebook: [],
          loadedAt: Date.now(),
        },
      },
    })

    const refresh = useAppStore.getState().selectSession(sessionsFixture[0])
    expect(useAppStore.getState().messages).toEqual([cachedMessage])
    expect(useAppStore.getState().loadingMessages).toBe(true)

    await refresh

    expect(useAppStore.getState().messages).toEqual([refreshedMessage])
    expect(useAppStore.getState().runtime?.revision).toBe(1)
  })
})
