from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

from app.utils.timezone_lookup import resolve_timezone_name

PROMPT_PATH = Path(__file__).resolve().parent.parent / "PROMPT.md"
PROMPT_RECTIFICATION_STAGE1_PATH = (
    Path(__file__).resolve().parent.parent / "PROMPT_RECTIFICATION_STAGE1.md"
)
STATIC_DIR = Path(__file__).resolve().parent / "static"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

TZ_OFFSET_PATTERN = re.compile(r"^[+-](?:0\d|1[0-4]):[0-5]\d$")

RECT_MIN_STEPS = 3
RECT_MAX_STEPS = 10
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

app = FastAPI(title="astro-web-ui", docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger(__name__)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ) and len(value) >= 2:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


ENV_FILE_VALUES = _read_env_file(ENV_PATH)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, ENV_FILE_VALUES.get(name, default))


DOCKER_COMPOSE_API_BASE_URL = _env("DOCKER_COMPOSE_API_BASE_URL", "http://astrodvish-api:8013")

QUESTION_BANK: list[dict[str, Any]] = [
    {
        "question_id": "q_first_impression_01",
        "question_text": "Как вас чаще всего воспринимают в самом начале общения?",
        "options": [
            {"id": "A", "text": "мягкий и дипломатичный"},
            {"id": "B", "text": "яркий и прямой"},
            {"id": "C", "text": "сдержанный и серьёзный"},
            {"id": "D", "text": "лёгкий и разговорчивый"},
            {"id": "E", "text": "необычный и независимый"},
            {"id": "X", "text": "не знаю / сложно сказать"},
        ],
    },
    {
        "question_id": "q_social_entry_02",
        "question_text": "Как вы обычно входите в новый коллектив?",
        "options": [
            {"id": "A", "text": "сначала наблюдаю и действую осторожно"},
            {"id": "B", "text": "быстро включаюсь и знакомлюсь"},
            {"id": "C", "text": "ищу 1-2 близких контакта, не иду в центр сразу"},
            {"id": "D", "text": "беру инициативу и задаю тон"},
            {"id": "E", "text": "держусь независимо и на своей волне"},
            {"id": "X", "text": "по-разному, зависит от ситуации"},
        ],
    },
    {
        "question_id": "q_communication_style_03",
        "question_text": "Какой стиль общения вам ближе всего?",
        "options": [
            {"id": "A", "text": "мягкий, дипломатичный, аккуратный"},
            {"id": "B", "text": "прямой и быстрый"},
            {"id": "C", "text": "структурный и по делу"},
            {"id": "D", "text": "эмоциональный и выразительный"},
            {"id": "E", "text": "живой, подвижный, с юмором"},
            {"id": "X", "text": "затрудняюсь выбрать"},
        ],
    },
    {
        "question_id": "q_reaction_tempo_04",
        "question_text": "Какой у вас типичный темп реакции в новой ситуации?",
        "options": [
            {"id": "A", "text": "очень быстрый, решаю на ходу"},
            {"id": "B", "text": "средний, сначала оцениваю контекст"},
            {"id": "C", "text": "неторопливый, предпочитаю устойчивость"},
            {"id": "D", "text": "скачкообразный: то быстро, то пауза"},
            {"id": "E", "text": "зависит от людей и атмосферы"},
            {"id": "X", "text": "сложно определить"},
        ],
    },
    {
        "question_id": "q_conflict_style_05",
        "question_text": "В конфликте вы чаще действуете как?",
        "options": [
            {"id": "A", "text": "сглаживаю и ищу компромисс"},
            {"id": "B", "text": "иду прямо в обсуждение, не избегаю остроты"},
            {"id": "C", "text": "держу дистанцию и холодную логику"},
            {"id": "D", "text": "защищаю границы жёстко, если нужно"},
            {"id": "E", "text": "перевожу в шутку или в лёгкий формат"},
            {"id": "X", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_visual_presence_06",
        "question_text": "Что чаще замечают в вашей внешней подаче?",
        "options": [
            {"id": "A", "text": "гармоничность и аккуратность"},
            {"id": "B", "text": "энергичность и напор"},
            {"id": "C", "text": "строгость и собранность"},
            {"id": "D", "text": "яркость и заметность"},
            {"id": "E", "text": "нестандартность и оригинальность"},
            {"id": "X", "text": "затрудняюсь ответить"},
        ],
    },
    {
        "question_id": "q_lead_or_balance_07",
        "question_text": "Что вам ближе в групповой динамике?",
        "options": [
            {"id": "A", "text": "вести и принимать решения"},
            {"id": "B", "text": "координировать и балансировать позиции"},
            {"id": "C", "text": "поддерживать стабильность процесса"},
            {"id": "D", "text": "генерировать идеи и быстро переключаться"},
            {"id": "E", "text": "сохранять независимую позицию"},
            {"id": "X", "text": "смешанный стиль"},
        ],
    },
    {
        "question_id": "q_energy_signature_08",
        "question_text": "Какая характеристика лучше описывает вашу базовую подачу энергии?",
        "options": [
            {"id": "A", "text": "дипломатичность и контактность"},
            {"id": "B", "text": "интенсивность и воля"},
            {"id": "C", "text": "надёжность и устойчивость"},
            {"id": "D", "text": "подвижность и адаптивность"},
            {"id": "E", "text": "чувствительность и эмпатичность"},
            {"id": "X", "text": "сложно выбрать"},
        ],
    },
    {
        "question_id": "q_new_people_effect_09",
        "question_text": "Когда вы знакомитесь с новыми людьми, какой эффект чаще возникает?",
        "options": [
            {"id": "A", "text": "со мной легко и спокойно"},
            {"id": "B", "text": "я быстро задаю динамику"},
            {"id": "C", "text": "я кажусь закрытым, но надёжным"},
            {"id": "D", "text": "я вызываю сильный интерес или полярные реакции"},
            {"id": "E", "text": "я воспринимаюсь как гибкий и разговорчивый"},
            {"id": "X", "text": "не замечал(а) устойчивого эффекта"},
        ],
    },
    {
        "question_id": "q_decision_mode_10",
        "question_text": "Как вы чаще принимаете решения в повседневности?",
        "options": [
            {"id": "A", "text": "быстро, опираясь на импульс"},
            {"id": "B", "text": "через баланс плюсов и минусов"},
            {"id": "C", "text": "через проверку рисков и устойчивости"},
            {"id": "D", "text": "через интуитивный образ и настроение"},
            {"id": "E", "text": "через обсуждение и обмен идеями"},
            {"id": "X", "text": "нет одного шаблона"},
        ],
    },
]

QUESTION_BANK_BY_ID = {item["question_id"]: item for item in QUESTION_BANK}


class GeocodeRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class GenerateRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    datetime_local: str
    timezone_mode: Literal["auto", "manual"] = "auto"
    timezone_offset: str = ""
    timezone_name: str | None = None
    latitude: float
    longitude: float
    house_system: str = "P"
    zodiac_mode: str = "tropical"
    sidereal_mode: str | None = None
    prompt_text: str = "Сделай гороскоп по этим данным."


class RectificationIntervalsRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    birth_date_local: str
    latitude: float
    longitude: float
    house_system: str = "P"
    zodiac_mode: str = "tropical"
    sidereal_mode: str | None = None


class DialogUserResponse(BaseModel):
    selected_option_id: str | None = None
    selected_option_text: str | None = None
    free_text: str | None = None


class RectificationDialogStartRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    birth_date_local: str
    latitude: float
    longitude: float
    house_system: str = "P"
    zodiac_mode: str = "tropical"
    sidereal_mode: str | None = None
    prompt_text: str
    user_profile_note: str | None = None


class RectificationDialogContinueRequest(BaseModel):
    prompt_text: str
    rectification_document: dict[str, Any]
    dialog_history: list[dict[str, Any]]
    step_count: int = 0
    mode: Literal["next_question", "finalize_now"] = "next_question"
    user_profile_note: str | None = None
    user_response: DialogUserResponse | None = None


class RectificationEventsStartRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)


class EventAnswerWebInput(BaseModel):
    question_id: str
    event_type: str
    title: str | None = None
    date_text: str | None = None
    impact_level: int | None = None
    reversibility: str | None = None
    life_area: str | None = None
    notes: str | None = None
    user_skipped: bool = False


class RectificationEventsContinueRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)
    last_answer: EventAnswerWebInput | None = None


class RectificationEventsFinalizeRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)


class AskQuestionOption(BaseModel):
    id: str
    text: str


class AskQuestionLLMResponse(BaseModel):
    type: Literal["ask_question"]
    step_index: int
    should_continue: bool
    debug_probability_text: str
    question_id: str
    question_text: str
    options: list[AskQuestionOption]
    allow_free_text: bool


class TimeRangeLocal(BaseModel):
    start: str
    end: str


class PrimaryCandidate(BaseModel):
    sign_name_ru: str
    sign_name_en: str
    time_range_local: TimeRangeLocal
    probability: float


class SecondaryCandidate(BaseModel):
    sign_name_ru: str
    sign_name_en: str
    probability: float


class FinalResultLLMResponse(BaseModel):
    type: Literal["final_result"]
    should_continue: bool
    primary_candidate: PrimaryCandidate
    secondary_candidates: list[SecondaryCandidate]
    summary_text: str


def _log_stage1_warning(event: str, **fields: object) -> None:
    logger.warning(
        json.dumps(
            {
                "event": event,
                **fields,
            },
            ensure_ascii=False,
            default=str,
        )
    )


def _empty_usage() -> dict[str, None]:
    return {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
    }


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _extract_asked_question_ids(dialog_history: list[dict[str, Any]]) -> list[str]:
    asked: list[str] = []
    for item in dialog_history:
        if item.get("role") != "assistant":
            continue
        if item.get("type") != "ask_question":
            continue
        question_id = item.get("question_id")
        if isinstance(question_id, str) and question_id:
            asked.append(question_id)
    return asked


def _validate_stage1_semantics(
    llm_json: dict[str, Any],
    *,
    dialog_history: list[dict[str, Any]],
    step_count: int,
) -> list[str]:
    errors: list[str] = []
    response_type = llm_json.get("type")
    asked_question_ids = set(_extract_asked_question_ids(dialog_history))

    if response_type == "ask_question":
        if llm_json.get("should_continue") is not True:
            errors.append("ask_question.should_continue must be true")

        expected_step_index = step_count + 1
        if llm_json.get("step_index") != expected_step_index:
            errors.append(f"ask_question.step_index must be {expected_step_index}")

        question_id = llm_json.get("question_id")
        if question_id not in QUESTION_BANK_BY_ID:
            errors.append("ask_question.question_id is not in Question Bank")
        elif question_id in asked_question_ids:
            errors.append("ask_question.question_id is repeated")

        if not _non_empty_string(llm_json.get("question_text")):
            errors.append("ask_question.question_text is empty")

        options = llm_json.get("options")
        if not isinstance(options, list) or not options:
            errors.append("ask_question.options must be a non-empty array")
        else:
            for index, option in enumerate(options):
                option_id = option.get("id") if isinstance(option, dict) else None
                option_text = option.get("text") if isinstance(option, dict) else None
                if not _non_empty_string(option_id):
                    errors.append(f"ask_question.options[{index}].id is empty")
                if not _non_empty_string(option_text):
                    errors.append(f"ask_question.options[{index}].text is empty")

        if not isinstance(llm_json.get("allow_free_text"), bool):
            errors.append("ask_question.allow_free_text must be boolean")

    elif response_type == "final_result":
        if llm_json.get("should_continue") is not False:
            errors.append("final_result.should_continue must be false")

        primary = llm_json.get("primary_candidate")
        if not isinstance(primary, dict):
            errors.append("final_result.primary_candidate is missing")
            return errors

        if not _non_empty_string(primary.get("sign_name_ru")):
            errors.append("final_result.primary_candidate.sign_name_ru is empty")
        if not _non_empty_string(primary.get("sign_name_en")):
            errors.append("final_result.primary_candidate.sign_name_en is empty")

        time_range = primary.get("time_range_local")
        if not isinstance(time_range, dict):
            errors.append("final_result.primary_candidate.time_range_local is missing")
        else:
            if not _non_empty_string(time_range.get("start")):
                errors.append("final_result.primary_candidate.time_range_local.start is empty")
            if not _non_empty_string(time_range.get("end")):
                errors.append("final_result.primary_candidate.time_range_local.end is empty")

        probability = primary.get("probability")
        if not isinstance(probability, (int, float)) or probability < 0 or probability > 1:
            errors.append("final_result.primary_candidate.probability must be in range 0..1")

        secondary = llm_json.get("secondary_candidates")
        if not isinstance(secondary, list):
            errors.append("final_result.secondary_candidates must be array")
        else:
            for index, candidate in enumerate(secondary):
                probability_value = candidate.get("probability") if isinstance(candidate, dict) else None
                if probability_value is None:
                    continue
                if (
                    not isinstance(probability_value, (int, float))
                    or probability_value < 0
                    or probability_value > 1
                ):
                    errors.append(f"final_result.secondary_candidates[{index}].probability must be 0..1")

        if not _non_empty_string(llm_json.get("summary_text")):
            errors.append("final_result.summary_text is empty")

    else:
        errors.append("type must be ask_question or final_result")

    return errors


def _build_safe_question(*, dialog_history: list[dict[str, Any]], step_count: int) -> dict[str, Any] | None:
    asked_question_ids = set(_extract_asked_question_ids(dialog_history))
    fallback_question = next(
        (item for item in QUESTION_BANK if item["question_id"] not in asked_question_ids),
        None,
    )
    if fallback_question is None:
        return None

    return {
        "type": "ask_question",
        "step_index": step_count + 1,
        "should_continue": True,
        "debug_probability_text": "Задаю уточняющий вопрос из резервного сценария.",
        "question_id": fallback_question["question_id"],
        "question_text": fallback_question["question_text"],
        "options": fallback_question["options"],
        "allow_free_text": False,
    }


def _sorted_intervals(rectification_document: dict[str, Any]) -> list[dict[str, Any]]:
    intervals = rectification_document.get("asc_sign_intervals")
    if not isinstance(intervals, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in intervals:
        if not isinstance(item, dict):
            continue
        if not _non_empty_string(item.get("sign_name_en")):
            continue
        if not _non_empty_string(item.get("sign_name_ru")):
            continue
        if not _non_empty_string(item.get("start_local")):
            continue
        if not _non_empty_string(item.get("end_local")):
            continue
        duration_minutes = item.get("duration_minutes")
        if not isinstance(duration_minutes, int):
            duration_minutes = 0
        normalized.append(
            {
                "sign_name_ru": item["sign_name_ru"].strip(),
                "sign_name_en": item["sign_name_en"].strip(),
                "start_local": item["start_local"].strip(),
                "end_local": item["end_local"].strip(),
                "duration_minutes": duration_minutes,
                "interval_index": item.get("interval_index", 999),
            }
        )

    normalized.sort(key=lambda x: (-x["duration_minutes"], x["interval_index"]))
    return normalized


def _build_safe_final_result(
    *,
    rectification_document: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    intervals = _sorted_intervals(rectification_document)
    if intervals:
        primary = intervals[0]
        secondary_source = intervals[1:4]
        secondary_probabilities = [0.22, 0.17, 0.11]
        secondary = []
        for index, item in enumerate(secondary_source):
            secondary.append(
                {
                    "sign_name_ru": item["sign_name_ru"],
                    "sign_name_en": item["sign_name_en"],
                    "probability": secondary_probabilities[index],
                }
            )
        return {
            "type": "final_result",
            "should_continue": False,
            "primary_candidate": {
                "sign_name_ru": primary["sign_name_ru"],
                "sign_name_en": primary["sign_name_en"],
                "time_range_local": {
                    "start": primary["start_local"],
                    "end": primary["end_local"],
                },
                "probability": 0.34,
            },
            "secondary_candidates": secondary,
            "summary_text": (
                "Предварительный результат Stage 1 сформирован в резервном безопасном режиме "
                f"({reason}). Уверенность намеренно снижена."
            ),
        }

    day_window = rectification_document.get("day_window") if isinstance(rectification_document, dict) else {}
    start_local = day_window.get("start_local") if isinstance(day_window, dict) else None
    end_local = day_window.get("end_local") if isinstance(day_window, dict) else None
    if not _non_empty_string(start_local):
        start_local = "1970-01-01T00:00:00"
    if not _non_empty_string(end_local):
        end_local = "1970-01-01T00:00:00"

    return {
        "type": "final_result",
        "should_continue": False,
        "primary_candidate": {
            "sign_name_ru": "Не определено",
            "sign_name_en": "Undetermined",
            "time_range_local": {"start": start_local, "end": end_local},
            "probability": 0.05,
        },
        "secondary_candidates": [],
        "summary_text": (
            "Предварительный результат Stage 1 сформирован в резервном безопасном режиме. "
            f"Не найдено пригодных интервалов ({reason})."
        ),
    }


def _apply_free_text_policy(llm_json: dict[str, Any]) -> dict[str, Any]:
    if llm_json.get("type") == "ask_question":
        llm_json = dict(llm_json)
        llm_json["allow_free_text"] = False
    return llm_json


def _run_stage1_guarded(
    *,
    prompt_text: str,
    mode: Literal["choose_next_question", "finalize_now"],
    rectification_document: dict[str, Any],
    dialog_history: list[dict[str, Any]],
    step_count: int,
    user_profile_note: str | None,
) -> dict[str, Any]:
    warnings: list[str] = []

    if mode == "choose_next_question" and step_count >= RECT_MAX_STEPS:
        warnings.append("max_steps_reached_safe_finalization")
        return {
            "llm_json": _build_safe_final_result(
                rectification_document=rectification_document,
                reason="max_steps_reached",
            ),
            "llm_text": "",
            "usage": _empty_usage(),
            "openai_raw_response": {},
            "warnings": warnings,
        }

    try:
        llm_result = _call_rectification_llm(
            prompt_text=prompt_text,
            mode=mode,
            rectification_document=rectification_document,
            dialog_history=dialog_history,
            step_count=step_count,
            user_profile_note=user_profile_note,
        )
    except HTTPException as exc:
        warnings.append("llm_request_failed")
        _log_stage1_warning(
            "stage1_llm_error",
            mode=mode,
            step_count=step_count,
            detail=exc.detail,
        )
        if mode == "finalize_now" or step_count >= RECT_MIN_STEPS:
            fallback_llm_json = _build_safe_final_result(
                rectification_document=rectification_document,
                reason="llm_request_failed",
            )
        else:
            fallback_llm_json = _build_safe_question(
                dialog_history=dialog_history,
                step_count=step_count,
            )
            if fallback_llm_json is None:
                fallback_llm_json = _build_safe_final_result(
                    rectification_document=rectification_document,
                    reason="no_safe_question_available",
                )
        return {
            "llm_json": fallback_llm_json,
            "llm_text": "",
            "usage": _empty_usage(),
            "openai_raw_response": {},
            "warnings": warnings,
        }

    llm_json_candidate = llm_result.get("llm_json")
    if not isinstance(llm_json_candidate, dict):
        semantic_errors = ["llm_json must be an object"]
    else:
        semantic_errors = _validate_stage1_semantics(
            llm_json_candidate,
            dialog_history=dialog_history,
            step_count=step_count,
        )
    if semantic_errors:
        warnings.append("llm_json_failed_guard")
        _log_stage1_warning(
            "stage1_llm_invalid_json",
            mode=mode,
            step_count=step_count,
            errors=semantic_errors,
            llm_json=llm_result["llm_json"],
        )

        if mode == "finalize_now" or step_count >= RECT_MIN_STEPS:
            fallback_llm_json = _build_safe_final_result(
                rectification_document=rectification_document,
                reason="llm_json_failed_guard",
            )
        else:
            fallback_llm_json = _build_safe_question(
                dialog_history=dialog_history,
                step_count=step_count,
            )
            if fallback_llm_json is None:
                fallback_llm_json = _build_safe_final_result(
                    rectification_document=rectification_document,
                    reason="no_safe_question_available",
                )

        llm_result["llm_json"] = fallback_llm_json

    llm_result["llm_json"] = _apply_free_text_policy(llm_result["llm_json"])
    llm_result["warnings"] = warnings
    return llm_result


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        return "Сделай гороскоп по этим данным."
    return PROMPT_PATH.read_text(encoding="utf-8").strip() or "Сделай гороскоп по этим данным."


def _load_rectification_prompt() -> str:
    if not PROMPT_RECTIFICATION_STAGE1_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Missing PROMPT_RECTIFICATION_STAGE1.md file in project root",
        )
    text = PROMPT_RECTIFICATION_STAGE1_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise HTTPException(status_code=500, detail="PROMPT_RECTIFICATION_STAGE1.md is empty")
    return text


def _load_openrouter_settings() -> dict[str, Any]:
    api_key = _env("OPENROUTER_API_KEY", "").strip()
    base_url = _env("OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_BASE_URL).strip().rstrip("/")
    model = _env("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip()
    site_url = _env("OPENROUTER_SITE_URL", "").strip()
    app_name = _env("OPENROUTER_APP_NAME", "AstroDvish").strip() or "AstroDvish"
    timeout_raw = _env("OPENROUTER_TIMEOUT_SECONDS", "120").strip()

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "OPENROUTER_API_KEY is not set. Configure it in environment "
                "or in .env file."
            ),
        )

    if not model:
        raise HTTPException(status_code=500, detail="OPENROUTER_MODEL is empty")

    try:
        timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="OPENROUTER_TIMEOUT_SECONDS must be integer") from exc
    if timeout_seconds <= 0:
        raise HTTPException(status_code=500, detail="OPENROUTER_TIMEOUT_SECONDS must be > 0")

    return {
        "api_key": api_key,
        "base_url": base_url or OPENROUTER_DEFAULT_BASE_URL,
        "model": model,
        "site_url": site_url,
        "app_name": app_name,
        "timeout_seconds": timeout_seconds,
    }


def _to_utc_iso(local_dt_str: str, tz_offset: str, timezone_name: str | None = None) -> str:
    try:
        local_naive = datetime.fromisoformat(local_dt_str)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid datetime_local format") from exc

    if timezone_name:
        try:
            timezone_info = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="Invalid timezone_name") from exc
        local_aware = local_naive.replace(tzinfo=timezone_info)
        return local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    if not TZ_OFFSET_PATTERN.match(tz_offset):
        raise HTTPException(status_code=422, detail="Invalid timezone_offset format. Use +03:00")

    sign = 1 if tz_offset[0] == "+" else -1
    hours = int(tz_offset[1:3])
    minutes = int(tz_offset[4:6])
    offset = timedelta(hours=hours, minutes=minutes) * sign
    dt_with_tz = local_naive.replace(tzinfo=timezone(offset))
    return dt_with_tz.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_offset(local_aware: datetime) -> str:
    offset = local_aware.utcoffset()
    if offset is None:
        raise HTTPException(status_code=422, detail="Could not resolve timezone offset for datetime_local")
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    abs_minutes = abs(total_minutes)
    hours = abs_minutes // 60
    minutes = abs_minutes % 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _resolve_timezone_context(payload: GenerateRequest) -> tuple[dict[str, Any], list[str]]:
    try:
        local_naive = datetime.fromisoformat(payload.datetime_local)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid datetime_local format") from exc

    warnings: list[str] = []
    timezone_mode = payload.timezone_mode

    if timezone_mode == "auto":
        timezone_name = (payload.timezone_name or "").strip()
        timezone_source = "auto_by_coordinates"
        if not timezone_name:
            try:
                timezone_name = resolve_timezone_name(latitude=payload.latitude, longitude=payload.longitude)
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Could not auto-detect timezone for coordinates: {exc}",
                ) from exc

        try:
            timezone_info = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="Invalid timezone_name") from exc

        local_aware = local_naive.replace(tzinfo=timezone_info)
        auto_offset = _format_offset(local_aware)
        if payload.timezone_offset and payload.timezone_offset != auto_offset:
            warnings.append("manual_offset_ignored_in_auto_timezone_mode")

        datetime_utc = local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return (
            {
                "mode": "auto",
                "timezone_name": timezone_name,
                "timezone_offset": auto_offset,
                "timezone_source": timezone_source,
                "datetime_local": payload.datetime_local,
                "datetime_utc": datetime_utc,
            },
            warnings,
        )

    if not TZ_OFFSET_PATTERN.match(payload.timezone_offset):
        raise HTTPException(status_code=422, detail="Invalid timezone_offset format. Use +03:00")

    sign = 1 if payload.timezone_offset[0] == "+" else -1
    hours = int(payload.timezone_offset[1:3])
    minutes = int(payload.timezone_offset[4:6])
    offset = timedelta(hours=hours, minutes=minutes) * sign
    dt_with_tz = local_naive.replace(tzinfo=timezone(offset))
    datetime_utc = dt_with_tz.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    warnings.append("manual_timezone_offset_used")
    return (
        {
            "mode": "manual",
            "timezone_name": payload.timezone_name,
            "timezone_offset": payload.timezone_offset,
            "timezone_source": "manual_offset",
            "datetime_local": payload.datetime_local,
            "datetime_utc": datetime_utc,
        },
        warnings,
    )


def _build_core_identity_block(chart: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    objects = chart.get("objects") if isinstance(chart, dict) else None
    angles = chart.get("angles") if isinstance(chart, dict) else None

    sun = objects.get("sun") if isinstance(objects, dict) else None
    moon = objects.get("moon") if isinstance(objects, dict) else None
    asc = angles.get("asc") if isinstance(angles, dict) else None

    if not isinstance(sun, dict):
        warnings.append("core_identity_missing_sun")
    if not isinstance(moon, dict):
        warnings.append("core_identity_missing_moon")
    if not isinstance(asc, (int, float)):
        warnings.append("core_identity_missing_asc")

    core_identity = {
        "sun": sun if isinstance(sun, dict) else None,
        "moon": moon if isinstance(moon, dict) else None,
        "asc": asc if isinstance(asc, (int, float)) else None,
    }
    return core_identity, warnings


def _is_localhost_base_url(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "localhost"}


def _post_to_api_with_fallback(*, base_url: str, path: str, payload: dict[str, Any], timeout: int) -> httpx.Response:
    primary_url = base_url.rstrip("/") + path
    try:
        return httpx.post(primary_url, json=payload, timeout=timeout)
    except httpx.HTTPError as primary_error:
        if not _is_localhost_base_url(base_url):
            raise primary_error

        fallback_url = DOCKER_COMPOSE_API_BASE_URL.rstrip("/") + path
        logger.warning(
            "Primary API base URL failed; retrying via docker-compose service name: %s -> %s",
            primary_url,
            fallback_url,
        )
        return httpx.post(fallback_url, json=payload, timeout=timeout)


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                text = item["text"].strip()
                if text:
                    chunks.append(text)
        return "\n\n".join(chunks).strip()

    return ""


def _call_openrouter_chat(
    *,
    system_prompt: str,
    user_prompt: str,
    model_override_env: str | None = None,
) -> dict[str, Any]:
    settings = _load_openrouter_settings()
    model = _env(model_override_env, "").strip() if model_override_env else ""
    if not model:
        model = settings["model"]

    headers: dict[str, str] = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
        "X-Title": settings["app_name"],
    }
    if settings["site_url"]:
        headers["HTTP-Referer"] = settings["site_url"]

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    try:
        response = httpx.post(
            f"{settings['base_url']}/chat/completions",
            headers=headers,
            json=body,
            timeout=settings["timeout_seconds"],
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter timeout: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "OpenRouter returned non-200 status",
                "status_code": response.status_code,
                "body": response.text[:4000],
            },
        )

    payload = response.json()
    text = _extract_chat_completion_text(payload)
    if not text:
        raise HTTPException(status_code=502, detail="OpenRouter response did not contain text")

    return {
        "text": text,
        "raw": payload,
    }


def _render_horoscope_via_openai(prompt_text: str, chart: dict[str, Any], core_identity: dict[str, Any]) -> str:
    system_prompt = (
        "Ты астрологический ассистент. Пиши по-русски. "
        "Дай структурированный и понятный разбор без мистификации, "
        "используя только переданные расчётные данные. "
        "Первый блок трактовки всегда обязан включать в явном виде: Солнце, Луну и Asc. "
        "Нельзя заменять Луну или Asc на узлы. Узлы допустимы только после базового блока."
    )
    user_prompt = (
        f"{prompt_text.strip()}\n\n"
        "Обязательный базовый блок (используй как основу для первого раздела):\n"
        f"{json.dumps(core_identity, ensure_ascii=False)}\n\n"
        "Ниже JSON с расчётом натальной карты. "
        "Сделай связный текстовый гороскоп: личность, эмоции, "
        "отношения, работа/реализация, сильные стороны и риски.\n\n"
        f"{json.dumps(chart, ensure_ascii=False)}"
    )
    chat_result = _call_openrouter_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_override_env="OPENROUTER_MODEL_HOROSCOPE",
    )
    return chat_result["text"]


def _extract_usage_stats(openai_response: dict[str, Any]) -> dict[str, int | None]:
    usage = openai_response.get("usage", {}) or {}
    input_tokens = usage.get("input_tokens")
    if not isinstance(input_tokens, int):
        input_tokens = usage.get("prompt_tokens")

    output_tokens = usage.get("output_tokens")
    if not isinstance(output_tokens, int):
        output_tokens = usage.get("completion_tokens")

    total_tokens = usage.get("total_tokens")

    input_details = usage.get("input_tokens_details", {}) or {}
    output_details = usage.get("output_tokens_details", {}) or {}

    cached_input_tokens = input_details.get("cached_tokens")
    reasoning_tokens = output_details.get("reasoning_tokens")

    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else None,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else None,
        "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
        "cached_input_tokens": cached_input_tokens if isinstance(cached_input_tokens, int) else None,
        "reasoning_tokens": reasoning_tokens if isinstance(reasoning_tokens, int) else None,
    }


def _parse_llm_json_text(llm_text: str) -> dict[str, Any]:
    text = llm_text.strip()
    if not text:
        raise HTTPException(status_code=502, detail="LLM returned empty output")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM output is not valid JSON",
                "error": str(exc),
                "llm_text": text[:4000],
            },
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM output JSON must be an object",
                "llm_text": text[:4000],
            },
        )
    return parsed


def _validate_llm_response_shape(parsed_json: dict[str, Any]) -> dict[str, Any]:
    response_type = parsed_json.get("type")
    try:
        if response_type == "ask_question":
            return AskQuestionLLMResponse.model_validate(parsed_json).model_dump()
        if response_type == "final_result":
            return FinalResultLLMResponse.model_validate(parsed_json).model_dump()
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM JSON has invalid structure",
                "validation_errors": exc.errors(),
                "llm_json": parsed_json,
            },
        ) from exc

    raise HTTPException(
        status_code=502,
        detail={
            "message": "LLM JSON type must be ask_question or final_result",
            "llm_json": parsed_json,
        },
    )


def _call_rectification_llm(
    *,
    prompt_text: str,
    mode: Literal["choose_next_question", "finalize_now"],
    rectification_document: dict[str, Any],
    dialog_history: list[dict[str, Any]],
    step_count: int,
    user_profile_note: str | None,
) -> dict[str, Any]:
    runtime_payload = {
        "mode": mode,
        "rectification_document": rectification_document,
        "dialog_history": dialog_history,
        "step_count": step_count,
        "min_steps": RECT_MIN_STEPS,
        "max_steps": RECT_MAX_STEPS,
        "user_profile_note": user_profile_note or "",
    }
    chat_result = _call_openrouter_chat(
        system_prompt=prompt_text,
        user_prompt=json.dumps(runtime_payload, ensure_ascii=False),
        model_override_env="OPENROUTER_MODEL_RECTIFICATION",
    )
    llm_text = chat_result["text"]

    parsed_llm = _parse_llm_json_text(llm_text)
    validated_llm = _validate_llm_response_shape(parsed_llm)
    usage = _extract_usage_stats(chat_result["raw"])

    return {
        "llm_json": validated_llm,
        "llm_text": llm_text,
        "usage": usage,
        "openai_raw_response": chat_result["raw"],
    }


def _fetch_rectification_document(payload: RectificationIntervalsRequest) -> dict[str, Any]:
    path = "/api/v1/rectification/asc-sign-intervals"
    api_payload = {
        "birth_date_local": payload.birth_date_local,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "house_system": payload.house_system,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }
    try:
        response = _post_to_api_with_fallback(
            base_url=payload.api_base_url,
            path=path,
            payload=api_payload,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Rectification API returned non-200 status",
                "status_code": response.status_code,
                "body": response.text[:2000],
            },
        )

    return response.json()


def _post_rectification_events(
    *,
    base_url: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = _post_to_api_with_fallback(
            base_url=base_url,
            path=path,
            payload=payload,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Rectification events API returned non-200 status",
                "status_code": response.status_code,
                "body": response.text[:2000],
                "path": path,
            },
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Rectification events API returned invalid JSON",
        ) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "astrodvish-web-ui"})


@app.get("/api/prompt")
def get_prompt() -> JSONResponse:
    return JSONResponse({"prompt_text": _load_prompt()})


@app.get("/api/rectification/prompt")
def get_rectification_prompt() -> JSONResponse:
    return JSONResponse({"prompt_text": _load_rectification_prompt()})


@app.post("/api/geocode")
def geocode_city(payload: GeocodeRequest) -> JSONResponse:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": payload.query, "count": 8, "language": "ru", "format": "json"}

    try:
        response = httpx.get(url, params=params, timeout=20)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding request failed: {exc}") from exc

    data = response.json()
    results = data.get("results", []) or []
    normalized = [
        {
            "name": item.get("name"),
            "country": item.get("country"),
            "admin1": item.get("admin1"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "timezone": item.get("timezone"),
            "timezone_name": item.get("timezone"),
            "timezone_source": "geocoder",
        }
        for item in results
    ]
    return JSONResponse({"results": normalized})


@app.post("/api/generate")
def generate(payload: GenerateRequest) -> JSONResponse:
    timezone_context, timezone_warnings = _resolve_timezone_context(payload)
    datetime_utc = timezone_context["datetime_utc"]

    chart_payload = {
        "datetime_utc": datetime_utc,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "house_system": payload.house_system,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }

    path = "/api/v1/chart"
    try:
        response = _post_to_api_with_fallback(
            base_url=payload.api_base_url,
            path=path,
            payload=chart_payload,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"API request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Chart API returned non-200 status",
                "status_code": response.status_code,
                "body": response.text[:2000],
            },
        )

    chart_response = response.json()
    core_identity, core_identity_warnings = _build_core_identity_block(chart_response)
    horoscope_text = _render_horoscope_via_openai(payload.prompt_text, chart_response, core_identity)
    warnings = timezone_warnings + core_identity_warnings
    return JSONResponse(
        {
            "datetime_utc": datetime_utc,
            "timezone": timezone_context,
            "warnings": warnings,
            "core_identity": core_identity,
            "horoscope_text": horoscope_text,
            "chart_response": chart_response,
        }
    )


@app.post("/api/rectification/asc-sign-intervals")
def rectification_asc_sign_intervals(payload: RectificationIntervalsRequest) -> JSONResponse:
    return JSONResponse(_fetch_rectification_document(payload))


@app.post("/api/rectification/dialog/start")
def rectification_dialog_start(payload: RectificationDialogStartRequest) -> JSONResponse:
    rectification_document = _fetch_rectification_document(
        RectificationIntervalsRequest(
            api_base_url=payload.api_base_url,
            birth_date_local=payload.birth_date_local,
            latitude=payload.latitude,
            longitude=payload.longitude,
            house_system=payload.house_system,
            zodiac_mode=payload.zodiac_mode,
            sidereal_mode=payload.sidereal_mode,
        )
    )

    llm_result = _run_stage1_guarded(
        prompt_text=payload.prompt_text,
        mode="choose_next_question",
        rectification_document=rectification_document,
        dialog_history=[],
        step_count=0,
        user_profile_note=payload.user_profile_note,
    )

    return JSONResponse(
        {
            "rectification_document": rectification_document,
            "llm_json": llm_result["llm_json"],
            "llm_text": llm_result["llm_text"],
            "usage": llm_result["usage"],
            "openai_raw_response": llm_result["openai_raw_response"],
            "warnings": llm_result["warnings"],
            "step_count": 1 if llm_result["llm_json"].get("type") == "ask_question" else 0,
        }
    )


@app.post("/api/rectification/dialog/continue")
def rectification_dialog_continue(payload: RectificationDialogContinueRequest) -> JSONResponse:
    effective_history = list(payload.dialog_history)
    if payload.user_response is not None:
        effective_history.append(
            {
                "role": "user",
                "selected_option_id": payload.user_response.selected_option_id,
                "selected_option_text": payload.user_response.selected_option_text,
                "free_text": None,
            }
        )

    mode = "finalize_now" if payload.mode == "finalize_now" else "choose_next_question"
    llm_result = _run_stage1_guarded(
        prompt_text=payload.prompt_text,
        mode=mode,
        rectification_document=payload.rectification_document,
        dialog_history=effective_history,
        step_count=payload.step_count,
        user_profile_note=payload.user_profile_note,
    )

    next_step_count = payload.step_count
    if llm_result["llm_json"].get("type") == "ask_question":
        next_step_count += 1

    return JSONResponse(
        {
            "llm_json": llm_result["llm_json"],
            "llm_text": llm_result["llm_text"],
            "usage": llm_result["usage"],
            "openai_raw_response": llm_result["openai_raw_response"],
            "warnings": llm_result["warnings"],
            "step_count": next_step_count,
        }
    )


@app.post("/api/rectification/events/start")
def rectification_events_start(payload: RectificationEventsStartRequest) -> JSONResponse:
    response_json = _post_rectification_events(
        base_url=payload.api_base_url,
        path="/api/v1/rectification/events/start",
        payload={
            "dialog_history": payload.dialog_history,
        },
    )
    return JSONResponse(response_json)


@app.post("/api/rectification/events/continue")
def rectification_events_continue(payload: RectificationEventsContinueRequest) -> JSONResponse:
    response_json = _post_rectification_events(
        base_url=payload.api_base_url,
        path="/api/v1/rectification/events/continue",
        payload={
            "dialog_history": payload.dialog_history,
            "last_answer": payload.last_answer.model_dump() if payload.last_answer is not None else None,
        },
    )
    return JSONResponse(response_json)


@app.post("/api/rectification/events/finalize")
def rectification_events_finalize(payload: RectificationEventsFinalizeRequest) -> JSONResponse:
    response_json = _post_rectification_events(
        base_url=payload.api_base_url,
        path="/api/v1/rectification/events/finalize",
        payload={
            "dialog_history": payload.dialog_history,
        },
    )
    return JSONResponse(response_json)


@app.get("/static/{filename}")
def static_files(filename: str) -> FileResponse:
    file_path = STATIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path)
