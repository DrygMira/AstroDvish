from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("SWEPH_EPHE_PATH", str(tmp_path / "ephe"))
    monkeypatch.setenv("SWEPH_AUTO_DOWNLOAD", "false")
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_invalid_datetime_utc(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "not-a-date",
            "latitude": 53.9,
            "longitude": 27.55,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_latitude(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 120,
            "longitude": 27.55,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_longitude(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 53.9,
            "longitude": 200,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_zodiac_mode(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 53.9,
            "longitude": 27.55,
            "zodiac_mode": "invalid_mode",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_sidereal_tropical_combination(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 53.9,
            "longitude": 27.55,
            "zodiac_mode": "tropical",
            "sidereal_mode": "lahiri",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unsupported_house_system(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 53.9,
            "longitude": 27.55,
            "house_system": "X",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_aspect_orb_profile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chart",
        json={
            "datetime_utc": "1984-11-13T11:35:00Z",
            "latitude": 53.9,
            "longitude": 27.55,
            "aspect_orb_profile": "invalid_profile",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

