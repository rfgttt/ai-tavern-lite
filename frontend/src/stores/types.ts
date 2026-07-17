import type { StateCreator } from 'zustand'
import type {
  AppSettings,
  Character,
  CharacterDraft,
  ChatSession,
  LorebookTrigger,
  Message,
  RuntimeSession,
  RuntimeState,
  SessionCreateOptions,
  TurnRuntime,
} from '@/types'

export interface SessionCacheEntry {
  messages: Message[]
  runtime: RuntimeSession | null
  timeline: TurnRuntime[]
  activeLorebook: LorebookTrigger[]
  loadedAt: number
}

export interface CharacterSlice {
  characters: Character[]
  selectedCharacter: Character | null
  loadingCharacters: boolean

  fetchCharacters: () => Promise<void>
  selectCharacter: (character: Character | null) => void
  createCharacter: (data: CharacterDraft) => Promise<Character>
  updateCharacter: (id: string, data: CharacterDraft) => Promise<Character>
  importCharacter: (file: File) => Promise<Character>
  deleteCharacter: (id: string) => Promise<void>
}

export interface SessionSlice {
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

  fetchSessions: (characterId?: string) => Promise<void>
  createSession: (characterId: string, options?: SessionCreateOptions) => Promise<ChatSession>
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
}

export interface ChatSlice {
  generatingMessageId: string | null
  streamController: AbortController | null

  sendMessage: (content: string) => Promise<void>
  sendChoice: (choice: string) => Promise<void>
  stopGeneration: () => Promise<void>
  regenerateLast: () => Promise<void>
  editMessage: (id: string, content: string) => Promise<void>
  deleteMessage: (id: string) => Promise<void>
}

export interface SettingsSlice {
  settings: AppSettings | null

  fetchSettings: () => Promise<void>
  updateSettings: (
    data: Partial<AppSettings> & { api_key?: string; clear_api_key?: boolean }
  ) => Promise<void>
}

export interface UiSlice {
  sidebarOpen: boolean
  runtimeDrawerOpen: boolean
  immersiveError: string | null

  toggleSidebar: () => void
  toggleRuntimeDrawer: (open?: boolean) => void
  clearImmersiveError: () => void
}

export interface AppState
  extends CharacterSlice,
    SessionSlice,
    ChatSlice,
    SettingsSlice,
    UiSlice {
  resetStore: () => void
}

export type AppStoreSlice<TSlice> = StateCreator<AppState, [], [], TSlice>
