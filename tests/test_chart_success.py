from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

MANDATORY_OBJECTS = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
    "true_node",
    "mean_node",
)


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SWEPH_EPHE_PATH", str(tmp_path / "ephe"))
    monkeypatch.setenv("SWEPH_AUTO_DOWNLOAD", "false")
    monkeypatch.setenv("APP_LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


def test_chart_success_endpoint(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = {
        "datetime_utc": "1984-11-13T11:35:00Z",
        "latitude": 53.9006,
        "longitude": 27.5590,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
    }

    with client:
        response = client.post("/api/v1/chart", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert "input" in data
    assert "normalized" in data
    assert "julian_day_ut" in data["normalized"]
    assert data["meta"]["ephemeris_source"] == "swisseph"

    objects = data["objects"]
    for name in MANDATORY_OBJECTS:
        assert name in objects
        obj = objects[name]
        assert 0 <= obj["longitude_deg"] <= 360
        assert 0 <= obj["absolute_degree_0_360"] <= 360
        assert -90 <= obj["latitude_deg"] <= 90
        assert 0 <= obj["sign_index"] <= 11

    assert len(data["houses"]["cusps"]) == 12
    for value in data["houses"]["cusps"].values():
        assert 0 <= value <= 360

    assert "asc" in data["angles"]
    assert "mc" in data["angles"]
    assert 0 <= data["angles"]["asc"] <= 360
    assert 0 <= data["angles"]["mc"] <= 360
    assert "aspects" in data
    assert isinstance(data["aspects"], list)
    for aspect in data["aspects"]:
        assert "object_a" in aspect
        assert "object_b" in aspect
        assert "aspect_type" in aspect
        assert "exact_angle" in aspect
        assert "actual_angle" in aspect
        assert "orb" in aspect
        assert aspect["applying"] is None


def test_chart_returns_real_calculation_output(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = {
        "datetime_utc": "2024-01-20T15:00:00Z",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "house_system": "K",
        "zodiac_mode": "sidereal",
        "sidereal_mode": "lahiri",
    }

    with client:
        response = client.post("/api/v1/chart", json=payload)

    assert response.status_code == 200
    body = response.json()

    sun_lon = body["objects"]["sun"]["longitude_deg"]
    moon_lon = body["objects"]["moon"]["longitude_deg"]
    assert sun_lon != moon_lon
    assert "horoscope_text" not in body
    assert "interpretation_text" not in body
    assert body["houses"]["system"] == "K"
    assert body["meta"]["zodiac_mode"] == "sidereal"
    assert body["meta"]["sidereal_mode"] == "lahiri"
