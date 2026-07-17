import * as api from '@/api'
import {
  beginSessionListRequest,
  getSessionLoadRequestId,
  invalidateSessionLoadRequests,
  isCurrentSessionListRequest,
  isCurrentSessionLoadRequest,
} from '../requestGuards'
import type { AppStoreSlice, SessionSlice } from '../types'

export const createSessionSlice: AppStoreSlice<SessionSlice> = (set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  loadingMessages: false,
  messageLoadError: null,
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
    invalidateSessionLoadRequests()
    const current = get().currentSession
    if (!session) {
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
        loadingMessages: false,
        runtimeLoading: false,
      })
      return
    }

    if (current?.id === session.id) {
      set({ currentSession: session, immersiveError: null })
      await get().refreshCurrentSession()
      return
    }

    get().streamController?.abort()
    const cached = get().sessionCache[session.id]
    set({
      currentSession: session,
      messages: cached?.messages || [],
      runtime: cached?.runtime || null,
      timeline: cached?.timeline || [],
      activeLorebook: cached?.activeLorebook || [],
      generatingMessageId: null,
      streamController: null,
      immersiveError: null,
      messageLoadError: null,
      loadingMessages: !cached,
    })
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
    const wasCurrent = get().currentSession?.id === id
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
        ...(wasCurrent
          ? {
              currentSession: null,
              messages: [],
              runtime: null,
              timeline: [],
              activeLorebook: [],
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
    if (get().currentSession?.id === sessionId) {
      set({ loadingMessages: true, messageLoadError: null })
    }
    try {
      const response = await api.getMessages(sessionId)
      set((state) => ({
        messages: state.currentSession?.id === sessionId ? response.data : state.messages,
        sessionCache: {
          ...state.sessionCache,
          [sessionId]: {
            messages: response.data,
            runtime:
              state.sessionCache[sessionId]?.runtime ||
              (state.currentSession?.id === sessionId ? state.runtime : null),
            timeline: state.sessionCache[sessionId]?.timeline || [],
            activeLorebook: state.sessionCache[sessionId]?.activeLorebook || [],
            loadedAt: Date.now(),
          },
        },
      }))
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
  },

  fetchRuntime: async (sessionId) => {
    const requestId = getSessionLoadRequestId()
    if (get().currentSession?.id === sessionId) set({ runtimeLoading: true })
    try {
      const response = await api.getRuntime(sessionId)
      const lorebook = response.data.last_turn?.triggered_lorebook || []
      set((state) => ({
        runtime: state.currentSession?.id === sessionId ? response.data : state.runtime,
        activeLorebook:
          state.currentSession?.id === sessionId ? lorebook : state.activeLorebook,
        sessionCache: {
          ...state.sessionCache,
          [sessionId]: {
            messages: state.sessionCache[sessionId]?.messages || [],
            runtime: response.data,
            timeline: state.sessionCache[sessionId]?.timeline || [],
            activeLorebook: lorebook,
            loadedAt: Date.now(),
          },
        },
      }))
    } catch (error) {
      if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
        set({ immersiveError: error instanceof Error ? error.message : '状态载入失败' })
      }
    } finally {
      if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
        set({ runtimeLoading: false })
      }
    }
  },

  fetchTimeline: async (sessionId) => {
    const requestId = getSessionLoadRequestId()
    try {
      const response = await api.getTimeline(sessionId)
      set((state) => ({
        timeline: state.currentSession?.id === sessionId ? response.data : state.timeline,
        sessionCache: {
          ...state.sessionCache,
          [sessionId]: {
            messages: state.sessionCache[sessionId]?.messages || [],
            runtime: state.sessionCache[sessionId]?.runtime || null,
            timeline: response.data,
            activeLorebook: state.sessionCache[sessionId]?.activeLorebook || [],
            loadedAt: Date.now(),
          },
        },
      }))
    } catch (error) {
      if (isCurrentSessionLoadRequest(requestId) && get().currentSession?.id === sessionId) {
        set({ immersiveError: error instanceof Error ? error.message : '时间线载入失败' })
      }
    }
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
      scrollPositions: { ...state.scrollPositions, [sessionId]: value },
    })),

  replaceRuntimeState: async (runtimeState) => {
    const session = get().currentSession
    if (!session) return
    set({ runtimeLoading: true, immersiveError: null })
    try {
      const response = await api.replaceRuntimeState(session.id, runtimeState)
      set({ runtime: response.data })
    } catch (error) {
      set({ immersiveError: error instanceof Error ? error.message : '状态保存失败' })
      throw error
    } finally {
      set({ runtimeLoading: false })
    }
  },

  rollbackToMessage: async (messageId) => {
    const session = get().currentSession
    if (!session || get().generatingMessageId) return
    set({ runtimeLoading: true, immersiveError: null })
    try {
      const response = await api.rollbackRuntime(session.id, messageId)
      set({
        runtime: response.data,
        activeLorebook: response.data.last_turn?.triggered_lorebook || [],
      })
      await Promise.all([get().fetchMessages(session.id), get().fetchTimeline(session.id)])
    } catch (error) {
      set({ immersiveError: error instanceof Error ? error.message : '剧情回溯失败' })
    } finally {
      set({ runtimeLoading: false })
    }
  },
})
