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


def test_configured_database_url_is_absolute_and_data_dir_scoped():
    config = Settings(_env_file=None)
    database_url = make_url(config.database_url)

    assert database_url.drivername == "sqlite"
    assert database_url.database

    db_path = Path(database_url.database).resolve()
    assert db_path.is_absolute()
    assert db_path.parent == config.data_dir.resolve()


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


def test_large_session_history_remains_complete_and_ordered(db_with_session):
    db, _char, session = db_with_session
    bulk_messages = [
        Message(
            session_id=session.id,
            role="user" if sequence % 2 else "assistant",
            content=f"长会话消息 {sequence}",
            sequence=sequence,
            generation_status="complete",
        )
        for sequence in range(2, 1002)
    ]
    db.bulk_save_objects(bulk_messages)
    db.commit()

    response = make_client(db).get(f"/api/sessions/{session.id}/messages")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1002
    assert [item["sequence"] for item in payload] == list(range(1002))
    assert payload[-1]["content"] == "长会话消息 1001"


def add_paginated_messages(db, session_id: str, start: int, stop: int) -> None:
    db.bulk_save_objects([
        Message(
            session_id=session_id,
            role="user" if sequence % 2 else "assistant",
            content=f"分页消息 {sequence}",
            sequence=sequence,
            generation_status="complete",
        )
        for sequence in range(start, stop)
    ])
    db.commit()


def test_message_page_defaults_to_latest_fifty_in_chronological_order(db_with_session):
    db, _char, session = db_with_session
    add_paginated_messages(db, session.id, 2, 124)

    with make_client(db) as client:
        response = client.get(f"/api/sessions/{session.id}/messages/page")

    assert response.status_code == 200
    payload = response.json()
    assert [item["sequence"] for item in payload["items"]] == list(range(74, 124))
    assert payload["has_more"] is True
    assert payload["oldest_sequence"] == 74
    assert payload["newest_sequence"] == 123


def test_message_page_uses_exclusive_sequence_cursor(db_with_session):
    db, _char, session = db_with_session
    add_paginated_messages(db, session.id, 2, 17)
    with make_client(db) as client:
        latest = client.get(f"/api/sessions/{session.id}/messages/page?limit=5").json()
        earlier = client.get(
            f"/api/sessions/{session.id}/messages/page",
            params={"before_sequence": latest["oldest_sequence"], "limit": 5},
        ).json()

    assert [item["sequence"] for item in latest["items"]] == [12, 13, 14, 15, 16]
    assert [item["sequence"] for item in earlier["items"]] == [7, 8, 9, 10, 11]
    assert set(item["sequence"] for item in latest["items"]).isdisjoint(
        item["sequence"] for item in earlier["items"]
    )
    assert earlier["has_more"] is True


def test_message_pages_tolerate_sequence_gaps_without_duplicates_or_loss(db_with_session):
    db, _char, session = db_with_session
    add_paginated_messages(db, session.id, 2, 15)
    db.query(Message).filter(
        Message.session_id == session.id,
        Message.sequence.in_([5, 9]),
    ).delete(synchronize_session=False)
    db.commit()

    expected = {
        row.sequence
        for row in db.query(Message).filter(Message.session_id == session.id).all()
    }
    cursor = None
    seen: list[int] = []

    with make_client(db) as client:
        while True:
            params = {"limit": 4}
            if cursor is not None:
                params["before_sequence"] = cursor
            response = client.get(f"/api/sessions/{session.id}/messages/page", params=params)
            assert response.status_code == 200
            page = response.json()
            sequences = [item["sequence"] for item in page["items"]]
            assert sequences == sorted(sequences)
            assert not set(sequences).intersection(seen)
            seen.extend(sequences)
            if not page["has_more"]:
                break
            cursor = page["oldest_sequence"]
            assert cursor is not None

    assert set(seen) == expected
    assert len(seen) == len(expected)


def test_message_page_keeps_legacy_full_history_endpoint_unchanged(db_with_session):
    db, _char, session = db_with_session
    add_paginated_messages(db, session.id, 2, 72)
    with make_client(db) as client:
        legacy = client.get(f"/api/sessions/{session.id}/messages")
        paged = client.get(f"/api/sessions/{session.id}/messages/page")

    assert legacy.status_code == 200
    assert [item["sequence"] for item in legacy.json()] == list(range(72))
    assert paged.status_code == 200
    assert [item["sequence"] for item in paged.json()["items"]] == list(range(22, 72))


def test_message_page_validates_cursor_limit_and_session(db_with_session):
    db, _char, session = db_with_session
    with make_client(db) as client:
        assert client.get(f"/api/sessions/{session.id}/messages/page?limit=0").status_code == 422
        assert client.get(f"/api/sessions/{session.id}/messages/page?limit=201").status_code == 422
        assert client.get(f"/api/sessions/{session.id}/messages/page?before_sequence=-1").status_code == 422
        assert client.get("/api/sessions/missing/messages/page").status_code == 404

