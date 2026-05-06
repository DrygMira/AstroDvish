from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


class _FakeHttpResponse:
    def __init__(self, *, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        return self._payload


def test_geocode_uses_fallback_provider_when_open_meteo_502(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(web_ui_main, "GEOCODE_CACHE_PATH", tmp_path / "geocode_cache.json")

    def fake_get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20):
        if "open-meteo.com" in url:
            return _FakeHttpResponse(status_code=502, payload={"error": "bad gateway"}, text="bad gateway")
        return _FakeHttpResponse(
            status_code=200,
            payload=[
                {
                    "lat": "52.58501",
                    "lon": "32.76314",
                    "display_name": "Стародуб, Брянская область, Россия",
                    "name": "Стародуб",
                    "address": {"country": "Россия", "state": "Брянская область"},
                }
            ],
            text="ok",
        )

    monkeypatch.setattr(web_ui_main.httpx, "get", fake_get)
    with TestClient(web_ui_main.app) as client:
        response = client.post("/api/geocode", json={"query": "Стародуб"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "nominatim"
    assert payload["fallback_provider_used"] is True
    assert payload["cached_result_used"] is False
    assert payload["results"]


def test_geocode_uses_cached_result_when_providers_unavailable(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "geocode_cache.json"
    monkeypatch.setattr(web_ui_main, "GEOCODE_CACHE_PATH", cache_path)
    web_ui_main._cache_geocode_result(
        "Стародуб",
        [
            {
                "name": "Стародуб",
                "country": "Россия",
                "admin1": "Брянская область",
                "latitude": 52.58501,
                "longitude": 32.76314,
                "timezone": "Europe/Moscow",
                "timezone_name": "Europe/Moscow",
                "timezone_source": "open_meteo",
            }
        ],
    )

    def fake_get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20):
        return _FakeHttpResponse(status_code=503, payload={"error": "unavailable"}, text="unavailable")

    monkeypatch.setattr(web_ui_main.httpx, "get", fake_get)
    with TestClient(web_ui_main.app) as client:
        response = client.post("/api/geocode", json={"query": "Стародуб"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "cache"
    assert payload["cached_result_used"] is True
    assert payload["results"][0]["name"] == "Стародуб"


def test_geocode_returns_human_message_when_all_sources_fail(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web_ui_main, "GEOCODE_CACHE_PATH", tmp_path / "geocode_cache.json")

    def fake_get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 20):
        return _FakeHttpResponse(status_code=502, payload={"error": "bad gateway"}, text="bad gateway")

    monkeypatch.setattr(web_ui_main.httpx, "get", fake_get)
    with TestClient(web_ui_main.app) as client:
        response = client.post("/api/geocode", json={"query": "Стародуб"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["user_message"].startswith("Сервис поиска города временно недоступен")
