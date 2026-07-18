import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Character, ChatSession, Memory
from app.db.session import Base, get_db
from app.main import create_app
from app.services.memory.service import MemoryDuplicateError, MemoryService


def _add_character(db, name="角色"):
    character = Character(name=name)
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


def _add_session(db, character, title="会话"):
    session = ChatSession(character_id=character.id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _client(test_db):
    app = create_app()

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_content_normalization_is_conservative():
    assert MemoryService.normalize_content("  第一行\r\n第二行  ") == "第一行\n第二行"
    assert MemoryService.normalize_content("用户  喜欢咖啡") != MemoryService.normalize_content("用户 喜欢咖啡")
    assert MemoryService.normalize_content("用户喜欢咖啡。") != MemoryService.normalize_content("用户喜欢咖啡")
    assert MemoryService.normalize_content("User") != MemoryService.normalize_content("user")


def test_unicode_nfc_forms_are_exact_duplicates(test_db):
    composed = "Café"
    decomposed = unicodedata.normalize("NFD", composed)
    first = MemoryService.add_memory(test_db, content=composed, category="fact")

    try:
        MemoryService.add_memory(test_db, content=decomposed, category="fact")
    except MemoryDuplicateError as error:
        assert error.memory.id == first.id
    else:
        raise AssertionError("NFC-equivalent content should be detected")


def test_manual_duplicate_returns_structured_409_and_can_be_forced(test_db):
    client = _client(test_db)
    payload = {"category": "fact", "content": "  用户住在北京\r\n"}

    first = client.post("/api/memories", json=payload)
    assert first.status_code == 200
    assert first.json()["content"] == "用户住在北京"

    duplicate = client.post("/api/memories", json={**payload, "content": "用户住在北京"})
    assert duplicate.status_code == 409
    detail = duplicate.json()["detail"]
    assert detail == {
        "code": "memory_duplicate",
        "message": "当前作用域和分类中已存在内容相同的记忆（已启用）",
        "memory_id": first.json()["id"],
        "enabled": True,
        "category": "fact",
        "scope": "global",
    }

    forced = client.post(
        "/api/memories",
        json={**payload, "content": "用户住在北京", "allow_duplicate": True},
    )
    assert forced.status_code == 200
    assert forced.json()["id"] != first.json()["id"]
    assert test_db.query(Memory).count() == 2


def test_disabled_duplicate_still_blocks_without_reenabling(test_db):
    existing = Memory(category="fact", content="用户喜欢咖啡", enabled=False)
    test_db.add(existing)
    test_db.commit()
    client = _client(test_db)

    response = client.post(
        "/api/memories",
        json={"category": "fact", "content": "用户喜欢咖啡"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["enabled"] is False
    test_db.refresh(existing)
    assert existing.enabled is False
    assert test_db.query(Memory).count() == 1


def test_scope_and_category_boundaries_allow_same_text(test_db):
    character_a = _add_character(test_db, "A")
    character_b = _add_character(test_db, "B")
    session_a1 = _add_session(test_db, character_a, "A1")
    session_a2 = _add_session(test_db, character_a, "A2")

    rows = [
        MemoryService.add_memory(test_db, content="相同内容", category="fact"),
        MemoryService.add_memory(test_db, content="相同内容", category="preference"),
        MemoryService.add_memory(test_db, content="相同内容", category="fact", character_id=character_a.id),
        MemoryService.add_memory(test_db, content="相同内容", category="fact", character_id=character_b.id),
        MemoryService.add_memory(test_db, content="相同内容", category="fact", session_id=session_a1.id),
        MemoryService.add_memory(test_db, content="相同内容", category="fact", session_id=session_a2.id),
    ]

    assert len({row.id for row in rows}) == 6


def test_legacy_session_row_and_legacy_category_participate_in_duplicate_check(test_db):
    character = _add_character(test_db)
    session = _add_session(test_db, character)
    legacy = Memory(
        character_id=None,
        session_id=session.id,
        category="user_fact",
        content="用户叫小明",
    )
    test_db.add(legacy)
    test_db.commit()

    try:
        MemoryService.add_memory(
            test_db,
            content="用户叫小明",
            category="fact",
            session_id=session.id,
        )
    except MemoryDuplicateError as error:
        assert error.memory.id == legacy.id
    else:
        raise AssertionError("legacy rows should participate in exact duplicate checks")


def test_category_alias_is_canonicalized_on_write_filter_and_prompt(test_db):
    legacy = Memory(category="user_fact", content="旧事实")
    test_db.add(legacy)
    test_db.commit()
    client = _client(test_db)

    created = client.post(
        "/api/memories",
        json={"category": "user_fact", "content": "新事实"},
    )
    assert created.status_code == 200
    assert created.json()["category"] == "fact"

    filtered = client.get("/api/memories", params={"category": "fact"})
    assert {item["content"] for item in filtered.json()} == {"旧事实", "新事实"}
    assert MemoryService.build_memory_text([legacy]) == "【长期记忆】\n- [fact] 旧事实"


def test_definition_category_is_preserved_and_not_merged_with_preference(test_db):
    definition = MemoryService.add_memory(
        test_db,
        category="definition",
        content="“吃饭”在当前会话表示执行秘密任务",
    )
    preference = MemoryService.add_memory(
        test_db,
        category="preference",
        content="用户喜欢吃饭",
    )

    assert definition.id != preference.id
    assert definition.category == "definition"


def test_update_self_is_allowed_but_update_into_another_duplicate_conflicts(test_db):
    first = MemoryService.add_memory(test_db, category="fact", content="事实一")
    second = MemoryService.add_memory(test_db, category="fact", content="事实二")
    client = _client(test_db)

    unchanged = client.put(first and f"/api/memories/{first.id}", json={"content": "  事实一  "})
    assert unchanged.status_code == 200

    conflict = client.put(f"/api/memories/{second.id}", json={"content": "事实一"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["memory_id"] == first.id

    forced = client.put(
        f"/api/memories/{second.id}",
        json={"content": "事实一", "allow_duplicate": True},
    )
    assert forced.status_code == 200
    assert forced.json()["content"] == "事实一"


def test_metadata_only_update_does_not_trigger_duplicate_check(test_db):
    first = MemoryService.add_memory(test_db, category="fact", content="相同")
    MemoryService.add_memory(
        test_db,
        category="fact",
        content="相同",
        allow_duplicate=True,
    )
    client = _client(test_db)

    response = client.put(
        f"/api/memories/{first.id}",
        json={"importance": 0.9, "keywords": "测试", "enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["importance"] == 0.9
    assert response.json()["enabled"] is False


def test_auto_extract_uses_canonical_categories_and_skips_stable_duplicates(test_db):
    extracted = MemoryService.extract_memories_simple("我住在北京", "知道了")
    assert extracted[0]["category"] == "fact"

    first = MemoryService.add_memory(
        test_db,
        content=extracted[0]["content"],
        category=extracted[0]["category"],
        skip_duplicate=True,
    )
    second = MemoryService.add_memory(
        test_db,
        content=extracted[0]["content"],
        category=extracted[0]["category"],
        skip_duplicate=True,
    )

    assert second.id == first.id
    assert test_db.query(Memory).count() == 1


def test_nonstable_categories_are_not_silently_deduped_by_auto_policy(test_db):
    first = MemoryService.add_memory(test_db, content="重复事件", category="event")
    second = MemoryService.add_memory(
        test_db,
        content="重复事件",
        category="event",
        skip_duplicate=("event" in MemoryService.AUTO_DEDUPE_CATEGORIES),
        allow_duplicate=True,
    )

    assert first.id != second.id


def test_concurrent_auto_writes_create_one_row(tmp_path: Path):
    db_path = tmp_path / "dedupe-concurrency.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def write_once():
        with SessionLocal() as db:
            return MemoryService.add_memory(
                db,
                content="并发事实",
                category="fact",
                skip_duplicate=True,
            ).id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(lambda _: write_once(), range(2)))

    with SessionLocal() as db:
        assert db.query(Memory).count() == 1
    assert ids[0] == ids[1]
    engine.dispose()
