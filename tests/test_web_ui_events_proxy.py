from __future__ import annotations

import io
import httpx
import time
import zipfile
from fastapi import HTTPException
from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


class _DummyResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


def _build_multi_card_payload(events: list[dict[str, object]], card_ids: list[str]) -> dict[str, object]:
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
            }
        ],
        "events": events,
        "settings": {
            "formula_card_ids": card_ids,
        },
    }


def _build_event(event_id: str, event_type: str, title: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "title": title,
        "date_text": "2015-05-12",
        "date_precision": "exact",
        "start_date": "2015-05-12",
        "end_date": "2015-05-12",
        "impact_level": 5,
        "reversibility": "irreversible",
        "life_area": "family",
        "sequence_number": 1,
        "notes": "",
        "user_skipped": False,
    }


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


def test_web_ui_rectification_pro_async_job_create_and_status(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_job(*, base_url: str, payload: dict[str, object], timeout: int) -> str:
        captured["base_url"] = base_url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return "job-123"

    def fake_get_job(job_id: str) -> dict[str, object] | None:
        if job_id != "job-123":
            return None
        return {
            "job_id": job_id,
            "status": "completed",
            "result": {"mode": "rectification_pro", "status": "completed"},
            "error": None,
        }

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    monkeypatch.setattr(web_ui_main, "_get_rectification_pro_job", fake_get_job)
    client = TestClient(web_ui_main.app)

    create_response = client.post(
        "/api/rectification/pro/run-async",
        json={"api_base_url": "http://127.0.0.1:8013", "payload": {"birth_date_local": "1990-05-12"}},
    )
    assert create_response.status_code == 202
    assert create_response.json()["job_id"] == "job-123"
    assert captured["timeout"] == web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS

    status_response = client.get("/api/rectification/pro/jobs/job-123")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["result"]["mode"] == "rectification_pro"


def test_web_ui_rectification_pro_async_accepts_heavy_multi_card_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_job(*, base_url: str, payload: dict[str, object], timeout: int) -> str:
        captured["base_url"] = base_url
        captured["payload"] = payload
        captured["timeout"] = timeout
        return "heavy-job-123"

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    client = TestClient(web_ui_main.app)

    response = client.post(
        "/api/rectification/pro/run-async",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "payload": {
                "birth_date_local": "1990-05-12",
                "latitude": 53.9006,
                "longitude": 27.5590,
                "timezone_name": "Europe/Moscow",
                "asc_windows": [
                    {
                        "start_local": "1990-05-12T14:00:00",
                        "end_local": "1990-05-12T14:20:00",
                        "sign_name_en": "Libra",
                    }
                ],
                "events": [
                    {
                        "event_id": f"ev{idx+1}",
                        "event_type": "child_birth",
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
                    for idx in range(5)
                ],
                "settings": {
                    "formula_card_ids": [
                        "RECT_CHILD_BIRTH_002_DRAFT",
                        "RECT_MARRIAGE_UNION_002_DRAFT",
                        "RECT_PROFESSION_CHANGE_002_DRAFT",
                    ]
                },
            },
        },
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == "heavy-job-123"
    assert captured["timeout"] == web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS
    assert len(captured["payload"]["events"]) == 5
    assert len(captured["payload"]["settings"]["formula_card_ids"]) == 3


def test_web_ui_rectification_pro_builds_chunked_plan_for_relevant_eight_card_payload() -> None:
    payload = _build_multi_card_payload(
        [
            _build_event("ev1", "child_birth", "Child birth"),
            _build_event("ev2", "marriage_start", "Marriage"),
            _build_event("ev3", "profession_change", "Profession"),
            _build_event("ev4", "divorce_separation", "Divorce"),
            _build_event("ev5", "death_father", "Father death"),
            _build_event("ev6", "death_mother", "Mother death"),
            _build_event("ev7", "death_sibling", "Sibling death"),
            _build_event("ev8", "death_grandparent", "Grandparent death"),
        ],
        [
            "RECT_CHILD_BIRTH_002_DRAFT",
            "RECT_MARRIAGE_UNION_002_DRAFT",
            "RECT_PROFESSION_CHANGE_002_DRAFT",
            "RECT_DIVORCE_SEPARATION_002_DRAFT",
            "RECT_FATHER_DEATH_002_DRAFT",
            "RECT_MOTHER_DEATH_002_DRAFT",
            "RECT_SIBLING_DEATH_002_DRAFT",
            "RECT_GRANDPARENT_DEATH_002_DRAFT",
        ],
    )

    plan = web_ui_main._build_rectification_pro_chunk_plan(payload)

    assert plan is not None
    assert plan["mode"] == "chunked_async_multi_card"
    assert plan["total_chunks"] == 8
    assert [chunk["card_id"] for chunk in plan["chunks"]] == [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
        "RECT_DIVORCE_SEPARATION_002_DRAFT",
        "RECT_FATHER_DEATH_002_DRAFT",
        "RECT_MOTHER_DEATH_002_DRAFT",
        "RECT_SIBLING_DEATH_002_DRAFT",
        "RECT_GRANDPARENT_DEATH_002_DRAFT",
    ]
    assert all(len(chunk["payload"]["events"]) == 1 for chunk in plan["chunks"])
    assert all(len(chunk["payload"]["settings"]["formula_card_ids"]) == 0 for chunk in plan["chunks"])
    assert [chunk["payload"]["settings"]["formula_card_id"] for chunk in plan["chunks"]] == [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
        "RECT_PROFESSION_CHANGE_002_DRAFT",
        "RECT_DIVORCE_SEPARATION_002_DRAFT",
        "RECT_FATHER_DEATH_002_DRAFT",
        "RECT_MOTHER_DEATH_002_DRAFT",
        "RECT_SIBLING_DEATH_002_DRAFT",
        "RECT_GRANDPARENT_DEATH_002_DRAFT",
    ]


def test_web_ui_rectification_pro_async_routes_relevant_eight_card_payload_to_chunked_job(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_job(
        *,
        base_url: str,
        payload: dict[str, object],
        timeout: int,
        chunk_plan: dict[str, object] | None = None,
    ) -> str:
        captured["base_url"] = base_url
        captured["payload"] = payload
        captured["timeout"] = timeout
        captured["chunk_plan"] = chunk_plan
        return "chunk-job-123"

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    client = TestClient(web_ui_main.app)

    response = client.post(
        "/api/rectification/pro/run-async",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "payload": _build_multi_card_payload(
                [
                    _build_event("ev1", "child_birth", "Child birth"),
                    _build_event("ev2", "marriage_start", "Marriage"),
                    _build_event("ev3", "profession_change", "Profession"),
                    _build_event("ev4", "divorce_separation", "Divorce"),
                    _build_event("ev5", "death_father", "Father death"),
                    _build_event("ev6", "death_mother", "Mother death"),
                    _build_event("ev7", "death_sibling", "Sibling death"),
                    _build_event("ev8", "death_grandparent", "Grandparent death"),
                ],
                [
                    "RECT_CHILD_BIRTH_002_DRAFT",
                    "RECT_MARRIAGE_UNION_002_DRAFT",
                    "RECT_PROFESSION_CHANGE_002_DRAFT",
                    "RECT_DIVORCE_SEPARATION_002_DRAFT",
                    "RECT_FATHER_DEATH_002_DRAFT",
                    "RECT_MOTHER_DEATH_002_DRAFT",
                    "RECT_SIBLING_DEATH_002_DRAFT",
                    "RECT_GRANDPARENT_DEATH_002_DRAFT",
                ],
            ),
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == "chunk-job-123"
    assert body["status"] == "queued"
    assert body["mode"] == "chunked_async_multi_card"
    assert body["total_chunks"] == 8
    assert captured["timeout"] == web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS
    assert captured["chunk_plan"] is not None
    assert captured["chunk_plan"]["planned_chunks"] == 8
    assert [len(chunk["payload"]["events"]) for chunk in captured["chunk_plan"]["chunks"]] == [1, 1, 1, 1, 1, 1, 1, 1]
    detail = {"user_message": "live-СЃРµСЂРІРµСЂР°"}
    assert captured["chunk_plan"]["total_chunks"] == 8


def test_web_ui_rectification_pro_chunk_label_text_covers_new_death_cards() -> None:
    assert web_ui_main._rectification_pro_chunk_label_text("death_sibling") == "смерть брата / сестры"
    assert web_ui_main._rectification_pro_chunk_label_text("death_grandparent") == "смерть бабушки / дедушки"


def test_v2_draft_card_accepted_event_types_derived_from_disk_matches_real_cards() -> None:
    derived = web_ui_main._v2_draft_card_accepted_event_types()
    assert derived == {
        "RECT_CHILD_BIRTH_002_DRAFT": {"child_birth", "children_birth"},
        "RECT_MARRIAGE_UNION_002_DRAFT": {"marriage_start", "marriage_union"},
        "RECT_PROFESSION_CHANGE_002_DRAFT": {"profession_change"},
        "RECT_DIVORCE_SEPARATION_002_DRAFT": {"divorce_separation", "divorce_breakup"},
        "RECT_FATHER_DEATH_002_DRAFT": {"death_father"},
        "RECT_MOTHER_DEATH_002_DRAFT": {"death_mother"},
        "RECT_SIBLING_DEATH_002_DRAFT": {"death_sibling"},
        "RECT_GRANDPARENT_DEATH_002_DRAFT": {"death_grandparent"},
    }


def test_v2_draft_card_accepted_event_types_picks_up_new_card_without_code_changes(tmp_path) -> None:
    """Главный эффект П3: новая draft-карточка = новый JSON-файл, без правок web_ui/main.py."""
    import json

    new_card = {
        "card_id": "RECT_NEW_EVENT_002_DRAFT",
        "event_type": "brand_new_event",
        "status": "draft",
        "core_logic": ["house_1"],
        "aspects": ["x"],
        "method_priority": ["directions"],
        "direction_rules": [],
    }
    (tmp_path / "RECT_NEW_EVENT_002_DRAFT.json").write_text(json.dumps(new_card), encoding="utf-8")

    derived = web_ui_main._v2_draft_card_accepted_event_types(cards_root=tmp_path)
    assert derived == {"RECT_NEW_EVENT_002_DRAFT": {"brand_new_event"}}


def test_v2_draft_card_accepted_event_types_ignores_non_draft_cards(tmp_path) -> None:
    import json

    production_card = {
        "card_id": "RECT_SOMETHING_001",
        "event_type": "something",
        "status": "test",
        "core_logic": ["house_1"],
        "aspects": ["x"],
        "method_priority": ["directions"],
        "direction_rules": [],
    }
    (tmp_path / "RECT_SOMETHING_001.json").write_text(json.dumps(production_card), encoding="utf-8")

    derived = web_ui_main._v2_draft_card_accepted_event_types(cards_root=tmp_path)
    assert derived == {}


def test_web_ui_rectification_pro_builds_subchunks_for_one_event_type_over_four_events() -> None:
    payload = _build_multi_card_payload(
        [_build_event(f"ev{idx+1}", "child_birth", f"Child birth {idx+1}") for idx in range(9)],
        [
            "RECT_CHILD_BIRTH_002_DRAFT",
            "RECT_MARRIAGE_UNION_002_DRAFT",
            "RECT_PROFESSION_CHANGE_002_DRAFT",
            "RECT_DIVORCE_SEPARATION_002_DRAFT",
            "RECT_FATHER_DEATH_002_DRAFT",
            "RECT_MOTHER_DEATH_002_DRAFT",
        ],
    )

    plan = web_ui_main._build_rectification_pro_chunk_plan(payload)

    assert plan is not None
    assert plan["mode"] == "chunked_async_multi_card"
    assert plan["total_chunks"] == 3
    assert plan["planned_chunks"] == 3
    assert plan["chunk_size"] == 3
    assert plan["estimated_weight"] == 54
    assert [len(chunk["payload"]["events"]) for chunk in plan["chunks"]] == [3, 3, 3]
    assert [chunk["subchunk_index"] for chunk in plan["chunks"]] == [1, 2, 3]
    assert all(chunk["subchunk_count"] == 3 for chunk in plan["chunks"])
    assert all(chunk["card_id"] == "RECT_CHILD_BIRTH_002_DRAFT" for chunk in plan["chunks"])


def test_web_ui_rectification_pro_async_accepts_ten_event_multi_card_payload_via_chunked_job(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_job(
        *,
        base_url: str,
        payload: dict[str, object],
        timeout: int,
        chunk_plan: dict[str, object] | None = None,
    ) -> str:
        captured["base_url"] = base_url
        captured["payload"] = payload
        captured["timeout"] = timeout
        captured["chunk_plan"] = chunk_plan
        return "chunk-job-10"

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    client = TestClient(web_ui_main.app)

    response = client.post(
        "/api/rectification/pro/run-async",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "payload": {
                "birth_date_local": "1990-05-12",
                "latitude": 53.9006,
                "longitude": 27.5590,
                "timezone_name": "Europe/Moscow",
                "asc_windows": [
                    {
                        "start_local": "1990-05-12T14:00:00",
                        "end_local": "1990-05-12T14:20:00",
                        "sign_name_en": "Libra",
                    }
                ],
                "events": [
                    {
                        "event_id": f"ev{idx+1}",
                        "event_type": "child_birth",
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
                    for idx in range(10)
                ],
                "settings": {
                    "formula_card_ids": [
                        "RECT_CHILD_BIRTH_002_DRAFT",
                        "RECT_MARRIAGE_UNION_002_DRAFT",
                        "RECT_PROFESSION_CHANGE_002_DRAFT",
                        "RECT_DIVORCE_SEPARATION_002_DRAFT",
                        "RECT_FATHER_DEATH_002_DRAFT",
                        "RECT_MOTHER_DEATH_002_DRAFT",
                    ]
                },
            },
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == "chunk-job-10"
    assert body["status"] == "queued"
    assert body["mode"] == "chunked_async_multi_card"
    assert body["total_chunks"] == 4
    assert captured["chunk_plan"] is not None
    assert body["planned_chunks"] == 4
    assert body["chunk_size"] == 3
    assert captured["chunk_plan"]["planned_chunks"] == 4
    assert captured["chunk_plan"]["chunk_size"] == 3
    assert captured["chunk_plan"]["estimated_weight"] == 60
    assert [len(chunk["payload"]["events"]) for chunk in captured["chunk_plan"]["chunks"]] == [3, 3, 3, 1]


def test_web_ui_rectification_pro_async_accepts_sixteen_event_multi_card_payload_via_subchunks(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_job(
        *,
        base_url: str,
        payload: dict[str, object],
        timeout: int,
        chunk_plan: dict[str, object] | None = None,
    ) -> str:
        captured["base_url"] = base_url
        captured["payload"] = payload
        captured["timeout"] = timeout
        captured["chunk_plan"] = chunk_plan
        return "chunk-job-16"

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    client = TestClient(web_ui_main.app)

    response = client.post(
        "/api/rectification/pro/run-async",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "payload": _build_multi_card_payload(
                [_build_event(f"ev{idx+1}", "child_birth", f"Child birth {idx+1}") for idx in range(16)],
                [
                    "RECT_CHILD_BIRTH_002_DRAFT",
                    "RECT_MARRIAGE_UNION_002_DRAFT",
                    "RECT_PROFESSION_CHANGE_002_DRAFT",
                    "RECT_DIVORCE_SEPARATION_002_DRAFT",
                    "RECT_FATHER_DEATH_002_DRAFT",
                    "RECT_MOTHER_DEATH_002_DRAFT",
                ],
            ),
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == "chunk-job-16"
    assert body["status"] == "queued"
    assert body["mode"] == "chunked_async_multi_card"
    assert body["total_chunks"] == 6
    assert captured["chunk_plan"] is not None
    assert body["planned_chunks"] == 6
    assert body["chunk_size"] == 3
    assert captured["chunk_plan"]["planned_chunks"] == 6
    assert captured["chunk_plan"]["chunk_size"] == 3
    assert captured["chunk_plan"]["estimated_weight"] == 96
    assert [len(chunk["payload"]["events"]) for chunk in captured["chunk_plan"]["chunks"]] == [3, 3, 3, 3, 3, 1]


def test_web_ui_rectification_pro_async_rejects_extreme_multi_card_payload_with_guard_details(monkeypatch) -> None:
    def fake_create_job(
        *,
        base_url: str,
        payload: dict[str, object],
        timeout: int,
        chunk_plan: dict[str, object] | None = None,
    ) -> str:
        raise AssertionError("oversized payload must be rejected before creating a job")

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    client = TestClient(web_ui_main.app)

    response = client.post(
        "/api/rectification/pro/run-async",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "payload": _build_multi_card_payload(
                [_build_event(f"ev{idx+1}", "child_birth", f"Child birth {idx+1}") for idx in range(25)],
                [
                    "RECT_CHILD_BIRTH_002_DRAFT",
                    "RECT_MARRIAGE_UNION_002_DRAFT",
                    "RECT_PROFESSION_CHANGE_002_DRAFT",
                    "RECT_DIVORCE_SEPARATION_002_DRAFT",
                    "RECT_FATHER_DEATH_002_DRAFT",
                    "RECT_MOTHER_DEATH_002_DRAFT",
                ],
            ),
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "payload_too_heavy"
    assert detail["guard_reason"] == "events_limit_exceeded"
    assert detail["events_count"] == 25
    assert detail["selected_cards_count"] == 6
    assert detail["complexity"] == 150
    assert detail["planned_chunks"] == 9
    assert detail["chunk_size"] == 3
    assert detail["candidate_count"] is None
    assert detail["formula_count"] is None
    assert detail["max_chunks"] == web_ui_main.RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS
    assert detail["max_events"] == web_ui_main.RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS
    assert detail["max_events_per_chunk"] == web_ui_main.RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK
    assert detail["estimated_weight"] == 150
    assert detail["guard_stage"] == "pre_job_chunk_plan"
    assert detail["job_id"].startswith("guard-")
    assert detail["current_limit"]["chunked_max_chunks"] == web_ui_main.RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS
    assert "process_cpu_seconds" in detail["runtime_snapshot"]
    assert detail["recommendation"]


def test_web_ui_rectification_pro_async_rejects_when_another_job_is_running(monkeypatch) -> None:
    def fake_create_job(*, base_url: str, payload: dict[str, object], timeout: int) -> str:
        raise AssertionError("second async job must be rejected before creating a new worker")

    now_ts = time.time()
    with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
        web_ui_main._RECTIFICATION_PRO_JOBS["job-active"] = {
            "job_id": "job-active",
            "status": "running",
            "result": None,
            "error": None,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    monkeypatch.setattr(web_ui_main, "_create_rectification_pro_job", fake_create_job)
    client = TestClient(web_ui_main.app)
    try:
        response = client.post(
            "/api/rectification/pro/run-async",
            json={
                "api_base_url": "http://127.0.0.1:8013",
                "payload": {"birth_date_local": "1990-05-12"},
            },
        )
    finally:
        with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
            web_ui_main._RECTIFICATION_PRO_JOBS.clear()

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["reason"] == "job_already_running"
    assert detail["active_job_id"] == "job-active"
    assert "выполняется" in detail["user_message"]


def test_web_ui_rectification_pro_chunked_job_aggregates_results(monkeypatch) -> None:
    payload = _build_multi_card_payload(
        [
            _build_event("ev1", "child_birth", "Child birth"),
            _build_event("ev2", "marriage_start", "Marriage"),
        ],
        [
            "RECT_CHILD_BIRTH_002_DRAFT",
            "RECT_MARRIAGE_UNION_002_DRAFT",
        ],
    )
    chunk_plan = {
        "mode": "chunked_async_multi_card",
        "total_chunks": 2,
        "chunks": [
            {
                "chunk_label": "child_birth",
                "card_id": "RECT_CHILD_BIRTH_002_DRAFT",
                "event_types": ["child_birth"],
                "payload": {
                    **_build_multi_card_payload(
                        [_build_event("ev1", "child_birth", "Child birth")],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_CHILD_BIRTH_002_DRAFT", "formula_card_ids": []},
                },
            },
            {
                "chunk_label": "marriage_union",
                "card_id": "RECT_MARRIAGE_UNION_002_DRAFT",
                "event_types": ["marriage_start"],
                "payload": {
                    **_build_multi_card_payload(
                        [_build_event("ev2", "marriage_start", "Marriage")],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_MARRIAGE_UNION_002_DRAFT", "formula_card_ids": []},
                },
            },
        ],
    }

    def fake_post(*, base_url: str, path: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        card_id = payload["settings"]["formula_card_id"]
        score = 80.0 if card_id == "RECT_CHILD_BIRTH_002_DRAFT" else 70.0
        event_type = payload["events"][0]["event_type"]
        return {
            "formula_refinement_results": {
                "enabled": True,
                "card_id": card_id,
                "card_version": "draft",
                "formulas_count": 10,
                "priority_counts": {"golden": 2, "supporting": 3, "context": 1, "ambiguity_risk": 0},
                "working_time_range": {
                    "start_local": "1990-05-12T14:00:00",
                    "end_local": "1990-05-12T14:10:00",
                    "candidate_count": 3,
                    "best_candidate": "1990-05-12T14:05:00",
                    "golden_matched_count": 2,
                    "score": score,
                },
                "working_time_ranges": [
                    {
                        "start_local": "1990-05-12T14:00:00",
                        "end_local": "1990-05-12T14:10:00",
                        "candidate_count": 3,
                        "best_candidate": "1990-05-12T14:05:00",
                        "golden_matched_count": 2,
                        "score": score,
                    }
                ],
                "best_candidate": {
                    "candidate_time_local": "1990-05-12T14:05:00",
                    "candidate_time_utc": "1990-05-12T11:05:00Z",
                    "score": score,
                    "matched_count": 4,
                    "rejected_count": 1,
                    "missing_count": 1,
                    "golden_matched_count": 2,
                    "golden_orb_sum": 0.4,
                    "supporting_matched_count": 1,
                    "context_matched_count": 1,
                    "context_score": 0.5,
                    "supporting_bonus": 1.2,
                    "event_confirmation_score": 3.0,
                    "time_refinement_score": 2.0,
                    "best_formulas": [f"{card_id}:rule"],
                    "top_rejected_reasons": [{"reason": "orb_too_wide", "count": 1}],
                    "unresolved_source_summary": [{"reason": "unresolved_source:moon", "count": 1}],
                    "event_contribution_audit": [
                        {
                            "event_id": payload["events"][0]["event_id"],
                            "event_type": event_type,
                            "event_title": payload["events"][0]["title"],
                            "event_date": payload["events"][0]["start_date"],
                            "card_id": card_id,
                            "score": score,
                            "matched_count": 4,
                            "rejected_count": 1,
                            "missed_count": 1,
                            "golden_matched_count": 2,
                            "supporting_matched_count": 1,
                            "context_matched_count": 1,
                            "context_score": 0.5,
                            "contribution_to_final_candidate": 100.0,
                        }
                    ],
                    "card_contribution_audit": [
                        {
                            "card_id": card_id,
                            "score": score,
                            "matched_count": 4,
                            "rejected_count": 1,
                            "missed_count": 1,
                            "golden_matched_count": 2,
                            "supporting_matched_count": 1,
                            "context_matched_count": 1,
                            "context_score": 0.5,
                            "contribution_to_final_candidate": 100.0,
                            "top_rejected_reasons": [{"reason": "orb_too_wide", "count": 1}],
                        }
                    ],
                    "event_type_contribution": [
                        {
                            "event_type": event_type,
                            "card_ids": [card_id],
                            "score": score,
                            "matched_count": 4,
                            "rejected_count": 1,
                            "missed_count": 1,
                            "golden_matched_count": 2,
                            "supporting_matched_count": 1,
                            "context_matched_count": 1,
                            "context_score": 0.5,
                            "contribution_to_final_candidate": 100.0,
                        }
                    ],
                    "score_breakdown": {
                        "matched_formula_score": 4.0,
                        "orb_strength_score": 2.0,
                        "participant_bonus_score": 1.0,
                        "golden_formula_score": 3.0,
                        "golden_orb_quality_score": 1.0,
                        "supporting_formula_score": 1.0,
                        "context_formula_score": 0.5,
                        "supporting_bonus": 1.2,
                        "ambiguity_penalty": 0.0,
                        "event_confirmation_score": 3.0,
                        "time_refinement_score": 2.0,
                        "rejected_penalty": 0.5,
                        "missing_penalty": 0.25,
                    },
                    "selection_reason": "best score in chunk",
                    "selected_card_ids": [card_id],
                    "multi_card_enabled": False,
                    "selected_candidate_time": "1990-05-12T14:05:00",
                    "chart_build_time": "1990-05-12T14:05:00",
                    "natal_houses_time": "1990-05-12T14:05:00",
                    "rulers_resolved_time": "1990-05-12T14:05:00",
                    "house_elements_resolved_time": "1990-05-12T14:05:00",
                    "directed_points_time": "1990-05-12T14:05:00",
                    "timezone_used": "Europe/Moscow",
                    "timezone_offset_used": "+03:00",
                },
            },
            "formula_multi_card_report": {},
            "performance_debug": {
                "card_id": card_id,
                "formula_count": 10,
                "event_count": 1,
                "candidate_count": 3,
                "total_runtime_ms": 1200.0,
                "slowest_stage": "formula_refinement_ms",
                "stage_timings_ms": {"formula_refinement_ms": 700.0},
            },
            "confidence": {"level": "high", "time_window_minutes": 10},
            "warnings": [],
            "limitations": [],
        }

    now_ts = time.time()
    with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
        web_ui_main._RECTIFICATION_PRO_JOBS["chunk-job"] = {
            "job_id": "chunk-job",
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    monkeypatch.setattr(web_ui_main, "_post_rectification_events", fake_post)
    try:
        web_ui_main._run_rectification_pro_job(
            job_id="chunk-job",
            base_url="http://127.0.0.1:8013",
            payload=payload,
            timeout=web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS,
            chunk_plan=chunk_plan,
        )
        job = web_ui_main._get_rectification_pro_job("chunk-job")
    finally:
        with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
            web_ui_main._RECTIFICATION_PRO_JOBS.clear()

    assert job is not None
    assert job["status"] == "completed"
    assert job["total_chunks"] == 2
    assert job["completed_chunks"] == 2
    assert job["progress_percent"] == 100
    result = job["result"]
    assert result["formula_multi_card_report"]["enabled"] is True
    assert result["formula_multi_card_report"]["selected_card_ids"] == [
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
    ]
    assert len(result["formula_multi_card_report"]["chunks"]) == 2
    assert {item["card_id"] for item in result["formula_multi_card_report"]["card_contribution_audit"]} == {
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
    }
    assert {item["event_type"] for item in result["formula_multi_card_report"]["event_type_contribution"]} == {
        "child_birth",
        "marriage_start",
    }
    event_metrics = result["formula_multi_card_report"]["event_contribution_audit"][0]
    assert "best_orb" in event_metrics
    assert "avg_orb" in event_metrics
    assert "score_contribution" in event_metrics
    assert "affected_best_candidate" in event_metrics
    assert event_metrics["card_id"] in {
        "RECT_CHILD_BIRTH_002_DRAFT",
        "RECT_MARRIAGE_UNION_002_DRAFT",
    }
    assert set((event_metrics.get("tier_summary") or {}).keys()) == {"golden", "supporting", "context"}
    expert_tables = result["formula_multi_card_report"].get("expert_tables")
    assert expert_tables
    assert {
        "Итог",
        "Кандидаты времени",
        "Совпавшие формулы",
        "Отклонённые формулы",
        "Не найденные формулы",
        "Орбис до 2°",
        "По карточкам",
        "Блоки расчёта",
        "Спорные зоны",
        "Эффективность вопросов",
    }.issubset({item["title"] for item in expert_tables})
    question_efficiency = result["formula_multi_card_report"]["question_efficiency_audit"][0]
    assert question_efficiency["recommendation_code"] in {"keep", "merge", "supplemental_block", "review_weak"}
    assert question_efficiency["action_policy"] == "advisory_only"
    excel_export = result["formula_multi_card_report"]["expert_excel_export"]
    assert excel_export["action_policy"] == "advisory_only"
    assert excel_export["sheets"][0]["sheet_name"] == "Эффективность вопросов"
    assert excel_export["sheets"][0]["rows"]
    assert {
        "Итог",
        "Кандидаты времени",
        "Совпавшие формулы",
        "Отклонённые формулы",
        "Не найденные формулы",
        "Орбис до 2°",
        "По карточкам",
        "Блоки расчёта",
        "Спорные зоны",
        "Эффективность вопросов",
    }.issubset({sheet["sheet_name"] for sheet in excel_export["sheets"]})


def test_web_ui_rectification_pro_export_excel_endpoint_returns_xlsx() -> None:
    payload = {
        "filename": "astrodvish-v2-combined-report.xlsx",
        "sheets": [
            {
                "sheet_name": "Итог",
                "columns": ["ID карточки", "Статус"],
                "rows": [{"ID карточки": "RECT_CHILD_BIRTH_002_DRAFT", "Статус": "готово"}],
            },
            {
                "sheet_name": "Эффективность вопросов",
                "columns": ["Тип события", "Вклад в score"],
                "rows": [{"Тип события": "child_birth", "Вклад в score": 96.4}],
            },
        ],
    }

    with TestClient(web_ui_main.app) as client:
        response = client.post("/api/rectification/pro/export-excel", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment;" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        first_sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Итог" in workbook_xml
    assert "Эффективность вопросов" in workbook_xml
    assert "RECT_CHILD_BIRTH_002_DRAFT" in first_sheet_xml


def test_web_ui_rectification_pro_chunked_job_merges_repeated_card_subchunks(monkeypatch) -> None:
    payload = _build_multi_card_payload(
        [
            _build_event("ev1", "child_birth", "Child birth 1"),
            _build_event("ev2", "child_birth", "Child birth 2"),
            _build_event("ev3", "child_birth", "Child birth 3"),
            _build_event("ev4", "child_birth", "Child birth 4"),
            _build_event("ev5", "marriage_start", "Marriage"),
        ],
        [
            "RECT_CHILD_BIRTH_002_DRAFT",
            "RECT_MARRIAGE_UNION_002_DRAFT",
        ],
    )
    chunk_plan = {
        "mode": "chunked_async_multi_card",
        "selected_card_ids": [
            "RECT_CHILD_BIRTH_002_DRAFT",
            "RECT_MARRIAGE_UNION_002_DRAFT",
        ],
        "total_chunks": 3,
        "planned_chunks": 3,
        "chunks": [
            {
                "chunk_label": "child_birth",
                "card_id": "RECT_CHILD_BIRTH_002_DRAFT",
                "event_types": ["child_birth"],
                "subchunk_index": 1,
                "subchunk_count": 2,
                "payload": {
                    **_build_multi_card_payload(
                        [
                            _build_event("ev1", "child_birth", "Child birth 1"),
                            _build_event("ev2", "child_birth", "Child birth 2"),
                        ],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_CHILD_BIRTH_002_DRAFT", "formula_card_ids": []},
                },
            },
            {
                "chunk_label": "child_birth",
                "card_id": "RECT_CHILD_BIRTH_002_DRAFT",
                "event_types": ["child_birth"],
                "subchunk_index": 2,
                "subchunk_count": 2,
                "payload": {
                    **_build_multi_card_payload(
                        [
                            _build_event("ev3", "child_birth", "Child birth 3"),
                            _build_event("ev4", "child_birth", "Child birth 4"),
                        ],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_CHILD_BIRTH_002_DRAFT", "formula_card_ids": []},
                },
            },
            {
                "chunk_label": "marriage_union",
                "card_id": "RECT_MARRIAGE_UNION_002_DRAFT",
                "event_types": ["marriage_start"],
                "subchunk_index": 1,
                "subchunk_count": 1,
                "payload": {
                    **_build_multi_card_payload(
                        [_build_event("ev5", "marriage_start", "Marriage")],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_MARRIAGE_UNION_002_DRAFT", "formula_card_ids": []},
                },
            },
        ],
    }

    def fake_post(*, base_url: str, path: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        card_id = payload["settings"]["formula_card_id"]
        event_type = payload["events"][0]["event_type"]
        event_count = len(payload["events"])
        score = 40.0 if card_id == "RECT_CHILD_BIRTH_002_DRAFT" else 25.0
        return {
            "formula_refinement_results": {
                "enabled": True,
                "card_id": card_id,
                "card_version": "draft",
                "formulas_count": 10 if card_id == "RECT_CHILD_BIRTH_002_DRAFT" else 8,
                "priority_counts": {"golden": 2, "supporting": 3, "context": 1, "ambiguity_risk": 0},
                "working_time_range": {
                    "start_local": "1990-05-12T14:00:00",
                    "end_local": "1990-05-12T14:10:00",
                    "candidate_count": 3,
                    "best_candidate": "1990-05-12T14:05:00",
                    "golden_matched_count": 2,
                    "score": score,
                },
                "working_time_ranges": [],
                "best_candidate": {
                    "candidate_time_local": "1990-05-12T14:05:00",
                    "score": score,
                    "matched_count": event_count * 2,
                    "rejected_count": event_count,
                    "missing_count": 0,
                    "golden_matched_count": event_count,
                    "golden_orb_sum": 0.4,
                    "supporting_matched_count": event_count,
                    "context_matched_count": 0,
                    "context_score": 0.25,
                    "supporting_bonus": 1.0,
                    "event_confirmation_score": 2.0,
                    "time_refinement_score": 1.5,
                    "best_formulas": [f"{card_id}:rule"],
                    "top_rejected_reasons": [{"reason": "orb_too_wide", "count": event_count}],
                    "unresolved_source_summary": [],
                    "event_contribution_audit": [
                        {
                            "event_id": event["event_id"],
                            "event_type": event["event_type"],
                            "event_title": event["title"],
                            "event_date": event["start_date"],
                            "card_id": card_id,
                            "score": score / event_count,
                            "matched_count": 2,
                            "rejected_count": 1,
                            "missed_count": 0,
                            "golden_matched_count": 1,
                            "supporting_matched_count": 1,
                            "context_matched_count": 0,
                            "context_score": 0.0,
                        }
                        for event in payload["events"]
                    ],
                    "card_contribution_audit": [
                        {
                            "card_id": card_id,
                            "score": score,
                            "matched_count": event_count * 2,
                            "rejected_count": event_count,
                            "missed_count": 0,
                            "golden_matched_count": event_count,
                            "supporting_matched_count": event_count,
                            "context_matched_count": 0,
                            "context_score": 0.25,
                            "top_rejected_reasons": [{"reason": "orb_too_wide", "count": event_count}],
                        }
                    ],
                    "event_type_contribution": [
                        {
                            "event_type": event_type,
                            "card_ids": [card_id],
                            "score": score,
                            "matched_count": event_count * 2,
                            "rejected_count": event_count,
                            "missed_count": 0,
                            "golden_matched_count": event_count,
                            "supporting_matched_count": event_count,
                            "context_matched_count": 0,
                            "context_score": 0.25,
                        }
                    ],
                    "score_breakdown": {
                        "matched_formula_score": score,
                        "orb_strength_score": 2.0,
                        "participant_bonus_score": 1.0,
                        "golden_formula_score": 3.0,
                        "golden_orb_quality_score": 1.0,
                        "supporting_formula_score": 1.0,
                        "context_formula_score": 0.25,
                        "supporting_bonus": 1.0,
                        "ambiguity_penalty": 0.0,
                        "event_confirmation_score": 2.0,
                        "time_refinement_score": 1.5,
                        "rejected_penalty": 0.0,
                        "missing_penalty": 0.0,
                    },
                    "selected_card_ids": [card_id],
                    "timezone_used": "Europe/Moscow",
                    "timezone_offset_used": "+03:00",
                },
            },
            "formula_multi_card_report": {},
            "performance_debug": {
                "card_id": card_id,
                "formula_count": 10 if card_id == "RECT_CHILD_BIRTH_002_DRAFT" else 8,
                "event_count": event_count,
                "candidate_count": 3,
                "total_runtime_ms": 1200.0,
                "slowest_stage": "formula_refinement_ms",
                "stage_timings_ms": {"formula_refinement_ms": 700.0},
            },
            "confidence": {"level": "high", "time_window_minutes": 10},
            "warnings": [],
            "limitations": [],
        }

    now_ts = time.time()
    with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
        web_ui_main._RECTIFICATION_PRO_JOBS["chunk-job-sub"] = {
            "job_id": "chunk-job-sub",
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    monkeypatch.setattr(web_ui_main, "_post_rectification_events", fake_post)
    try:
        web_ui_main._run_rectification_pro_job(
            job_id="chunk-job-sub",
            base_url="http://127.0.0.1:8013",
            payload=payload,
            timeout=web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS,
            chunk_plan=chunk_plan,
        )
        job = web_ui_main._get_rectification_pro_job("chunk-job-sub")
    finally:
        with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
            web_ui_main._RECTIFICATION_PRO_JOBS.clear()

    assert job is not None
    result = job["result"]
    card_audit = result["formula_multi_card_report"]["card_contribution_audit"]
    assert len(card_audit) == 2
    child_card = next(item for item in card_audit if item["card_id"] == "RECT_CHILD_BIRTH_002_DRAFT")
    assert child_card["matched_count"] == 8
    assert child_card["rejected_count"] == 4
    assert result["formula_refinement_results"]["formulas_count"] == 18
    assert len(result["formula_multi_card_report"]["chunks"]) == 3


def test_web_ui_rectification_pro_chunked_job_keeps_partial_results_on_failure(monkeypatch) -> None:
    payload = _build_multi_card_payload(
        [
            _build_event("ev1", "child_birth", "Child birth"),
            _build_event("ev2", "marriage_start", "Marriage"),
        ],
        [
            "RECT_CHILD_BIRTH_002_DRAFT",
            "RECT_MARRIAGE_UNION_002_DRAFT",
        ],
    )
    chunk_plan = {
        "mode": "chunked_async_multi_card",
        "total_chunks": 2,
        "chunks": [
            {
                "chunk_label": "child_birth",
                "card_id": "RECT_CHILD_BIRTH_002_DRAFT",
                "event_types": ["child_birth"],
                "payload": {
                    **_build_multi_card_payload(
                        [_build_event("ev1", "child_birth", "Child birth")],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_CHILD_BIRTH_002_DRAFT", "formula_card_ids": []},
                },
            },
            {
                "chunk_label": "marriage_union",
                "card_id": "RECT_MARRIAGE_UNION_002_DRAFT",
                "event_types": ["marriage_start"],
                "payload": {
                    **_build_multi_card_payload(
                        [_build_event("ev2", "marriage_start", "Marriage")],
                        [],
                    ),
                    "settings": {"formula_card_id": "RECT_MARRIAGE_UNION_002_DRAFT", "formula_card_ids": []},
                },
            },
        ],
    }

    def fake_post(*, base_url: str, path: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        card_id = payload["settings"]["formula_card_id"]
        if card_id == "RECT_MARRIAGE_UNION_002_DRAFT":
            raise HTTPException(
                status_code=504,
                detail={
                    "reason": "upstream_timeout",
                    "user_message": "Расчёт занял слишком много времени. Попробуйте позже.",
                },
            )
        return {
            "formula_refinement_results": {
                "enabled": True,
                "card_id": card_id,
                "card_version": "draft",
                "formulas_count": 10,
                "priority_counts": {"golden": 2, "supporting": 3, "context": 1, "ambiguity_risk": 0},
                "working_time_range": {
                    "start_local": "1990-05-12T14:00:00",
                    "end_local": "1990-05-12T14:10:00",
                    "candidate_count": 3,
                    "best_candidate": "1990-05-12T14:05:00",
                    "golden_matched_count": 2,
                    "score": 80.0,
                },
                "working_time_ranges": [],
                "best_candidate": {
                    "candidate_time_local": "1990-05-12T14:05:00",
                    "score": 80.0,
                    "matched_count": 4,
                    "rejected_count": 1,
                    "missing_count": 1,
                    "golden_matched_count": 2,
                    "supporting_matched_count": 1,
                    "context_matched_count": 1,
                    "context_score": 0.5,
                    "event_contribution_audit": [],
                    "card_contribution_audit": [],
                    "event_type_contribution": [],
                    "score_breakdown": {},
                },
            },
            "formula_multi_card_report": {},
            "performance_debug": {"card_id": card_id, "formula_count": 10, "event_count": 1, "candidate_count": 3},
            "confidence": {"level": "high"},
            "warnings": [],
            "limitations": [],
        }

    now_ts = time.time()
    with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
        web_ui_main._RECTIFICATION_PRO_JOBS["chunk-job"] = {
            "job_id": "chunk-job",
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": now_ts,
            "updated_at": now_ts,
        }

    monkeypatch.setattr(web_ui_main, "_post_rectification_events", fake_post)
    try:
        web_ui_main._run_rectification_pro_job(
            job_id="chunk-job",
            base_url="http://127.0.0.1:8013",
            payload=payload,
            timeout=web_ui_main.RECTIFICATION_PRO_TIMEOUT_SECONDS,
            chunk_plan=chunk_plan,
        )
        job = web_ui_main._get_rectification_pro_job("chunk-job")
    finally:
        with web_ui_main._RECTIFICATION_PRO_JOBS_LOCK:
            web_ui_main._RECTIFICATION_PRO_JOBS.clear()

    assert job is not None
    assert job["status"] == "failed"
    assert job["completed_chunks"] == 1
    assert job["failed_chunks"] == 1
    assert job["current_chunk_label"] == "marriage_union"
    assert len(job["partial_results"]) == 1
    assert job["error"]["detail"]["reason"] == "upstream_timeout"


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
