from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import web_ui.main as web_main


SAMPLE_RECTIFICATION_DOCUMENT: dict[str, Any] = {
    "mode": "asc_sign_intervals",
    "version": "1.0",
    "day_window": {
        "start_local": "1978-03-19T00:00:00",
        "end_local": "1978-03-19T23:59:59",
    },
    "asc_sign_intervals": [
        {
            "interval_index": 1,
            "sign_name_ru": "Скорпион",
            "sign_name_en": "Scorpio",
            "start_local": "1978-03-19T00:00:00",
            "end_local": "1978-03-19T00:41:14",
            "duration_minutes": 41,
        },
        {
            "interval_index": 2,
            "sign_name_ru": "Стрелец",
            "sign_name_en": "Sagittarius",
            "start_local": "1978-03-19T00:41:14",
            "end_local": "1978-03-19T02:16:20",
            "duration_minutes": 95,
        },
        {
            "interval_index": 3,
            "sign_name_ru": "Весы",
            "sign_name_en": "Libra",
            "start_local": "1978-03-19T20:20:00",
            "end_local": "1978-03-19T22:05:00",
            "duration_minutes": 105,
        },
        {
            "interval_index": 4,
            "sign_name_ru": "Скорпион",
            "sign_name_en": "Scorpio",
            "start_local": "1978-03-19T22:05:00",
            "end_local": "1978-03-19T23:59:59",
            "duration_minutes": 114,
        },
    ],
}


def _start_payload() -> dict[str, Any]:
    return {
        "api_base_url": "http://127.0.0.1:8013",
        "birth_date_local": "1978-03-19",
        "latitude": 40.23417,
        "longitude": 69.69481,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
        "prompt_text": "stage1 prompt",
        "user_profile_note": None,
    }


def _continue_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt_text": "stage1 prompt",
        "rectification_document": SAMPLE_RECTIFICATION_DOCUMENT,
        "dialog_history": [],
        "step_count": 0,
        "mode": "next_question",
        "user_profile_note": None,
        "user_response": None,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(web_main, "_fetch_rectification_document", lambda payload: SAMPLE_RECTIFICATION_DOCUMENT)
    with TestClient(web_main.app) as test_client:
        yield test_client


def test_stage1_question_bank_contains_body_and_behavior_blocks() -> None:
    texts = " ".join(item["question_text"].lower() for item in web_main.QUESTION_BANK)
    assert "телосложения" in texts
    assert "первое впечатление" in texts
    assert "стиль одежды" in texts
    assert "стресс" in texts
    assert "стиль жизни" in texts
    assert "двигаетесь" in texts


def test_element_scoring_water_and_fire() -> None:
    dialog_history = [
        {"role": "assistant", "type": "ask_question", "question_id": "q_body_type_01"},
        {"role": "user", "selected_option_id": "D", "selected_option_text": "water", "free_text": None},
        {"role": "assistant", "type": "ask_question", "question_id": "q_first_impression_02"},
        {"role": "user", "selected_option_id": "A", "selected_option_text": "fire", "free_text": None},
    ]
    element_scores, sign_scores = web_main._calculate_element_and_sign_scores(dialog_history)
    assert element_scores["water"] > 0
    assert element_scores["fire"] > 0
    assert sign_scores["Scorpio"] > 0
    assert sign_scores["Aries"] > 0


def test_valid_ask_question_from_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "ask_question",
                "step_index": 1,
                "should_continue": True,
                "debug_probability_text": "test",
                "question_id": "q_body_type_01",
                "question_text": "Какой тип телосложения вам ближе?",
                "options": [{"id": "A", "text": "атлетичное"}],
                "allow_free_text": True,
            },
            "llm_text": "{}",
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30, "cached_input_tokens": 0, "reasoning_tokens": 0},
            "openai_raw_response": {"ok": True},
        },
    )

    response = client.post("/api/rectification/dialog/start", json=_start_payload())
    assert response.status_code == 200
    body = response.json()

    assert body["llm_json"]["type"] == "ask_question"
    assert body["llm_json"]["allow_free_text"] is False
    assert body["warnings"] == []
    assert body["step_count"] == 1


def test_bad_json_from_llm_falls_back_to_safe_question(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_http_error(**kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status_code=502, detail={"message": "LLM output is not valid JSON"})

    monkeypatch.setattr(web_main, "_call_rectification_llm", _raise_http_error)

    response = client.post("/api/rectification/dialog/start", json=_start_payload())
    assert response.status_code == 200
    body = response.json()

    assert body["llm_json"]["type"] == "ask_question"
    assert body["llm_json"]["options"]
    assert "Промежуточная оценка:" in body["llm_json"]["debug_probability_text"]
    assert body["llm_json"]["question_text"] == web_main.QUESTION_BANK[0]["question_text"]
    assert body["llm_json"]["options"] == web_main.QUESTION_BANK[0]["options"]
    assert "llm_request_failed" in body["warnings"]


def test_ask_question_without_options_uses_fallback(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "ask_question",
                "step_index": 1,
                "should_continue": True,
                "debug_probability_text": "test",
                "question_id": "q_body_type_01",
                "question_text": "Bad question",
                "options": [],
                "allow_free_text": False,
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )

    response = client.post("/api/rectification/dialog/start", json=_start_payload())
    assert response.status_code == 200
    body = response.json()

    assert body["llm_json"]["type"] == "ask_question"
    assert body["llm_json"]["options"]
    assert "Промежуточная оценка:" in body["llm_json"]["debug_probability_text"]
    assert "llm_json_failed_guard" in body["warnings"]


def test_final_result_without_primary_candidate_falls_back(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "final_result",
                "should_continue": False,
                "secondary_candidates": [],
                "summary_text": "incomplete",
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )

    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(
            dialog_history=_earth_dialog_history(web_main.RECT_MIN_STEPS),
            step_count=web_main.RECT_MIN_STEPS,
            mode="finalize_now",
        ),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["llm_json"]["type"] == "final_result"
    assert body["llm_json"]["primary_candidate"]["sign_name_en"]
    assert len(body["llm_json"]["primary_candidate"]["time_ranges_local"]) >= 1
    assert "использован" in body["llm_json"]["summary_text"]
    assert "llm_json_failed_guard" in body["warnings"]


def test_probability_out_of_range_falls_back(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "final_result",
                "should_continue": False,
                "primary_candidate": {
                    "sign_name_ru": "Скорпион",
                    "sign_name_en": "Scorpio",
                    "time_range_local": {"start": "1978-03-19T00:00:00", "end": "1978-03-19T00:41:14"},
                    "probability": 2.0,
                },
                "secondary_candidates": [],
                "summary_text": "invalid probability",
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )

    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(
            dialog_history=_earth_dialog_history(web_main.RECT_MIN_STEPS),
            step_count=web_main.RECT_MIN_STEPS,
            mode="finalize_now",
        ),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["llm_json"]["type"] == "final_result"
    assert body["llm_json"]["primary_candidate"]["probability"] <= 1
    assert "использован" in body["llm_json"]["summary_text"]
    assert "llm_json_failed_guard" in body["warnings"]


def test_max_steps_leads_to_safe_finalization_without_llm_call(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def _call_llm(**kwargs: Any) -> dict[str, Any]:
        called["value"] = True
        return {
            "llm_json": {
                "type": "ask_question",
                "step_index": 11,
                "should_continue": True,
                "debug_probability_text": "test",
                "question_id": "q_body_type_01",
                "question_text": "Q",
                "options": [{"id": "A", "text": "атлетичное"}],
                "allow_free_text": False,
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        }

    monkeypatch.setattr(web_main, "_call_rectification_llm", _call_llm)

    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(step_count=web_main.RECT_MAX_STEPS, mode="next_question"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_json"]["type"] == "final_result"
    assert "max_steps_reached_safe_finalization" in body["warnings"]
    assert called["value"] is False


def test_repeated_question_id_uses_fallback_question(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "ask_question",
                "step_index": 2,
                "should_continue": True,
                "debug_probability_text": "test",
                "question_id": "q_body_type_01",
                "question_text": "Repeated",
                "options": [{"id": "A", "text": "атлетичное"}],
                "allow_free_text": False,
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )

    dialog_history = [
        {
            "role": "assistant",
            "type": "ask_question",
            "question_id": "q_body_type_01",
            "question_text": "Какой тип телосложения вам ближе?",
            "options": [{"id": "A", "text": "атлетичное"}],
        },
        {"role": "user", "selected_option_id": "A", "selected_option_text": "атлетичное", "free_text": None},
    ]

    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(dialog_history=dialog_history, step_count=1, mode="next_question"),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["llm_json"]["type"] == "ask_question"
    assert body["llm_json"]["question_id"] != "q_body_type_01"
    assert "Промежуточная оценка:" in body["llm_json"]["debug_probability_text"]
    assert "llm_json_failed_guard" in body["warnings"]


def test_stage1_final_result_contains_duplicate_sign_intervals(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "final_result",
                "should_continue": False,
                "primary_candidate": {
                    "sign_name_ru": "Скорпион",
                    "sign_name_en": "Scorpio",
                    "time_range_local": {"start": "1978-03-19T00:00:00", "end": "1978-03-19T00:41:14"},
                    "probability": 0.34,
                },
                "secondary_candidates": [],
                "summary_text": "ok",
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )

    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(
            dialog_history=_earth_dialog_history(web_main.RECT_MIN_STEPS),
            step_count=web_main.RECT_MIN_STEPS,
            mode="finalize_now",
        ),
    )
    assert response.status_code == 200
    body = response.json()
    ranges = body["llm_json"]["primary_candidate"]["time_ranges_local"]
    assert len(ranges) == 2
    assert ranges[0]["start"] == "1978-03-19T00:00:00"
    assert ranges[1]["start"] == "1978-03-19T22:05:00"


def test_stage1_user_visible_text_is_russian_in_safe_paths(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_http_error(**kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status_code=502, detail={"message": "LLM output is not valid JSON"})

    monkeypatch.setattr(web_main, "_call_rectification_llm", _raise_http_error)
    response = client.post("/api/rectification/dialog/start", json=_start_payload())
    assert response.status_code == 200
    body = response.json()
    assert "How are you usually perceived at first contact?" not in body["llm_json"]["question_text"]

    response_finalize = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(step_count=web_main.RECT_MAX_STEPS, mode="next_question"),
    )
    assert response_finalize.status_code == 200
    finalize_body = response_finalize.json()
    assert "Stage 1 preliminary result returned in deterministic safe mode" not in finalize_body["llm_json"]["summary_text"]


def test_stage1_rejects_stage2_event_question_and_uses_bank_fallback(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "ask_question",
                "step_index": 1,
                "should_continue": True,
                "debug_probability_text": "test",
                "question_id": "q_stage2_event_01",
                "question_text": "Назовите дату важного жизненного события",
                "options": [{"id": "A", "text": "2008"}],
                "allow_free_text": False,
            },
            "llm_text": "{}",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )
    response = client.post("/api/rectification/dialog/start", json=_start_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["llm_json"]["type"] == "ask_question"
    assert body["llm_json"]["question_id"] == web_main.QUESTION_BANK[0]["question_id"]
    assert body["llm_json"]["question_text"] == web_main.QUESTION_BANK[0]["question_text"]
    assert "llm_json_failed_guard" in body["warnings"]


def test_web_ui_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "astrodvish-web-ui"}


def test_generate_keeps_calculation_and_interpretation_separate(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "input": {"datetime_utc": "1984-11-13T11:35:00Z", "latitude": 53.9, "longitude": 27.55, "house_system": "P", "zodiac_mode": "tropical", "sidereal_mode": None},
                "normalized": {"julian_day_ut": 2446017.9},
                "objects": {"sun": {"longitude_deg": 231.0}},
                "houses": {"system": "P", "cusps": {"1": 145.0}},
                "angles": {"asc": 145.0, "mc": 58.0},
                "meta": {"ephemeris_source": "swisseph", "zodiac_mode": "tropical", "sidereal_mode": None, "object_constants": {"sun": 0}},
            }

    monkeypatch.setattr(web_main, "_post_to_api_with_fallback", lambda **kwargs: _FakeResponse())
    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", lambda prompt_text, chart, core_identity: "INTERPRETATION")

    response = client.post(
        "/api/generate",
        json={
            "api_base_url": "http://127.0.0.1:8013",
            "datetime_local": "1984-11-13T14:35:00",
            "timezone_offset": "+03:00",
            "latitude": 53.9,
            "longitude": 27.55,
            "house_system": "P",
            "zodiac_mode": "tropical",
            "sidereal_mode": None,
            "prompt_text": "prompt",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["horoscope_text"] == "INTERPRETATION"
    assert isinstance(body["chart_response"], dict)
    assert "horoscope_text" not in body["chart_response"]


def test_calculation_endpoint_is_computation_only(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_if_called(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("LLM layer must not be used by pure calculation endpoint")

    monkeypatch.setattr(web_main, "_render_horoscope_via_openai", _raise_if_called)

    payload = {
        "birth_date_local": "2000-04-16",
        "latitude": 53.9,
        "longitude": 27.56667,
        "house_system": "P",
        "zodiac_mode": "tropical",
        "sidereal_mode": None,
        "api_base_url": "http://127.0.0.1:8013",
    }
    response = client.post("/api/rectification/asc-sign-intervals", json=payload)

    assert response.status_code == 200
    assert response.json()["mode"] == "asc_sign_intervals"


def _earth_dialog_history(question_count: int) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in web_main.QUESTION_BANK[:question_count]:
        history.append(
            {
                "role": "assistant",
                "type": "ask_question",
                "question_id": item["question_id"],
                "question_text": item["question_text"],
                "options": item["options"],
            }
        )
        history.append(
            {
                "role": "user",
                "selected_option_id": "B",
                "selected_option_text": "earth",
                "free_text": None,
            }
        )
    return history


def test_safe_final_uses_user_scores_not_interval_duration() -> None:
    rectification_document = {
        "mode": "asc_sign_intervals",
        "version": "1.0",
        "day_window": {
            "start_local": "1978-03-19T00:00:00",
            "end_local": "1978-03-19T23:59:59",
        },
        "asc_sign_intervals": [
            {
                "interval_index": 1,
                "sign_name_ru": "Лев",
                "sign_name_en": "Leo",
                "start_local": "1978-03-19T00:00:00",
                "end_local": "1978-03-19T04:00:00",
                "duration_minutes": 240,
            },
            {
                "interval_index": 2,
                "sign_name_ru": "Телец",
                "sign_name_en": "Taurus",
                "start_local": "1978-03-19T04:00:00",
                "end_local": "1978-03-19T06:00:00",
                "duration_minutes": 120,
            },
            {
                "interval_index": 3,
                "sign_name_ru": "Дева",
                "sign_name_en": "Virgo",
                "start_local": "1978-03-19T06:00:00",
                "end_local": "1978-03-19T08:00:00",
                "duration_minutes": 120,
            },
            {
                "interval_index": 4,
                "sign_name_ru": "Козерог",
                "sign_name_en": "Capricorn",
                "start_local": "1978-03-19T08:00:00",
                "end_local": "1978-03-19T10:00:00",
                "duration_minutes": 120,
            },
        ],
    }

    safe_result = web_main._build_safe_final_result(
        rectification_document=rectification_document,
        dialog_history=_earth_dialog_history(6),
        reason="llm_request_failed",
    )

    assert safe_result["type"] == "final_result"
    assert safe_result["primary_candidate"]["sign_name_en"] != "Leo"
    assert safe_result["primary_candidate"]["sign_name_en"] in {"Taurus", "Virgo", "Capricorn"}
    assert safe_result["candidate_group"]["signs"] == ["Taurus", "Virgo", "Capricorn"]
    assert safe_result["needs_more_questions"] is True


def test_stage1_equal_earth_scores_produce_candidate_group() -> None:
    rectification_document = {
        "mode": "asc_sign_intervals",
        "version": "1.0",
        "day_window": {
            "start_local": "1978-03-19T00:00:00",
            "end_local": "1978-03-19T23:59:59",
        },
        "asc_sign_intervals": [
            {
                "interval_index": 1,
                "sign_name_ru": "Телец",
                "sign_name_en": "Taurus",
                "start_local": "1978-03-19T04:00:00",
                "end_local": "1978-03-19T06:00:00",
                "duration_minutes": 120,
            },
            {
                "interval_index": 2,
                "sign_name_ru": "Дева",
                "sign_name_en": "Virgo",
                "start_local": "1978-03-19T06:00:00",
                "end_local": "1978-03-19T08:00:00",
                "duration_minutes": 120,
            },
            {
                "interval_index": 3,
                "sign_name_ru": "Козерог",
                "sign_name_en": "Capricorn",
                "start_local": "1978-03-19T08:00:00",
                "end_local": "1978-03-19T10:00:00",
                "duration_minutes": 120,
            },
        ],
    }

    safe_result = web_main._build_safe_final_result(
        rectification_document=rectification_document,
        dialog_history=_earth_dialog_history(6),
        reason="llm_request_failed",
    )

    assert safe_result["candidate_group"]["element"] == "earth"
    assert safe_result["candidate_group"]["reason"] == "equal_sign_scores"
    assert "Для выбора точного знака нужны дополнительные вопросы." in safe_result["summary_text"]


def test_stage1_llm_failure_before_min_questions_returns_next_question(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_http_error(**kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status_code=502, detail={"message": "LLM output is not valid JSON"})

    monkeypatch.setattr(web_main, "_call_rectification_llm", _raise_http_error)
    dialog_history = _earth_dialog_history(3)

    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(dialog_history=dialog_history, step_count=3, mode="finalize_now"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_json"]["type"] == "ask_question"
    assert "min_questions_not_reached" in body["warnings"]
