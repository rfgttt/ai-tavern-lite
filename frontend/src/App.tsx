import { useEffect } from 'react'
import AppShell from '@/components/AppShell'
import { useAppStore } from '@/stores/appStore'
import { getCharacter, getSessions } from '@/api'

function App() {
  const { fetchSettings } = useAppStore()

  useEffect(() => {
    void fetchSettings()
  }, [fetchSettings])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('selftest') !== '1') return

    window.__AI_TAVERN_TEST__ = {
      prepare: async (characterId: string, sessionId: string) => {
        const character = (await getCharacter(characterId)).data
        useAppStore.getState().selectCharacter(character)
        const sessions = (await getSessions(characterId)).data
        const session = sessions.find((item) => item.id === sessionId)
        if (!session) throw new Error('自检会话不存在')
        await useAppStore.getState().selectSession(session)
        return window.__AI_TAVERN_TEST__!.snapshot()
      },
      snapshot: () => {
        const state = useAppStore.getState()
        const sessionId = state.currentSession?.id || ''
        return {
          selectedCharacterId: state.selectedCharacter?.id || null,
          currentSessionId: state.currentSession?.id || null,
          messageCount: state.messages.length,
          loadingMessages: state.loadingMessages,
          messageLoadError: state.messageLoadError,
          draft: sessionId ? state.drafts[sessionId] || '' : '',
          scrollPosition: sessionId ? state.scrollPositions[sessionId] || 0 : 0,
        }
      },
      setDraft: (sessionId: string, value: string) => useAppStore.getState().setDraft(sessionId, value),
      setScrollPosition: (sessionId: string, value: number) => useAppStore.getState().setScrollPosition(sessionId, value),
    }
    return () => { delete window.__AI_TAVERN_TEST__ }
  }, [])

  return <AppShell />
}

export default App
