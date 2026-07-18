import copy
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.models import AppSetting, Character, ChatSession, Memory, Message
from app.db.session import get_db
from app.main import create_app
from app.core.config import settings
from app.services.prompt_builder.builder import PromptBuilder
from app.services.prompt_builder.inspection import build_prompt_inspection


def _client(test_db) -> TestClient:
    app = create_app()

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_inspection_observes_built_prompt_without_mutating_messages(db_with_character):
    _, character = db_with_character
    messages = [
        SimpleNamespace(role="user", content="你好", sequence=0),
        SimpleNamespace(role="assistant", content="欢迎", sequence=1),
    ]
    built = PromptBuilder(character, context_window=1024, max_new_tokens=128).build(
        messages=messages,
        lorebook_entries=[],
        memories=[],
        user_message="继续",
        runtime_profile={},
        runtime_state={},
    )
    before_messages = copy.deepcopy(built.messages)
    before_sections = copy.deepcopy(built.sections)

    report = build_prompt_inspection(
        built_prompt=built,
        context_window=1024,
        max_new_tokens=128,
        memory_catalog=[],
        selected_memories=[],
        lorebook_catalog=[],
        triggered_lorebook=[],
        recent_text="你好\n继续",
    )

    assert built.messages == before_messages
    assert built.sections == before_sections
    assert report["summary"]["input_budget"] == 896
    assert report["summary"]["estimated_input_tokens"] == built.total_estimated_tokens
    assert report["history"]["included_messages"] == 2


def test_prompt_preview_returns_structured_inspection_without_secrets(test_db):
    normalized = {
        "name": "检查器角色",
        "character_book": {
            "entries": [
                {
                    "id": 1,
                    "comment": "常驻设定",
                    "content": "王国位于北方。",
                    "constant": True,
                    "enabled": True,
                    "probability": 100,
                    "insertion_order": 0,
                },
                {
                    "id": 2,
                    "comment": "龙之传闻",
                    "keys": ["龙"],
                    "content": "古龙沉睡在山脉中。",
                    "enabled": True,
                    "probability": 100,
                    "insertion_order": 1,
                },
                {
                    "id": 3,
                    "comment": "未命中条目",
                    "keys": ["海盗"],
                    "content": "海盗占据南港。",
                    "enabled": True,
                    "probability": 100,
                    "insertion_order": 2,
                },
                {
                    "id": 4,
                    "comment": "禁用条目",
                    "content": "不应注入。",
                    "constant": True,
                    "enabled": False,
                    "probability": 100,
                    "insertion_order": 3,
                },
                {
                    "id": 5,
                    "comment": "选择性条目",
                    "keys": ["龙"],
                    "secondary_keys": ["王冠"],
                    "selective": True,
                    "content": "只有王冠与龙同时出现才注入。",
                    "enabled": True,
                    "probability": 100,
                    "insertion_order": 4,
                },
            ]
        },
    }
    character = Character(
        name="检查器角色",
        description="用于检查 Prompt 的角色。",
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        raw_json="{}",
    )
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title="检查器会话")
    test_db.add(session)
    test_db.flush()

    for index in range(18):
        test_db.add(
            Message(
                session_id=session.id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"第 {index} 条历史 " + ("很长的内容" * 25),
                sequence=index,
                generation_status="complete",
            )
        )
    test_db.add_all(
        [
            Memory(content="全局事实", category="fact", importance=0.9),
            Memory(
                character_id=character.id,
                content="角色旧分类事实",
                category="user_fact",
                importance=0.8,
            ),
            Memory(
                character_id=character.id,
                session_id=session.id,
                content="禁用会话记忆",
                category="definition",
                enabled=False,
                importance=1.0,
            ),
            AppSetting(key="context_window", value="1024"),
            AppSetting(key="max_tokens", value="128"),
            AppSetting(key="api_key", value="SECRET-API-KEY-DO-NOT-LEAK"),
            AppSetting(
                key="custom_headers",
                value=json.dumps({"Authorization": "SECRET-CUSTOM-HEADER"}),
            ),
        ]
    )
    test_db.commit()

    response = _client(test_db).post(
        "/api/chat/prompt-preview",
        json={"session_id": session.id, "message": "继续调查龙的传闻"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(("sections", "total_estimated_tokens", "context_budget", "inspection")).issubset(payload)
    assert payload["section_content_complete"] is True
    inspection = payload["inspection"]
    assert inspection["summary"] == {
        "context_window": 1024,
        "reserved_output_tokens": 128,
        "input_budget": 896,
        "estimated_input_tokens": payload["total_estimated_tokens"],
        "remaining_tokens": 896 - payload["total_estimated_tokens"],
        "usage_percent": round(payload["total_estimated_tokens"] / 896 * 100, 1),
    }
    assert inspection["history"]["total_messages"] == 18
    assert inspection["history"]["trimmed_messages"] > 0
    assert inspection["history"]["included_messages"] < 18

    memories = {item["content"]: item for item in inspection["memories"]}
    assert memories["全局事实"]["scope"] == "global"
    assert memories["全局事实"]["included"] is True
    assert memories["角色旧分类事实"]["category"] == "fact"
    assert memories["禁用会话记忆"]["reason"] == "disabled"
    assert memories["禁用会话记忆"]["included"] is False

    lore = {item["title"]: item for item in inspection["lorebook"]}
    assert lore["常驻设定"]["triggered"] is True
    assert lore["龙之传闻"]["matched_keys"] == ["龙"]
    assert lore["龙之传闻"]["triggered"] is True
    assert lore["未命中条目"]["reason"] == "no_primary_match"
    assert lore["禁用条目"]["reason"] == "disabled"
    assert lore["选择性条目"]["reason"] == "no_secondary_match"
    assert lore["龙之传闻"]["content"] == "古龙沉睡在山脉中。"
    assert lore["龙之传闻"]["resolved_content"] == "古龙沉睡在山脉中。"
    assert lore["龙之传闻"]["injected_characters"] == len(
        lore["龙之传闻"]["injected_content"]
    )
    assert "龙之传闻" in lore["龙之传闻"]["injected_content"]

    history_section = next(item for item in payload["sections"] if item["name"] == "聊天历史")
    assert "[user · sequence=" in history_section["content"]
    assert "第 " in history_section["content"]
    assert len(history_section["content"]) > 500
    assert "生产环境预览仅显示" not in history_section["content"]

    serialized = response.text
    assert "SECRET-API-KEY-DO-NOT-LEAK" not in serialized
    assert "SECRET-CUSTOM-HEADER" not in serialized


def test_inspection_reports_memory_entry_limit_separately(test_db):
    character = Character(name="记忆限制角色", normalized_json="{}", raw_json="{}")
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title="记忆限制")
    test_db.add(session)
    test_db.flush()
    test_db.add_all(
        [
            Memory(
                character_id=character.id,
                content=f"候选记忆-{index}",
                category="fact",
                importance=1.0 - index * 0.05,
            )
            for index in range(13)
        ]
    )
    test_db.commit()

    response = _client(test_db).post(
        "/api/chat/prompt-preview",
        json={"session_id": session.id, "message": "继续"},
    )

    assert response.status_code == 200
    memories = {item["content"]: item for item in response.json()["inspection"]["memories"]}
    assert memories["候选记忆-0"]["selected"] is True
    assert memories["候选记忆-12"]["selected"] is False
    assert memories["候选记忆-12"]["reason"] == "entry_limit"


def test_inspection_distinguishes_forced_duplicate_memory_rows(db_with_character):
    _, character = db_with_character
    first = Memory(id="memory-first", content="重复内容" * 30, category="fact", importance=1.0, enabled=True)
    second = Memory(id="memory-second", content="重复内容" * 30, category="fact", importance=1.0, enabled=True)
    built = PromptBuilder(character, context_window=1024, max_new_tokens=128).build(
        messages=[],
        lorebook_entries=[],
        memories=[first, second],
        runtime_profile={},
        runtime_state={},
    )

    report = build_prompt_inspection(
        built_prompt=built,
        context_window=1024,
        max_new_tokens=128,
        memory_catalog=[first, second],
        selected_memories=[first, second],
        lorebook_catalog=[],
        triggered_lorebook=[],
        recent_text="",
    )
    by_id = {item["id"]: item for item in report["memories"]}

    assert len(report["memories"]) == 2
    assert by_id["memory-first"]["included"] is True
    assert by_id["memory-second"]["included"] is True
    assert by_id["memory-second"]["truncated"] is True
    assert by_id["memory-second"]["reason"] == "memory_budget_partial"


def test_inspection_distinguishes_lore_entries_with_duplicate_card_ids(db_with_character):
    from app.services.lorebook.service import LorebookEntry

    _, character = db_with_character
    first = LorebookEntry({
        "id": 0,
        "comment": "第一个零 ID 条目",
        "content": "第一条世界设定" * 100,
        "constant": True,
        "enabled": True,
        "probability": 100,
        "insertion_order": 0,
    })
    second = LorebookEntry({
        "id": 0,
        "comment": "第二个零 ID 条目",
        "content": "第二条世界设定" * 100,
        "constant": True,
        "enabled": True,
        "probability": 100,
        "insertion_order": 1,
    })
    built = PromptBuilder(character, context_window=512, max_new_tokens=128).build(
        messages=[],
        lorebook_entries=[first, second],
        lorebook_catalog=[first, second],
        memories=[],
        runtime_profile={},
        runtime_state={},
    )

    report = build_prompt_inspection(
        built_prompt=built,
        context_window=512,
        max_new_tokens=128,
        memory_catalog=[],
        selected_memories=[],
        lorebook_catalog=[first, second],
        triggered_lorebook=[first, second],
        recent_text="",
    )
    by_title = {item["title"]: item for item in report["lorebook"]}

    assert by_title["第一个零 ID 条目"]["included"] is True
    assert by_title["第二个零 ID 条目"]["included"] is False
    assert by_title["第二个零 ID 条目"]["reason"] == "context_budget"


def test_production_preview_keeps_safe_character_limit(test_db, monkeypatch):
    character = Character(
        name="生产预览角色",
        description="设定内容" * 300,
        normalized_json="{}",
        raw_json="{}",
    )
    test_db.add(character)
    test_db.flush()
    session = ChatSession(character_id=character.id, title="生产预览")
    test_db.add(session)
    test_db.commit()

    client = _client(test_db)
    monkeypatch.setattr(settings, "environment", "production")
    response = client.post(
        "/api/chat/prompt-preview",
        json={"session_id": session.id, "message": "继续"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["section_content_complete"] is False
    character_section = next(
        item for item in payload["sections"] if item["name"] == "角色设定"
    )
    assert "生产环境预览仅显示前 500 个字符" in character_section["content"]
    assert len(character_section["content"]) < 600
