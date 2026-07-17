import type { AppStoreSlice, UiSlice } from '../types'

export const createUiSlice: AppStoreSlice<UiSlice> = (set) => ({
  sidebarOpen: true,
  runtimeDrawerOpen: false,
  immersiveError: null,

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  toggleRuntimeDrawer: (open) =>
    set((state) => ({ runtimeDrawerOpen: open ?? !state.runtimeDrawerOpen })),
  clearImmersiveError: () => set({ immersiveError: null }),
})
