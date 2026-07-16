import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useAppStore } from '@/stores/appStore'
import { ToastProvider } from '@/components/ui/ToastProvider'

export const resetAppStore = () => {
  useAppStore.setState({
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
  })
}

export const renderWithRouter = (ui: ReactElement, initialEntries = ['/chat']) =>
  render(
    <MemoryRouter
      initialEntries={initialEntries}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ToastProvider>{ui}</ToastProvider>
    </MemoryRouter>,
  )
