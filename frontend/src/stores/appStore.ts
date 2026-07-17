import { create } from 'zustand'
import { createInitialAppState } from './initialState'
import { resetRequestGuards } from './requestGuards'
import { createCharacterSlice } from './slices/characterSlice'
import { createChatSlice } from './slices/chatSlice'
import { createSessionSlice } from './slices/sessionSlice'
import { createSettingsSlice } from './slices/settingsSlice'
import { createUiSlice } from './slices/uiSlice'
import type { AppState } from './types'

export type { AppState } from './types'

export const useAppStore = create<AppState>()((...store) => ({
  ...createCharacterSlice(...store),
  ...createSessionSlice(...store),
  ...createChatSlice(...store),
  ...createSettingsSlice(...store),
  ...createUiSlice(...store),

  resetStore: () => {
    const [, get] = store
    get().streamController?.abort()
    resetRequestGuards()
    store[0](createInitialAppState())
  },
}))
