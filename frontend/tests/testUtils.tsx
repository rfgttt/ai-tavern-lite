import type { ReactElement } from 'react'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useAppStore } from '@/stores/appStore'
import { ToastProvider } from '@/components/ui/ToastProvider'

export const resetAppStore = () => {
  useAppStore.getState().resetStore()
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
