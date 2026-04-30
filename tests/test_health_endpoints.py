from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SWEPH_EPHE_PATH", str(tmp_path / "ephe"))
    monkeypatch.setenv("SWEPH_AUTO_DOWNLOAD", "false")
    monkeypatch.setenv("APP_LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


def test_health_endpoint(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "astrodvish-api"
    assert body["version"] == "0.5.0"
    assert isinstance(body.get("request_id"), str)
    assert body["request_id"]


def test_api_v1_health_endpoint_and_request_id_echo(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    request_id = "test-request-id-123"

    with client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
    body = response.json()
    assert body["request_id"] == request_id
