from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

import web_ui.main as web_main


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload


def _object_payload(
    name: str,
    degree: float,
    *,
    sign_name_en: str,
    sign_degree: float,
    speed: float,
) -> dict[str, Any]:
    return {
        "name": name,
        "longitude_deg": degree,
        "latitude_deg": 0.0,
        "distance_au": 1.0,
        "speed_longitude_deg_per_day": speed,
        "retrograde": speed < 0,
        "sign_index": 0,
        "sign_name_en": sign_name_en,
        "sign_degree": sign_degree,
        "sign_degree_dms": "0deg00'00\"",
        "absolute_degree_0_360": degree,
        "house": 1,
    }


def _natal_chart_payload(datetime_utc: str) -> dict[str, Any]:
    return {
        "input": {
            "datetime_utc": datetime_utc,
            "latitude": 0.0,
            "longitude": 0.0,
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
        "normalized": {"julian_day_ut": 2447907.0},
        "objects": {
            "sun": _object_payload("sun", 10.0, sign_name_en="Aries", sign_degree=10.0, speed=1.0),
            "moon": _object_payload("moon", 50.0, sign_name_en="Taurus", sign_degree=20.0, speed=12.0),
            "mercury": _object_payload("mercury", 75.0, sign_name_en="Gemini", sign_degree=15.0, speed=1.2),
            "venus": _object_payload("venus", 110.0, sign_name_en="Cancer", sign_degree=20.0, speed=1.1),
            "mars": _object_payload("mars", 125.0, sign_name_en="Leo", sign_degree=5.0, speed=0.6),
            "jupiter": _object_payload("jupiter", 160.0, sign_name_en="Virgo", sign_degree=10.0, speed=0.08),
            "saturn": _object_payload("saturn", 180.0, sign_name_en="Libra", sign_degree=0.0, speed=0.03),
            "uranus": _object_payload("uranus", 222.0, sign_name_en="Scorpio", sign_degree=12.0, speed=0.01),
            "neptune": _object_payload("neptune", 260.0, sign_name_en="Sagittarius", sign_degree=20.0, speed=0.005),
            "pluto": _object_payload("pluto", 280.0, sign_name_en="Capricorn", sign_degree=10.0, speed=-0.002),
        },
        "houses": {"system": "P", "cusps": {"1": 145.0}, "cusp_details": {"1": {"absolute_degree_0_360": 145.0}}},
        "angles": {"asc": 145.0, "mc": 58.0},
        "meta": {
            "ephemeris_source": "swisseph",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
    }


def _transit_chart_payload(datetime_utc: str) -> dict[str, Any]:
    return {
        "input": {
            "datetime_utc": datetime_utc,
            "latitude": 0.0,
            "longitude": 0.0,
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
        "normalized": {"julian_day_ut": 2461203.0},
        "objects": {
            "sun": _object_payload("sun", 70.0, sign_name_en="Gemini", sign_degree=10.0, speed=0.98),
            "moon": _object_payload("moon", 110.0, sign_name_en="Cancer", sign_degree=20.0, speed=13.2),
            "mercury": _object_payload("mercury", 129.4, sign_name_en="Leo", sign_degree=9.4, speed=1.4),
            "venus": _object_payload("venus", 155.3, sign_name_en="Virgo", sign_degree=5.3, speed=1.1),
            "mars": _object_payload("mars", 11.2, sign_name_en="Aries", sign_degree=11.2, speed=0.55),
            "jupiter": _object_payload("jupiter", 339.2, sign_name_en="Pisces", sign_degree=9.2, speed=0.07),
            "saturn": _object_payload("saturn", 281.0, sign_name_en="Capricorn", sign_degree=11.0, speed=0.02),
            "uranus": _object_payload("uranus", 190.0, sign_name_en="Libra", sign_degree=10.0, speed=0.008),
            "neptune": _object_payload("neptune", 230.6, sign_name_en="Scorpio", sign_degree=20.6, speed=0.004),
            "pluto": _object_payload("pluto", 100.0, sign_name_en="Cancer", sign_degree=10.0, speed=-0.0015),
        },
        "houses": {"system": "P", "cusps": {"1": 200.0}, "cusp_details": {"1": {"absolute_degree_0_360": 200.0}}},
        "angles": {"asc": 200.0, "mc": 140.0},
        "meta": {
            "ephemeris_source": "swisseph",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
    }


def _fake_http_post(url: str, *args, **kwargs) -> _FakeResponse:
    if url.endswith("/api/v1/chart"):
        datetime_utc = kwargs["json"]["datetime_utc"]
        if datetime_utc.startswith("1990-01-15"):
            return _FakeResponse(_natal_chart_payload(datetime_utc))
        return _FakeResponse(_transit_chart_payload(datetime_utc))
    raise AssertionError(f"Unexpected url: {url}")


def test_generate_no_time_accepts_birth_date_only_and_sets_facts(monkeypatch) -> None:
    monkeypatch.setattr(web_main.httpx, "post", _fake_http_post)
    monkeypatch.setattr(
        web_main,
        "_render_no_time_forecast_via_openai",
        lambda prompt_text, forecast_context: {"text": "NO_TIME_OK"},
    )
    monkeypatch.setattr(
        web_main,
        "_now_utc",
        lambda: datetime(2026, 6, 12, 9, 0, 0, tzinfo=timezone.utc),
    )

    payload = {
        "api_base_url": "http://127.0.0.1:8013",
        "birth_date_local": "1990-01-15",
        "timezone_mode": "auto",
        "profile_timezone_name": "Europe/Moscow",
        "prompt_text": "Сделай персональный прогноз.",
    }

    with TestClient(web_main.app) as client:
        response = client.post("/api/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    facts = body["calculation_facts"]
    assert body["horoscope_text"] == "NO_TIME_OK"
    assert facts["precision"] == "birth_date_no_time"
    assert facts["birth_time_used"] == "12:00"
    assert facts["birth_time_assumption"] == "date_midpoint"
    assert facts["houses_available"] is False
    assert facts["asc_mc_available"] is False
    assert facts["forecast_mode"] == "transit_to_natal_no_houses"
    assert facts["transit_aspects"]
    assert facts["moon_daily_windows"]


def test_generate_no_time_sanitizes_houses_angles_and_cusps(monkeypatch) -> None:
    monkeypatch.setattr(web_main.httpx, "post", _fake_http_post)
    monkeypatch.setattr(
        web_main,
        "_render_no_time_forecast_via_openai",
        lambda prompt_text, forecast_context: {"text": "NO_TIME_OK"},
    )
    monkeypatch.setattr(
        web_main,
        "_now_utc",
        lambda: datetime(2026, 6, 12, 9, 0, 0, tzinfo=timezone.utc),
    )

    with TestClient(web_main.app) as client:
        response = client.post(
            "/api/generate",
            json={
                "api_base_url": "http://127.0.0.1:8013",
                "birth_date_local": "1990-01-15",
                "timezone_mode": "auto",
                "profile_timezone_name": "Europe/Moscow",
                "prompt_text": "Сделай персональный прогноз.",
            },
        )

    assert response.status_code == 200
    chart = response.json()["chart_response"]
    assert chart["angles"] == {}
    assert chart["houses"]["cusps"] == {}
    assert chart["houses"]["cusp_details"] == {}
    assert all(item.get("house") is None for item in chart["objects"].values())


def test_generate_no_time_excludes_natal_moon_and_supports_minor_aspects(monkeypatch) -> None:
    monkeypatch.setattr(web_main.httpx, "post", _fake_http_post)
    monkeypatch.setattr(
        web_main,
        "_render_no_time_forecast_via_openai",
        lambda prompt_text, forecast_context: {"text": "NO_TIME_OK"},
    )
    monkeypatch.setattr(
        web_main,
        "_now_utc",
        lambda: datetime(2026, 6, 12, 9, 0, 0, tzinfo=timezone.utc),
    )

    with TestClient(web_main.app) as client:
        response = client.post(
            "/api/generate",
            json={
                "api_base_url": "http://127.0.0.1:8013",
                "birth_date_local": "1990-01-15",
                "timezone_mode": "auto",
                "profile_timezone_name": "Europe/Moscow",
                "prompt_text": "Сделай персональный прогноз.",
            },
        )

    assert response.status_code == 200
    aspects = response.json()["calculation_facts"]["transit_aspects"]
    assert all(item["natal_body"] != "Moon" for item in aspects)
    assert any(item["aspect"] == "trine" and abs(item["orb"] - 0.6) < 1e-6 for item in aspects)
    assert any(item["aspect"] == "semi-sextile" and item["orb"] <= 0.5 for item in aspects)
    assert any(item["aspect"] == "quincunx" and item["orb"] <= 0.5 for item in aspects)
    assert any(item["phase"] in {"applying", "exact", "separating"} for item in aspects)


def test_generate_birth_date_is_required_when_datetime_missing() -> None:
    with TestClient(web_main.app) as client:
        response = client.post(
            "/api/generate",
            json={
                "api_base_url": "http://127.0.0.1:8013",
                "timezone_mode": "auto",
                "prompt_text": "Сделай персональный прогноз.",
            },
        )

    assert response.status_code == 422
    assert "birth date" in str(response.json()).lower()


def test_generate_full_datetime_mode_stays_on_old_path(monkeypatch) -> None:
    monkeypatch.setattr(web_main.httpx, "post", _fake_http_post)
    captured: dict[str, Any] = {"full_called": False}

    def _fake_full_render(prompt_text: str, chart: dict[str, Any]) -> str:
        captured["full_called"] = True
        return "FULL_OK"

    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", _fake_full_render)
    monkeypatch.setattr(
        web_main,
        "_render_no_time_forecast_via_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no-time renderer must not be used")),
    )

    with TestClient(web_main.app) as client:
        response = client.post(
            "/api/generate",
            json={
                "api_base_url": "http://127.0.0.1:8013",
                "datetime_local": "1990-01-15T12:00:00",
                "timezone_mode": "manual",
                "timezone_offset": "+03:00",
                "timezone_name": "Europe/Moscow",
                "latitude": 53.9,
                "longitude": 27.55,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
                "prompt_text": "Сделай гороскоп по этим данным.",
            },
        )

    assert response.status_code == 200
    assert response.json()["horoscope_text"] == "FULL_OK"
    assert captured["full_called"] is True
