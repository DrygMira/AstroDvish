from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.core.errors import TimezoneLookupError
from app.main import create_app


def _build_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SWEPH_EPHE_PATH", str(tmp_path / "ephe"))
    monkeypatch.setenv("SWEPH_AUTO_DOWNLOAD", "false")
    monkeypatch.setenv("APP_LOG_LEVEL", "INFO")
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


def test_asc_sign_intervals_success(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = {
        "birth_date_local": "2000-04-16",
        "latitude": 53.9,
        "longitude": 27.56667,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
    }

    with client:
        response = client.post("/api/v1/rectification/asc-sign-intervals", json=payload)

    assert response.status_code == 200
    body = response.json()

    assert body["mode"] == "asc_sign_intervals"
    assert body["version"] == "1.0"
    assert "generated_at_utc" in body
    assert "birth_context" in body
    assert "day_window" in body
    assert "day_window_utc" in body
    assert "shared_day_summary" in body
    assert "asc_sign_intervals" in body
    assert body["birth_context"]["timezone_source"] == "coordinates"
    assert body["day_window_utc"]["start_utc"].endswith("Z")
    assert body["day_window_utc"]["end_utc"].endswith("Z")

    intervals = body["asc_sign_intervals"]
    assert intervals
    assert len(intervals) == 13

    start_day = datetime.fromisoformat(body["day_window"]["start_local"])
    end_day = datetime.fromisoformat(body["day_window"]["end_local"])
    first_interval_start = datetime.fromisoformat(intervals[0]["start_local"])
    last_interval_end = datetime.fromisoformat(intervals[-1]["end_local"])
    assert first_interval_start < start_day
    assert last_interval_end > end_day

    previous_start: datetime | None = None
    previous_end: datetime | None = None
    for interval in intervals:
        assert interval["start_local"]
        assert interval["end_local"]
        assert isinstance(interval["duration_minutes"], int)
        assert interval["sign_name_ru"]

        sample_points = interval["sample_points"]
        assert "p15" in sample_points
        assert "p50" in sample_points
        assert "p85" in sample_points

        interval_start = datetime.fromisoformat(interval["start_local"])
        interval_end = datetime.fromisoformat(interval["end_local"])
        assert interval_start <= interval_end

        if previous_start is not None:
            assert previous_start <= interval_start
        previous_start = interval_start
        if previous_end is not None:
            assert previous_end <= interval_start
        previous_end = interval_end

        p15 = datetime.fromisoformat(sample_points["p15"]["local_time"])
        p50 = datetime.fromisoformat(sample_points["p50"]["local_time"])
        p85 = datetime.fromisoformat(sample_points["p85"]["local_time"])
        assert interval_start <= p15 <= interval_end
        assert interval_start <= p50 <= interval_end
        assert interval_start <= p85 <= interval_end
        assert p15 < p50 < p85


def test_asc_sign_intervals_timezone_lookup_error(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)

    def _raise_timezone_error(*, latitude: float, longitude: float) -> str:
        raise TimezoneLookupError(
            "Could not determine timezone for coordinates",
            details={"latitude": latitude, "longitude": longitude},
        )

    monkeypatch.setattr(
        "app.services.asc_sign_intervals_service.timezone_lookup.resolve_timezone_name",
        _raise_timezone_error,
    )

    payload = {
        "birth_date_local": "2000-04-16",
        "latitude": 53.9,
        "longitude": 27.56667,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
    }

    with client:
        response = client.post("/api/v1/rectification/asc-sign-intervals", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "timezone_lookup_error"


def test_asc_sign_intervals_respects_manual_timezone_override(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = {
        "birth_date_local": "2000-04-16",
        "latitude": 53.9,
        "longitude": 27.56667,
        "timezone_mode": "manual",
        "timezone_offset": "+05:00",
        "timezone_name": None,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
    }

    with client:
        response = client.post("/api/v1/rectification/asc-sign-intervals", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["birth_context"]["timezone_source"] == "manual_offset"
    assert body["birth_context"]["timezone"] == "GMT+05:00"
    assert body["birth_context"]["timezone_offset"] == "+05:00"
    assert body["day_window_utc"]["start_utc"] == "2000-04-15T19:00:00Z"


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected_timezone"),
    [
        (52.2297, 21.0122, "Europe/Warsaw"),
        (55.7558, 37.6173, "Europe/Moscow"),
        (40.7128, -74.0060, "America/New_York"),
    ],
)
def test_asc_sign_intervals_timezone_universal_by_coordinates(
    monkeypatch,
    tmp_path,
    latitude: float,
    longitude: float,
    expected_timezone: str,
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = {
        "birth_date_local": "2000-04-16",
        "latitude": latitude,
        "longitude": longitude,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
    }

    with client:
        response = client.post("/api/v1/rectification/asc-sign-intervals", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["birth_context"]["latitude"] == latitude
    assert body["birth_context"]["longitude"] == longitude
    assert body["birth_context"]["timezone"] == expected_timezone
    assert body["birth_context"]["timezone_source"] == "coordinates"
    assert body["day_window_utc"]["start_utc"].endswith("Z")
    assert body["day_window_utc"]["end_utc"].endswith("Z")
