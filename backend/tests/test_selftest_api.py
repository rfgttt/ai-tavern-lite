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


def test_selftest_run_collects_results_and_exports_zip(db_with_session, tmp_path):
    from app.services.selftest.service import selftest_service

    db, _char, _session = db_with_session
    selftest_service.reconfigure(tmp_path / "selftest")
    client = make_client(db)

    created = client.post("/api/self-test/runs")
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    backend = client.post(
        f"/api/self-test/runs/{run_id}/backend",
        json={"status": "passed", "tests": [{"name": "health", "status": "passed"}]},
    )
    assert backend.status_code == 200

    frontend = client.post(
        f"/api/self-test/runs/{run_id}/frontend",
        json={"status": "failed", "tests": [{"name": "cache", "status": "failed", "error": "boom"}]},
    )
    assert frontend.status_code == 200

    status = client.get(f"/api/self-test/runs/{run_id}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["backend"]["status"] == "passed"
    assert payload["frontend"]["status"] == "failed"
    assert payload["status"] == "failed"

    exported = client.post(f"/api/self-test/runs/{run_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = set(archive.namelist())
        assert "self-test-summary.json" in names
        assert "backend-tests.json" in names
        assert "frontend-tests.json" in names
        assert "diagnostics.zip" in names
