import type { AppState } from './types'

export type AppStateData = Pick<
  AppState,
  | 'characters'
  | 'selectedCharacter'
  | 'loadingCharacters'
  | 'sessions'
  | 'currentSession'
  | 'messages'
  | 'loadingMessages'
  | 'messageLoadError'
  | 'sessionCache'
  | 'drafts'
  | 'scrollPositions'
  | 'runtime'
  | 'timeline'
  | 'activeLorebook'
  | 'runtimeLoading'
  | 'settings'
  | 'sidebarOpen'
  | 'runtimeDrawerOpen'
  | 'immersiveError'
  | 'generatingMessageId'
  | 'streamController'
>

export const createInitialAppState = (): AppStateData => ({
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

  settings: null,

  sidebarOpen: true,
  runtimeDrawerOpen: false,
  immersiveError: null,
  generatingMessageId: null,
  streamController: null,
})
