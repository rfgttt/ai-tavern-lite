/// <reference types="vite/client" />

interface Window {
  __AI_TAVERN_TEST__?: {
    prepare: (characterId: string, sessionId: string) => Promise<{
      selectedCharacterId: string | null
      currentSessionId: string | null
      messageCount: number
      loadingMessages: boolean
      messageLoadError: string | null
      hasMoreMessages: boolean
      loadingOlderMessages: boolean
      olderMessageLoadError: string | null
      draft: string
      scrollPosition: number
    }>
    snapshot: () => {
      selectedCharacterId: string | null
      currentSessionId: string | null
      messageCount: number
      loadingMessages: boolean
      messageLoadError: string | null
      hasMoreMessages: boolean
      loadingOlderMessages: boolean
      olderMessageLoadError: string | null
      draft: string
      scrollPosition: number
    }
    setDraft: (sessionId: string, value: string) => void
    setScrollPosition: (sessionId: string, value: number) => void
  }
}
