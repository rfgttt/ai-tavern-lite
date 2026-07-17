import * as api from '@/api'
import type { AppStoreSlice, SettingsSlice } from '../types'

export const createSettingsSlice: AppStoreSlice<SettingsSlice> = (set) => ({
  settings: null,

  fetchSettings: async () => {
    const response = await api.getSettings()
    set({ settings: response.data })
  },

  updateSettings: async (data) => {
    const response = await api.updateSettings(data)
    set({ settings: response.data })
  },
})
