import axios from 'axios'
import type {
  Character,
  CharacterDraft,
  CharacterSessionOptions,
  ChatSession,
  SessionCreateOptions,
  Message,
  Memory,
  AppSettings,
  Lorebook,
  PromptPreview,
  ConnectionTestResult,
  StreamDoneEvent,
  StreamMessageEvent,
  StreamRuntimeEvent,
  RuntimeSession,
  RuntimeState,
  TurnRuntime,
  DiagnosticHealth,
  DiagnosticRequestSummary,
  CardCompatibilityReport,
  Persona,
  CharacterGroup,
  SessionBranch,
} from '@/types'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Health
export const healthCheck = () => api.get('/health')

// Characters
export const getCharacters = () => api.get<Character[]>('/characters')
export const createCharacter = (data: CharacterDraft) => api.post<Character>('/characters', data)
export const getCharacter = (id: string) => api.get<Character>(`/characters/${id}`)
export const getCharacterSessionOptions = (id: string) => api.get<CharacterSessionOptions>(`/characters/${id}/session-options`)
export const getCharacterCompatibility = (id: string) => api.get<CardCompatibilityReport>(`/characters/${id}/compatibility`)
export const importCharacter = (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<Character>('/characters/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
export const updateCharacter = (id: string, data: Partial<Character> & { normalized_json?: string }) =>
  api.put<Character>(`/characters/${id}`, data)
export const deleteCharacter = (id: string) => api.delete(`/characters/${id}`)
export const exportCharacter = (id: string) => api.get(`/characters/${id}/export`)
export const getLorebook = (id: string) => api.get<Lorebook>(`/characters/${id}/lorebook`)
export const updateLorebook = (id: string, data: Lorebook) =>
  api.put<Lorebook>(`/characters/${id}/lorebook`, data)

// Sessions
export const getSessions = (characterId?: string) =>
  api.get<ChatSession[]>('/sessions', { params: characterId ? { character_id: characterId } : undefined })
export const createSession = (characterId: string, title?: string, options?: SessionCreateOptions) =>
  api.post<ChatSession>('/sessions', { character_id: characterId, title, ...options })
export const updateSession = (id: string, data: { title?: string }) =>
  api.put<ChatSession>(`/sessions/${id}`, data)
export const deleteSession = (id: string) => api.delete(`/sessions/${id}`)
export const getMessages = (sessionId: string) =>
  api.get<Message[]>(`/sessions/${sessionId}/messages`)
export const addMessage = (sessionId: string, role: string, content: string) =>
  api.post<Message>(`/sessions/${sessionId}/messages`, { session_id: sessionId, role, content })
export const updateMessage = (id: string, data: { content?: string; generation_status?: string }) =>
  api.put<Message>(`/messages/${id}`, data)
export const deleteMessage = (id: string) => api.delete(`/messages/${id}`)
export const exportSession = (id: string) => api.get(`/sessions/${id}/export`)

export interface StreamHandlers {
  onRuntime: (event: StreamRuntimeEvent) => void
  onMessage: (event: StreamMessageEvent) => void
  onChunk: (content: string, messageId: string) => void
  onDone: (event: StreamDoneEvent) => void
  onError: (error: string, messageId?: string) => void
}

const postSse = (path: string, body: unknown, handlers: StreamHandlers) => {
  const controller = new AbortController()

  fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try {
          const payload = await response.json()
          detail = payload.detail || detail
        } catch {
          // Keep the HTTP status fallback.
        }
        throw new Error(detail)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('响应不包含可读取的数据流')

      const decoder = new TextDecoder()
      let buffer = ''
      let receivedDoneEvent = false

      const processLine = (line: string) => {
        if (!line.startsWith('data: ')) return
        const data = line.slice(6)
        if (!data || data === '[DONE]') return

        try {
          const parsed = JSON.parse(data)
          if (parsed.type === 'runtime') {
            handlers.onRuntime(parsed as StreamRuntimeEvent)
          } else if (parsed.type === 'message') {
            handlers.onMessage(parsed as StreamMessageEvent)
          } else if (parsed.type === 'content') {
            handlers.onChunk(parsed.content, parsed.message_id)
          } else if (parsed.type === 'done') {
            receivedDoneEvent = true
            handlers.onDone(parsed as StreamDoneEvent)
          } else if (parsed.type === 'error') {
            handlers.onError(parsed.message, parsed.message_id)
          }
        } catch {
          // Ignore malformed individual SSE frames without terminating the stream.
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        lines.forEach(processLine)
      }

      buffer += decoder.decode()
      if (buffer) processLine(buffer)
      if (!receivedDoneEvent) {
        handlers.onError('数据流意外结束')
      }
    })
    .catch((error: Error) => {
      if (error.name !== 'AbortError') {
        handlers.onError(error.message)
      }
    })

  return controller
}


// Immersive runtime
export const getRuntime = (sessionId: string) =>
  api.get<RuntimeSession>(`/sessions/${sessionId}/runtime`)
export const replaceRuntimeState = (sessionId: string, state: RuntimeState) =>
  api.put<RuntimeSession>(`/sessions/${sessionId}/runtime/state`, { state })
export const getTimeline = (sessionId: string) =>
  api.get<TurnRuntime[]>(`/sessions/${sessionId}/timeline`)
export const rollbackRuntime = (sessionId: string, messageId: string) =>
  api.post<RuntimeSession>(`/sessions/${sessionId}/rollback`, { message_id: messageId })

// Chat
export const streamChat = (sessionId: string, message: string, handlers: StreamHandlers) =>
  postSse('/api/chat/stream', { session_id: sessionId, message }, handlers)

export const stopGeneration = (messageId: string) =>
  api.post('/chat/stop', { message_id: messageId })

export const regenerate = (sessionId: string, handlers: StreamHandlers) =>
  postSse('/api/chat/regenerate', { session_id: sessionId, message: '' }, handlers)

export const previewPrompt = (sessionId: string, message: string) =>
  api.post<PromptPreview>('/chat/prompt-preview', { session_id: sessionId, message })

// Settings
export const getSettings = () => api.get<AppSettings>('/settings')
export const updateSettings = (data: Partial<AppSettings> & { api_key?: string; clear_api_key?: boolean }) =>
  api.put<AppSettings>('/settings', data)
export const testConnection = (data?: Partial<AppSettings> & { api_key?: string }) =>
  api.post<ConnectionTestResult>('/settings/test-connection', data || {})


// Diagnostics
export const getDiagnosticsHealth = () =>
  api.get<DiagnosticHealth>('/diagnostics/health')
export const getLatestDiagnostics = () =>
  api.get<DiagnosticRequestSummary | null>('/diagnostics/latest')
export const exportDiagnostics = () =>
  api.post<Blob>('/diagnostics/export', undefined, { responseType: 'blob' })
export const clearDiagnosticsLogs = () =>
  api.delete<{ success: boolean; message: string }>('/diagnostics/logs')

// Memory
export type MemoryScopeFilter = 'effective' | 'session' | 'character' | 'global'

export const getMemories = (params?: {
  character_id?: string
  session_id?: string
  scope?: MemoryScopeFilter
  category?: string
  search?: string
}) => api.get<Memory[]>('/memories', { params })
export const createMemory = (data: Partial<Memory>) =>
  api.post<Memory>('/memories', data)
export const updateMemory = (id: string, data: Partial<Memory>) =>
  api.put<Memory>(`/memories/${id}`, data)
export const deleteMemory = (id: string) => api.delete(`/memories/${id}`)

export default api


// AI Tavern 2.0 foundations
export const getPersonas = () => api.get<Persona[]>('/personas')
export const createPersona = (data: Partial<Persona> & { name: string }) => api.post<Persona>('/personas', data)
export const updatePersona = (id: string, data: Partial<Persona>) => api.put<Persona>(`/personas/${id}`, data)
export const deletePersona = (id: string) => api.delete(`/personas/${id}`)

export const getGroups = () => api.get<CharacterGroup[]>('/groups')
export const createGroup = (data: { name: string; description?: string; character_ids: string[]; metadata?: Record<string, unknown> }) => api.post<CharacterGroup>('/groups', data)
export const updateGroup = (id: string, data: { name: string; description?: string; character_ids: string[]; metadata?: Record<string, unknown> }) => api.put<CharacterGroup>(`/groups/${id}`, data)
export const deleteGroup = (id: string) => api.delete(`/groups/${id}`)

export const getBranches = (sessionId: string) => api.get<SessionBranch[]>(`/sessions/${sessionId}/branches`)
export const saveBranch = (sessionId: string, data: { title: string; parent_message_id?: string }) => api.post<SessionBranch>(`/sessions/${sessionId}/branches`, data)
export const restoreBranch = (sessionId: string, branchId: string) => api.post(`/sessions/${sessionId}/branches/${branchId}/restore`)
export const deleteBranch = (sessionId: string, branchId: string) => api.delete(`/sessions/${sessionId}/branches/${branchId}`)


// One-click self-test
export const submitSelfTestFrontend = (runId: string, report: Record<string, unknown>) =>
  api.post(`/self-test/runs/${runId}/frontend`, report)
export const getSelfTestRun = (runId: string) =>
  api.get(`/self-test/runs/${runId}`)
