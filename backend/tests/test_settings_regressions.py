from fastapi.testclient import TestClient

from app.db.models import AppSetting
from app.db.session import get_db
from app.main import create_app
from app.services.settings_service import SettingsService


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_database_settings_are_not_overwritten_by_defaults(test_db):
    result = SettingsService.update_settings(
        test_db,
        {"provider_name": "自定义服务", "username": "Alice"},
    )
    assert result["provider_name"] == "自定义服务"
    assert result["username"] == "Alice"


def test_clear_api_key_removes_saved_key(test_db):
    SettingsService.update_settings(test_db, {"api_key": "secret-key"})
    result = SettingsService.update_settings(test_db, {"clear_api_key": True})

    saved = test_db.query(AppSetting).filter(AppSetting.key == "api_key").first()
    assert saved.value == ""
    assert result["api_key"] == ""


def test_settings_reject_invalid_generation_ranges(test_db):
    client = make_client(test_db)

    assert client.put("/api/settings", json={"temperature": 3}).status_code == 422
    assert client.put("/api/settings", json={"top_p": -0.1}).status_code == 422
    assert client.put(
        "/api/settings",
        json={"max_tokens": 4096, "context_window": 2048},
    ).status_code == 422


def test_settings_reject_partial_update_that_breaks_token_budget(test_db):
    SettingsService.update_settings(
        test_db,
        {"max_tokens": 1024, "context_window": 2048},
    )
    client = make_client(test_db)

    assert client.put("/api/settings", json={"max_tokens": 4096}).status_code == 422
    assert client.put("/api/settings", json={"context_window": 512}).status_code == 422


def test_stream_error_sanitizer_removes_all_configured_secrets():
    from app.api.chat import _sanitize_error

    result = _sanitize_error(RuntimeError("api-secret header-secret"), "api-secret", "header-secret")
    assert result == "*** ***"


def test_settings_update_logs_once(test_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.services.settings_service.logger.info",
        lambda message, *args, **kwargs: calls.append(message),
    )

    response = make_client(test_db).put("/api/settings", json={"username": "单次日志"})

    assert response.status_code == 200
    assert calls.count("Settings updated") == 1
