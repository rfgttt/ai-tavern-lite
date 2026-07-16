import io
import json
import zipfile


def test_redact_payload_masks_secrets_and_sanitizes_urls(tmp_path):
    from app.services.diagnostics.service import DiagnosticService

    service = DiagnosticService(logs_dir=tmp_path / "logs", diagnostics_dir=tmp_path / "diagnostics")
    payload = service.redact_payload(
        {
            "api_key": "sk-super-secret-value",
            "base_url": "https://user:pass@example.com/v1?token=hidden#fragment",
            "custom_headers": {"Authorization": "Bearer abc", "X-Trace": "private"},
            "nested": {"access_token": "token-value", "safe": "ok"},
        }
    )

    assert payload["api_key"].startswith("sk-")
    assert "super-secret" not in payload["api_key"]
    assert payload["api_key"].endswith("alue")
    assert payload["base_url"] == "https://example.com/v1"
    assert payload["custom_headers"] == {"Authorization": "<redacted>", "X-Trace": "<redacted>"}
    assert payload["nested"]["access_token"] == "<redacted>"
    assert payload["nested"]["safe"] == "ok"


def test_record_request_persists_safe_latest_and_jsonl(tmp_path):
    from app.services.diagnostics.service import DiagnosticService

    service = DiagnosticService(logs_dir=tmp_path / "logs", diagnostics_dir=tmp_path / "diagnostics")
    service.record_chat_request(
        {
            "request_id": "req-1",
            "provider": "DeepSeek",
            "model": "deepseek-chat",
            "api_key": "sk-secret-do-not-write",
            "status": "complete",
        }
    )

    latest = service.get_latest_request()
    assert latest["request_id"] == "req-1"
    assert "secret-do-not-write" not in json.dumps(latest)
    latest_file = json.loads((tmp_path / "diagnostics" / "latest-request.json").read_text("utf-8"))
    assert latest_file == latest
    chat_files = list((tmp_path / "logs").glob("chat-*.jsonl"))
    assert len(chat_files) == 1
    assert "secret-do-not-write" not in chat_files[0].read_text("utf-8")


def test_export_zip_contains_only_sanitized_diagnostics(tmp_path):
    from app.services.diagnostics.service import DiagnosticService

    service = DiagnosticService(logs_dir=tmp_path / "logs", diagnostics_dir=tmp_path / "diagnostics")
    service.record_chat_request({"request_id": "req-zip", "status": "complete"})
    archive = service.build_export_bytes(
        health={"status": "ok"},
        system={"python": "3.10"},
        settings_payload={"api_key": "sk-never-export-me", "base_url": "https://api.example.com/v1?key=no"},
        database_summary={"messages": 3},
    )

    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = set(bundle.namelist())
        assert {
            "README.txt",
            "health.json",
            "system.json",
            "settings-sanitized.json",
            "database-summary.json",
            "latest-request.json",
        }.issubset(names)
        combined = "\n".join(bundle.read(name).decode("utf-8", errors="replace") for name in names)

    assert "never-export-me" not in combined
    assert "?key=no" not in combined
