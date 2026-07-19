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
import type { AppSettings, ChatSession, Message, RuntimeSession } from '@/types'
import type { SessionCacheEntry } from '@/stores/types'
import { appSettingsFixture, charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { resetAppStore } from '../testUtils'

const session = sessionsFixture[0]

const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

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
      http.get('*/api/sessions/:sessionId/messages/page', async () => {
        counts.messages += 1
        await gate
        return HttpResponse.json({ items: [messagePayload], has_more: false, oldest_sequence: messagePayload.sequence, newest_sequence: messagePayload.sequence })
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

  it('loads older pages without duplicates and keeps pagination state in the session cache', async () => {
    const newerMessages: Message[] = [
      { ...messagePayload, id: 'message-3', sequence: 3, content: '第三条' },
      { ...messagePayload, id: 'message-4', sequence: 4, content: '第四条' },
    ]
    const olderMessages: Message[] = [
      { ...messagePayload, id: 'message-1', sequence: 1, content: '第一条' },
      { ...messagePayload, id: 'message-2', sequence: 2, content: '第二条' },
      { ...messagePayload, id: 'message-3', sequence: 3, content: '重复边界' },
    ]

    server.use(
      http.get('*/api/sessions/:sessionId/messages/page', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('before_sequence')).toBe('3')
        expect(url.searchParams.get('limit')).toBe('50')
        return HttpResponse.json({
          items: olderMessages,
          has_more: false,
          oldest_sequence: 1,
          newest_sequence: 2,
        })
      }),
    )

    useAppStore.setState({
      currentSession: session,
      messages: newerMessages,
      hasMoreMessages: true,
      oldestMessageSequence: 3,
    })

    await useAppStore.getState().fetchOlderMessages(session.id)

    expect(useAppStore.getState().messages.map((message) => message.id)).toEqual([
      'message-1',
      'message-2',
      'message-3',
      'message-4',
    ])
    expect(useAppStore.getState().hasMoreMessages).toBe(false)
    expect(useAppStore.getState().oldestMessageSequence).toBe(1)
    expect(useAppStore.getState().sessionCache[session.id]?.messages).toEqual(
      useAppStore.getState().messages,
    )
  })

  it('ignores an older-page response after the user leaves that session', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    const nextSession: ChatSession = { ...session, id: 'session-after-older-load' }
    const nextMessage: Message = {
      ...messagePayload,
      id: 'message-after-older-load',
      session_id: nextSession.id,
    }

    server.use(
      http.get('*/api/sessions/:sessionId/messages/page', async () => {
        await gate
        return HttpResponse.json({
          items: [{ ...messagePayload, id: 'old-page-message', sequence: 1 }],
          has_more: false,
          oldest_sequence: 1,
          newest_sequence: 1,
        })
      }),
    )

    useAppStore.setState({
      currentSession: session,
      messages: [{ ...messagePayload, id: 'message-50', sequence: 50 }],
      hasMoreMessages: true,
      oldestMessageSequence: 50,
    })
    const pending = useAppStore.getState().fetchOlderMessages(session.id)
    await waitFor(() => expect(useAppStore.getState().loadingOlderMessages).toBe(true))

    await useAppStore.getState().selectSession(null)
    useAppStore.setState({ currentSession: nextSession, messages: [nextMessage] })
    release()
    await pending

    expect(useAppStore.getState().currentSession?.id).toBe(nextSession.id)
    expect(useAppStore.getState().messages).toEqual([nextMessage])
    expect(useAppStore.getState().loadingOlderMessages).toBe(false)
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
      http.get('*/api/sessions/:sessionId/messages/page', async ({ params }) => {
        if (params.sessionId === session.id) {
          await oldGate
          return HttpResponse.json({ items: [messagePayload], has_more: false, oldest_sequence: messagePayload.sequence, newest_sequence: messagePayload.sequence })
        }
        return HttpResponse.json({ items: [nextMessage], has_more: false, oldest_sequence: nextMessage.sequence, newest_sequence: nextMessage.sequence })
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

  it('restores a fresh paged cache without collapsing it to the latest page', async () => {
    const requests = vi.spyOn(api, 'getMessagePage')
    const previousSession: ChatSession = { ...session, id: 'session-previous' }
    const cachedMessages = [
      { ...messagePayload, id: 'cached-older', sequence: 1 },
      { ...messagePayload, id: 'cached-newer', sequence: 51 },
    ]
    const now = Date.now()

    useAppStore.setState({
      currentSession: previousSession,
      messages: [],
      sessionCache: {
        [session.id]: {
          messages: cachedMessages,
          runtime: runtimePayload,
          timeline: [],
          activeLorebook: [],
          hasMoreMessages: true,
          oldestMessageSequence: 1,
          loadedAt: now,
          messagesLoadedAt: now,
          runtimeLoadedAt: now,
          timelineLoadedAt: now,
        },
      },
    })

    await useAppStore.getState().selectSession(session)

    expect(requests).not.toHaveBeenCalled()
    expect(useAppStore.getState().messages).toEqual(cachedMessages)
    expect(useAppStore.getState().hasMoreMessages).toBe(true)
    expect(useAppStore.getState().oldestMessageSequence).toBe(1)
  })

  it('does not refetch when the active session cache is still fresh', async () => {
    const requests = vi.spyOn(api, 'getMessagePage')
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

  it('does not let a delayed session deletion clear a newly selected session', async () => {
    const deletion = deferred<never>()
    vi.spyOn(api, 'deleteSession').mockReturnValue(deletion.promise)
    const nextSession: ChatSession = { ...session, id: 'session-after-delete' }
    const nextMessage: Message = { ...messagePayload, id: 'message-after-delete', session_id: nextSession.id }

    useAppStore.setState({ currentSession: session, sessions: [session, nextSession] })
    const pending = useAppStore.getState().deleteSession(session.id)
    useAppStore.setState({ currentSession: nextSession, messages: [nextMessage] })

    deletion.resolve({ data: null } as never)
    await pending

    expect(useAppStore.getState().currentSession).toEqual(nextSession)
    expect(useAppStore.getState().messages).toEqual([nextMessage])
  })

  it('ignores a runtime save that completes after leaving its session', async () => {
    const replacement = deferred<never>()
    vi.spyOn(api, 'replaceRuntimeState').mockReturnValue(replacement.promise)
    const nextSession: ChatSession = { ...session, id: 'session-after-runtime' }
    const nextRuntime = { ...runtimePayload, session_id: nextSession.id, revision: 7 }

    useAppStore.setState({ currentSession: session, runtime: runtimePayload })
    const pending = useAppStore.getState().replaceRuntimeState({ scene: { location: '旧地点' } })
    await useAppStore.getState().selectSession(null)
    useAppStore.setState({ currentSession: nextSession, runtime: nextRuntime, runtimeLoading: false })

    replacement.resolve({ data: { ...runtimePayload, revision: 99 } } as never)
    await pending

    expect(useAppStore.getState().runtime).toEqual(nextRuntime)
    expect(useAppStore.getState().runtimeLoading).toBe(false)
  })

  it('ignores a rollback that completes after leaving its session', async () => {
    const rollback = deferred<never>()
    vi.spyOn(api, 'rollbackRuntime').mockReturnValue(rollback.promise)
    const nextSession: ChatSession = { ...session, id: 'session-after-rollback' }
    const nextRuntime = { ...runtimePayload, session_id: nextSession.id, revision: 8 }

    useAppStore.setState({ currentSession: session, runtime: runtimePayload })
    const pending = useAppStore.getState().rollbackToMessage(messagePayload.id)
    await useAppStore.getState().selectSession(null)
    useAppStore.setState({ currentSession: nextSession, runtime: nextRuntime, runtimeLoading: false })

    rollback.resolve({ data: { ...runtimePayload, revision: 100 } } as never)
    await pending

    expect(useAppStore.getState().runtime).toEqual(nextRuntime)
    expect(useAppStore.getState().runtimeLoading).toBe(false)
  })

  it('does not let an old stop request clear a newer stream', async () => {
    const stopping = deferred<never>()
    vi.spyOn(api, 'stopGeneration').mockReturnValue(stopping.promise)
    const oldController = new AbortController()
    const newController = new AbortController()
    const nextSession: ChatSession = { ...session, id: 'session-new-stream' }

    useAppStore.setState({
      currentSession: session,
      generatingMessageId: messagePayload.id,
      streamController: oldController,
      messages: [messagePayload],
    })
    const pending = useAppStore.getState().stopGeneration()
    useAppStore.setState({
      currentSession: nextSession,
      generatingMessageId: 'message-new-stream',
      streamController: newController,
      messages: [],
    })

    stopping.resolve({ data: null } as never)
    await pending

    expect(useAppStore.getState().generatingMessageId).toBe('message-new-stream')
    expect(useAppStore.getState().streamController).toBe(newController)
    expect(newController.signal.aborted).toBe(false)
  })

  it('prevents an older settings fetch from overwriting a completed save', async () => {
    const fetching = deferred<never>()
    const saving = deferred<never>()
    vi.spyOn(api, 'getSettings').mockReturnValue(fetching.promise)
    vi.spyOn(api, 'updateSettings').mockReturnValue(saving.promise)
    const savedSettings: AppSettings = { ...appSettingsFixture, username: '最新保存' }

    const oldFetch = useAppStore.getState().fetchSettings()
    const write = useAppStore.getState().updateSettings({ username: savedSettings.username })

    saving.resolve({ data: savedSettings } as never)
    await write
    fetching.resolve({ data: { ...appSettingsFixture, username: '旧读取' } } as never)
    await oldFetch

    expect(useAppStore.getState().settings?.username).toBe('最新保存')
  })

  it('keeps only the newest settings write response', async () => {
    const first = deferred<never>()
    const second = deferred<never>()
    let call = 0
    vi.spyOn(api, 'updateSettings').mockImplementation(() => {
      call += 1
      return call === 1 ? first.promise : second.promise
    })

    const older = useAppStore.getState().updateSettings({ username: '较旧保存' })
    const newer = useAppStore.getState().updateSettings({ username: '最新保存' })

    second.resolve({ data: { ...appSettingsFixture, username: '最新保存' } } as never)
    await newer
    first.resolve({ data: { ...appSettingsFixture, username: '较旧保存' } } as never)
    await older

    expect(useAppStore.getState().settings?.username).toBe('最新保存')
  })

})
