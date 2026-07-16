import { waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from '@/stores/appStore'
import { charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { resetAppStore } from '../testUtils'

describe('appStore character and session actions', () => {
  beforeEach(() => {
    resetAppStore()
  })

  it('loads characters and always clears the loading flag', async () => {
    const request = useAppStore.getState().fetchCharacters()
    expect(useAppStore.getState().loadingCharacters).toBe(true)

    await request

    expect(useAppStore.getState().characters).toEqual(charactersFixture)
    expect(useAppStore.getState().loadingCharacters).toBe(false)
  })

  it('selecting a character resets the current conversation and loads its sessions', async () => {
    useAppStore.setState({
      currentSession: sessionsFixture[0],
      messages: [
        {
          id: 'old-message',
          session_id: sessionsFixture[0].id,
          role: 'user',
          content: '旧消息',
          sequence: 0,
          generation_status: 'complete',
          created_at: '2026-07-16T00:00:00Z',
          updated_at: '2026-07-16T00:00:00Z',
        },
      ],
    })

    useAppStore.getState().selectCharacter(charactersFixture[0])

    expect(useAppStore.getState().selectedCharacter?.id).toBe('character-linya')
    expect(useAppStore.getState().currentSession).toBeNull()
    expect(useAppStore.getState().messages).toEqual([])

    await waitFor(() => expect(useAppStore.getState().sessions).toEqual(sessionsFixture))
  })

  it('creates a session with persona and group bindings, then refreshes the list', async () => {
    useAppStore.setState({ selectedCharacter: charactersFixture[0] })

    const created = await useAppStore.getState().createSession('character-linya', {
      title: '新的旅程',
      persona_id: 'persona-1',
      group_id: 'group-1',
    })

    expect(created).toMatchObject({
      id: 'session-created',
      title: '新的旅程',
      persona_id: 'persona-1',
      group_id: 'group-1',
    })
    expect(useAppStore.getState().sessions).toEqual(sessionsFixture)
  })
})
