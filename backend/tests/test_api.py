import pytest
import json
import io
from PIL import Image, PngImagePlugin
import base64


class TestHealthCheck:
    def test_health_check(self, test_db):
        """Test health check endpoint."""
        from fastapi.testclient import TestClient
        from app.main import create_app

        # Override DB dependency
        from app.db.session import get_db

        app = create_app()

        def override_get_db():
            try:
                yield test_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestDatabaseInit:
    def test_tables_created(self, test_db):
        """Test that all tables are created on init."""
        from app.db.models import Character, ChatSession, Message, Memory, AppSetting

        # Query each table to verify they exist
        assert test_db.query(Character).count() == 0
        assert test_db.query(ChatSession).count() == 0
        assert test_db.query(Message).count() == 0
        assert test_db.query(Memory).count() == 0
        assert test_db.query(AppSetting).count() == 0


class TestCharacterParser:
    def test_tavern_v2_json_import(self, sample_v2_character_json):
        """Test Tavern V2 JSON parsing."""
        from app.services.character_parser.parser import parse_json_character

        normalized, raw = parse_json_character(sample_v2_character_json)

        assert normalized.name == "测试角色 V2"
        assert normalized.description == "这是一个 V2 格式的测试角色"
        assert normalized.personality == "性格开朗"
        assert normalized.first_mes == "你好，我是测试角色！"
        assert "custom_field" in normalized.extensions
        assert normalized.extensions["custom_field"] == "custom_value_v2"

    def test_v3_json_prefers_data_field(self, sample_v3_character_json):
        """Test that V3 data field takes priority over top-level fields."""
        from app.services.character_parser.parser import parse_json_character

        normalized, raw = parse_json_character(sample_v3_character_json)

        # Should use data.name, not top-level name
        assert normalized.name == "测试角色 V3"
        assert normalized.spec == "chara_card_v3"
        assert normalized.spec_version == "3.0"
        assert len(normalized.tags) == 3
        assert "V3" in normalized.tags

    def test_v3_preserves_unknown_extensions(self, sample_v3_character_json):
        """Test that unknown extensions are preserved."""
        from app.services.character_parser.parser import parse_json_character

        normalized, raw = parse_json_character(sample_v3_character_json)

        assert "custom_extension" in normalized.extensions
        assert normalized.extensions["custom_extension"] == "extension_value"
        assert normalized.extensions["another_field"] == "should_be_preserved"

    def test_chinese_character_name(self, sample_chinese_character_json):
        """Test characters with Chinese names and special characters."""
        from app.services.character_parser.parser import parse_json_character

        normalized, raw = parse_json_character(sample_chinese_character_json)

        assert normalized.name == "林夕·星尘酒馆招待"
        assert "温柔" in normalized.description
        assert "中文" in normalized.tags

    def test_template_variable_replacement(self):
        """Test {{char}} and {{user}} replacement."""
        from app.services.character_parser.parser import replace_template_vars

        text = "{{char}} 对 {{user}} 说：你好，{{user}}！"
        result = replace_template_vars(text, "小明", "访客")

        assert result == "小明 对 访客 说：你好，访客！"
        assert "{{char}}" not in result
        assert "{{user}}" not in result


class TestPNGCharacterCard:
    def _create_test_png_with_metadata(self, json_data: dict) -> bytes:
        """Create a test PNG with embedded character card metadata."""
        # Create a simple 1x1 PNG
        img = Image.new("RGB", (10, 10), color="red")
        buf = io.BytesIO()

        json_str = json.dumps(json_data, ensure_ascii=False)
        # Encode as base64
        b64_json = base64.b64encode(json_str.encode("utf-8")).decode("ascii")

        # Save with tEXt chunk via Pillow PngInfo
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("chara", b64_json)
        img.save(buf, format="PNG", pnginfo=pnginfo)
        return buf.getvalue()

    def test_png_with_base64_json_import(self, sample_v3_character_json):
        """Test PNG with base64 encoded character card."""
        from app.services.character_parser.parser import parse_png_character

        png_bytes = self._create_test_png_with_metadata(sample_v3_character_json)
        normalized, raw, avatar = parse_png_character(png_bytes)

        assert normalized.name == "测试角色 V3"
        assert len(avatar) > 0

    def test_non_character_png_returns_error(self):
        """Test that regular PNG without character data raises error."""
        from app.services.character_parser.parser import parse_png_character

        img = Image.new("RGB", (10, 10), color="blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        with pytest.raises(ValueError) as exc_info:
            parse_png_character(png_bytes)

        assert "未找到角色卡数据" in str(exc_info.value)


class TestCharacterAPI:
    def _get_client(self, db):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.db.session import get_db

        app = create_app()

        def override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        return TestClient(app)

    def test_create_character_from_editor(self, test_db):
        """Test creating a character without importing a card file."""
        client = self._get_client(test_db)

        response = client.post(
            "/api/characters",
            json={
                "name": "  新建角色  ",
                "description": "由内置编辑器创建",
                "personality": "沉着",
                "scenario": "雨夜酒馆",
                "first_message": "欢迎。",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "新建角色"

        from app.db.models import Character
        created = test_db.query(Character).filter(Character.id == data["id"]).one()
        normalized = json.loads(created.normalized_json)
        assert normalized["name"] == "新建角色"
        assert normalized["first_mes"] == "欢迎。"

    def test_create_character_rejects_blank_name(self, test_db):
        client = self._get_client(test_db)
        response = client.post("/api/characters", json={"name": "   "})
        assert response.status_code == 422

    def test_import_json_character(self, test_db, sample_v2_character_json):
        """Test importing a JSON character card via API."""
        client = self._get_client(test_db)

        files = {
            "file": ("test.json", json.dumps(sample_v2_character_json, ensure_ascii=False).encode("utf-8"), "application/json")
        }
        response = client.post("/api/characters/import", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "测试角色 V2"
        assert "id" in data

    def test_list_characters(self, db_with_character):
        """Test listing characters."""
        db, char = db_with_character
        client = self._get_client(db)

        response = client.get("/api/characters")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["name"] == "测试角色 V3"

    def test_get_character_by_id(self, db_with_character):
        """Test getting character by ID."""
        db, char = db_with_character
        client = self._get_client(db)

        response = client.get(f"/api/characters/{char.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "测试角色 V3"

    def test_update_character_preserves_extensions(self, db_with_character):
        """Test that editing character doesn't lose unknown extensions."""
        db, char = db_with_character
        client = self._get_client(db)

        # Update just the name
        response = client.put(
            f"/api/characters/{char.id}",
            json={"name": "修改后的名称"}
        )
        assert response.status_code == 200

        # Check that extensions are preserved in normalized_json
        from app.db.models import Character
        updated = db.query(Character).filter(Character.id == char.id).first()
        norm = json.loads(updated.normalized_json)

        assert norm["name"] == "修改后的名称"
        assert "extensions" in norm
        assert norm["extensions"]["custom_extension"] == "extension_value"

    def test_export_character_emits_strict_ccv3(self, db_with_character):
        db, char = db_with_character
        client = self._get_client(db)

        normalized = json.loads(char.normalized_json)
        normalized["creator_notes"] = ""
        normalized["creatorcomment"] = "旧版作者备注"
        normalized["ai_tavern_runtime"] = {"mode": "relationship"}
        normalized["character_book"] = {
            "entries": [
                {
                    "id": None,
                    "keys": ["魔法"],
                    "content": "古代图书馆",
                    "enabled": True,
                    "insertion_order": 0,
                    "use_regex": False,
                    "probability": 75,
                    "extensions": {},
                }
            ]
        }
        char.normalized_json = json.dumps(normalized, ensure_ascii=False)
        db.commit()

        response = client.get(f"/api/characters/{char.id}/export")
        assert response.status_code == 200

        card = response.json()
        assert card["spec"] == "chara_card_v3"
        assert card["spec_version"] == "3.0"
        data = card["data"]
        assert "spec" not in data
        assert "spec_version" not in data
        assert "creatorcomment" not in data
        assert "ai_tavern_runtime" not in data
        assert data["creator_notes"] == "旧版作者备注"
        assert data["extensions"]["ai_tavern_runtime"] == {"mode": "relationship"}

        character_book = data["character_book"]
        assert character_book["extensions"] == {}
        entry = character_book["entries"][0]
        assert "id" not in entry
        assert "probability" not in entry
        assert entry["extensions"]["probability"] == 75

    def test_exported_probability_survives_reimport(self, db_with_character):
        db, char = db_with_character
        client = self._get_client(db)

        normalized = json.loads(char.normalized_json)
        normalized["character_book"] = {
            "entries": [
                {
                    "keys": ["魔法"],
                    "content": "古代图书馆",
                    "enabled": True,
                    "insertion_order": 0,
                    "use_regex": False,
                    "probability": 42,
                    "extensions": {},
                }
            ]
        }
        char.normalized_json = json.dumps(normalized, ensure_ascii=False)
        db.commit()

        exported = client.get(f"/api/characters/{char.id}/export").json()

        from app.services.character_parser.parser import parse_json_character
        reparsed, _ = parse_json_character(exported)
        assert reparsed.character_book["entries"][0]["probability"] == 42
        assert reparsed.character_book["entries"][0]["extensions"]["probability"] == 42

    def test_delete_character(self, db_with_character):
        """Test deleting a character."""
        db, char = db_with_character
        client = self._get_client(db)

        char_id = char.id
        response = client.delete(f"/api/characters/{char_id}")
        assert response.status_code == 200

        # Verify deleted
        response = client.get(f"/api/characters/{char_id}")
        assert response.status_code == 404


class TestLorebook:
    def test_constant_lorebook_triggers(self, sample_v3_character_json):
        """Test that constant lorebook entries always trigger."""
        from app.services.lorebook.service import LorebookService
        from app.services.character_parser.parser import parse_json_character

        normalized, _ = parse_json_character(sample_v3_character_json)
        entries = LorebookService.parse_entries(normalized.character_book)

        triggered = LorebookService.get_triggered_entries(entries, "任意文本")
        triggered_ids = [e.id for e in triggered]

        # Constant entry (id=1) should trigger
        assert 1 in triggered_ids
        # Disabled entry (id=3) should not trigger
        assert 3 not in triggered_ids

    def test_keyword_lorebook_triggers(self, sample_v3_character_json):
        """Test that keyword lorebook entries trigger on matching text."""
        from app.services.lorebook.service import LorebookService
        from app.services.character_parser.parser import parse_json_character

        normalized, _ = parse_json_character(sample_v3_character_json)
        entries = LorebookService.parse_entries(normalized.character_book)

        # Text containing "魔法" should trigger entry 2
        triggered = LorebookService.get_triggered_entries(entries, "我想找魔法相关的内容")
        triggered_ids = [e.id for e in triggered]

        assert 2 in triggered_ids

    def test_disabled_entry_does_not_trigger(self, sample_v3_character_json):
        """Test that disabled lorebook entries don't trigger."""
        from app.services.lorebook.service import LorebookService
        from app.services.character_parser.parser import parse_json_character

        normalized, _ = parse_json_character(sample_v3_character_json)
        entries = LorebookService.parse_entries(normalized.character_book)

        triggered = LorebookService.get_triggered_entries(entries, "禁用条目测试")
        triggered_ids = [e.id for e in triggered]

        assert 3 not in triggered_ids


class TestPromptBuilder:
    def test_template_vars_in_prompt(self, db_with_session):
        """Test that template variables are replaced in prompt."""
        db, char, session = db_with_session

        from app.services.prompt_builder.builder import PromptBuilder
        from app.db.models import Message

        messages = db.query(Message).filter(Message.session_id == session.id).all()

        builder = PromptBuilder(character=char, username="测试用户")
        result = builder.build(messages, [], [], "你好")

        # Check that system prompt contains character name
        system_msg = result.messages[0]
        assert system_msg["role"] == "system"
        assert char.name in system_msg["content"]

    def test_context_trimming(self, db_with_session):
        """Test that prompt context is trimmed to fit budget."""
        db, char, session = db_with_session

        from app.services.prompt_builder.builder import PromptBuilder
        from app.db.models import Message

        # Add many long messages
        for i in range(20):
            msg = Message(
                session_id=session.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"这是第 {i} 条非常长的消息内容。" * 50,
                sequence=i + 2,
                generation_status="complete"
            )
            db.add(msg)
        db.commit()

        messages = db.query(Message).filter(Message.session_id == session.id).all()

        # Small context window to force trimming
        builder = PromptBuilder(
            character=char,
            username="测试用户",
            context_window=1000,
            max_new_tokens=200
        )
        result = builder.build(messages, [], [], "测试")

        # The 2.0 planner trims old turns while preserving the newest suffix.
        history_section = [s for s in result.sections if s.name == "聊天历史"][0]
        assert "条消息" in history_section.content
        assert history_section.source.startswith("保留最近消息，裁剪")
        assert result.total_estimated_tokens <= result.context_budget

    def test_recent_history_survives_when_budget_is_tight(self, db_with_session):
        """Optional sections must not erase all conversational continuity."""
        db, char, session = db_with_session

        from app.services.prompt_builder.builder import PromptBuilder
        from app.db.models import Message

        messages = db.query(Message).filter(Message.session_id == session.id).all()

        builder = PromptBuilder(
            character=char,
            username="测试用户",
            context_window=100,
            max_new_tokens=50
        )
        result = builder.build(messages, [], [], "测试")

        user_assistant_msgs = [
            m for m in result.messages
            if m["role"] in ("user", "assistant")
        ]
        assert user_assistant_msgs[-1] == {"role": "user", "content": "测试"}
        assert any(message["role"] == "assistant" for message in user_assistant_msgs[:-1])
        assert result.total_estimated_tokens <= result.context_budget


class TestChatSessions:
    def test_create_session(self, db_with_character):
        """Test creating a chat session."""
        db, char = db_with_character
        from app.db.models import ChatSession

        session = ChatSession(character_id=char.id, title="测试对话")
        db.add(session)
        db.commit()
        db.refresh(session)

        assert session.id is not None
        assert session.character_id == char.id
        assert session.title == "测试对话"

    def test_first_message_added(self, db_with_character):
        """Test that first message is added when creating session."""
        db, char = db_with_character
        from app.db.models import ChatSession, Message
        from app.services.settings_service import SettingsService

        session = ChatSession(character_id=char.id, title="测试")
        db.add(session)
        db.flush()

        # Manually add first message like the API does
        if char.first_message:
            first_msg = Message(
                session_id=session.id,
                role="assistant",
                content=char.first_message,
                sequence=0,
                generation_status="complete"
            )
            db.add(first_msg)

        db.commit()

        messages = db.query(Message).filter(Message.session_id == session.id).all()
        assert len(messages) == 1
        assert messages[0].role == "assistant"

    def test_save_message(self, db_with_session):
        """Test saving messages to a session."""
        db, char, session = db_with_session
        from app.db.models import Message

        msg = Message(
            session_id=session.id,
            role="user",
            content="测试消息内容",
            sequence=5,
            generation_status="complete"
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        assert msg.id is not None
        assert msg.content == "测试消息内容"


class TestMockLLM:
    @pytest.mark.asyncio
    async def test_mock_provider_streams(self):
        """Test that Mock LLM provider streams content."""
        from app.services.llm.provider import MockLLMProvider

        provider = MockLLMProvider(character_name="测试角色")
        messages = [{"role": "user", "content": "你好"}]

        chunks = []
        async for chunk in provider.chat_completion(messages):
            chunks.append(chunk)

        full_response = "".join(chunks)
        assert len(chunks) > 1  # Should be multiple chunks (streaming)
        assert "测试角色" in full_response
        assert "Mock" in full_response

    @pytest.mark.asyncio
    async def test_mock_provider_stop(self):
        """Test that Mock LLM provider can be stopped."""
        import asyncio
        from app.services.llm.provider import MockLLMProvider

        provider = MockLLMProvider(character_name="测试")
        messages = [{"role": "user", "content": "hi"}]

        chunks = []

        async def stream_with_cancel():
            async for chunk in provider.chat_completion(messages):
                chunks.append(chunk)
                if len(chunks) == 5:
                    provider.cancel()

        await stream_with_cancel()

        # Should have stopped early
        assert len(chunks) < 50  # Full response would be much longer


class TestSettingsSecurity:
    def test_api_key_not_leaked(self, test_db):
        """Test that API key is not returned from settings endpoint."""
        from app.services.settings_service import SettingsService

        # Set an API key
        SettingsService.update_settings(test_db, {
            "api_key": "sk-this-is-a-secret-key-12345",
            "base_url": "https://api.example.com",
            "model": "test-model"
        })

        # Get masked settings
        masked = SettingsService.get_masked_settings(test_db)

        assert "api_key" not in masked
        assert masked["api_key_configured"] is True
        assert "api_key_masked" in masked
        assert "this-is-a-secret" not in masked["api_key_masked"]

    def test_empty_api_key_preserves_existing(self, test_db):
        """Test that updating with empty API key preserves existing value."""
        from app.services.settings_service import SettingsService

        # Set initial API key
        SettingsService.update_settings(test_db, {
            "api_key": "original-secret-key"
        })

        # Update with empty API key (should NOT clear)
        SettingsService.update_settings(test_db, {
            "api_key": "",
            "model": "new-model"
        })

        # Check original key is preserved
        all_settings = SettingsService.get_all_settings(test_db)
        assert all_settings["api_key"] == "original-secret-key"
        assert all_settings["model"] == "new-model"


class TestCharacterDeletionCascades:
    def test_delete_character_removes_sessions_and_memories(self, db_with_session):
        """Test that deleting a character removes related sessions, messages, and memories."""
        db, char, session = db_with_session
        from app.db.models import ChatSession, Message, Memory

        # Add a memory for this character
        memory = Memory(
            character_id=char.id,
            category="test",
            content="测试记忆",
            importance=0.5
        )
        db.add(memory)
        db.commit()

        # Verify data exists
        assert db.query(ChatSession).filter(ChatSession.character_id == char.id).count() >= 1
        assert db.query(Message).filter(Message.session_id == session.id).count() >= 1
        assert db.query(Memory).filter(Memory.character_id == char.id).count() >= 1

        # Delete character
        db.delete(char)
        db.commit()

        # Verify all related data is gone
        assert db.query(ChatSession).filter(ChatSession.character_id == char.id).count() == 0
        assert db.query(Message).filter(Message.session_id == session.id).count() == 0
        assert db.query(Memory).filter(Memory.character_id == char.id).count() == 0
