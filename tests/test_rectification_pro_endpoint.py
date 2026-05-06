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


def _payload(events_count: int) -> dict:
    events = []
    for idx in range(events_count):
        events.append(
            {
                "event_id": f"ev{idx+1}",
                "event_type": "children_birth",
                "title": f"event {idx+1}",
                "date_text": f"201{idx}-05-12",
                "date_precision": "exact",
                "start_date": f"201{idx}-05-12",
                "end_date": f"201{idx}-05-12",
                "impact_level": 5,
                "reversibility": "irreversible",
                "life_area": "family",
                "sequence_number": idx + 1,
                "notes": "",
                "user_skipped": False,
            }
        )
    return {
        "birth_date_local": "1990-05-12",
        "latitude": 53.9006,
        "longitude": 27.5590,
        "timezone_name": "Europe/Moscow",
        "asc_windows": [
            {
                "start_local": "1990-05-12T14:00:00",
                "end_local": "1990-05-12T14:20:00",
                "sign_name_en": "Libra",
                "sign_name_ru": "Весы",
            }
        ],
        "events": events,
        "settings": {
            "candidate_step_minutes": 5,
            "include_directions": True,
            "include_solars": True,
            "include_lunars": False,
            "include_transits": True,
            "include_totems": False,
        },
    }


def test_rectification_pro_run_endpoint_contract(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=_payload(5))
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "rectification_pro"
    assert body["status"] == "completed"
    assert "candidate_windows" in body
    assert "best_candidates" in body
    assert "method_results" in body
    assert "confidence" in body


def test_rectification_pro_run_low_confidence_for_weak_data(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=_payload(1))
    assert response.status_code == 200
    body = response.json()
    assert body["confidence"]["level"] in {"low", "medium"}


def test_rectification_pro_accepts_new_event_types(monkeypatch, tmp_path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    payload = _payload(1)
    payload["events"][0]["event_type"] = "child_birth"
    payload["events"][0]["life_area"] = "family"
    payload["events"][0]["sequence_number"] = 1
    with client:
        response = client.post("/api/v1/rectification/pro/run", json=payload)
    assert response.status_code == 200
