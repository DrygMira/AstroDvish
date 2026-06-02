from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


def test_web_ui_rectification_intervals_proxy_forwards_timezone_fields(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        captured["base_url"] = base_url
        captured["path"] = path
        captured["payload"] = payload
        captured["timeout"] = timeout
        return _DummyResponse(
            200,
            {
                "mode": "asc_sign_intervals",
                "version": "1.0",
                "generated_at_utc": "2026-06-02T00:00:00Z",
                "birth_context": {
                    "birth_date_local": "2000-04-16",
                    "latitude": 53.9,
                    "longitude": 27.56667,
                    "timezone": "GMT+05:00",
                    "timezone_source": "manual_offset",
                    "timezone_mode": "manual",
                    "timezone_offset": "+05:00",
                    "house_system": "P",
                    "zodiac_mode": "tropical",
                    "sidereal_mode": None,
                },
                "day_window": {"start_local": "2000-04-16T00:00:00", "end_local": "2000-04-17T00:00:00"},
                "day_window_utc": {"start_utc": "2000-04-15T19:00:00Z", "end_utc": "2000-04-16T19:00:00Z"},
                "shared_day_summary": {
                    "sun_sign": "Aries",
                    "moon_sign_start": "Leo",
                    "moon_sign_end": "Leo",
                    "moon_changes_sign_today": False,
                    "mercury_sign": "Aries",
                    "venus_sign": "Taurus",
                    "mars_sign": "Gemini",
                    "jupiter_sign": "Cancer",
                    "saturn_sign": "Leo",
                },
                "asc_sign_intervals": [],
            },
        )

    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/asc-sign-intervals",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "birth_date_local": "2000-04-16",
            "latitude": 53.9,
            "longitude": 27.56667,
            "timezone_mode": "manual",
            "timezone_offset": "+05:00",
            "timezone_name": None,
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
        },
    )

    assert response.status_code == 200
    assert captured["path"] == "/api/v1/rectification/asc-sign-intervals"
    assert captured["payload"]["timezone_mode"] == "manual"
    assert captured["payload"]["timezone_offset"] == "+05:00"
    assert captured["payload"]["timezone_name"] is None


def test_web_ui_rectification_dialog_start_forwards_timezone_fields(monkeypatch) -> None:
    captured: dict = {}

    def fake_fetch_document(payload):
        captured["payload"] = payload
        return {
            "birth_context": {
                "birth_date_local": "2000-04-16",
                "latitude": 53.9,
                "longitude": 27.56667,
                "timezone": "Europe/Moscow",
                "timezone_source": "provided_timezone_name",
                "timezone_mode": "auto",
                "timezone_offset": "+03:00",
                "house_system": "P",
                "zodiac_mode": "tropical",
                "sidereal_mode": None,
            },
            "asc_sign_intervals": [],
        }

    monkeypatch.setattr(web_ui_main, "_fetch_rectification_document", fake_fetch_document)
    monkeypatch.setattr(
        web_ui_main,
        "_run_stage1_guarded",
        lambda **kwargs: {
            "llm_json": {
                "type": "final_result",
                "step_index": 1,
                "primary_candidate": {"sign_name_en": "Scorpio", "sign_name_ru": "Скорпион", "probability": 0.8},
                "secondary_candidates": [],
                "summary_text": "ok",
                "explanation_text": "ok",
            },
            "llm_text": "ok",
            "usage": {},
            "openai_raw_response": {},
            "warnings": [],
        },
    )

    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/dialog/start",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "birth_date_local": "2000-04-16",
            "latitude": 53.9,
            "longitude": 27.56667,
            "timezone_mode": "auto",
            "timezone_offset": "",
            "timezone_name": "Europe/Moscow",
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
            "prompt_text": "test",
            "user_profile_note": None,
        },
    )

    assert response.status_code == 200
    assert captured["payload"].timezone_mode == "auto"
    assert captured["payload"].timezone_name == "Europe/Moscow"
    assert captured["payload"].timezone_offset == ""


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


def test_web_ui_events_start_proxy_uses_internal_default_when_api_base_blank(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        captured["base_url"] = base_url
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

    monkeypatch.setattr(web_ui_main, "WEB_UI_INTERNAL_API_BASE_URL", "http://astrodvish-api:8013")
    monkeypatch.setattr(web_ui_main, "_post_to_api_with_fallback", fake_post)
    client = TestClient(web_ui_main.app)
    response = client.post(
        "/api/rectification/events/start",
        json={"api_base_url": "", "dialog_history": []},
    )

    assert response.status_code == 200
    assert captured["base_url"] == "http://astrodvish-api:8013"


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
                "repeat_count": 2,
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
    assert captured["payload"]["last_answer"]["repeat_count"] == 2
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
    assert captured["timeout"] == web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS


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


def test_web_ui_rectification_pro_proxy_returns_controlled_504_on_timeout(monkeypatch) -> None:
    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        raise httpx.ReadTimeout("timed out")

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
                "events": [],
            },
        },
    )

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["reason"] == "upstream_timeout"
    assert detail["timeout_seconds"] == web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS
    assert "Pro-" in detail["user_message"]


def test_web_ui_rectification_pro_proxy_humanizes_non_json_upstream_504(monkeypatch) -> None:
    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        return _DummyResponse(504, {}, text="<html><title>504 Gateway Time-out</title></html>")

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
                "events": [],
            },
        },
    )

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["reason"] == "upstream_timeout"
    assert "V1" in detail["user_message"]
    assert detail["technical_message"] == "upstream_status=504"


def test_post_to_api_with_fallback_does_not_retry_on_timeout(monkeypatch) -> None:
    calls: list[str] = []

    def fake_post(url: str, json: dict, timeout: int):
        calls.append(url)
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    try:
        web_ui_main._post_to_api_with_fallback(
            base_url="http://127.0.0.1:8013",
            path="/api/v1/rectification/pro/run",
            payload={"ok": True},
            timeout=120,
        )
    except httpx.ReadTimeout:
        pass
    else:
        raise AssertionError("expected timeout to be re-raised")

    assert calls == ["http://127.0.0.1:8013/api/v1/rectification/pro/run"]


def test_post_to_api_with_fallback_retries_on_connect_error(monkeypatch) -> None:
    calls: list[str] = []

    def fake_post(url: str, json: dict, timeout: int):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectError("connect failed")
        return _DummyResponse(200, {"ok": True})

    monkeypatch.setattr(web_ui_main, "DOCKER_COMPOSE_API_FALLBACK_ENABLED", True)
    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)
    response = web_ui_main._post_to_api_with_fallback(
        base_url="http://127.0.0.1:8013",
        path="/api/v1/rectification/pro/run",
        payload={"ok": True},
        timeout=120,
    )

    assert response.status_code == 200
    assert calls == [
        "http://127.0.0.1:8013/api/v1/rectification/pro/run",
        f"{web_ui_main.DOCKER_COMPOSE_API_BASE_URL.rstrip('/')}/api/v1/rectification/pro/run",
    ]


def test_post_to_api_with_fallback_does_not_retry_on_connect_error_when_disabled(monkeypatch) -> None:
    calls: list[str] = []

    def fake_post(url: str, json: dict, timeout: int):
        calls.append(url)
        raise httpx.ConnectError("connect failed")

    monkeypatch.setattr(web_ui_main, "DOCKER_COMPOSE_API_FALLBACK_ENABLED", False)
    monkeypatch.setattr(web_ui_main.httpx, "post", fake_post)

    try:
        web_ui_main._post_to_api_with_fallback(
            base_url="http://127.0.0.1:8013",
            path="/api/v1/rectification/pro/run",
            payload={"ok": True},
            timeout=120,
        )
    except httpx.ConnectError:
        pass
    else:
        raise AssertionError("expected connect error to be re-raised")

    assert calls == ["http://127.0.0.1:8013/api/v1/rectification/pro/run"]


def test_web_ui_rectification_pro_proxy_returns_controlled_502_on_dns_error(monkeypatch) -> None:
    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution")

    monkeypatch.setattr(web_ui_main, "DOCKER_COMPOSE_API_FALLBACK_ENABLED", False)
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
                "events": [],
            },
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["reason"] == "upstream_unavailable"
    assert detail["fallback_enabled"] is False
    assert detail["upstream_host"] == "127.0.0.1"
    assert "временно недоступен" in detail["user_message"]


def test_web_ui_rectification_pro_proxy_accepts_repeated_eventcards(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(*, base_url: str, path: str, payload: dict, timeout: int):
        captured["payload"] = payload
        return _DummyResponse(
            200,
            {
                "mode": "rectification_pro",
                "version": "0.1",
                "status": "completed",
                "candidate_windows": [],
                "best_candidates": [],
                "method_results": {"directions": [], "solars": [], "lunars": [], "transits": [], "totems": []},
                "confidence": {"level": "low", "time_window_minutes": 60, "explanation": "ok"},
                "warnings": [],
                "limitations": [],
            },
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
                "events": [
                    {
                        "event_id": "ev-1",
                        "event_type": "child_birth",
                        "title": "Рождение ребёнка №1",
                        "date_text": "2010-01-10",
                        "date_precision": "exact",
                        "start_date": "2010-01-10",
                        "end_date": "2010-01-10",
                        "impact_level": 5,
                        "reversibility": "irreversible",
                        "life_area": "family",
                        "sequence_number": 1,
                        "notes": "",
                        "user_skipped": False,
                    },
                    {
                        "event_id": "ev-2",
                        "event_type": "child_birth",
                        "title": "Рождение ребёнка №2",
                        "date_text": "2013-05-21",
                        "date_precision": "exact",
                        "start_date": "2013-05-21",
                        "end_date": "2013-05-21",
                        "impact_level": 5,
                        "reversibility": "irreversible",
                        "life_area": "family",
                        "sequence_number": 2,
                        "notes": "",
                        "user_skipped": False,
                    },
                ],
                "settings": {
                    "candidate_step_minutes": 5,
                    "include_directions": True,
                    "include_solars": True,
                    "include_lunars": False,
                    "include_transits": True,
                    "include_totems": False,
                },
            },
        },
    )
    assert response.status_code == 200
    assert captured["payload"]["events"][0]["sequence_number"] == 1
    assert captured["payload"]["events"][1]["sequence_number"] == 2
