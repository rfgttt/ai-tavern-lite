import atexit
import os
from pathlib import Path
import shutil
import sys
import tempfile

import pytest

# Every backend test run uses one isolated runtime root. This must be set before
# importing app modules so create_app() can never initialize or back up a user's
# real database during pytest.
_TEST_RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="ai-tavern-pytest-"))
os.environ["AI_TAVERN_DATA_DIR"] = str(_TEST_RUNTIME_ROOT / "data")
os.environ["AI_TAVERN_DATABASE_URL"] = f"sqlite:///{(_TEST_RUNTIME_ROOT / 'data' / 'pytest.db').as_posix()}"
os.environ["AI_TAVERN_CREATE_DEMO_DATA"] = "false"
os.environ["AI_TAVERN_STORAGE_GUARD_ENABLED"] = "false"
atexit.register(lambda: shutil.rmtree(_TEST_RUNTIME_ROOT, ignore_errors=True))

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.session import Base
from app.db.models import Character, ChatSession, Message, Memory, AppSetting
from app.core.config import settings


@pytest.fixture
def test_db():
    """Create a test database using temp file."""
    import tempfile
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_file.close()
    db_path = db_file.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        import os
        try:
            os.unlink(db_path)
        except:
            pass


@pytest.fixture
def sample_v2_character_json():
    """Sample Tavern V2 character card."""
    return {
        "name": "测试角色 V2",
        "description": "这是一个 V2 格式的测试角色",
        "personality": "性格开朗",
        "scenario": "在一个虚拟的场景中",
        "first_mes": "你好，我是测试角色！",
        "mes_example": "{{user}}: 你好\n{{char}}: 你好呀！",
        "system_prompt": "",
        "post_history_instructions": "",
        "creator_notes": "测试用",
        "tags": ["测试", "V2"],
        "creator": "Test",
        "character_version": "1.0",
        "extensions": {"custom_field": "custom_value_v2"}
    }


@pytest.fixture
def sample_v3_character_json():
    """Sample Character Card V3 with data field."""
    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "name": "顶层名称不应被使用",
        "data": {
            "name": "测试角色 V3",
            "description": "这是一个 V3 格式的测试角色，包含 data 字段",
            "personality": "沉稳睿智",
            "scenario": "图书馆场景",
            "first_mes": "*抬起头从书本中看向你* 欢迎来到图书馆。",
            "mes_example": "",
            "system_prompt": "",
            "post_history_instructions": "",
            "creator_notes": "V3 测试角色",
            "tags": ["测试", "V3", "图书馆"],
            "creator": "TestCreator",
            "character_version": "2.0",
            "alternate_greetings": ["你好，又见面了。"],
            "extensions": {
                "custom_extension": "extension_value",
                "another_field": "should_be_preserved"
            },
            "character_book": {
                "entries": [
                    {
                        "id": 1,
                        "keys": ["图书馆", "书籍"],
                        "content": "这是一座古老的图书馆，藏书丰富。",
                        "constant": True,
                        "enabled": True,
                        "insertion_order": 0
                    },
                    {
                        "id": 2,
                        "keys": ["魔法"],
                        "content": "图书馆的禁书区藏有魔法书籍。",
                        "constant": False,
                        "enabled": True,
                        "insertion_order": 1
                    },
                    {
                        "id": 3,
                        "keys": ["禁用条目"],
                        "content": "这个条目是禁用的，不应该触发。",
                        "constant": True,
                        "enabled": False,
                        "insertion_order": 2
                    }
                ]
            }
        }
    }


@pytest.fixture
def sample_chinese_character_json():
    """Character with Chinese name and special characters."""
    return {
        "name": "林夕·星尘酒馆招待",
        "description": "一位温柔的酒馆招待，喜欢听故事。",
        "personality": "温柔、耐心、善于倾听",
        "scenario": "星尘酒馆内，暖黄的灯光下",
        "first_mes": "欢迎光临，想喝点什么？",
        "mes_example": "",
        "tags": ["中文", "测试"],
        "extensions": {}
    }


@pytest.fixture
def db_with_character(test_db, sample_v3_character_json):
    """Database with a character already created."""
    import json
    from app.services.character_parser.parser import parse_json_character

    normalized, raw = parse_json_character(sample_v3_character_json)

    char = Character(
        name=normalized.name,
        description=normalized.description,
        personality=normalized.personality,
        scenario=normalized.scenario,
        first_message=normalized.first_mes,
        normalized_json=json.dumps(normalized.to_dict(), ensure_ascii=False),
        raw_json=json.dumps(raw, ensure_ascii=False),
        avatar_path=""
    )
    test_db.add(char)
    test_db.commit()
    test_db.refresh(char)

    return test_db, char


@pytest.fixture
def db_with_session(db_with_character):
    """Database with a character and chat session."""
    db, char = db_with_character

    session = ChatSession(
        character_id=char.id,
        title="测试对话"
    )
    db.add(session)
    db.flush()

    # Add some messages
    msg1 = Message(
        session_id=session.id,
        role="assistant",
        content=char.first_message,
        sequence=0,
        generation_status="complete"
    )
    db.add(msg1)

    msg2 = Message(
        session_id=session.id,
        role="user",
        content="你好，请问这里有魔法相关的书吗？",
        sequence=1,
        generation_status="complete"
    )
    db.add(msg2)

    db.commit()
    db.refresh(session)

    return db, char, session
