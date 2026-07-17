import { http, HttpResponse } from 'msw'
import { appSettingsFixture, characterSessionOptionsFixture, charactersFixture, groupsFixture, lorebookFixture, personasFixture, sessionsFixture } from './fixtures'

export const handlers = [
  http.get('*/api/settings', () => HttpResponse.json(appSettingsFixture)),
  http.get('*/api/characters', () => HttpResponse.json(charactersFixture)),
  http.get('*/api/characters/:characterId/session-options', ({ params }) => {
    const character = charactersFixture.find((item) => item.id === params.characterId) || charactersFixture[0]
    return HttpResponse.json({
      ...characterSessionOptionsFixture,
      character_id: character.id,
      character_name: character.name,
      greetings: character.id === 'character-linya' ? characterSessionOptionsFixture.greetings : [character.first_message],
      initial_state: {
        ...characterSessionOptionsFixture.initial_state,
        scene: { location: character.scenario },
        character: { name: character.name },
      },
    })
  }),
  http.get('*/api/personas', () => HttpResponse.json(personasFixture)),
  http.get('*/api/groups', () => HttpResponse.json(groupsFixture)),
  http.post('*/api/characters', async ({ request }) => {
    const body = (await request.json()) as Record<string, string>
    return HttpResponse.json({
      id: 'character-created',
      name: body.name,
      description: body.description || '',
      personality: body.personality || '',
      scenario: body.scenario || '',
      first_message: body.first_message || '',
      avatar_path: '',
      created_at: '2026-07-16T00:00:00Z',
      updated_at: '2026-07-16T00:00:00Z',
    }, { status: 201 })
  }),
  http.put('*/api/characters/:characterId', async ({ params, request }) => {
    const body = (await request.json()) as Record<string, string>
    const existing = charactersFixture.find((character) => character.id === params.characterId) || charactersFixture[0]
    return HttpResponse.json({ ...existing, ...body, id: String(params.characterId) })
  }),
  http.delete('*/api/characters/:characterId', () => HttpResponse.json({ success: true })),
  http.get('*/api/characters/:characterId/export', ({ params }) => HttpResponse.json({
    spec: 'chara_card_v3',
    spec_version: '3.0',
    data: { name: charactersFixture.find((item) => item.id === params.characterId)?.name || '角色' },
  })),
  http.get('*/api/characters/:characterId/lorebook', () => HttpResponse.json(lorebookFixture)),
  http.put('*/api/characters/:characterId/lorebook', async ({ request }) => HttpResponse.json(await request.json())),
  http.get('*/api/sessions', ({ request }) => {
    const url = new URL(request.url)
    const characterId = url.searchParams.get('character_id')
    return HttpResponse.json(characterId ? sessionsFixture.filter((session) => session.character_id === characterId) : sessionsFixture)
  }),
  http.post('*/api/sessions', async ({ request }) => {
    const body = (await request.json()) as { character_id: string; title?: string; persona_id?: string; group_id?: string; use_default_persona?: boolean }
    return HttpResponse.json({
      id: 'session-created',
      character_id: body.character_id,
      persona_id: body.persona_id ?? null,
      group_id: body.group_id ?? null,
      title: body.title || '新对话',
      created_at: '2026-07-16T00:00:00Z',
      updated_at: '2026-07-16T00:00:00Z',
    }, { status: 201 })
  }),
]
