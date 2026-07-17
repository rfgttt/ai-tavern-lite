import json

from fastapi.testclient import TestClient

from app.db.models import Message, TurnSnapshot


def _client(db):
    from app.main import create_app
    from app.db.session import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: (yield db)
    return TestClient(app)


def test_persona_crud(test_db):
    client = _client(test_db)
    created = client.post('/api/personas', json={
        'name': '旅行者',
        'description': '来自北方的旅行者',
        'pronouns': '他/他',
        'metadata': {'tone': '沉稳'},
    })
    assert created.status_code == 200
    persona_id = created.json()['id']
    listed = client.get('/api/personas').json()
    assert listed[0]['name'] == '旅行者'
    updated = client.put(f'/api/personas/{persona_id}', json={'name': '远行者'})
    assert updated.json()['name'] == '远行者'
    assert client.delete(f'/api/personas/{persona_id}').json()['success'] is True


def test_group_crud_with_members(db_with_character):
    db, character = db_with_character
    client = _client(db)
    created = client.post('/api/groups', json={
        'name': '冒险小队',
        'description': '多人剧情测试',
        'character_ids': [character.id],
    })
    assert created.status_code == 200
    payload = created.json()
    assert payload['character_ids'] == [character.id]
    assert client.get('/api/groups').json()[0]['name'] == '冒险小队'


def test_branch_save_and_restore(db_with_session):
    db, _, session = db_with_session
    assistant = (
        db.query(Message)
        .filter(Message.session_id == session.id, Message.role == 'assistant')
        .order_by(Message.sequence.asc())
        .first()
    )
    db.add(TurnSnapshot(
        session_id=session.id,
        message_id=assistant.id,
        state_before_json=json.dumps({'relationship': {'trust': 0}}, ensure_ascii=False),
        patch_json=json.dumps([{'op': 'replace', 'path': '/relationship/trust', 'value': 1}], ensure_ascii=False),
        state_after_json=json.dumps({'relationship': {'trust': 1}}, ensure_ascii=False),
        events_json=json.dumps(['建立信任'], ensure_ascii=False),
        choices_json='[]',
        dice_json='[]',
        battle_checks_json='[]',
        battle_json='null',
        triggered_lorebook_json='[]',
        rejected_patch_json='[]',
        parser_errors_json='[]',
    ))
    db.commit()

    client = _client(db)
    saved = client.post(f'/api/sessions/{session.id}/branches', json={'title': '进入魔法区之前'})
    assert saved.status_code == 200
    branch = saved.json()
    assert branch['message_count'] == 2

    client.post(f'/api/sessions/{session.id}/messages', json={
        'session_id': session.id,
        'role': 'user',
        'content': '继续前进',
    })
    assert len(client.get(f'/api/sessions/{session.id}/messages').json()) == 3

    restored = client.post(f'/api/sessions/{session.id}/branches/{branch["id"]}/restore')
    assert restored.status_code == 200
    messages = client.get(f'/api/sessions/{session.id}/messages').json()
    assert len(messages) == 2
    assert messages[-1]['content'].startswith('你好')

    timeline = client.get(f'/api/sessions/{session.id}/timeline').json()
    assert len(timeline) == 1
    restored_assistant = next(message for message in messages if message['role'] == 'assistant')
    assert timeline[0]['message_id'] == restored_assistant['id']
    assert timeline[0]['patch'][0]['path'] == '/relationship/trust'


def test_session_can_bind_default_persona_and_group(db_with_character):
    db, character = db_with_character
    client = _client(db)
    persona = client.post('/api/personas', json={
        'name': '北境旅人', 'description': '谨慎而善良', 'pronouns': '', 'metadata': {}, 'is_default': True,
    }).json()
    group = client.post('/api/groups', json={
        'name': '双人舞台', 'description': '', 'character_ids': [character.id], 'metadata': {},
    }).json()

    response = client.post('/api/sessions', json={
        'character_id': character.id,
        'title': '群组测试',
        'group_id': group['id'],
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload['persona_id'] == persona['id']
    assert payload['group_id'] == group['id']


def test_character_session_options_include_greetings_and_initial_state(db_with_character):
    db, character = db_with_character
    client = _client(db)

    response = client.get(f'/api/characters/{character.id}/session-options')

    assert response.status_code == 200
    payload = response.json()
    assert payload['character_id'] == character.id
    assert payload['greetings'][0].startswith('*抬起头')
    assert '你好，又见面了。' in payload['greetings']
    assert payload['initial_state']['scene']['location'] == '图书馆场景'
    assert payload['initial_state']['character']['name'] == character.name
    assert isinstance(payload['runtime_profile'], dict)


def test_session_wizard_options_control_persona_greeting_group_and_state(db_with_character):
    db, character = db_with_character
    client = _client(db)
    client.post('/api/personas', json={
        'name': '默认玩家', 'description': '', 'pronouns': '', 'metadata': {}, 'is_default': True,
    })
    group = client.post('/api/groups', json={
        'name': '调查小队', 'description': '', 'character_ids': [character.id], 'metadata': {},
    }).json()
    initial_state = {
        'scene': {'location': '钟楼'},
        'character': {'name': character.name},
        'relationship': {'trust': 12},
        'custom': {'chapter': 2},
    }

    response = client.post('/api/sessions', json={
        'character_id': character.id,
        'title': '  钟楼序章  ',
        'group_id': group['id'],
        'use_default_persona': False,
        'opening_message': '你好，又见面了。',
        'initial_state': initial_state,
    })

    assert response.status_code == 200
    session = response.json()
    assert session['title'] == '钟楼序章'
    assert session['persona_id'] is None
    assert session['group_id'] == group['id']

    messages = client.get(f'/api/sessions/{session["id"]}/messages').json()
    assert [message['content'] for message in messages] == ['你好，又见面了。']
    runtime = client.get(f'/api/sessions/{session["id"]}/runtime').json()
    assert runtime['initial_state'] == initial_state
    assert runtime['state'] == initial_state


def test_session_rejects_primary_character_outside_selected_group(test_db):
    from app.db.models import Character

    first = Character(name='甲', description='', personality='', scenario='', first_message='你好')
    second = Character(name='乙', description='', personality='', scenario='', first_message='你好')
    test_db.add_all([first, second])
    test_db.commit()
    client = _client(test_db)
    group = client.post('/api/groups', json={
        'name': '仅甲', 'description': '', 'character_ids': [first.id], 'metadata': {},
    }).json()

    response = client.post('/api/sessions', json={
        'character_id': second.id,
        'title': '错误群组',
        'group_id': group['id'],
    })

    assert response.status_code == 400
    assert response.json()['detail'] == '主角色不属于所选群组'
