from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings, settings
from app.db import models  # noqa: F401
from app.db.migrations import upgrade_database, validate_database_schema
from app.db.session import Base
import app.db.storage_guard as storage_guard
from app.db.storage_guard import (
    INSTANCE_SETTING_KEY,
    StorageGuardError,
    finalize_storage_identity,
    prepare_storage,
)


@dataclass
class FakeStorageSettings:
    data_dir: Path
    legacy_data_dir: Path
    database_url: str
    storage_registry_path: Path
    uses_managed_storage: bool = True


def _settings(tmp_path: Path, *, legacy_name: str = "legacy") -> FakeStorageSettings:
    data_dir = tmp_path / "managed" / "data"
    return FakeStorageSettings(
        data_dir=data_dir,
        legacy_data_dir=tmp_path / legacy_name,
        database_url=f"sqlite:///{(data_dir / 'ai_tavern.db').as_posix()}",
        storage_registry_path=data_dir.parent / "storage.json",
    )


def _seed_legacy_database(path: Path, *, character_name: str = "保留角色") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO characters "
                "(id, name, description, personality, scenario, first_message, normalized_json, raw_json, avatar_path) "
                "VALUES ('legacy-character', :name, '', '', '', '', '{}', '{}', 'avatar.png')"
            ),
            {"name": character_name},
        )
    engine.dispose()


def _migrate_and_finalize(config: FakeStorageSettings, preflight):
    engine = create_engine(
        config.database_url,
        connect_args={"check_same_thread": False},
    )
    upgrade_database(engine)
    validate_database_schema(engine)
    status = finalize_storage_identity(engine, preflight)
    return engine, status


def test_default_storage_is_stable_and_not_project_local(monkeypatch):
    for key in (
        "AI_TAVERN_DATA_DIR",
        "AI_TAVERN_DATABASE_URL",
        "AI_TAVERN_STORAGE_REGISTRY_PATH",
        "AI_TAVERN_STORAGE_GUARD_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)

    config = Settings(_env_file=None)
    database_path = Path(config.database_url.removeprefix("sqlite:///"))

    assert database_path.resolve() == (config.data_dir / "ai_tavern.db").resolve()
    assert config.data_dir.resolve() != config.legacy_data_dir.resolve()
    assert config.storage_registry_path.resolve() == (config.data_dir.parent / "storage.json").resolve()
    assert config.uses_managed_storage is True
    assert config.create_demo_data is False


def test_explicit_database_url_is_isolated_and_bypasses_managed_registry(tmp_path):
    config = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'isolated.db').as_posix()}",
        data_dir=tmp_path / "isolated-data",
    )

    assert config.uses_managed_storage is False


def test_pytest_global_runtime_is_isolated_from_user_storage():
    assert settings.uses_managed_storage is False
    assert "ai-tavern-pytest-" in str(settings.data_dir)
    assert "ai-tavern-pytest-" in settings.database_url
    assert settings.create_demo_data is False



def test_sqlite_copy_closes_all_connections_before_atomic_replace(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    destination = tmp_path / "managed" / "ai_tavern.db"
    _seed_legacy_database(source)

    real_connect = sqlite3.connect
    opened = []

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            if not self.closed:
                super().close()
                self.closed = True

    def tracked_connect(*args, **kwargs):
        kwargs["factory"] = TrackedConnection
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    real_replace = storage_guard.os.replace

    def guarded_replace(source_path, destination_path):
        assert opened
        assert all(connection.closed for connection in opened)
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(storage_guard.sqlite3, "connect", tracked_connect)
    monkeypatch.setattr(storage_guard.os, "replace", guarded_replace)

    storage_guard._copy_sqlite_database(source, destination)

    assert destination.exists()
    assert all(connection.closed for connection in opened)

def test_first_managed_start_adopts_legacy_database_and_assets(tmp_path):
    config = _settings(tmp_path)
    legacy_database = config.legacy_data_dir / "ai_tavern.db"
    _seed_legacy_database(legacy_database)
    (config.legacy_data_dir / "avatars").mkdir(parents=True)
    (config.legacy_data_dir / "avatars" / "avatar.png").write_bytes(b"avatar")

    preflight = prepare_storage(config)

    managed_database = config.data_dir / "ai_tavern.db"
    assert managed_database.exists()
    assert legacy_database.exists()
    assert (config.data_dir / "avatars" / "avatar.png").read_bytes() == b"avatar"
    assert preflight.adopted_from == str(legacy_database.resolve())

    engine, status = _migrate_and_finalize(config, preflight)
    with engine.connect() as connection:
        character_name = connection.execute(
            text("SELECT name FROM characters WHERE id='legacy-character'")
        ).scalar_one()
        instance_id = connection.execute(
            text("SELECT value FROM app_settings WHERE key=:key"),
            {"key": INSTANCE_SETTING_KEY},
        ).scalar_one()

    registry = json.loads(config.storage_registry_path.read_text(encoding="utf-8"))
    assert character_name == "保留角色"
    assert registry["database_instance_id"] == instance_id == status.database_instance_id
    assert registry["database_path"] == str(managed_database.resolve())
    assert registry["counts"]["characters"] == 1
    engine.dispose()



def test_two_unregistered_database_candidates_fail_closed(tmp_path):
    config = _settings(tmp_path)
    _seed_legacy_database(config.legacy_data_dir / "ai_tavern.db", character_name="Legacy")
    _seed_legacy_database(config.data_dir / "ai_tavern.db", character_name="Managed")

    with pytest.raises(StorageGuardError, match="Two unregistered AI Tavern databases"):
        prepare_storage(config)

    assert not config.storage_registry_path.exists()


def test_registered_database_missing_fails_without_creating_replacement(tmp_path):
    config = _settings(tmp_path)
    _seed_legacy_database(config.legacy_data_dir / "ai_tavern.db")
    preflight = prepare_storage(config)
    engine, _status = _migrate_and_finalize(config, preflight)
    engine.dispose()

    managed_database = config.data_dir / "ai_tavern.db"
    moved_database = managed_database.with_suffix(".moved")
    managed_database.replace(moved_database)

    with pytest.raises(StorageGuardError, match="registered AI Tavern database is missing"):
        prepare_storage(config)

    assert not managed_database.exists()
    assert moved_database.exists()


def test_replacing_registered_database_with_another_file_is_rejected(tmp_path):
    config = _settings(tmp_path)
    _seed_legacy_database(config.legacy_data_dir / "ai_tavern.db")
    preflight = prepare_storage(config)
    engine, _status = _migrate_and_finalize(config, preflight)
    engine.dispose()

    managed_database = config.data_dir / "ai_tavern.db"
    managed_database.unlink()
    _seed_legacy_database(managed_database, character_name="错误数据库")

    with pytest.raises(StorageGuardError, match="does not match the registered storage identity"):
        prepare_storage(config)


def test_source_directory_change_does_not_change_registered_database(tmp_path):
    config = _settings(tmp_path, legacy_name="source-a")
    _seed_legacy_database(config.legacy_data_dir / "ai_tavern.db")
    preflight = prepare_storage(config)
    engine, status = _migrate_and_finalize(config, preflight)
    engine.dispose()

    moved_source_config = _settings(tmp_path, legacy_name="source-b")
    second_preflight = prepare_storage(moved_source_config)

    assert second_preflight.database_path == preflight.database_path
    assert second_preflight.registry["database_instance_id"] == status.database_instance_id


def test_count_regression_is_reported_but_does_not_rebind_identity(tmp_path):
    config = _settings(tmp_path)
    _seed_legacy_database(config.legacy_data_dir / "ai_tavern.db")
    preflight = prepare_storage(config)
    engine, status = _migrate_and_finalize(config, preflight)
    assert status.counts["characters"] == 1

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM characters"))
    engine.dispose()

    second_preflight = prepare_storage(config)
    second_engine, second_status = _migrate_and_finalize(config, second_preflight)

    assert second_status.database_instance_id == status.database_instance_id
    assert second_status.count_regressions["characters"] == {"previous": 1, "current": 0}
    second_engine.dispose()


def test_registry_contains_no_application_secrets(tmp_path):
    config = _settings(tmp_path)
    _seed_legacy_database(config.legacy_data_dir / "ai_tavern.db")
    preflight = prepare_storage(config)
    engine, _status = _migrate_and_finalize(config, preflight)
    engine.dispose()

    registry_text = config.storage_registry_path.read_text(encoding="utf-8").lower()
    assert "api_key" not in registry_text
    assert "authorization" not in registry_text
    assert "custom_headers" not in registry_text
