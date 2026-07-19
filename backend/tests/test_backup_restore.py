from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile

from sqlalchemy import create_engine, text

from app.db.migrations import get_head_revision, upgrade_database
from app.services.backup.service import (
    DATABASE_ARCHIVE_PATH,
    INSTANCE_SETTING_KEY,
    MANIFEST_ARCHIVE_PATH,
    apply_pending_restore,
    build_backup_archive,
    cancel_pending_restore,
    commit_pending_restore,
    get_backup_status,
    rollback_pending_restore,
    stage_restore_archive,
    BackupError,
)


def _seed_database(
    path: Path,
    *,
    character_name: str,
    instance_id: str,
    api_key: str,
    custom_headers: str = '{"Authorization":"Bearer local-secret"}',
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    upgrade_database(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO personas (id, name, description, pronouns, avatar_path, metadata_json, is_default) "
            "VALUES ('persona-1', '旅人', '测试 Persona', '她', '', '{}', 1)"
        ))
        connection.execute(text(
            "INSERT INTO characters "
            "(id, name, description, personality, scenario, first_message, normalized_json, raw_json, avatar_path) "
            "VALUES ('character-1', :name, '描述', '性格', '场景', '开场', '{}', '{}', '/avatars/avatar.png')"
        ), {"name": character_name})
        connection.execute(text(
            "INSERT INTO character_groups (id, name, description, metadata_json) "
            "VALUES ('group-1', '测试组', '', '{}')"
        ))
        connection.execute(text(
            "INSERT INTO group_members (id, group_id, character_id, role, position) "
            "VALUES ('member-1', 'group-1', 'character-1', 'member', 0)"
        ))
        connection.execute(text(
            "INSERT INTO chat_sessions (id, character_id, title, persona_id, group_id) "
            "VALUES ('session-1', 'character-1', '测试会话', 'persona-1', 'group-1')"
        ))
        connection.execute(text(
            "INSERT INTO messages "
            "(id, session_id, role, content, sequence, generation_status, segments_json, artifacts_json, speaker_metadata_json, render_version) "
            "VALUES ('message-1', 'session-1', 'assistant', '测试消息', 0, 'complete', '[]', '[]', '{}', 2)"
        ))
        connection.execute(text(
            "INSERT INTO session_states "
            "(session_id, profile_json, initial_state_json, state_json, revision) "
            "VALUES ('session-1', '{}', '{}', '{\"scene\":{\"location\":\"酒馆\"}}', 1)"
        ))
        connection.execute(text(
            "INSERT INTO turn_snapshots "
            "(id, session_id, message_id, state_before_json, patch_json, state_after_json, events_json, choices_json, dice_json, battle_checks_json, battle_json, expression, triggered_lorebook_json, rejected_patch_json, parser_errors_json) "
            "VALUES ('snapshot-1', 'session-1', 'message-1', '{}', '[]', '{}', '[]', '[]', '[]', '[]', 'null', '', '[]', '[]', '[]')"
        ))
        connection.execute(text(
            "INSERT INTO memories "
            "(id, character_id, session_id, category, content, importance, keywords, enabled) "
            "VALUES ('memory-1', 'character-1', 'session-1', 'fact', '测试记忆', 0.8, '', 1)"
        ))
        connection.execute(text(
            "INSERT INTO session_branches "
            "(id, session_id, title, parent_message_id, messages_json, runtime_state_json, runtime_revision) "
            "VALUES ('branch-1', 'session-1', '分支', 'message-1', '[]', '{}', 1)"
        ))
        for key, value in {
            INSTANCE_SETTING_KEY: instance_id,
            "api_key": api_key,
            "custom_headers": custom_headers,
            "model": "test-model",
            "username": "测试用户",
        }.items():
            connection.execute(
                text("INSERT INTO app_settings (key, value) VALUES (:key, :value)"),
                {"key": key, "value": value},
            )
    engine.dispose()


def _read_character_name(path: Path) -> str:
    with closing(sqlite3.connect(str(path))) as connection:
        return str(connection.execute("SELECT name FROM characters LIMIT 1").fetchone()[0])


def _read_setting(path: Path, key: str) -> str | None:
    with closing(sqlite3.connect(str(path))) as connection:
        row = connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None


def _export(tmp_path: Path, source_database: Path, *, avatar_content: bytes = b"source-avatar"):
    source_root = source_database.parent
    avatars = source_root / "avatars"
    characters = source_root / "characters"
    avatars.mkdir(parents=True, exist_ok=True)
    characters.mkdir(parents=True, exist_ok=True)
    (avatars / "avatar.png").write_bytes(avatar_content)
    (characters / "source-card.json").write_text('{"name":"backup"}', encoding="utf-8")
    return build_backup_archive(
        database_path=source_database,
        avatars_dir=avatars,
        characters_dir=characters,
        exports_dir=tmp_path / "exports",
        max_uncompressed_bytes=64 * 1024 * 1024,
    )


def test_portable_backup_contains_complete_data_assets_and_no_secrets(tmp_path):
    source_database = tmp_path / "source" / "ai_tavern.db"
    secret = "sk-super-secret-backup-value"
    _seed_database(
        source_database,
        character_name="备份角色",
        instance_id="source-instance",
        api_key=secret,
    )
    result = _export(tmp_path, source_database)

    try:
        with zipfile.ZipFile(result.archive_path, "r") as archive:
            names = set(archive.namelist())
            assert MANIFEST_ARCHIVE_PATH in names
            assert DATABASE_ARCHIVE_PATH in names
            assert "assets/avatars/avatar.png" in names
            assert "assets/characters/source-card.json" in names
            manifest = json.loads(archive.read(MANIFEST_ARCHIVE_PATH))
            extracted = tmp_path / "portable.db"
            extracted.write_bytes(archive.read(DATABASE_ARCHIVE_PATH))

        assert manifest["format"] == "ai-tavern-backup"
        assert manifest["database"]["counts"]["characters"] == 1
        assert manifest["database"]["counts"]["messages"] == 1
        assert manifest["notes"]["api_key_included"] is False
        assert _read_character_name(extracted) == "备份角色"
        assert _read_setting(extracted, "api_key") is None
        assert _read_setting(extracted, "custom_headers") is None
        assert _read_setting(extracted, INSTANCE_SETTING_KEY) is None
        assert secret.encode() not in extracted.read_bytes()
        assert b"Bearer local-secret" not in extracted.read_bytes()
    finally:
        shutil.rmtree(result.cleanup_root, ignore_errors=True)


def test_portable_backup_ignores_gitkeep_and_declares_fixed_sensitive_exclusions(tmp_path):
    source_database = tmp_path / "source" / "ai_tavern.db"
    _seed_database(
        source_database,
        character_name="占位文件测试角色",
        instance_id="source-instance",
        api_key="source-secret",
    )
    with closing(sqlite3.connect(str(source_database))) as connection:
        connection.execute("DELETE FROM app_settings WHERE key='custom_headers'")
        connection.commit()

    source_root = source_database.parent
    avatars = source_root / "avatars"
    characters = source_root / "characters"
    avatars.mkdir(parents=True, exist_ok=True)
    characters.mkdir(parents=True, exist_ok=True)
    (avatars / ".gitkeep").write_bytes(b"")
    (characters / ".gitkeep").write_bytes(b"")

    result = build_backup_archive(
        database_path=source_database,
        avatars_dir=avatars,
        characters_dir=characters,
        exports_dir=tmp_path / "exports",
        max_uncompressed_bytes=64 * 1024 * 1024,
    )

    try:
        with zipfile.ZipFile(result.archive_path, "r") as archive:
            manifest = json.loads(archive.read(MANIFEST_ARCHIVE_PATH))
            names = set(archive.namelist())

        assert "assets/avatars/.gitkeep" not in names
        assert "assets/characters/.gitkeep" not in names
        assert manifest["assets"] == []
        assert manifest["excluded_settings"] == [
            "api_key",
            "custom_headers",
            INSTANCE_SETTING_KEY,
        ]
    finally:
        shutil.rmtree(result.cleanup_root, ignore_errors=True)

def test_restore_staging_preserves_current_machine_secrets_and_identity(tmp_path):
    source_database = tmp_path / "source" / "ai_tavern.db"
    _seed_database(
        source_database,
        character_name="恢复来源角色",
        instance_id="source-instance",
        api_key="source-secret",
    )
    export = _export(tmp_path, source_database)

    data_dir = tmp_path / "managed" / "data"
    current_database = data_dir / "ai_tavern.db"
    _seed_database(
        current_database,
        character_name="当前角色",
        instance_id="current-instance",
        api_key="current-local-secret",
        custom_headers='{"X-Local":"local-header-secret"}',
    )

    try:
        pending = stage_restore_archive(
            archive_path=export.archive_path,
            data_dir=data_dir,
            database_path=current_database,
            expected_revision=get_head_revision(),
            database_instance_id="current-instance",
            preserved_settings={
                "api_key": "current-local-secret",
                "custom_headers": '{"X-Local":"local-header-secret"}',
            },
            max_entries=1000,
            max_uncompressed_bytes=64 * 1024 * 1024,
        )
        status = get_backup_status(data_dir=data_dir, database_path=current_database)
        marker = json.loads((data_dir / "pending-restore.json").read_text(encoding="utf-8"))
        staged_database = Path(marker["database_path"])

        assert pending["counts"]["characters"] == 1
        assert status["pending_restore"]["restore_id"] == pending["restore_id"]
        assert _read_character_name(staged_database) == "恢复来源角色"
        assert _read_setting(staged_database, "api_key") == "current-local-secret"
        assert _read_setting(staged_database, "custom_headers") == '{"X-Local":"local-header-secret"}'
        assert _read_setting(staged_database, INSTANCE_SETTING_KEY) == "current-instance"
        assert _read_character_name(current_database) == "当前角色"
    finally:
        cancel_pending_restore(data_dir=data_dir)
        shutil.rmtree(export.cleanup_root, ignore_errors=True)


def test_pending_restore_can_rollback_to_exact_current_database_and_assets(tmp_path):
    source_database = tmp_path / "source" / "ai_tavern.db"
    _seed_database(
        source_database,
        character_name="恢复来源角色",
        instance_id="source-instance",
        api_key="source-secret",
    )
    export = _export(tmp_path, source_database, avatar_content=b"new-avatar")

    data_dir = tmp_path / "managed" / "data"
    current_database = data_dir / "ai_tavern.db"
    _seed_database(
        current_database,
        character_name="当前角色",
        instance_id="current-instance",
        api_key="current-secret",
    )
    (data_dir / "avatars").mkdir(parents=True)
    (data_dir / "characters").mkdir(parents=True)
    (data_dir / "avatars" / "avatar.png").write_bytes(b"old-avatar")
    (data_dir / "characters" / "old.json").write_text("old", encoding="utf-8")
    registry = {"database_instance_id": "current-instance"}

    try:
        stage_restore_archive(
            archive_path=export.archive_path,
            data_dir=data_dir,
            database_path=current_database,
            expected_revision=get_head_revision(),
            database_instance_id="current-instance",
            preserved_settings={"api_key": "current-secret"},
            max_entries=1000,
            max_uncompressed_bytes=64 * 1024 * 1024,
        )
        application = apply_pending_restore(
            data_dir=data_dir,
            backups_dir=data_dir / "backups",
            database_path=current_database,
            registry=registry,
        )
        assert application is not None
        assert _read_character_name(current_database) == "恢复来源角色"
        assert (data_dir / "avatars" / "avatar.png").read_bytes() == b"new-avatar"
        assert not (data_dir / "characters" / "old.json").exists()

        rollback_pending_restore(application)
        assert _read_character_name(current_database) == "当前角色"
        assert _read_setting(current_database, "api_key") == "current-secret"
        assert (data_dir / "avatars" / "avatar.png").read_bytes() == b"old-avatar"
        assert (data_dir / "characters" / "old.json").read_text(encoding="utf-8") == "old"
        assert not (data_dir / "pending-restore.json").exists()
        assert application.safety_dir.exists()
    finally:
        shutil.rmtree(export.cleanup_root, ignore_errors=True)


def test_pending_restore_commit_keeps_restored_data_and_pre_restore_safety(tmp_path):
    source_database = tmp_path / "source" / "ai_tavern.db"
    _seed_database(
        source_database,
        character_name="正式恢复角色",
        instance_id="source-instance",
        api_key="source-secret",
    )
    export = _export(tmp_path, source_database)
    data_dir = tmp_path / "managed" / "data"
    current_database = data_dir / "ai_tavern.db"
    _seed_database(
        current_database,
        character_name="恢复前角色",
        instance_id="current-instance",
        api_key="local-secret",
    )

    try:
        stage_restore_archive(
            archive_path=export.archive_path,
            data_dir=data_dir,
            database_path=current_database,
            expected_revision=get_head_revision(),
            database_instance_id="current-instance",
            preserved_settings={"api_key": "local-secret"},
            max_entries=1000,
            max_uncompressed_bytes=64 * 1024 * 1024,
        )
        application = apply_pending_restore(
            data_dir=data_dir,
            backups_dir=data_dir / "backups",
            database_path=current_database,
            registry={"database_instance_id": "current-instance"},
        )
        assert application is not None
        commit_pending_restore(application)

        assert _read_character_name(current_database) == "正式恢复角色"
        assert _read_setting(current_database, "api_key") == "local-secret"
        assert _read_setting(current_database, INSTANCE_SETTING_KEY) == "current-instance"
        assert not (data_dir / "pending-restore.json").exists()
        assert not application.staging_dir.exists()
        assert (application.safety_dir / DATABASE_ARCHIVE_PATH).exists()
        assert _read_character_name(application.safety_dir / DATABASE_ARCHIVE_PATH) == "恢复前角色"
    finally:
        shutil.rmtree(export.cleanup_root, ignore_errors=True)


def test_static_restore_removes_stale_sqlite_sidecars(tmp_path):
    from app.services.backup import service as backup_service

    source = tmp_path / "source.db"
    destination = tmp_path / "destination.db"
    _seed_database(
        source,
        character_name="新数据库",
        instance_id="instance",
        api_key="secret",
    )
    _seed_database(
        destination,
        character_name="旧数据库",
        instance_id="instance",
        api_key="secret",
    )
    Path(f"{destination}-wal").write_bytes(b"stale-wal")
    Path(f"{destination}-shm").write_bytes(b"stale-shm")

    backup_service._copy_static_database(source, destination)

    assert _read_character_name(destination) == "新数据库"
    assert not Path(f"{destination}-wal").exists()
    assert not Path(f"{destination}-shm").exists()



def test_restore_rejects_zip_path_traversal(tmp_path):
    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../outside.txt", b"escape")
        archive.writestr(
            MANIFEST_ARCHIVE_PATH,
            json.dumps({"format": "ai-tavern-backup", "format_version": 1}),
        )

    data_dir = tmp_path / "managed" / "data"
    current_database = data_dir / "ai_tavern.db"
    _seed_database(
        current_database,
        character_name="当前角色",
        instance_id="current-instance",
        api_key="current-secret",
    )

    import pytest
    with pytest.raises(BackupError, match="ZIP 路径"):
        stage_restore_archive(
            archive_path=malicious,
            data_dir=data_dir,
            database_path=current_database,
            expected_revision=get_head_revision(),
            database_instance_id="current-instance",
            preserved_settings={"api_key": "current-secret"},
            max_entries=1000,
            max_uncompressed_bytes=64 * 1024 * 1024,
        )
    assert not (tmp_path / "outside.txt").exists()
    assert _read_character_name(current_database) == "当前角色"


def test_restore_rejects_database_with_trigger_even_when_manifest_matches(tmp_path):
    source_database = tmp_path / "source" / "ai_tavern.db"
    _seed_database(
        source_database,
        character_name="恶意来源角色",
        instance_id="source-instance",
        api_key="source-secret",
    )
    export = _export(tmp_path, source_database)
    tampered = tmp_path / "trigger-backup.zip"
    extracted_db = tmp_path / "trigger.db"

    try:
        with zipfile.ZipFile(export.archive_path, "r") as original:
            manifest = json.loads(original.read(MANIFEST_ARCHIVE_PATH))
            extracted_db.write_bytes(original.read(DATABASE_ARCHIVE_PATH))
            asset_payloads = {
                name: original.read(name)
                for name in original.namelist()
                if name.startswith("assets/") and not name.endswith("/")
            }
        with closing(sqlite3.connect(str(extracted_db))) as connection:
            connection.execute(
                "CREATE TRIGGER exfiltrate_after_insert AFTER INSERT ON messages "
                "BEGIN UPDATE app_settings SET value='changed' WHERE key='model'; END"
            )
            connection.commit()
        manifest["database"]["size"] = extracted_db.stat().st_size
        from hashlib import sha256
        manifest["database"]["sha256"] = sha256(extracted_db.read_bytes()).hexdigest()

        with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_ARCHIVE_PATH, json.dumps(manifest, ensure_ascii=False))
            archive.write(extracted_db, DATABASE_ARCHIVE_PATH)
            for name, payload in asset_payloads.items():
                archive.writestr(name, payload)

        data_dir = tmp_path / "managed" / "data"
        current_database = data_dir / "ai_tavern.db"
        _seed_database(
            current_database,
            character_name="当前角色",
            instance_id="current-instance",
            api_key="current-secret",
        )

        import pytest
        with pytest.raises(BackupError, match="触发器或视图"):
            stage_restore_archive(
                archive_path=tampered,
                data_dir=data_dir,
                database_path=current_database,
                expected_revision=get_head_revision(),
                database_instance_id="current-instance",
                preserved_settings={"api_key": "current-secret"},
                max_entries=1000,
                max_uncompressed_bytes=64 * 1024 * 1024,
            )
        assert _read_character_name(current_database) == "当前角色"
    finally:
        shutil.rmtree(export.cleanup_root, ignore_errors=True)
