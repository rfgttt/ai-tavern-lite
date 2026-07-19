from __future__ import annotations

from pathlib import Path
import os
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.models import AppSetting
from app.db.session import Base, get_db, init_db
from app.main import create_app
from app.services.secrets import ApiKeyStorageError, FileApiKeyStore, WindowsDpapiProtector
from app.services.settings_service import SettingsService


def _make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_secure_api_key_never_enters_sqlite_or_secret_file_plaintext(
    test_db,
    isolated_api_key_store,
):
    secret = "sk-secure-test-value-1234"

    result = SettingsService.update_settings(
        test_db,
        {"api_key": secret, "model": "secure-model"},
    )

    saved = test_db.query(AppSetting).filter(AppSetting.key == "api_key").first()
    assert saved is None
    assert isolated_api_key_store.is_configured() is True
    assert secret.encode("utf-8") not in isolated_api_key_store.path.read_bytes()
    assert result["api_key"] == secret

    masked = SettingsService.get_masked_settings(test_db)
    assert "api_key" not in masked
    assert masked["api_key_configured"] is True
    assert masked["api_key_masked"] == "••••••••1234"
    assert masked["api_key_storage"] == "windows_dpapi"
    assert masked["api_key_error"] == ""


def test_legacy_plaintext_is_migrated_and_removed(test_db, isolated_api_key_store):
    secret = "legacy-secret-5678"
    test_db.add(AppSetting(key="api_key", value=secret))
    test_db.commit()
    database_path = Path(str(test_db.get_bind().url.database))

    assert SettingsService.migrate_plaintext_api_key(test_db) is True

    saved = test_db.query(AppSetting).filter(AppSetting.key == "api_key").first()
    assert saved is None
    assert isolated_api_key_store.read() == secret
    for path in (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
        Path(f"{database_path}-journal"),
    ):
        if path.exists():
            assert secret.encode("utf-8") not in path.read_bytes()


def test_conflicting_legacy_and_dpapi_keys_fail_closed(test_db, isolated_api_key_store):
    isolated_api_key_store.write("dpapi-secret")
    test_db.add(AppSetting(key="api_key", value="different-database-secret"))
    test_db.commit()

    with pytest.raises(ApiKeyStorageError, match="存在不同的 API Key"):
        SettingsService.migrate_plaintext_api_key(test_db)

    saved = test_db.query(AppSetting).filter(AppSetting.key == "api_key").first()
    assert saved is not None
    assert saved.value == "different-database-secret"
    assert isolated_api_key_store.read() == "dpapi-secret"


def test_corrupt_secure_store_is_visible_and_can_be_cleared(
    test_db,
    isolated_api_key_store,
):
    isolated_api_key_store.path.parent.mkdir(parents=True, exist_ok=True)
    isolated_api_key_store.path.write_bytes(b"not-a-valid-secure-store")

    masked = SettingsService.get_masked_settings(test_db)

    assert masked["api_key_configured"] is True
    assert masked["api_key_masked"] == ""
    assert "安全存储格式无效" in masked["api_key_error"]

    SettingsService.update_settings(test_db, {"clear_api_key": True})
    assert isolated_api_key_store.is_configured() is False
    assert SettingsService.get_masked_settings(test_db)["api_key_error"] == ""


def test_init_db_migrates_plaintext_before_creating_startup_backup(
    tmp_path,
    monkeypatch,
    isolated_api_key_store,
):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    db.add(AppSetting(key="api_key", value="startup-legacy-secret"))
    db.commit()
    db.close()

    observed = {}

    def inspect_backup_input(target_engine):
        with sqlite3.connect(database_path) as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key='api_key'"
            ).fetchone()
        observed["api_key_row"] = row
        return None

    monkeypatch.setattr("app.db.session.backup_database", inspect_backup_input)
    monkeypatch.setattr("app.db.migrations.upgrade_database", lambda _engine: "test-revision")
    monkeypatch.setattr(
        "app.db.migrations.validate_database_schema",
        lambda _engine: SimpleNamespace(table_count=11),
    )
    monkeypatch.setattr(
        "app.db.session.finalize_storage_identity",
        lambda _engine, _preflight: SimpleNamespace(
            database_path=str(database_path),
            database_instance_id="",
            counts={},
        ),
    )

    try:
        init_db(engine)
    finally:
        engine.dispose()

    assert observed["api_key_row"] is None
    assert isolated_api_key_store.read() == "startup-legacy-secret"


def test_settings_endpoint_returns_only_masked_dpapi_metadata(
    test_db,
    isolated_api_key_store,
):
    secret = "sk-endpoint-secret-4455"
    SettingsService.update_settings(test_db, {"api_key": secret, "mock_llm": False})

    response = _make_client(test_db).get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert "api_key" not in payload
    assert secret not in response.text
    assert payload["api_key_configured"] is True
    assert payload["api_key_masked"] == "••••••••4455"
    assert payload["api_key_storage"] == "windows_dpapi"
    assert payload["api_key_error"] == ""


def test_settings_endpoint_exposes_recoverable_store_error(
    test_db,
    isolated_api_key_store,
):
    isolated_api_key_store.path.parent.mkdir(parents=True, exist_ok=True)
    isolated_api_key_store.path.write_bytes(b"broken-store")
    client = _make_client(test_db)

    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["api_key_configured"] is True
    assert "安全存储格式无效" in response.json()["api_key_error"]

    clear_response = client.put("/api/settings", json={"clear_api_key": True})
    assert clear_response.status_code == 200
    assert clear_response.json()["api_key_configured"] is False
    assert clear_response.json()["api_key_error"] == ""


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI acceptance runs on Windows")
def test_windows_dpapi_round_trip_uses_current_user_profile(tmp_path):
    store = FileApiKeyStore(tmp_path / "api-key.dpapi", WindowsDpapiProtector())
    secret = "sk-windows-dpapi-acceptance-9012"

    store.write(secret)

    assert store.read() == secret
    assert secret.encode("utf-8") not in store.path.read_bytes()
    store.clear()
    assert store.is_configured() is False
