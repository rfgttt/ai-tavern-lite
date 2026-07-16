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
  it('creates and updates characters while keeping the selected record current', async () => {
    const created = await useAppStore.getState().createCharacter({
      name: '雾叶泠',
      description: '魔法少女',
      personality: '坚定',
      scenario: '雨夜',
      first_message: '晚上好。',
    })

    expect(created.id).toBe('character-created')
    expect(useAppStore.getState().characters[0].name).toBe('雾叶泠')

    useAppStore.setState({
      characters: charactersFixture,
      selectedCharacter: charactersFixture[0],
    })
    const updated = await useAppStore.getState().updateCharacter('character-linya', {
      name: '林雅（编辑后）',
      description: '新的描述',
      personality: '更坚定',
      scenario: '清晨酒馆',
      first_message: '早上好。',
    })

    expect(updated.name).toBe('林雅（编辑后）')
    expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅（编辑后）')
    expect(useAppStore.getState().characters[0].description).toBe('新的描述')
  })

})
