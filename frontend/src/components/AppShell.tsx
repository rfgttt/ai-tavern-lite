import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ChatPage from '@/pages/ChatPage'
import SettingsPage from '@/pages/SettingsPage'
import MemoryPage from '@/pages/MemoryPage'
import SelfTestPage from '@/pages/SelfTestPage'

export default function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    if (location.pathname === '/') navigate('/chat', { replace: true })
  }, [location.pathname, navigate])

  if (location.pathname === '/self-test') return <SelfTestPage />

  const overlay = location.pathname === '/settings' || location.pathname === '/memory'

  return (
    <div data-testid="app-shell" className="relative min-h-screen bg-tavern-bg-deepest text-tavern-text-primary antialiased">
      <ChatPage />
      {overlay ? (
        <div data-testid="settings-overlay" className="fixed inset-0 z-[80] bg-black/55 backdrop-blur-sm p-0 sm:p-5 animate-fade-in">
          <div className="h-full max-w-6xl mx-auto overflow-hidden rounded-none sm:rounded-2xl border border-tavern-border-subtle bg-tavern-bg-deepest shadow-large">
            {location.pathname === '/settings' ? <SettingsPage embedded /> : <MemoryPage embedded />}
          </div>
        </div>
      ) : null}
    </div>
  )
}
