import type { Character, ChatSession } from '@/types'

export const charactersFixture: Character[] = [
  {
    id: 'character-linya',
    name: '林雅',
    description: '安静而敏锐的旅店常客',
    personality: '克制、友善',
    scenario: '深夜的酒馆',
    first_message: '晚上好。',
    avatar_path: '',
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
  },
  {
    id: 'character-arden',
    name: 'Arden',
    description: 'Travelling cartographer',
    personality: 'Curious',
    scenario: 'A roadside inn',
    first_message: 'Good evening.',
    avatar_path: '',
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
  },
]

export const sessionsFixture: ChatSession[] = [
  {
    id: 'session-linya-1',
    character_id: 'character-linya',
    persona_id: null,
    group_id: null,
    title: '初次见面',
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
  },
]
