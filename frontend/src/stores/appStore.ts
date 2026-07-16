import { create } from 'zustand'
import type {
  AppSettings,
  Character,
  CharacterDraft,
  ChatSession,
  LorebookTrigger,
  Message,
  RuntimeSession,
  RuntimeState,
  StreamDoneEvent,
  StreamRuntimeEvent,
  TurnRuntime,
} from '@/types'
import * as api from '@/api'

let sessionListRequestId = 0
let sessionLoadRequestId = 0


interface SessionCacheEntry {
  messages: Message[]
  runtime: RuntimeSession | null
  timeline: TurnRuntime[]
  activeLorebook: LorebookTrigger[]
  loadedAt: number
}

interface AppState {
  characters: Character[]
  selectedCharacter: Character | null
  loadingCharacters: boolean

  sessions: ChatSession[]
  currentSession: ChatSession | null
  messages: Message[]
  loadingMessages: boolean
  messageLoadError: string | null
  sessionCache: Record<string, SessionCacheEntry>
  drafts: Record<string, string>
  scrollPositions: Record<string, number>

  runtime: RuntimeSession | null
  timeline: TurnRuntime[]
  activeLorebook: LorebookTrigger[]
  runtimeLoading: boolean
  runtimeDrawerOpen: boolean
  immersiveError: string | null

  settings: AppSettings | null

  sidebarOpen: boolean
  generatingMessageId: string | null
  streamController: AbortController | null

  fetchCharacters: () => Promise<void>
  selectCharacter: (char: Character | null) => void
  createCharacter: (data: CharacterDraft) => Promise<Character>
  updateCharacter: (id: string, data: CharacterDraft) => Promise<Character>
  importCharacter: (file: File) => Promise<Character>
  deleteCharacter: (id: string) => Promise<void>

  fetchSessions: (characterId?: string) => Promise<void>
  createSession: (characterId: string, options?: { title?: string; persona_id?: string; group_id?: string }) => Promise<ChatSession>
  selectSession: (session: ChatSession | null) => Promise<void>
  renameSession: (id: string, title: string) => Promise<void>
  deleteSession: (id: string) => Promise<void>
  fetchMessages: (sessionId: string) => Promise<void>
  fetchRuntime: (sessionId: string) => Promise<void>
  fetchTimeline: (sessionId: string) => Promise<void>
  refreshCurrentSession: () => Promise<void>
  setDraft: (sessionId: string, value: string) => void
  setScrollPosition: (sessionId: string, value: number) => void
  replaceRuntimeState: (state: RuntimeState) => Promise<void>
  rollbackToMessage: (messageId: string) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  sendChoice: (choice: string) => Promise<void>
  stopGeneration: () => Promise<void>
  regenerateLast: () => Promise<void>
  editMessage: (id: string, content: string) => Promise<void>
  deleteMessage: (id: string) => Promise<void>

  fetchSettings: () => Promise<void>
  updateSettings: (
    data: Partial<AppSettings> & { api_key?: string; clear_api_key?: boolean }
  ) => Promise<void>

  toggleSidebar: () => void
  toggleRuntimeDrawer: (open?: boolean) => void
  clearImmersiveError: () => void
}

const createLocalMessage = (
  sessionId: string,
  role: Message['role'],
  content: string,
  sequence: number,
  generationStatus: Message['generation_status'] = 'complete'
): Message => {
  const now = new Date().toISOString()
  return {
    id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    session_id: sessionId,
    role,
    content,
    sequence,
    generation_status: generationStatus,
    created_at: now,
    updated_at: now,
  }
}

const mergeTurn = (timeline: TurnRuntime[], turn: TurnRuntime): TurnRuntime[] => {
  const withoutCurrent = timeline.filter((item) => item.message_id !== turn.message_id)
  return [...withoutCurrent, turn].sort((a, b) => {
    const aTime = a.created_at ? Date.parse(a.created_at) : 0
    const bTime = b.created_at ? Date.parse(b.created_at) : 0
    return aTime - bTime
  })
}

const runtimeFromEvent = (
  current: RuntimeSession | null,
  sessionId: string,
  event: StreamRuntimeEvent
): RuntimeSession => ({
  session_id: sessionId,
  profile: event.profile,
  initial_state: current?.initial_state || event.state,
  state: event.state,
  revision: event.revision,
  last_turn: current?.last_turn || null,
  updated_at: current?.updated_at || null,
})

const runtimeAfterDone = (
  current: RuntimeSession | null,
  sessionId: string,
  event: StreamDoneEvent
): RuntimeSession | null => {
  if (!current) return null
  return {
    ...current,
    session_id: sessionId,
    state: event.state,
    revision: event.revision,
    last_turn: event.runtime || current.last_turn,
    updated_at: new Date().toISOString(),
  }
}

export const useAppStore = create<AppState>((set, get) => ({
  characters: [],
  selectedCharacter: null,
  loadingCharacters: false,

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
  runtimeDrawerOpen: false,
  immersiveError: null,

  settings: null,

  sidebarOpen: true,
  generatingMessageId: null,
  streamController: null,

  fetchCharacters: async () => {
    set({ loadingCharacters: true })
    try {
      const res = await api.getCharacters()
      set({ characters: res.data })
    } finally {
      set({ loadingCharacters: false })
    }
  },

  selectCharacter: (char) => {
    sessionListRequestId += 1
    sessionLoadRequestId += 1
    set({
      selectedCharacter: char,
      sessions: [],
      currentSession: null,
      messages: [],
      runtime: null,
      timeline: [],
      activeLorebook: [],
      immersiveError: null,
    })
    if (char) {
      void get().fetchSessions(char.id)
    } else {
      set({ sessions: [] })
    }
  },

  createCharacter: async (data: CharacterDraft) => {
    const response = await api.createCharacter(data)
    set((state) => ({ characters: [response.data, ...state.characters] }))
    return response.data
  },

  updateCharacter: async (id: string, data: CharacterDraft) => {
    const response = await api.updateCharacter(id, data)
    set((state) => ({
      characters: state.characters.map((character) => character.id === id ? response.data : character),
      selectedCharacter: state.selectedCharacter?.id === id ? response.data : state.selectedCharacter,
    }))
    return response.data
  },

  importCharacter: async (file: File) => {
    const res = await api.importCharacter(file)
    await get().fetchCharacters()
    return res.data
  },

  deleteCharacter: async (id: string) => {
    await api.deleteCharacter(id)
    set((state) => {
      const wasSelected = state.selectedCharacter?.id === id
      return {
        characters: state.characters.filter((character) => character.id !== id),
        ...(wasSelected ? {
          selectedCharacter: null,
          sessions: [],
          currentSession: null,
          messages: [],
          runtime: null,
          timeline: [],
          activeLorebook: [],
        } : {}),
      }
    })
  },

  fetchSessions: async (characterId?: string) => {
    const requestId = ++sessionListRequestId
    const res = await api.getSessions(characterId)
    if (requestId !== sessionListRequestId) return
    if (characterId && get().selectedCharacter?.id !== characterId) return
    set({ sessions: res.data })
  },

  createSession: async (characterId: string, options) => {
    const res = await api.createSession(characterId, options?.title, options)
    await get().fetchSessions(characterId)
    return res.data
  },

  selectSession: async (session: ChatSession | null) => {
    sessionLoadRequestId += 1
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

  renameSession: async (id: string, title: string) => {
    const cleanTitle = title.trim()
    if (!cleanTitle) return
    const response = await api.updateSession(id, { title: cleanTitle })
    set((state) => ({
      sessions: state.sessions.map((session) => session.id === id ? response.data : session),
      currentSession: state.currentSession?.id === id ? response.data : state.currentSession,
    }))
  },

  deleteSession: async (id: string) => {
    const charId = get().selectedCharacter?.id
    const wasCurrent = get().currentSession?.id === id
    get().streamController?.abort()
    await api.deleteSession(id)
    set((state) => {
      const { [id]: _cache, ...sessionCache } = state.sessionCache
      const { [id]: _draft, ...drafts } = state.drafts
      const { [id]: _scroll, ...scrollPositions } = state.scrollPositions
      return {
        sessions: state.sessions.filter((session) => session.id !== id),
        sessionCache, drafts, scrollPositions,
        ...(wasCurrent ? {
          currentSession: null, messages: [], runtime: null, timeline: [], activeLorebook: [],
          generatingMessageId: null, streamController: null, immersiveError: null, messageLoadError: null,
        } : {}),
      }
    })
    if (charId) await get().fetchSessions(charId)
  },

  fetchMessages: async (sessionId: string) => {
    const requestId = sessionLoadRequestId
    if (get().currentSession?.id === sessionId) set({ loadingMessages: true, messageLoadError: null })
    try {
      const res = await api.getMessages(sessionId)
      set((state) => ({
        messages: state.currentSession?.id === sessionId ? res.data : state.messages,
        sessionCache: {
          ...state.sessionCache,
          [sessionId]: {
            messages: res.data,
            runtime: state.sessionCache[sessionId]?.runtime || (state.currentSession?.id === sessionId ? state.runtime : null),
            timeline: state.sessionCache[sessionId]?.timeline || [],
            activeLorebook: state.sessionCache[sessionId]?.activeLorebook || [],
            loadedAt: Date.now(),
          },
        },
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : '消息载入失败'
      if (requestId === sessionLoadRequestId && get().currentSession?.id === sessionId) {
        set({ messageLoadError: message, immersiveError: message })
      }
    } finally {
      if (requestId === sessionLoadRequestId && get().currentSession?.id === sessionId) {
        set({ loadingMessages: false })
      }
    }
  },

  fetchRuntime: async (sessionId: string) => {
    const requestId = sessionLoadRequestId
    if (get().currentSession?.id === sessionId) set({ runtimeLoading: true })
    try {
      const res = await api.getRuntime(sessionId)
      const lorebook = res.data.last_turn?.triggered_lorebook || []
      set((state) => ({
        runtime: state.currentSession?.id === sessionId ? res.data : state.runtime,
        activeLorebook: state.currentSession?.id === sessionId ? lorebook : state.activeLorebook,
        sessionCache: {
          ...state.sessionCache,
          [sessionId]: {
            messages: state.sessionCache[sessionId]?.messages || [],
            runtime: res.data,
            timeline: state.sessionCache[sessionId]?.timeline || [],
            activeLorebook: lorebook,
            loadedAt: Date.now(),
          },
        },
      }))
    } catch (error) {
      if (requestId === sessionLoadRequestId && get().currentSession?.id === sessionId) {
        set({ immersiveError: error instanceof Error ? error.message : '状态载入失败' })
      }
    } finally {
      if (requestId === sessionLoadRequestId && get().currentSession?.id === sessionId) {
        set({ runtimeLoading: false })
      }
    }
  },

  fetchTimeline: async (sessionId: string) => {
    const requestId = sessionLoadRequestId
    try {
      const res = await api.getTimeline(sessionId)
      set((state) => ({
        timeline: state.currentSession?.id === sessionId ? res.data : state.timeline,
        sessionCache: {
          ...state.sessionCache,
          [sessionId]: {
            messages: state.sessionCache[sessionId]?.messages || [],
            runtime: state.sessionCache[sessionId]?.runtime || null,
            timeline: res.data,
            activeLorebook: state.sessionCache[sessionId]?.activeLorebook || [],
            loadedAt: Date.now(),
          },
        },
      }))
    } catch (error) {
      if (requestId === sessionLoadRequestId && get().currentSession?.id === sessionId) {
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

  setDraft: (sessionId, value) => set((state) => ({ drafts: { ...state.drafts, [sessionId]: value } })),
  setScrollPosition: (sessionId, value) => set((state) => ({ scrollPositions: { ...state.scrollPositions, [sessionId]: value } })),

  replaceRuntimeState: async (state: RuntimeState) => {
    const session = get().currentSession
    if (!session) return
    set({ runtimeLoading: true, immersiveError: null })
    try {
      const res = await api.replaceRuntimeState(session.id, state)
      set({ runtime: res.data })
    } catch (error) {
      set({ immersiveError: error instanceof Error ? error.message : '状态保存失败' })
      throw error
    } finally {
      set({ runtimeLoading: false })
    }
  },

  rollbackToMessage: async (messageId: string) => {
    const session = get().currentSession
    if (!session || get().generatingMessageId) return
    set({ runtimeLoading: true, immersiveError: null })
    try {
      const res = await api.rollbackRuntime(session.id, messageId)
      set({ runtime: res.data, activeLorebook: res.data.last_turn?.triggered_lorebook || [] })
      await Promise.all([get().fetchMessages(session.id), get().fetchTimeline(session.id)])
    } catch (error) {
      set({ immersiveError: error instanceof Error ? error.message : '剧情回溯失败' })
    } finally {
      set({ runtimeLoading: false })
    }
  },

  sendMessage: async (content: string) => {
    const session = get().currentSession
    if (!session || !content.trim() || get().generatingMessageId) return

    const pendingUser = createLocalMessage(session.id, 'user', content, get().messages.length)
    set((state) => ({
      messages: [...state.messages, pendingUser],
      generatingMessageId: 'pending',
      immersiveError: null,
    }))

    let assistantMessageId: string | null = null
    let assistantContent = ''

    const controller = api.streamChat(session.id, content, {
      onRuntime: (event) => {
        set((state) => ({
          runtime: runtimeFromEvent(state.runtime, session.id, event),
          activeLorebook: event.triggered_lorebook || [],
        }))
      },
      onMessage: ({ user_message, assistant_message }) => {
        assistantMessageId = assistant_message.id
        set((state) => {
          let messages = state.messages.map((message) =>
            message.id === pendingUser.id && user_message ? user_message : message
          )
          const existing = messages.some((message) => message.id === assistant_message.id)
          messages = existing
            ? messages.map((message) =>
                message.id === assistant_message.id ? assistant_message : message
              )
            : [...messages, assistant_message]
          return { messages, generatingMessageId: assistant_message.id }
        })
      },
      onChunk: (chunk, messageId) => {
        assistantMessageId = messageId
        assistantContent += chunk
        set((state) => {
          const existing = state.messages.some((message) => message.id === messageId)
          if (existing) {
            return {
              messages: state.messages.map((message) =>
                message.id === messageId
                  ? { ...message, content: assistantContent, generation_status: 'generating' }
                  : message
              ),
              generatingMessageId: messageId,
            }
          }
          const localAssistant = {
            ...createLocalMessage(
              session.id,
              'assistant',
              assistantContent,
              state.messages.length,
              'generating'
            ),
            id: messageId,
          }
          return {
            messages: [...state.messages, localAssistant],
            generatingMessageId: messageId,
          }
        })
      },
      onDone: (event) => {
        set((state) => ({
          messages: state.messages.map((message) =>
            message.id === event.message_id
              ? {
                  ...message,
                  content: event.content,
                  generation_status: event.status,
                  segments: event.segments,
                  artifacts: event.artifacts,
                  speaker_metadata: event.speaker_metadata,
                  render_version: event.render_version,
                }
              : message
          ),
          runtime: runtimeAfterDone(state.runtime, session.id, event),
          timeline: event.runtime ? mergeTurn(state.timeline, event.runtime) : state.timeline,
          activeLorebook: event.runtime?.triggered_lorebook || state.activeLorebook,
          generatingMessageId: null,
          streamController: null,
        }))
        const characterId = get().selectedCharacter?.id
        if (characterId) void get().fetchSessions(characterId)
      },
      onError: (error, messageId) => {
        const targetId = messageId || assistantMessageId
        set((state) => {
          const base = {
            generatingMessageId: null,
            streamController: null,
            immersiveError: error,
          }
          if (targetId && state.messages.some((message) => message.id === targetId)) {
            return {
              ...base,
              messages: state.messages.map((message) =>
                message.id === targetId
                  ? {
                      ...message,
                      content: message.content || `生成失败：${error}`,
                      generation_status: 'error' as const,
                    }
                  : message
              ),
            }
          }
          return {
            ...base,
            messages: [
              ...state.messages,
              createLocalMessage(
                session.id,
                'assistant',
                `生成失败：${error}`,
                state.messages.length,
                'error'
              ),
            ],
          }
        })
      },
    })

    set({ streamController: controller })
  },

  sendChoice: async (choice: string) => {
    await get().sendMessage(choice)
  },

  stopGeneration: async () => {
    const controller = get().streamController
    const messageId = get().generatingMessageId
    try {
      if (messageId && messageId !== 'pending') {
        await api.stopGeneration(messageId)
        set((state) => ({
          messages: state.messages.map((message) =>
            message.id === messageId
              ? { ...message, generation_status: 'stopped' }
              : message
          ),
        }))
      }
    } catch {
      // The stream may already have completed between the click and this request.
    } finally {
      controller?.abort()
      set({ generatingMessageId: null, streamController: null })
    }
  },

  regenerateLast: async () => {
    const session = get().currentSession
    if (!session || get().generatingMessageId) return

    const previousAssistant = [...get().messages]
      .reverse()
      .find((message) => message.role === 'assistant')
    const previousAssistantId = previousAssistant?.id
    let assistantMessageId: string | null = null
    let assistantContent = ''

    set({ generatingMessageId: 'pending', immersiveError: null })

    const controller = api.regenerate(session.id, {
      onRuntime: (event) => {
        set((state) => ({
          runtime: runtimeFromEvent(state.runtime, session.id, event),
          activeLorebook: event.triggered_lorebook || [],
        }))
      },
      onMessage: ({ assistant_message }) => {
        assistantMessageId = assistant_message.id
        set((state) => ({
          messages: state.messages.some((message) => message.id === assistant_message.id)
            ? state.messages
            : [...state.messages, assistant_message],
          generatingMessageId: assistant_message.id,
        }))
      },
      onChunk: (chunk, messageId) => {
        assistantMessageId = messageId
        assistantContent += chunk
        set((state) => ({
          messages: state.messages.map((message) =>
            message.id === messageId
              ? { ...message, content: assistantContent, generation_status: 'generating' }
              : message
          ),
          generatingMessageId: messageId,
        }))
      },
      onDone: (event) => {
        set((state) => {
          const updated = state.messages.map((message) =>
            message.id === event.message_id
              ? {
                  ...message,
                  content: event.content,
                  generation_status: event.status,
                  segments: event.segments,
                  artifacts: event.artifacts,
                  speaker_metadata: event.speaker_metadata,
                  render_version: event.render_version,
                }
              : message
          )
          const messages = event.status === 'complete'
            ? updated.filter((message) => message.id !== previousAssistantId)
            : updated.filter((message) => message.id !== event.message_id)
          const timelineWithoutOld = previousAssistantId
            ? state.timeline.filter((turn) => turn.message_id !== previousAssistantId)
            : state.timeline
          return {
          messages,
          runtime: runtimeAfterDone(state.runtime, session.id, event),
          timeline: event.runtime ? mergeTurn(timelineWithoutOld, event.runtime) : timelineWithoutOld,
          activeLorebook: event.runtime?.triggered_lorebook || state.activeLorebook,
          generatingMessageId: null,
          streamController: null,
          }
        })
        const characterId = get().selectedCharacter?.id
        if (characterId) void get().fetchSessions(characterId)
      },
      onError: (error, messageId) => {
        const targetId = messageId || assistantMessageId
        set((state) => ({
          messages: targetId
            ? state.messages.filter((message) => message.id !== targetId)
            : state.messages,
          generatingMessageId: null,
          streamController: null,
          immersiveError: `重新生成失败，已保留原回复：${error}`,
        }))
      },
    })

    set({ streamController: controller })
  },

  editMessage: async (id: string, content: string) => {
    const response = await api.updateMessage(id, { content })
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? response.data : message
      ),
    }))
  },

  deleteMessage: async (id: string) => {
    const session = get().currentSession
    try {
      await api.deleteMessage(id)
      set((state) => ({ messages: state.messages.filter((message) => message.id !== id) }))
      if (session) {
        await Promise.all([get().fetchRuntime(session.id), get().fetchTimeline(session.id)])
      }
    } catch (error) {
      set({ immersiveError: error instanceof Error ? error.message : '消息删除失败' })
      throw error
    }
  },

  fetchSettings: async () => {
    const res = await api.getSettings()
    set({ settings: res.data })
  },

  updateSettings: async (data) => {
    const res = await api.updateSettings(data)
    set({ settings: res.data })
  },

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleRuntimeDrawer: (open) =>
    set((state) => ({ runtimeDrawerOpen: open ?? !state.runtimeDrawerOpen })),
  clearImmersiveError: () => set({ immersiveError: null }),
}))
