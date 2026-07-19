import { http, HttpResponse } from 'msw'
import { appSettingsFixture, characterSecurityScanFixture, characterSessionOptionsFixture, charactersFixture, groupsFixture, lorebookFixture, personasFixture, sessionsFixture } from './fixtures'

export const handlers = [
  http.get('*/api/settings', () => HttpResponse.json(appSettingsFixture)),
  http.get('*/api/backups/status', () => HttpResponse.json({
    format_version: 1,
    current: {
      database_path: 'C:/Users/Test/AppData/Local/AI-Tavern-Lite/data/ai_tavern.db',
      exists: true,
      revision: '20260717_0001',
      counts: { characters: 2, sessions: 1, messages: 3, memories: 0 },
      integrity: 'ok',
    },
    pending_restore: null,
    portable_backup_excludes: ['api_key', 'custom_headers', 'database_instance_id'],
  })),
  http.post('*/api/backups/export', () => new HttpResponse(new Blob(['backup']), {
    headers: {
      'Content-Type': 'application/zip',
      'Content-Disposition': 'attachment; filename="ai-tavern-backup-test.zip"',
    },
  })),
  http.post('*/api/backups/restore', () => HttpResponse.json({
    success: true,
    message: '恢复包已验证并暂存。请停止服务后重新启动，恢复才会生效。',
    restore_id: 'restore-test',
    staged_at: '2026-07-19T01:00:00Z',
    backup_created_at: '2026-07-18T20:00:00Z',
    source_app_version: '2.2.0-preview.1',
    alembic_revision: '20260717_0001',
    counts: { characters: 4, sessions: 11, messages: 74, memories: 0 },
    asset_count: 2,
    restart_required: true,
  })),
  http.delete('*/api/backups/restore/pending', () => HttpResponse.json({
    success: true,
    cancelled: true,
    message: '待恢复任务已取消',
  })),
  http.get('*/api/diagnostics/health', () => HttpResponse.json({
    status: 'ok',
    version: '2.2.0-preview.1',
    checked_at: '2026-07-19T00:00:00',
    mock_mode: true,
    provider: 'OpenAI Compatible',
    model: 'test-model',
    components: { backend: true, database: true, frontend_build: true, provider_configured: true, state_engine: true, log_writable: true },
    storage: {},
  })),
  http.get('*/api/diagnostics/latest', () => HttpResponse.json(null)),
  http.get('*/api/characters', () => HttpResponse.json(charactersFixture)),
  http.post('*/api/characters/security/scan', () => HttpResponse.json(characterSecurityScanFixture)),
  http.get('*/api/characters/:characterId/security', ({ params }) => HttpResponse.json({ ...characterSecurityScanFixture, card_name: charactersFixture.find((item) => item.id === params.characterId)?.name || characterSecurityScanFixture.card_name })),
  http.post('*/api/characters/:characterId/security/safe-copy', ({ params }) => {
    const existing = charactersFixture.find((item) => item.id === params.characterId) || charactersFixture[0]
    return HttpResponse.json({ ...existing, id: `${existing.id}-safe`, name: `${existing.name}（安全副本）` }, { status: 201 })
  }),
  http.post('*/api/characters/import', async ({ request }) => {
    const form = await request.formData()
    const mode = String(form.get('security_mode') || 'safe_copy')
    return HttpResponse.json({ ...charactersFixture[0], id: `imported-${mode}`, name: mode === 'safe_copy' ? '风险角色卡' : '风险角色卡（隔离）' })
  }),
  http.get('*/api/characters/:characterId/session-options', ({ params }) => {
    const character = charactersFixture.find((item) => item.id === params.characterId) || charactersFixture[0]
    return HttpResponse.json({
      ...characterSessionOptionsFixture,
      character_id: character.id,
      character_name: character.name,
      greetings: character.id === 'character-linya' ? characterSessionOptionsFixture.greetings : [character.first_message],
      greeting_options: character.id === 'character-linya'
        ? characterSessionOptionsFixture.greeting_options
        : [{ key: 'default', kind: 'default', label: '默认开场白', content: character.first_message, source_index: null }],
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
    const body = (await request.json()) as Record<string, unknown>
    return HttpResponse.json({
      id: 'character-created',
      name: String(body.name || ''),
      description: String(body.description || ''),
      personality: String(body.personality || ''),
      scenario: String(body.scenario || ''),
      first_message: String(body.first_message || ''),
      alternate_greetings: Array.isArray(body.alternate_greetings) ? body.alternate_greetings : [],
      avatar_path: '',
      created_at: '2026-07-16T00:00:00Z',
      updated_at: '2026-07-16T00:00:00Z',
    }, { status: 201 })
  }),
  http.put('*/api/characters/:characterId', async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>
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
