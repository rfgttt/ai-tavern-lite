import * as api from '@/api'
import type { Message } from '@/types'
import {
  beginSessionListRequest,
  getSessionLoadRequestId,
  invalidateChatStreamRequests,
  invalidateSessionLoadRequests,
  isCurrentSessionListRequest,
  isCurrentSessionLoadRequest,
} from '../requestGuards'
import { dedupeSessionRequest, isSessionCacheFresh, mergeSessionCache } from '../sessionReliability'
import type { AppStoreSlice, SessionSlice } from '../types'

const MESSAGE_PAGE_SIZE = 50

const prependUniqueMessages = (older: Message[], current: Message[]): Message[] => {
  const seen = new Set(current.map((message) => message.id))
  return [
    ...older.filter((message) => {
      if (seen.has(message.id)) return false
      seen.add(message.id)
      return true
    }),
    ...current,
  ]
}

export const createSessionSlice: AppStoreSlice<SessionSlice> = (set, get) => {
  const cacheCurrentSession = (nextSessionId?: string | null) => {
    const state = get()
    const sessionId = state.currentSession?.id
    if (!sessionId) return

    const cachePatch = {
      messages: state.messages,
      runtime: state.runtime,
      timeline: state.timeline,
      activeLorebook: state.activeLorebook,
      hasMoreMessages: state.hasMoreMessages,
      oldestMessageSequence: state.oldestMessageSequence,
      ...(!state.loadingMessages && !state.generatingMessageId
        ? { messagesLoadedAt: Date.now() }
        : {}),
    }
    set({
      sessionCache: mergeSessionCache(
        state.sessionCache,
        sessionId,
        cachePatch,
        nextSessionId,
      ),
    })
  }

  return {
    sessions: [],
    currentSession: null,
    messages: [],
    loadingMessages: false,
    messageLoadError: null,
    hasMoreMessages: false,
    oldestMessageSequence: null,
    loadingOlderMessages: false,
    olderMessageLoadError: null,
    sessionCache: {},
    drafts: {},
    scrollPositions: {},

    runtime: null,
    timeline: [],
    activeLorebook: [],
    runtimeLoading: false,

    fetchSessions: async (characterId) => {
      const requestId = beginSessionListRequest()
      const response = await api.getSessions(characterId)
      if (!isCurrentSessionListRequest(requestId)) return
      if (characterId && get().selectedCharacter?.id !== characterId) return
      set({ sessions: response.data })
    },

    createSession: async (characterId, options) => {
      const response = await api.createSession(characterId, options?.title, options)
      await get().fetchSessions(characterId)
      return response.data
    },

    selectSession: async (session) => {
      const current = get().currentSession
      if (!session) {
        cacheCurrentSession(null)
        invalidateSessionLoadRequests()
        invalidateChatStreamRequests()
        get().streamController?.abort()
        set({
          currentSession: null,
          messages: [],
          runtime: null,
          timeline: [],
          activeLorebook: [],
          generatingMessageId: null,
          streamController: null,
          immersiveError: null,
          messageLoadError: null,
          hasMoreMessages: false,
          oldestMessageSequence: null,
          loadingMessages: false,
          loadingOlderMessages: false,
          olderMessageLoadError: null,
          runtimeLoading: false,
        })
        return
      }

      if (current?.id === session.id) {
        set({ currentSession: session, immersiveError: null })
        if (isSessionCacheFresh(get().sessionCache[session.id])) return
        await get().refreshCurrentSession()
        return
      }

      cacheCurrentSession(session.id)
      invalidateSessionLoadRequests()
      invalidateChatStreamRequests()
      get().streamController?.abort()
      const cached = get().sessionCache[session.id]
      set({
        currentSession: session,
        messages: cached?.messages || [],
        runtime: cached?.runtime || null,
        timeline: cached?.timeline || [],
        activeLorebook: cached?.activeLorebook || [],
        hasMoreMessages: cached?.hasMoreMessages ?? false,
        oldestMessageSequence: cached?.oldestMessageSequence ?? null,
        generatingMessageId: null,
        streamController: null,
        immersiveError: null,
        messageLoadError: null,
        loadingMessages: !cached,
        loadingOlderMessages: false,
        olderMessageLoadError: null,
        runtimeLoading: !cached,
      })
      if (cached && isSessionCacheFresh(cached)) return
      await get().refreshCurrentSession()
    },

    renameSession: async (id, title) => {
      const cleanTitle = title.trim()
      if (!cleanTitle) return
      const response = await api.updateSession(id, { title: cleanTitle })
      set((state) => ({
        sessions: state.sessions.map((session) =>
          session.id === id ? response.data : session
        ),
        currentSession:
          state.currentSession?.id === id ? response.data : state.currentSession,
      }))
    },

    deleteSession: async (id) => {
      const characterId = get().selectedCharacter?.id
      get().streamController?.abort()
      await api.deleteSession(id)
      set((state) => {
        const { [id]: _cache, ...sessionCache } = state.sessionCache
        const { [id]: _draft, ...drafts } = state.drafts
        const { [id]: _scroll, ...scrollPositions } = state.scrollPositions
        return {
          sessions: state.sessions.filter((session) => session.id !== id),
          sessionCache,
          drafts,
          scrollPositions,
          ...(state.currentSession?.id === id
            ? {
                currentSession: null,
                messages: [],
                runtime: null,
                timeline: [],
                activeLorebook: [],
                hasMoreMessages: false,
                oldestMessageSequence: null,
                loadingOlderMessages: false,
                olderMessageLoadError: null,
                generatingMessageId: null,
                streamController: null,
                immersiveError: null,
                messageLoadError: null,
              }
            : {}),
        }
      })
      if (characterId) await get().fetchSessions(characterId)
    },

    fetchMessages: async (sessionId) => {
      const requestId = getSessionLoadRequestId()
      return dedupeSessionRequest(`${requestId}:messages:${sessionId}`, async () => {
        if (get().currentSession?.id === sessionId) {
          set({
            loadingMessages: true,
            messageLoadError: null,
            loadingOlderMessages: false,
            olderMessageLoadError: null,
          })
        }
        try {
          const response = await api.getMessagePage(sessionId, { limit: MESSAGE_PAGE_SIZE })
          const page = response.data
          set((state) => {
            const isCurrent =
              isCurrentSessionLoadRequest(requestId) && state.currentSession?.id === sessionId
            return {
              messages: isCurrent ? page.items : state.messages,
              hasMoreMessages: isCurrent ? page.has_more : state.hasMoreMessages,
              oldestMessageSequence: isCurrent
                ? page.oldest_sequence
                : state.oldestMessageSequence,
              sessionCache: mergeSessionCache(
                state.sessionCache,
                sessionId,
                {
                  messages: page.items,
                  hasMoreMessages: page.has_more,
                  oldestMessageSequence: page.oldest_sequence,
                  messagesLoadedAt: Date.now(),
                },
                state.currentSession?.id,
              ),
            }
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : '消息载入失败'
          if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
            set({ messageLoadError: message, immersiveError: message })
          }
        } finally {
          if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
            set({ loadingMessages: false })
          }
        }
      })
    },

    fetchOlderMessages: async (sessionId) => {
      const snapshot = get()
      if (
        snapshot.currentSession?.id !== sessionId
        || snapshot.loadingMessages
        || snapshot.loadingOlderMessages
        || !snapshot.hasMoreMessages
      ) return

      const beforeSequence = snapshot.oldestMessageSequence
      if (beforeSequence === null) {
        set({ hasMoreMessages: false })
        return
      }

      const requestId = getSessionLoadRequestId()
      return dedupeSessionRequest(
        `${requestId}:older-messages:${sessionId}:${beforeSequence}`,
        async () => {
          if (get().currentSession?.id === sessionId) {
            set({ loadingOlderMessages: true, olderMessageLoadError: null })
          }
          try {
            const response = await api.getMessagePage(sessionId, {
              before_sequence: beforeSequence,
              limit: MESSAGE_PAGE_SIZE,
            })
            const page = response.data
            set((state) => {
              const isCurrent =
                isCurrentSessionLoadRequest(requestId) && state.currentSession?.id === sessionId
              if (!isCurrent) return {}

              const messages = prependUniqueMessages(page.items, state.messages)
              const hasMoreMessages = page.items.length > 0 && page.has_more
              const oldestMessageSequence =
                page.oldest_sequence ?? state.oldestMessageSequence
              return {
                messages,
                hasMoreMessages,
                oldestMessageSequence,
                olderMessageLoadError: null,
                sessionCache: mergeSessionCache(
                  state.sessionCache,
                  sessionId,
                  {
                    messages,
                    hasMoreMessages,
                    oldestMessageSequence,
                    messagesLoadedAt: Date.now(),
                  },
                  state.currentSession?.id,
                ),
              }
            })
          } catch (error) {
            const message = error instanceof Error ? error.message : '更早消息载入失败'
            if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
              set({ olderMessageLoadError: message })
            }
            throw error
          } finally {
            if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
              set({ loadingOlderMessages: false })
            }
          }
        },
      )
    },

    fetchRuntime: async (sessionId) => {
      const requestId = getSessionLoadRequestId()
      return dedupeSessionRequest(`${requestId}:runtime:${sessionId}`, async () => {
        if (get().currentSession?.id === sessionId) set({ runtimeLoading: true })
        try {
          const response = await api.getRuntime(sessionId)
          const lorebook = response.data.last_turn?.triggered_lorebook || []
          set((state) => {
            const isCurrent =
              isCurrentSessionLoadRequest(requestId) && state.currentSession?.id === sessionId
            return {
              runtime: isCurrent ? response.data : state.runtime,
              activeLorebook: isCurrent ? lorebook : state.activeLorebook,
              sessionCache: mergeSessionCache(
                state.sessionCache,
                sessionId,
                { runtime: response.data, activeLorebook: lorebook, runtimeLoadedAt: Date.now() },
                state.currentSession?.id,
              ),
            }
          })
        } catch (error) {
          if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
            set({ immersiveError: error instanceof Error ? error.message : '状态载入失败' })
          }
        } finally {
          if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
            set({ runtimeLoading: false })
          }
        }
      })
    },

    fetchTimeline: async (sessionId) => {
      const requestId = getSessionLoadRequestId()
      return dedupeSessionRequest(`${requestId}:timeline:${sessionId}`, async () => {
        try {
          const response = await api.getTimeline(sessionId)
          set((state) => ({
            timeline:
              isCurrentSessionLoadRequest(requestId) && state.currentSession?.id === sessionId
                ? response.data
                : state.timeline,
            sessionCache: mergeSessionCache(
              state.sessionCache,
              sessionId,
              { timeline: response.data, timelineLoadedAt: Date.now() },
              state.currentSession?.id,
            ),
          }))
        } catch (error) {
          if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
            set({ immersiveError: error instanceof Error ? error.message : '时间线载入失败' })
          }
        }
      })
    },

    refreshCurrentSession: async () => {
      const session = get().currentSession
      if (!session) return
      await Promise.all([
        get().fetchMessages(session.id),
        get().fetchRuntime(session.id),
        get().fetchTimeline(session.id),
      ])
    },

    setDraft: (sessionId, value) =>
      set((state) => ({ drafts: { ...state.drafts, [sessionId]: value } })),

    setScrollPosition: (sessionId, value) =>
      set((state) => ({
        scrollPositions: { ...state.scrollPositions, [sessionId]: Math.max(0, value) },
      })),

    replaceRuntimeState: async (runtimeState) => {
      const session = get().currentSession
      if (!session) return
      set({ runtimeLoading: true, immersiveError: null })
      try {
        const response = await api.replaceRuntimeState(session.id, runtimeState)
        if (get().currentSession?.id !== session.id) return
        set({ runtime: response.data })
      } catch (error) {
        if (get().currentSession?.id !== session.id) return
        set({ immersiveError: error instanceof Error ? error.message : '状态保存失败' })
        throw error
      } finally {
        if (get().currentSession?.id === session.id) {
          set({ runtimeLoading: false })
        }
      }
    },

    rollbackToMessage: async (messageId) => {
      const session = get().currentSession
      if (!session || get().generatingMessageId) return
      set({ runtimeLoading: true, immersiveError: null })
      try {
        const response = await api.rollbackRuntime(session.id, messageId)
        if (get().currentSession?.id !== session.id) return
        set({
          runtime: response.data,
          activeLorebook: response.data.last_turn?.triggered_lorebook || [],
        })
        await Promise.all([get().fetchMessages(session.id), get().fetchTimeline(session.id)])
      } catch (error) {
        if (get().currentSession?.id === session.id) {
          set({ immersiveError: error instanceof Error ? error.message : '剧情回溯失败' })
        }
      } finally {
        if (get().currentSession?.id === session.id) {
          set({ runtimeLoading: false })
        }
      }
    },
  }
}
