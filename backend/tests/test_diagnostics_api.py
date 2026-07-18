import io
import zipfile

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app


def make_client(db):
    app = create_app()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_diagnostics_health_reports_components(db_with_session):
    db, _char, _session = db_with_session
    response = make_client(db).get("/api/diagnostics/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["components"]["backend"] is True
    assert payload["components"]["database"] is True
    assert payload["components"]["state_engine"] is True
    assert "provider_configured" in payload["components"]
    assert "mock_mode" in payload
    assert "storage" in payload
    assert "database_path" in payload["storage"]
    assert "api_key" not in str(payload["storage"]).lower()


def test_diagnostics_export_returns_readable_zip(db_with_session):
    db, _char, _session = db_with_session
    response = make_client(db).post("/api/diagnostics/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert "health.json" in bundle.namelist()
        assert "settings-sanitized.json" in bundle.namelist()
        assert "database-summary.json" in bundle.namelist()


def test_diagnostics_latest_and_clear(db_with_session, monkeypatch, tmp_path):
    from app.services.diagnostics.service import diagnostic_service

    db, _char, _session = db_with_session
    diagnostic_service.reconfigure(tmp_path / "logs", tmp_path / "diagnostics")
    diagnostic_service.record_chat_request({"request_id": "req-clear", "status": "complete"})
    client = make_client(db)

    latest = client.get("/api/diagnostics/latest")
    assert latest.status_code == 200
    assert latest.json()["request_id"] == "req-clear"

    cleared = client.delete("/api/diagnostics/logs")
    assert cleared.status_code == 200
    assert cleared.json()["success"] is True
    assert client.get("/api/diagnostics/latest").json() is None
