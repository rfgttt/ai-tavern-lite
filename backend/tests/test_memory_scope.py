from fastapi.testclient import TestClient

from app.db.models import Character, ChatSession, Memory
from app.db.session import get_db
from app.main import create_app
from app.services.memory.service import MemoryService


def _add_character(db, name: str) -> Character:
    character = Character(name=name)
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


def _add_session(db, character: Character, title: str) -> ChatSession:
    session = ChatSession(character_id=character.id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _client(test_db) -> TestClient:
    app = create_app()

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_effective_scope_isolates_sibling_sessions_and_characters(test_db):
    character_a = _add_character(test_db, "角色 A")
    character_b = _add_character(test_db, "角色 B")
    session_a1 = _add_session(test_db, character_a, "A-1")
    session_a2 = _add_session(test_db, character_a, "A-2")
    session_b1 = _add_session(test_db, character_b, "B-1")

    rows = [
        Memory(content="全局记忆", importance=0.5),
        Memory(character_id=character_a.id, content="角色 A 共享", importance=0.5),
        Memory(character_id=character_b.id, content="角色 B 共享", importance=0.5),
        # Legacy session row: older UI stored session_id without character_id.
        Memory(session_id=session_a1.id, content="A-1 会话旧数据", importance=0.5),
        Memory(
            character_id=character_a.id,
            session_id=session_a2.id,
            content="A-2 会话",
            importance=0.5,
        ),
        Memory(
            character_id=character_b.id,
            session_id=session_b1.id,
            content="B-1 会话",
            importance=0.5,
        ),
    ]
    test_db.add_all(rows)
    test_db.commit()

    visible = MemoryService.get_relevant_memories(
        test_db,
        character_id=character_a.id,
        session_id=session_a1.id,
        max_entries=20,
    )
    contents = {memory.content for memory in visible}

    assert contents == {"全局记忆", "角色 A 共享", "A-1 会话旧数据"}


def test_character_context_without_session_excludes_all_session_memories(test_db):
    character = _add_character(test_db, "角色")
    session = _add_session(test_db, character, "会话")
    test_db.add_all(
        [
            Memory(content="全局", importance=0.5),
            Memory(character_id=character.id, content="角色共享", importance=0.5),
            Memory(session_id=session.id, content="旧会话记忆", importance=1.0),
        ]
    )
    test_db.commit()

    visible = MemoryService.get_relevant_memories(
        test_db,
        character_id=character.id,
        max_entries=20,
    )

    assert {memory.content for memory in visible} == {"全局", "角色共享"}


def test_add_session_memory_normalizes_character_owner(test_db):
    character = _add_character(test_db, "角色")
    session = _add_session(test_db, character, "会话")

    memory = MemoryService.add_memory(
        test_db,
        content="只属于此会话",
        session_id=session.id,
    )

    assert memory.session_id == session.id
    assert memory.character_id == character.id


def test_add_memory_rejects_mismatched_character_and_session(test_db):
    character_a = _add_character(test_db, "角色 A")
    character_b = _add_character(test_db, "角色 B")
    session_a = _add_session(test_db, character_a, "A")

    try:
        MemoryService.add_memory(
            test_db,
            content="错误作用域",
            character_id=character_b.id,
            session_id=session_a.id,
        )
    except ValueError as error:
        assert str(error) == "会话不属于指定角色"
    else:
        raise AssertionError("mismatched scope should be rejected")


def test_memory_api_supports_exact_and_effective_scope_filters(test_db):
    character = _add_character(test_db, "角色")
    sibling = _add_character(test_db, "其他角色")
    session = _add_session(test_db, character, "当前会话")
    other_session = _add_session(test_db, character, "其他会话")

    test_db.add_all(
        [
            Memory(content="全局"),
            Memory(character_id=character.id, content="角色共享"),
            Memory(character_id=sibling.id, content="其他角色"),
            Memory(session_id=session.id, content="当前会话旧数据"),
            Memory(character_id=character.id, session_id=other_session.id, content="其他会话"),
        ]
    )
    test_db.commit()

    client = _client(test_db)

    effective = client.get(
        "/api/memories",
        params={
            "scope": "effective",
            "character_id": character.id,
            "session_id": session.id,
        },
    )
    assert effective.status_code == 200
    assert {item["content"] for item in effective.json()} == {
        "全局",
        "角色共享",
        "当前会话旧数据",
    }

    global_only = client.get("/api/memories", params={"scope": "global"})
    assert global_only.status_code == 200
    assert [item["content"] for item in global_only.json()] == ["全局"]

    character_only = client.get(
        "/api/memories",
        params={"scope": "character", "character_id": character.id},
    )
    assert character_only.status_code == 200
    assert [item["content"] for item in character_only.json()] == ["角色共享"]

    session_only = client.get(
        "/api/memories",
        params={"scope": "session", "session_id": session.id},
    )
    assert session_only.status_code == 200
    assert [item["content"] for item in session_only.json()] == ["当前会话旧数据"]


def test_memory_api_rejects_invalid_scope_context(test_db):
    character_a = _add_character(test_db, "角色 A")
    character_b = _add_character(test_db, "角色 B")
    session_a = _add_session(test_db, character_a, "A")
    client = _client(test_db)

    response = client.get(
        "/api/memories",
        params={
            "scope": "effective",
            "character_id": character_b.id,
            "session_id": session_a.id,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "会话不属于指定角色"


def test_prompt_preview_uses_current_session_memory_only(test_db):
    character = _add_character(test_db, "角色")
    current_session = _add_session(test_db, character, "当前")
    sibling_session = _add_session(test_db, character, "同角色其他会话")
    test_db.add_all(
        [
            Memory(content="全局上下文"),
            Memory(character_id=character.id, content="角色共享上下文"),
            Memory(session_id=current_session.id, content="当前会话上下文"),
            Memory(
                character_id=character.id,
                session_id=sibling_session.id,
                content="不应出现的其他会话上下文",
            ),
        ]
    )
    test_db.commit()

    response = _client(test_db).post(
        "/api/chat/prompt-preview",
        json={"session_id": current_session.id, "message": "继续"},
    )

    assert response.status_code == 200
    memory_section = next(
        section for section in response.json()["sections"]
        if section["name"] == "长期记忆"
    )
    assert "全局上下文" in memory_section["content"]
    assert "角色共享上下文" in memory_section["content"]
    assert "当前会话上下文" in memory_section["content"]
    assert "不应出现的其他会话上下文" not in memory_section["content"]
