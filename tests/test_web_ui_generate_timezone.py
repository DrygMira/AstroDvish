from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import web_ui.main as web_main


class _FakeResponse:
    status_code = 200

    @staticmethod
    def json() -> dict[str, Any]:
        return {
            "input": {
                "datetime_utc": "1984-11-13T11:35:00Z",
                "latitude": 53.9,
                "longitude": 27.55,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
            "normalized": {"julian_day_ut": 2446017.9},
            "objects": {
                "sun": {"longitude_deg": 231.0},
                "moon": {"longitude_deg": 102.0},
            },
            "houses": {"system": "P", "cusps": {"1": 145.0}},
            "angles": {"asc": 145.0, "mc": 58.0},
            "meta": {
                "ephemeris_source": "swisseph",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
                "object_constants": {"sun": 0},
            },
        }


def _base_payload() -> dict[str, Any]:
    return {
        "api_base_url": "http://127.0.0.1:8013",
        "datetime_local": "1990-01-15T12:00:00",
        "timezone_mode": "auto",
        "timezone_offset": "+05:00",
        "timezone_name": "Europe/London",
        "latitude": 53.9,
        "longitude": 27.55,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
        "prompt_text": "prompt",
    }


def test_generate_auto_timezone_ignores_manual_offset_and_returns_source(monkeypatch) -> None:
    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "OK")

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=_base_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["chart_status"] == "ok"
    assert body["llm_status"] == "ok"
    assert body["timezone"]["mode"] == "auto"
    assert body["timezone"]["timezone_name"] == "Europe/London"
    assert body["timezone"]["timezone_source"] == "auto_by_coordinates"
    assert body["timezone"]["timezone_offset"] == "+00:00"
    assert "manual_offset_ignored_in_auto_timezone_mode" in body["warnings"]


def test_generate_auto_timezone_uses_historical_offset_for_date(monkeypatch) -> None:
    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "OK")

    winter_payload = _base_payload()
    summer_payload = _base_payload()
    summer_payload["datetime_local"] = "1990-07-15T12:00:00"

    with TestClient(web_main.app) as client:
        winter_response = client.post("/api/generate", json=winter_payload)
        summer_response = client.post("/api/generate", json=summer_payload)

    assert winter_response.status_code == 200
    assert summer_response.status_code == 200
    assert winter_response.json()["timezone"]["timezone_offset"] == "+00:00"
    assert summer_response.json()["timezone"]["timezone_offset"] == "+01:00"


def test_generate_manual_timezone_mode_marks_manual_source(monkeypatch) -> None:
    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "OK")

    payload = _base_payload()
    payload["timezone_mode"] = "manual"
    payload["timezone_offset"] = "+05:00"

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"]["timezone_source"] == "manual_offset"
    assert body["timezone"]["timezone_offset"] == "+05:00"
    assert "manual_timezone_offset_used" in body["warnings"]


def test_generate_passes_core_identity_sun_moon_asc(monkeypatch) -> None:
    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    captured: dict[str, Any] = {}

    def _fake_render(prompt_text: str, chart: dict[str, Any], core_identity: dict[str, Any]) -> str:
        captured["core_identity"] = core_identity
        return "OK"

    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", _fake_render)

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=_base_payload())

    assert response.status_code == 200
    assert captured["core_identity"]["sun"] is not None
    assert captured["core_identity"]["moon"] is not None
    assert captured["core_identity"]["asc"] == 145.0


def test_generate_preserves_seconds_in_datetime_local_and_utc(monkeypatch) -> None:
    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "OK")

    payload = _base_payload()
    payload["timezone_mode"] = "manual"
    payload["timezone_offset"] = "+00:00"
    payload["datetime_local"] = "1990-01-15T12:00:30"

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"]["datetime_local"] == "1990-01-15T12:00:30"
    assert body["timezone"]["datetime_utc"].endswith("12:00:30Z")


def test_generate_defaults_missing_seconds_to_zero(monkeypatch) -> None:
    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "OK")

    payload = _base_payload()
    payload["timezone_mode"] = "manual"
    payload["timezone_offset"] = "+00:00"
    payload["datetime_local"] = "1990-01-15T12:00"

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"]["datetime_utc"].endswith("12:00:00Z")


def test_generate_preserves_asymmetric_orb_aspects_in_final_chart_response(monkeypatch) -> None:
    class _AspectResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "input": {
                    "datetime_utc": "1984-10-25T09:28:30Z",
                    "latitude": 54.7388,
                    "longitude": 55.9721,
                    "house_system": "P",
                    "zodiac_mode": "tropical",
                    "sidereal_mode": None,
                },
                "normalized": {"julian_day_ut": 2446000.0},
                "objects": {
                    "sun": {"longitude_deg": 210.0},
                    "uranus": {"longitude_deg": 215.033333},
                    "moon": {"longitude_deg": 30.0},
                    "neptune": {"longitude_deg": 205.333333},
                    "venus": {"longitude_deg": 10.0},
                },
                "houses": {"system": "P", "cusps": {"1": 270.0}},
                "angles": {"asc": 270.0, "mc": 210.0},
                "aspects": [
                    {
                        "object_a": "Sun",
                        "object_b": "Uranus",
                        "aspect_type": "conjunction",
                        "exact_angle": 0.0,
                        "actual_angle": 5.033333,
                        "orb": 5.033333,
                        "applying": None,
                    },
                    {
                        "object_a": "Moon",
                        "object_b": "Neptune",
                        "aspect_type": "opposition",
                        "exact_angle": 180.0,
                        "actual_angle": 175.333333,
                        "orb": 4.666667,
                        "applying": None,
                    },
                    {
                        "object_a": "Venus",
                        "object_b": "Neptune",
                        "aspect_type": "trine",
                        "exact_angle": 120.0,
                        "actual_angle": 123.1,
                        "orb": 3.1,
                        "applying": None,
                    },
                ],
                "meta": {
                    "ephemeris_source": "swisseph",
                    "zodiac_mode": "tropical",
                    "sidereal_mode": None,
                    "object_constants": {"sun": 0},
                    "aspect_orb_profile": "avestan",
                },
            }

    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _AspectResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "OK")

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=_base_payload())

    assert response.status_code == 200
    aspects = response.json()["chart_response"]["aspects"]
    pairs = {(item["object_a"], item["object_b"], item["aspect_type"]) for item in aspects}
    assert ("Sun", "Uranus", "conjunction") in pairs
    assert ("Moon", "Neptune", "opposition") in pairs
    assert ("Venus", "Neptune", "trine") in pairs
