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


def test_contract_chart_response_is_stable_and_computation_only(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    request_id = "contract-chart-001"

    with client:
        response = client.post(
            "/api/v1/chart",
            headers={"X-Request-ID": request_id},
            json={
                "datetime_utc": "1984-11-13T11:35:00Z",
                "latitude": 53.9006,
                "longitude": 27.5590,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
        )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
    body = response.json()
    assert set(body.keys()) == {"input", "normalized", "objects", "aspects", "houses", "angles", "meta"}
    assert isinstance(body["aspects"], list)
    for aspect in body["aspects"]:
        assert set(aspect.keys()) == {
            "object_a",
            "object_b",
            "aspect_type",
            "exact_angle",
            "actual_angle",
            "orb",
            "applying",
        }
    assert "interpretation_text" not in body
    assert "horoscope_text" not in body


def test_contract_rectification_response_has_timezone_block_and_expected_fields(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    request_id = "contract-rect-001"

    with client:
        response = client.post(
            "/api/v1/rectification/asc-sign-intervals",
            headers={"X-Request-ID": request_id},
            json={
                "birth_date_local": "2000-04-16",
                "latitude": 53.9,
                "longitude": 27.56667,
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
        )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
    body = response.json()
    assert set(body.keys()) == {
        "mode",
        "version",
        "generated_at_utc",
        "birth_context",
        "day_window",
        "day_window_utc",
        "shared_day_summary",
        "asc_sign_intervals",
    }
    assert "timezone" in body["birth_context"]
    assert "timezone_source" in body["birth_context"]
    assert body["birth_context"]["timezone_source"] == "coordinates"
    assert "interpretation_text" not in body


def test_contract_events_finalize_has_expected_fields_and_no_interpretation_text(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    request_id = "contract-events-finalize-001"

    with client:
        response = client.post(
            "/api/v1/rectification/events/finalize",
            headers={"X-Request-ID": request_id},
            json={"dialog_history": []},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
    body = response.json()
    assert set(body.keys()) == {
        "status",
        "step_index",
        "events_collected_count",
        "warnings",
        "events",
        "events_count",
        "strong_events_count",
        "confidence_preliminary",
        "dialog_history",
    }
    assert body["status"] == "finalized"
    assert body["confidence_preliminary"] in {"low", "medium", "high"}
    assert "interpretation_text" not in body


def test_contract_health_includes_request_id_in_header_and_body(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    request_id = "contract-health-001"

    with client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == request_id
    body = response.json()
    assert body["request_id"] == request_id
    assert body["status"] == "ok"
