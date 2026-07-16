import type { AppSettings, Character, ChatSession, Lorebook } from '@/types'

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

export const lorebookFixture: Lorebook = {
  entries: [
    {
      id: 1,
      keys: ['图书馆'],
      secondary_keys: [],
      comment: '古老图书馆',
      content: '这里收藏着失落的魔法书。',
      constant: false,
      selective: false,
      enabled: true,
      insertion_order: 0,
      position: 'before_char',
      use_regex: false,
      probability: 100,
      extensions: {},
    },
  ],
}


export const appSettingsFixture: AppSettings = {
  provider_name: 'OpenAI Compatible',
  base_url: 'https://api.example.com/v1',
  model: 'test-model',
  temperature: 0.7,
  top_p: 0.9,
  max_tokens: 1024,
  context_window: 8192,
  username: '用户',
  mock_llm: true,
  auto_memory_extraction: false,
  api_key_configured: false,
  api_key_masked: '',
  custom_headers: {},
  settings_writable: true,
  diagnostics_enabled: true,
  selftest_enabled: true,
}
