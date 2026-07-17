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

export const personasFixture = [
  {
    id: 'persona-traveler',
    name: '北境旅人',
    description: '谨慎而善良的旅行者',
    pronouns: '她/她',
    avatar_path: '',
    metadata: {},
    is_default: true,
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
  },
]

export const groupsFixture = [
  {
    id: 'group-tavern',
    name: '酒馆调查组',
    description: '共同调查酒馆里的秘密',
    character_ids: ['character-linya', 'character-arden'],
    members: [
      { character_id: 'character-linya', name: '林雅', avatar_path: '', role: 'member', position: 0 },
      { character_id: 'character-arden', name: 'Arden', avatar_path: '', role: 'member', position: 1 },
    ],
    metadata: {},
    created_at: '2026-07-16T00:00:00Z',
    updated_at: '2026-07-16T00:00:00Z',
  },
]

export const characterSessionOptionsFixture = {
  character_id: 'character-linya',
  character_name: '林雅',
  greetings: ['晚上好。', '你终于来了。'],
  runtime_profile: { mode: 'relationship' },
  initial_state: {
    runtime_version: 2,
    mode: 'relationship',
    scene: { location: '深夜的酒馆' },
    character: { name: '林雅' },
    relationship: { trust: 0 },
    player: { name: '用户' },
    custom: {},
  },
}
