from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


def test_web_ui_events_start_proxy_success(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        captured["base_url"] = base_url
        captured["path"] = path
        captured["payload"] = payload
        captured["timeout"] = timeout
        return _DummyResponse(
            200,
            {
                "status": "ask_question",
                "step_index": 1,
                "events_collected_count": 0,
                "warnings": [],
                "question": {
                    "question_id": "ev_child_birth_01",
                    "event_type": "child_birth",
                    "question_text": "test",
                    "options": [{"id": "yes", "text": "Да"}],
                    "repeatable": True,
                    "requires_sequence_number": True,
                },
                "dialog_history": [],
            },
        )

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/events/start",
        json={"api_base_url": "http://127.0.0.1:8013", "dialog_history": []},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ask_question"
    assert captured["base_url"] == "http://127.0.0.1:8013"
    assert captured["path"] == "/api/v1/rectification/events/start"
    assert captured["payload"] == {"dialog_history": []}
    assert captured["timeout"] == 120


def test_web_ui_events_continue_proxy_payload(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        captured["base_url"] = base_url
        captured["path"] = path
        captured["payload"] = payload
        captured["timeout"] = timeout
        return _DummyResponse(
            200,
            {
                "status": "finalized",
                "step_index": 1,
                "events_collected_count": 1,
                "warnings": [],
                "events": [
                    {
                        "event_id": "uuid-1",
                        "event_type": "child_birth",
                        "title": "major event",
                        "date_text": "2018",
                        "date_precision": "year",
                        "start_date": "2018-01-01",
                        "end_date": "2018-12-31",
                        "impact_level": 4,
                        "reversibility": "irreversible",
                        "life_area": "family",
                        "sequence_number": 1,
                        "notes": "note",
                        "user_skipped": False,
                    }
                ],
                "events_count": 1,
                "strong_events_count": 1,
                "confidence_preliminary": "low",
                "dialog_history": [],
            },
        )

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/events/continue",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "dialog_history": [{"role": "assistant", "step_index": 1}],
            "last_answer": {
                "question_id": "ev_child_birth_01",
                "event_type": "child_birth",
                "title": "major event",
                "date_text": "2018",
                "impact_level": 4,
                "reversibility": None,
                "life_area": None,
                "sequence_number": 1,
                "notes": "note",
                "user_skipped": False,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "finalized"
    assert captured["path"] == "/api/v1/rectification/events/continue"
    assert captured["payload"]["last_answer"]["question_id"] == "ev_child_birth_01"
    assert captured["payload"]["last_answer"]["sequence_number"] == 1
    assert captured["timeout"] == 120


def test_web_ui_events_finalize_proxy_preserves_backend_422(monkeypatch) -> None:
    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        return _DummyResponse(422, {"detail": "bad request"}, text='{"detail":"bad request"}')

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/events/finalize",
        json={"api_base_url": "http://127.0.0.1:8013", "dialog_history": []},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "bad request"


def test_web_ui_rectification_pro_proxy_success(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        captured["base_url"] = base_url
        captured["path"] = path
        captured["payload"] = payload
        captured["timeout"] = timeout
        return _DummyResponse(
            200,
            {
                "mode": "rectification_pro",
                "version": "0.1",
                "status": "completed",
                "candidate_windows": [],
                "best_candidates": [],
                "method_results": {"directions": [], "solars": [], "lunars": [], "transits": [], "totems": []},
                "confidence": {"level": "low", "time_window_minutes": 120, "explanation": "test"},
                "warnings": [],
                "limitations": [],
            },
        )

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/pro/run",
        json={"api_base_url": "http://127.0.0.1:8013", "payload": {"birth_date_local": "1990-05-12"}},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "rectification_pro"
    assert captured["path"] == "/api/v1/rectification/pro/run"


def test_web_ui_rectification_pro_proxy_preserves_backend_422(monkeypatch) -> None:
    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        return _DummyResponse(
            422,
            {
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", "events", 0, "event_id"],
                        "msg": "Field required",
                    }
                ]
            },
            text='{"detail":[{"type":"missing","loc":["body","events",0,"event_id"],"msg":"Field required"}]}',
        )

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/pro/run",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "payload": {
                "birth_date_local": "1990-05-12",
                "latitude": 53.9006,
                "longitude": 27.5590,
                "timezone_name": "Europe/Moscow",
                "asc_windows": [],
                "events": [{}],
            },
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "events", 0, "event_id"]
