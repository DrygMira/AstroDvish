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
                    "question_id": "ev_children_birth_01",
                    "event_type": "children_birth",
                    "question_text": "test",
                    "options": [{"id": "yes", "text": "Да"}],
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
                        "event_type": "children_birth",
                        "title": "major event",
                        "date_text": "2018",
                        "date_precision": "year",
                        "start_date": "2018-01-01",
                        "end_date": "2018-12-31",
                        "impact_level": 4,
                        "reversibility": "irreversible",
                        "life_area": "relationships",
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
                "question_id": "ev_children_birth_01",
                "event_type": "children_birth",
                "title": "major event",
                "date_text": "2018",
                "impact_level": 4,
                "reversibility": None,
                "life_area": None,
                "notes": "note",
                "user_skipped": False,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "finalized"
    assert captured["path"] == "/api/v1/rectification/events/continue"
    assert captured["payload"]["last_answer"]["question_id"] == "ev_children_birth_01"
    assert captured["timeout"] == 120


def test_web_ui_events_finalize_proxy_non_200_to_502(monkeypatch) -> None:
    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        return _DummyResponse(422, {"error": "bad request"}, text='{"error":"bad request"}')

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)

    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/events/finalize",
        json={"api_base_url": "http://127.0.0.1:8013", "dialog_history": []},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["message"] == "Rectification events API returned non-200 status"
    assert detail["path"] == "/api/v1/rectification/events/finalize"

