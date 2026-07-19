import * as api from '@/api'
import type { AppStoreSlice, SettingsSlice } from '../types'

let settingsFetchRequestId = 0
let settingsWriteRequestId = 0
let settingsWriteGeneration = 0
let activeSettingsWriteRequestId: number | null = null

export const createSettingsSlice: AppStoreSlice<SettingsSlice> = (set) => ({
  settings: null,

  fetchSettings: async () => {
    const requestId = ++settingsFetchRequestId
    const writeGeneration = settingsWriteGeneration
    const response = await api.getSettings()
    if (
      requestId === settingsFetchRequestId
      && writeGeneration === settingsWriteGeneration
      && activeSettingsWriteRequestId === null
    ) {
      set({ settings: response.data })
    }
  },

  updateSettings: async (data) => {
    settingsWriteGeneration += 1
    const requestId = ++settingsWriteRequestId
    activeSettingsWriteRequestId = requestId
    try {
      const response = await api.updateSettings(data)
      if (requestId === settingsWriteRequestId) {
        set({ settings: response.data })
      }
    } finally {
      if (activeSettingsWriteRequestId === requestId) {
        activeSettingsWriteRequestId = null
      }
    }
  },
})
