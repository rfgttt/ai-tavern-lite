import { http, HttpResponse } from 'msw'
import { charactersFixture, sessionsFixture } from './fixtures'

export const handlers = [
  http.get('*/api/characters', () => HttpResponse.json(charactersFixture)),
  http.get('*/api/sessions', ({ request }) => {
    const url = new URL(request.url)
    const characterId = url.searchParams.get('character_id')
    return HttpResponse.json(
      characterId
        ? sessionsFixture.filter((session) => session.character_id === characterId)
        : sessionsFixture,
    )
  }),
  http.post('*/api/sessions', async ({ request }) => {
    const body = (await request.json()) as {
      character_id: string
      title?: string
      persona_id?: string
      group_id?: string
    }
    return HttpResponse.json(
      {
        id: 'session-created',
        character_id: body.character_id,
        persona_id: body.persona_id ?? null,
        group_id: body.group_id ?? null,
        title: body.title || '新对话',
        created_at: '2026-07-16T00:00:00Z',
        updated_at: '2026-07-16T00:00:00Z',
      },
      { status: 201 },
    )
  }),
  http.delete('*/api/characters/:characterId', () => new HttpResponse(null, { status: 204 })),
]
