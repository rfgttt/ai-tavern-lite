import * as api from '@/api'
import {
  invalidateSessionListRequests,
  invalidateSessionLoadRequests,
} from '../requestGuards'
import type { AppStoreSlice, CharacterSlice } from '../types'

export const createCharacterSlice: AppStoreSlice<CharacterSlice> = (set, get) => ({
  characters: [],
  selectedCharacter: null,
  loadingCharacters: false,

  fetchCharacters: async () => {
    set({ loadingCharacters: true })
    try {
      const response = await api.getCharacters()
      set({ characters: response.data })
    } finally {
      set({ loadingCharacters: false })
    }
  },

  selectCharacter: (character) => {
    invalidateSessionListRequests()
    invalidateSessionLoadRequests()
    get().streamController?.abort()
    set({
      selectedCharacter: character,
      sessions: [],
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
    if (character) {
      void get().fetchSessions(character.id)
    }
  },

  createCharacter: async (data) => {
    const response = await api.createCharacter(data)
    set((state) => ({ characters: [response.data, ...state.characters] }))
    return response.data
  },

  updateCharacter: async (id, data) => {
    const response = await api.updateCharacter(id, data)
    set((state) => ({
      characters: state.characters.map((character) =>
        character.id === id ? response.data : character
      ),
      selectedCharacter:
        state.selectedCharacter?.id === id ? response.data : state.selectedCharacter,
    }))
    return response.data
  },

  importCharacter: async (file, securityMode = 'safe_copy') => {
    const response = await api.importCharacter(file, securityMode)
    await get().fetchCharacters()
    return response.data
  },

  deleteCharacter: async (id) => {
    const wasSelected = get().selectedCharacter?.id === id
    if (wasSelected) {
      invalidateSessionListRequests()
      invalidateSessionLoadRequests()
      get().streamController?.abort()
    }
    await api.deleteCharacter(id)
    set((state) => {
      return {
        characters: state.characters.filter((character) => character.id !== id),
        ...(wasSelected
          ? {
              selectedCharacter: null,
              sessions: [],
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
  },
})
