import * as api from '@/api'
import { createLocalMessage, mergeTurn, runtimeAfterDone, runtimeFromEvent } from '../chatHelpers'
import { beginChatStreamRequest, invalidateChatStreamRequests, isCurrentChatStreamRequest } from '../requestGuards'
import type { AppStoreSlice, ChatSlice } from '../types'

export const createChatSlice: AppStoreSlice<ChatSlice> = (set, get) => ({
  generatingMessageId: null,
  streamController: null,

  sendMessage: async (content) => {
    const session = get().currentSession
    if (!session || !content.trim() || get().generatingMessageId) return

    const requestId = beginChatStreamRequest()
    const isActiveStream = () =>
      isCurrentChatStreamRequest(requestId) && get().currentSession?.id === session.id

    const pendingUser = createLocalMessage(
      session.id,
      'user',
      content,
      get().messages.length,
    )
    set((state) => ({
      messages: [...state.messages, pendingUser],
      generatingMessageId: 'pending',
      immersiveError: null,
    }))

    let assistantMessageId: string | null = null
    let assistantContent = ''

    const controller = api.streamChat(session.id, content, {
      onRuntime: (event) => {
        if (!isActiveStream()) return
        set((state) => ({
          runtime: runtimeFromEvent(state.runtime, session.id, event),
          activeLorebook: event.triggered_lorebook || [],
        }))
      },
      onMessage: ({ user_message, assistant_message }) => {
        if (!isActiveStream()) return
        assistantMessageId = assistant_message.id
        set((state) => {
          let messages = state.messages.map((message) =>
            message.id === pendingUser.id && user_message ? user_message : message,
          )
          const existing = messages.some(
            (message) => message.id === assistant_message.id,
          )
          messages = existing
            ? messages.map((message) =>
                message.id === assistant_message.id ? assistant_message : message,
              )
            : [...messages, assistant_message]
          return { messages, generatingMessageId: assistant_message.id }
        })
      },
      onChunk: (chunk, messageId) => {
        if (!isActiveStream()) return
        assistantMessageId = messageId
        assistantContent += chunk
        set((state) => {
          const existing = state.messages.some((message) => message.id === messageId)
          if (existing) {
            return {
              messages: state.messages.map((message) =>
                message.id === messageId
                  ? {
                      ...message,
                      content: assistantContent,
                      generation_status: 'generating',
                    }
                  : message,
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
              'generating',
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
        if (!isActiveStream()) return
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
              : message,
          ),
          runtime: runtimeAfterDone(state.runtime, session.id, event),
          timeline: event.runtime ? mergeTurn(state.timeline, event.runtime) : state.timeline,
          activeLorebook:
            event.runtime?.triggered_lorebook || state.activeLorebook,
          generatingMessageId: null,
          streamController: null,
        }))
        const characterId = get().selectedCharacter?.id
        if (characterId) void get().fetchSessions(characterId)
      },
      onError: (error, messageId) => {
        if (!isActiveStream()) return
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
                  : message,
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
                'error',
              ),
            ],
          }
        })
      },
    })

    if (isActiveStream()) set({ streamController: controller })
    else controller.abort()
  },

  sendChoice: async (choice) => {
    await get().sendMessage(choice)
  },

  stopGeneration: async () => {
    const controller = get().streamController
    const messageId = get().generatingMessageId
    invalidateChatStreamRequests()
    try {
      if (messageId && messageId !== 'pending') {
        await api.stopGeneration(messageId)
        set((state) => ({
          messages: state.messages.map((message) =>
            message.id === messageId
              ? { ...message, generation_status: 'stopped' }
              : message,
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

    const requestId = beginChatStreamRequest()
    const isActiveStream = () =>
      isCurrentChatStreamRequest(requestId) && get().currentSession?.id === session.id

    const previousAssistant = [...get().messages]
      .reverse()
      .find((message) => message.role === 'assistant')
    const previousAssistantId = previousAssistant?.id
    let assistantMessageId: string | null = null
    let assistantContent = ''

    set({ generatingMessageId: 'pending', immersiveError: null })

    const controller = api.regenerate(session.id, {
      onRuntime: (event) => {
        if (!isActiveStream()) return
        set((state) => ({
          runtime: runtimeFromEvent(state.runtime, session.id, event),
          activeLorebook: event.triggered_lorebook || [],
        }))
      },
      onMessage: ({ assistant_message }) => {
        if (!isActiveStream()) return
        assistantMessageId = assistant_message.id
        set((state) => ({
          messages: state.messages.some(
            (message) => message.id === assistant_message.id,
          )
            ? state.messages
            : [...state.messages, assistant_message],
          generatingMessageId: assistant_message.id,
        }))
      },
      onChunk: (chunk, messageId) => {
        if (!isActiveStream()) return
        assistantMessageId = messageId
        assistantContent += chunk
        set((state) => ({
          messages: state.messages.map((message) =>
            message.id === messageId
              ? {
                  ...message,
                  content: assistantContent,
                  generation_status: 'generating',
                }
              : message,
          ),
          generatingMessageId: messageId,
        }))
      },
      onDone: (event) => {
        if (!isActiveStream()) return
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
              : message,
          )
          const messages =
            event.status === 'complete'
              ? updated.filter((message) => message.id !== previousAssistantId)
              : updated.filter((message) => message.id !== event.message_id)
          const timelineWithoutOld = previousAssistantId
            ? state.timeline.filter(
                (turn) => turn.message_id !== previousAssistantId,
              )
            : state.timeline
          return {
            messages,
            runtime: runtimeAfterDone(state.runtime, session.id, event),
            timeline: event.runtime
              ? mergeTurn(timelineWithoutOld, event.runtime)
              : timelineWithoutOld,
            activeLorebook:
              event.runtime?.triggered_lorebook || state.activeLorebook,
            generatingMessageId: null,
            streamController: null,
          }
        })
        const characterId = get().selectedCharacter?.id
        if (characterId) void get().fetchSessions(characterId)
      },
      onError: (error, messageId) => {
        if (!isActiveStream()) return
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

    if (isActiveStream()) set({ streamController: controller })
    else controller.abort()
  },

  editMessage: async (id, content) => {
    const response = await api.updateMessage(id, { content })
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? response.data : message,
      ),
    }))
  },

  deleteMessage: async (id) => {
    const session = get().currentSession
    try {
      await api.deleteMessage(id)
      set((state) => ({
        messages: state.messages.filter((message) => message.id !== id),
      }))
      if (session) {
        await Promise.all([
          get().fetchRuntime(session.id),
          get().fetchTimeline(session.id),
        ])
      }
    } catch (error) {
      set({ immersiveError: error instanceof Error ? error.message : '消息删除失败' })
      throw error
    }
  },
})
