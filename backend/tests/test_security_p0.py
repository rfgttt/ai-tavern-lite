import base64
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, settings
from app.core.middleware import BasicAuthMiddleware, InMemoryRateLimitMiddleware, RequestSizeLimitMiddleware
from app.core.security import UnsafeOutboundURLError, validate_outbound_url


def _basic(username: str, password: str) -> dict[str, str]:
    value = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {value}"}


def test_ssrf_guard_rejects_local_and_private_destinations(monkeypatch):
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url("http://127.0.0.1:8000")
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url("http://169.254.169.254/latest/meta-data")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443))],
    )
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url("https://model.example")


def test_ssrf_guard_accepts_public_allowlisted_destination(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    result = validate_outbound_url(
        "https://model.example/v1",
        allowed_hosts=("model.example",),
    )
    assert result.hostname == "model.example"
    assert result.addresses == ("93.184.216.34",)


def test_basic_auth_protects_app_and_exempts_health(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_username", "owner")
    monkeypatch.setattr(settings, "auth_password", SecretStr("strong-password"))
    monkeypatch.setattr(settings, "auth_exempt_paths_csv", "/api/health")

    app = FastAPI()
    app.add_middleware(BasicAuthMiddleware)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/private")
    def private():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/private").status_code == 401
    assert client.get("/private", headers=_basic("owner", "wrong")).status_code == 401
    assert client.get("/private", headers=_basic("owner", "strong-password")).status_code == 200


def test_json_request_size_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_json_body_bytes", 32)
    monkeypatch.setattr(settings, "max_request_body_bytes", 64)

    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware)

    @app.post("/echo")
    def echo(payload: dict):
        return payload

    client = TestClient(app)
    assert client.post("/echo", json={"value": "ok"}).status_code == 200
    response = client.post("/echo", json={"value": "x" * 100})
    assert response.status_code == 413


def test_api_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    monkeypatch.setattr(settings, "ai_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "ai_rate_limit_window_seconds", 60)

    app = FastAPI()
    app.add_middleware(InMemoryRateLimitMiddleware)

    @app.get("/api/items")
    def items():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/api/items").status_code == 200
    assert client.get("/api/items").status_code == 200
    response = client.get("/api/items")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_production_configuration_fails_closed_without_authentication():
    config = Settings(
        _env_file=None,
        environment="production",
        allowed_hosts="tavern.real-domain.dev",
        rate_limit_enabled=True,
        enable_diagnostics=False,
        enable_selftest=False,
        auth_enabled=False,
    )
    with pytest.raises(RuntimeError, match="AUTH_ENABLED"):
        config.validate_runtime_security()


def test_production_configuration_accepts_required_controls():
    config = Settings(
        _env_file=None,
        environment="production",
        allowed_hosts="tavern.real-domain.dev",
        rate_limit_enabled=True,
        enable_diagnostics=False,
        enable_selftest=False,
        auth_enabled=True,
        auth_username="owner",
        auth_password=SecretStr("a-secure-password"),
    )
    config.validate_runtime_security()
