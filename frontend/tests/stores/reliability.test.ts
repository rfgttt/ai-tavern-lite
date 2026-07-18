import { http, HttpResponse } from 'msw'
import { waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '@/api'
import { useAppStore } from '@/stores/appStore'
import {
  SESSION_CACHE_LIMIT,
  isSessionCacheFresh,
  mergeSessionCache,
} from '@/stores/sessionReliability'
import type { ChatSession, Message, RuntimeSession } from '@/types'
import type { SessionCacheEntry } from '@/stores/types'
import { charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { resetAppStore } from '../testUtils'

const session = sessionsFixture[0]

const runtimePayload: RuntimeSession = {
  session_id: session.id,
  profile: {
    version: 2,
    mode: 'relationship',
    card_spec: 'chara_card_v3',
    card_spec_version: '3.0',
    capabilities: {},
    native_renderers: [],
    script_execution: 'disabled',
    regex_script_count: 0,
    lorebook_entry_count: 0,
    external_resource_count: 0,
    warnings: [],
  },
  initial_state: {},
  state: {},
  revision: 1,
  last_turn: null,
  updated_at: '2026-07-18T00:00:00Z',
}

const messagePayload: Message = {
  id: 'message-reliability',
  session_id: session.id,
  role: 'assistant',
  content: '可靠性测试',
  sequence: 0,
  generation_status: 'complete',
  created_at: '2026-07-18T00:00:00Z',
  updated_at: '2026-07-18T00:00:00Z',
}

describe('session and stream reliability', () => {
  beforeEach(() => {
    resetAppStore()
    vi.restoreAllMocks()
  })

  it('deduplicates concurrent loads for the same session resources', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    const counts = { messages: 0, runtime: 0, timeline: 0 }

    server.use(
      http.get('*/api/sessions/:sessionId/messages', async () => {
        counts.messages += 1
        await gate
        return HttpResponse.json([messagePayload])
      }),
      http.get('*/api/sessions/:sessionId/runtime', async () => {
        counts.runtime += 1
        await gate
        return HttpResponse.json(runtimePayload)
      }),
      http.get('*/api/sessions/:sessionId/timeline', async () => {
        counts.timeline += 1
        await gate
        return HttpResponse.json([])
      }),
    )

    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: session,
    })

    const first = useAppStore.getState().refreshCurrentSession()
    const second = useAppStore.getState().refreshCurrentSession()
    await waitFor(() => {
      expect(counts).toEqual({ messages: 1, runtime: 1, timeline: 1 })
    })

    release()
    await Promise.all([first, second])
    expect(useAppStore.getState().messages).toEqual([messagePayload])
  })

  it('prevents a delayed previous-session response from replacing the active session', async () => {
    let releaseOld!: () => void
    const oldGate = new Promise<void>((resolve) => { releaseOld = resolve })
    const nextSession: ChatSession = {
      ...session,
      id: 'session-newer',
      title: '较新的会话',
    }
    const nextMessage: Message = {
      ...messagePayload,
      id: 'message-newer',
      session_id: nextSession.id,
      content: '新会话内容',
    }

    server.use(
      http.get('*/api/sessions/:sessionId/messages', async ({ params }) => {
        if (params.sessionId === session.id) {
          await oldGate
          return HttpResponse.json([messagePayload])
        }
        return HttpResponse.json([nextMessage])
      }),
      http.get('*/api/sessions/:sessionId/runtime', async ({ params }) => {
        if (params.sessionId === session.id) await oldGate
        return HttpResponse.json({
          ...runtimePayload,
          session_id: String(params.sessionId),
        })
      }),
      http.get('*/api/sessions/:sessionId/timeline', async ({ params }) => {
        if (params.sessionId === session.id) await oldGate
        return HttpResponse.json([])
      }),
    )

    useAppStore.setState({ selectedCharacter: charactersFixture[0] })
    const oldSelection = useAppStore.getState().selectSession(session)
    await waitFor(() => expect(useAppStore.getState().currentSession?.id).toBe(session.id))

    await useAppStore.getState().selectSession(nextSession)
    expect(useAppStore.getState().messages).toEqual([nextMessage])

    releaseOld()
    await oldSelection

    expect(useAppStore.getState().currentSession?.id).toBe(nextSession.id)
    expect(useAppStore.getState().messages).toEqual([nextMessage])
  })

  it('does not refetch when the active session cache is still fresh', async () => {
    const requests = vi.spyOn(api, 'getMessages')
    useAppStore.setState({
      currentSession: session,
      sessionCache: {
        [session.id]: {
          messages: [messagePayload],
          runtime: runtimePayload,
          timeline: [],
          activeLorebook: [],
          loadedAt: Date.now(),
        },
      },
    })

    await useAppStore.getState().selectSession(session)

    expect(requests).not.toHaveBeenCalled()
  })

  it('does not treat a partially loaded cache entry as a complete fresh bundle', () => {
    const now = Date.now()
    expect(isSessionCacheFresh({
      messages: [messagePayload],
      runtime: null,
      timeline: [],
      activeLorebook: [],
      loadedAt: now,
      messagesLoadedAt: now,
    }, now)).toBe(false)
  })

  it('ignores callbacks from a stream after the user leaves its session', async () => {
    let handlers: api.StreamHandlers | undefined
    const controller = new AbortController()
    const abort = vi.spyOn(controller, 'abort')
    vi.spyOn(api, 'streamChat').mockImplementation((_sessionId, _message, nextHandlers) => {
      handlers = nextHandlers
      return controller
    })

    const nextSession: ChatSession = {
      ...session,
      id: 'session-next',
      title: '另一个会话',
    }
    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: session,
      messages: [],
    })

    await useAppStore.getState().sendMessage('开始旧会话流')
    await useAppStore.getState().selectSession(null)
    useAppStore.setState({ currentSession: nextSession, messages: [] })

    if (!handlers) throw new Error('流处理器未注册')
    handlers.onError('旧流晚到的错误')
    handlers.onChunk('旧流内容', 'old-assistant')

    expect(abort).toHaveBeenCalledOnce()
    expect(useAppStore.getState().currentSession?.id).toBe(nextSession.id)
    expect(useAppStore.getState().messages).toEqual([])
    expect(useAppStore.getState().immersiveError).toBeNull()
  })

  it('bounds the in-memory session cache while preserving the active session', () => {
    let now = 0
    vi.spyOn(Date, 'now').mockImplementation(() => now++)
    let cache: Record<string, SessionCacheEntry> = {}
    for (let index = 0; index < SESSION_CACHE_LIMIT + 3; index += 1) {
      cache = mergeSessionCache(
        cache,
        `session-${index}`,
        { messages: [], loadedAt: index },
        'session-active',
      )
    }
    cache = mergeSessionCache(
      cache,
      'session-active',
      { messages: [messagePayload] },
      'session-active',
    )

    expect(Object.keys(cache)).toHaveLength(SESSION_CACHE_LIMIT)
    expect(cache['session-active']?.messages).toEqual([messagePayload])
    expect(cache['session-0']).toBeUndefined()
  })
})
