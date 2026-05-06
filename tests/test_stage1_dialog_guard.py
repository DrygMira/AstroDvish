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
            "sign_name_ru": "Овен",
            "sign_name_en": "Aries",
            "start_local": "1978-03-19T00:00:00",
            "end_local": "1978-03-19T01:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 2,
            "sign_name_ru": "Телец",
            "sign_name_en": "Taurus",
            "start_local": "1978-03-19T01:00:00",
            "end_local": "1978-03-19T02:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 3,
            "sign_name_ru": "Близнецы",
            "sign_name_en": "Gemini",
            "start_local": "1978-03-19T02:00:00",
            "end_local": "1978-03-19T03:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 4,
            "sign_name_ru": "Рак",
            "sign_name_en": "Cancer",
            "start_local": "1978-03-19T03:00:00",
            "end_local": "1978-03-19T04:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 5,
            "sign_name_ru": "Лев",
            "sign_name_en": "Leo",
            "start_local": "1978-03-19T04:00:00",
            "end_local": "1978-03-19T05:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 6,
            "sign_name_ru": "Дева",
            "sign_name_en": "Virgo",
            "start_local": "1978-03-19T05:00:00",
            "end_local": "1978-03-19T06:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 7,
            "sign_name_ru": "Весы",
            "sign_name_en": "Libra",
            "start_local": "1978-03-19T06:00:00",
            "end_local": "1978-03-19T07:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 8,
            "sign_name_ru": "Скорпион",
            "sign_name_en": "Scorpio",
            "start_local": "1978-03-19T07:00:00",
            "end_local": "1978-03-19T08:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 9,
            "sign_name_ru": "Стрелец",
            "sign_name_en": "Sagittarius",
            "start_local": "1978-03-19T08:00:00",
            "end_local": "1978-03-19T09:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 10,
            "sign_name_ru": "Козерог",
            "sign_name_en": "Capricorn",
            "start_local": "1978-03-19T09:00:00",
            "end_local": "1978-03-19T10:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 11,
            "sign_name_ru": "Водолей",
            "sign_name_en": "Aquarius",
            "start_local": "1978-03-19T10:00:00",
            "end_local": "1978-03-19T11:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 12,
            "sign_name_ru": "Рыбы",
            "sign_name_en": "Pisces",
            "start_local": "1978-03-19T11:00:00",
            "end_local": "1978-03-19T12:00:00",
            "duration_minutes": 60,
        },
        {
            "interval_index": 13,
            "sign_name_ru": "Козерог",
            "sign_name_en": "Capricorn",
            "start_local": "1978-03-19T22:00:00",
            "end_local": "1978-03-19T23:00:00",
            "duration_minutes": 60,
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


def _history_with_element_answers(option_id: str, count: int = 6) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for qid in web_main.STAGE1_ELEMENT_QUESTION_IDS[:count]:
        q = web_main.QUESTION_BANK_BY_ID[qid]
        history.append(
            {
                "role": "assistant",
                "type": "ask_question",
                "question_id": qid,
                "question_text": q["question_text"],
                "options": q["options"],
            }
        )
        history.append(
            {
                "role": "user",
                "selected_option_id": option_id,
                "selected_option_text": option_id,
                "free_text": None,
            }
        )
    return history


def _history_with_modality_answers(
    *,
    element_option_id: str,
    element_count: int = 6,
    element_name: str,
    modality_answers: list[str],
) -> list[dict[str, Any]]:
    history = _history_with_element_answers(element_option_id, element_count)
    for idx, answer in enumerate(modality_answers):
        qid = web_main.STAGE1_MODALITY_QUESTION_IDS_BY_ELEMENT[element_name][idx]
        q = web_main.QUESTION_BANK_BY_ID[qid]
        history.append(
            {
                "role": "assistant",
                "type": "ask_question",
                "question_id": qid,
                "question_text": q["question_text"],
                "options": q["options"],
            }
        )
        history.append(
            {
                "role": "user",
                "selected_option_id": answer,
                "selected_option_text": answer,
                "free_text": None,
            }
        )
    return history


def test_phase1_questions_cover_element_detection_topics() -> None:
    assert len(web_main.STAGE1_ELEMENT_QUESTION_IDS) == 6
    assert all(qid in web_main.QUESTION_BANK_BY_ID for qid in web_main.STAGE1_ELEMENT_QUESTION_IDS)


def test_phase2_has_four_modality_questions_per_element() -> None:
    for element_name, question_ids in web_main.STAGE1_MODALITY_QUESTION_IDS_BY_ELEMENT.items():
        assert len(question_ids) == 4, element_name
        assert all(qid in web_main.QUESTION_BANK_BY_ID for qid in question_ids)


def test_phase1_element_scoring_works() -> None:
    history = _history_with_element_answers("B", 3) + _history_with_element_answers("A", 1)
    element_scores, modality_scores, sign_scores = web_main._calculate_stage1_scores(history)
    assert element_scores["earth"] > 0
    assert element_scores["fire"] > 0
    assert modality_scores["cardinal"] == 0
    assert sign_scores["Capricorn"] == 0


def test_phase2_uses_earth_questions_when_earth_leads() -> None:
    history = _history_with_element_answers("B", 6)
    question = web_main._build_safe_question(dialog_history=history, step_count=6)
    assert question is not None
    assert question["phase"] == "modality_detection"
    assert question["question_id"].startswith("q_mod_earth_")


@pytest.mark.parametrize(
    ("element_name", "element_option", "modality_answer", "expected_sign"),
    [
        ("earth", "B", "A", "Capricorn"),
        ("earth", "B", "B", "Taurus"),
        ("earth", "B", "C", "Virgo"),
        ("fire", "A", "A", "Aries"),
        ("fire", "A", "B", "Leo"),
        ("fire", "A", "C", "Sagittarius"),
        ("air", "C", "A", "Libra"),
        ("air", "C", "B", "Aquarius"),
        ("air", "C", "C", "Gemini"),
        ("water", "D", "A", "Cancer"),
        ("water", "D", "B", "Scorpio"),
        ("water", "D", "C", "Pisces"),
    ],
)
def test_element_plus_modality_formula_maps_to_sign(
    element_name: str,
    element_option: str,
    modality_answer: str,
    expected_sign: str,
) -> None:
    history = _history_with_modality_answers(
        element_option_id=element_option,
        element_name=element_name,
        modality_answers=[modality_answer, modality_answer, modality_answer, modality_answer],
    )
    result = web_main._build_safe_final_result(
        rectification_document=SAMPLE_RECTIFICATION_DOCUMENT,
        dialog_history=history,
        reason="test_formula",
    )
    assert result["primary_candidate"]["sign_name_en"] == expected_sign
    assert result["leading_element"] == element_name


def test_primary_and_secondary_candidates_keep_all_intervals() -> None:
    history = _history_with_modality_answers(
        element_option_id="B",
        element_name="earth",
        modality_answers=["A", "A", "A", "A"],
    )
    result = web_main._build_safe_final_result(
        rectification_document=SAMPLE_RECTIFICATION_DOCUMENT,
        dialog_history=history,
        reason="test_intervals",
    )
    assert result["primary_candidate"]["sign_name_en"] == "Capricorn"
    assert len(result["primary_candidate"]["time_ranges_local"]) == 2
    for sec in result["secondary_candidates"]:
        assert sec["time_ranges_local"]


def test_close_candidates_add_warning_and_candidate_group() -> None:
    history = _history_with_modality_answers(
        element_option_id="B",
        element_name="earth",
        modality_answers=["A", "B", "C", "D"],
    )
    result = web_main._build_safe_final_result(
        rectification_document=SAMPLE_RECTIFICATION_DOCUMENT,
        dialog_history=history,
        reason="test_close_scores",
    )
    assert result["needs_more_questions"] is True
    assert result["candidate_group"] is not None
    assert "sign_scores_are_close" in result["warnings"]


def test_final_result_contains_method_limitations_block() -> None:
    history = _history_with_modality_answers(
        element_option_id="A",
        element_name="fire",
        modality_answers=["A", "A", "A", "A"],
    )
    result = web_main._build_safe_final_result(
        rectification_document=SAMPLE_RECTIFICATION_DOCUMENT,
        dialog_history=history,
        reason="test_limitations",
    )
    limitations = result.get("method_limitations") or []
    assert any("1–3 часа" in item for item in limitations)
    assert any("быстро восходящие" in item for item in limitations)
    assert any("дирекционные формулы" in item for item in limitations)


def test_stage1_llm_failure_before_min_questions_returns_question(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: (_ for _ in ()).throw(HTTPException(status_code=502, detail="fail")),
    )
    history = _history_with_element_answers("B", 3)
    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(dialog_history=history, step_count=3, mode="finalize_now"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm_json"]["type"] == "ask_question"
    assert "min_questions_not_reached" in body["warnings"]


def test_stage1_max_steps_forces_safe_final(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {"type": "ask_question"},
            "llm_text": "",
            "usage": web_main._empty_usage(),
            "openai_raw_response": {},
        },
    )
    response = client.post(
        "/api/rectification/dialog/continue",
        json=_continue_payload(step_count=web_main.RECT_MAX_STEPS, mode="next_question"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["llm_json"]["type"] == "final_result"
    assert "max_steps_reached_safe_finalization" in body["warnings"]


def test_stage1_start_endpoint_works_with_guarded_question(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        web_main,
        "_call_rectification_llm",
        lambda **kwargs: {
            "llm_json": {
                "type": "ask_question",
                "step_index": 1,
                "should_continue": True,
                "phase": "element_detection",
                "debug_probability_text": "x",
                "question_id": "q_element_energy_01",
                "question_text": web_main.QUESTION_BANK_BY_ID["q_element_energy_01"]["question_text"],
                "options": web_main.QUESTION_BANK_BY_ID["q_element_energy_01"]["options"],
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
    assert body["llm_json"]["question_id"] == "q_element_energy_01"
