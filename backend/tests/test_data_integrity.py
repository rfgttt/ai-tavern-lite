import pytest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.db.models import Memory, Message
from app.db.session import get_db
from app.main import create_app


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_default_database_url_is_absolute_and_backend_scoped():
    config = Settings(_env_file=None)
    database_url = make_url(config.database_url)

    assert database_url.drivername == "sqlite"
    assert database_url.database

    db_path = Path(database_url.database).resolve()
    expected_path = (config.data_dir / "ai_tavern.db").resolve()

    assert db_path.is_absolute()
    assert db_path == expected_path


def test_deleting_session_removes_session_memories(db_with_session):
    db, char, session = db_with_session
    memory = Memory(
        character_id=char.id,
        session_id=session.id,
        content="只属于该会话",
    )
    db.add(memory)
    db.commit()
    memory_id = memory.id

    response = make_client(db).delete(f"/api/sessions/{session.id}")

    assert response.status_code == 200
    assert db.query(Memory).filter(Memory.id == memory_id).first() is None


def test_message_sequence_is_server_assigned(db_with_session):
    db, _char, session = db_with_session
    response = make_client(db).post(
        f"/api/sessions/{session.id}/messages",
        json={"session_id": session.id, "role": "user", "content": "服务端排序", "sequence": 999},
    )

    assert response.status_code == 200
    assert response.json()["sequence"] == 2
    sequences = [m.sequence for m in db.query(Message).filter(Message.session_id == session.id).order_by(Message.sequence).all()]
    assert sequences == [0, 1, 2]


@pytest.mark.asyncio
async def test_upload_limit_stops_reading_after_limit_plus_one_byte():
    import io
    from fastapi import HTTPException, UploadFile
    from app.api.characters import _read_upload_limited

    upload = UploadFile(filename="large.json", file=io.BytesIO(b"0123456789"))
    with pytest.raises(HTTPException) as error:
        await _read_upload_limited(upload, max_size=5)

    assert error.value.status_code == 400
    assert upload.file.tell() == 6


def test_prompt_history_never_exceeds_its_budget(db_with_session):
    db, char, session = db_with_session
    from app.services.prompt_builder.builder import PromptBuilder

    messages = db.query(Message).filter(Message.session_id == session.id).order_by(Message.sequence).all()
    for message in messages:
        message.content = "很长的上下文" * 100

    builder = PromptBuilder(character=char, context_window=256, max_new_tokens=128)
    kept, token_count = builder._trim_history(messages, max_tokens=10)

    assert token_count <= 10
    assert kept == []


def test_legacy_message_schema_is_renumbered_and_gets_unique_index(tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError
    from app.db.session import migrate_sqlite_schema

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                created_at DATETIME
            )
        """))
        connection.execute(
            text("INSERT INTO messages (id, session_id, sequence) VALUES ('a', 's1', 0), ('b', 's1', 0)")
        )

    migrate_sqlite_schema(legacy_engine)

    with legacy_engine.begin() as connection:
        sequences = connection.execute(
            text("SELECT sequence FROM messages WHERE session_id='s1' ORDER BY sequence")
        ).scalars().all()
    assert sequences == [0, 1]

    with pytest.raises(IntegrityError):
        with legacy_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO messages (id, session_id, sequence) VALUES ('c', 's1', 1)")
            )


def test_2x_migration_adds_render_and_identity_columns(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.db.session import migrate_sqlite_schema

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy-2x.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                created_at DATETIME
            )
        """))
        connection.execute(text("""
            CREATE TABLE chat_sessions (
                id TEXT PRIMARY KEY,
                character_id TEXT NOT NULL,
                title TEXT
            )
        """))

    migrate_sqlite_schema(legacy_engine)

    inspector = inspect(legacy_engine)
    message_columns = {column["name"] for column in inspector.get_columns("messages")}
    session_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
    assert {"segments_json", "artifacts_json", "speaker_metadata_json", "render_version"} <= message_columns
    assert {"persona_id", "group_id"} <= session_columns
