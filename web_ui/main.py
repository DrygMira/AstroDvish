from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from io import BytesIO
from time import perf_counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

import httpx
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
try:
    import resource
except ImportError:  # pragma: no cover - Windows fallback.
    resource = None  # type: ignore[assignment]

from app.services.aspects_service import OBJECT_DISPLAY_NAMES
from app.utils.timezone_lookup import resolve_timezone_name

PROMPT_PATH = Path(__file__).resolve().parent.parent / "PROMPT.md"
PROMPT_RECTIFICATION_STAGE1_PATH = (
    Path(__file__).resolve().parent.parent / "PROMPT_RECTIFICATION_STAGE1.md"
)
STATIC_DIR = Path(__file__).resolve().parent / "static"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

TZ_OFFSET_PATTERN = re.compile(r"^[+-](?:0\d|1[0-4]):[0-5]\d$")

STAGE1_MIN_QUESTIONS = 6
STAGE1_MAX_QUESTIONS = 10
STAGE1_EARLY_FINAL_THRESHOLD = 0.65
STAGE1_CLOSE_SCORE_GAP = 0.12
RECT_MIN_STEPS = STAGE1_MIN_QUESTIONS
RECT_MAX_STEPS = STAGE1_MAX_QUESTIONS
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_REQUEST_KIND_DEFAULT = "default"
OPENROUTER_REQUEST_KIND_STAGE1 = "stage1"
OPENROUTER_REQUEST_KIND_GENERATE = "generate"
OPENROUTER_REQUEST_KIND_PRO = "pro"
OPENROUTER_CASCADE_FALLBACK_STATUSES = {401, 402, 403, 429, 500, 502, 503, 504}
LLM_UNAVAILABLE_MESSAGE = (
    "Карта рассчитана, но текстовая интерпретация сейчас недоступна. "
    "Попробуйте повторить позже."
)
GEOCODE_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "geocode_cache.json"
GEOCODE_CACHE_MAX_ITEMS = 300
GEOCODE_CACHE_VERSION = 1
NO_TIME_FALLBACK_LOCAL_CLOCK = "12:00"
NO_TIME_PLACEHOLDER_LATITUDE = 0.0
NO_TIME_PLACEHOLDER_LONGITUDE = 0.0
NO_TIME_STATIONARY_THRESHOLD = 0.0002
NO_TIME_PHASE_EXACT_EPSILON = 0.05
NO_TIME_MAJOR_ASPECTS: tuple[tuple[str, float, float], ...] = (
    ("conjunction", 0.0, 1.0),
    ("sextile", 60.0, 1.0),
    ("square", 90.0, 1.0),
    ("trine", 120.0, 1.0),
    ("opposition", 180.0, 1.0),
)
NO_TIME_MINOR_ASPECTS: tuple[tuple[str, float, float], ...] = (
    ("semi-sextile", 30.0, 0.5),
    ("quincunx", 150.0, 0.5),
)
NO_TIME_TRANSIT_BODIES: tuple[str, ...] = (
    "moon",
    "sun",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
)
NO_TIME_NATAL_TARGET_BODIES: tuple[str, ...] = (
    "sun",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
)
NO_TIME_MOON_SIGN_MEANINGS: dict[str, str] = {
    "Aries": "инициатива / импульс / быстрый эмоциональный отклик",
    "Taurus": "стабилизация / телесность / потребность в опоре",
    "Gemini": "коммуникация / мыслительная активность / переключаемость",
    "Cancer": "чувствительность / дом / эмоциональная память",
    "Leo": "самовыражение / признание / сердечная энергия",
    "Virgo": "анализ / порядок / внимание к деталям",
    "Libra": "контакт / баланс / тема отношений",
    "Scorpio": "интенсивность / внутренние триггеры / глубина",
    "Sagittarius": "смысл / перспектива / движение вперёд",
    "Capricorn": "структура / дисциплина / практичность",
    "Aquarius": "дистанция / идеи / обновление взгляда",
    "Pisces": "интуиция / расплывчатость / эмоциональный фон",
}
NO_TIME_SLOW_TRANSIT_REFERENCE_DURATIONS: dict[str, str] = {
    "Saturn": "1–1.5 months",
    "Jupiter": "2–3 months",
    "Uranus": "1–1.5 years",
    "Neptune": "1.5–2 years",
    "Pluto": "2–3 years",
}

app = FastAPI(title="astro-web-ui", docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger(__name__)


def _collect_rectification_pro_runtime_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "pid": os.getpid(),
        "process_cpu_seconds": round(time.process_time(), 4),
    }
    if hasattr(os, "getloadavg"):
        try:
            load1, load5, load15 = os.getloadavg()
            snapshot["loadavg"] = {
                "1m": round(float(load1), 4),
                "5m": round(float(load5), 4),
                "15m": round(float(load15), 4),
            }
        except OSError:
            pass
    if resource is not None:
        try:
            rss_raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            rss_mb = (rss_raw / 1024.0) if os.name == "posix" else (rss_raw / (1024.0 * 1024.0))
            snapshot["process_max_rss_mb"] = round(float(rss_mb), 2)
        except (AttributeError, OSError, ValueError):
            pass
    return snapshot


def _current_rectification_pro_chunk_limits() -> dict[str, int]:
    return {
        "async_max_events": RECTIFICATION_PRO_ASYNC_MULTI_CARD_MAX_EVENTS,
        "async_complexity_limit": RECTIFICATION_PRO_ASYNC_MULTI_CARD_COMPLEXITY_LIMIT,
        "chunked_max_events": RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS,
        "chunked_max_chunks": RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS,
        "chunked_max_events_per_chunk": RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK,
    }


def _resolve_rectification_pro_chunk_batch_size(
    *,
    relevant_events_count: int,
    selected_cards_count: int,
    complexity: int,
) -> int:
    max_size = max(1, RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK)
    if max_size <= 3:
        return max_size
    if complexity >= 48 or relevant_events_count >= 9 or selected_cards_count >= 5:
        return min(3, max_size)
    return max_size


def _log_rectification_pro_chunk_guard(
    *,
    level: int,
    message: str,
    job_id: str,
    guard_stage: str,
    events_count: int,
    selected_cards_count: int,
    planned_chunks: int | None,
    chunk_size: int | None,
    candidate_count: int | None,
    formula_count: int | None,
    estimated_weight: int | None,
    guard_reason: str,
    current_limit: dict[str, Any],
    runtime_snapshot: dict[str, Any],
) -> None:
    logger.log(
        level,
        (
            "%s job_id=%s stage=%s events=%s cards=%s planned_chunks=%s chunk_size=%s "
            "candidate_count=%s formula_count=%s estimated_weight=%s guard_reason=%s "
            "current_limit=%s runtime_snapshot=%s"
        ),
        message,
        job_id,
        guard_stage,
        events_count,
        selected_cards_count,
        planned_chunks,
        chunk_size,
        candidate_count,
        formula_count,
        estimated_weight,
        guard_reason,
        json.dumps(current_limit, ensure_ascii=False, sort_keys=True),
        json.dumps(runtime_snapshot, ensure_ascii=False, sort_keys=True),
    )


def _load_preview_fixture(filename: str) -> dict[str, Any]:
    path = FIXTURES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Preview fixture not found: {filename}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid preview fixture JSON: {filename}") from exc


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


def _env_flag(name: str, default: str = "0") -> bool:
    return (_env(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


DOCKER_COMPOSE_API_BASE_URL = _env("DOCKER_COMPOSE_API_BASE_URL", "http://astrodvish-api:8013")
DOCKER_COMPOSE_API_FALLBACK_ENABLED = _env_flag("DOCKER_COMPOSE_API_FALLBACK_ENABLED", "0")
WEB_UI_INTERNAL_API_BASE_URL = _env("WEB_UI_INTERNAL_API_BASE_URL", "http://127.0.0.1:8013")
RECTIFICATION_PRO_TIMEOUT_SECONDS = int(_env("RECTIFICATION_PRO_TIMEOUT_SECONDS", "600") or "600")
RECTIFICATION_PRO_JOB_TTL_SECONDS = int(_env("RECTIFICATION_PRO_JOB_TTL_SECONDS", "3600") or "3600")
RECTIFICATION_PRO_MULTI_CARD_MAX_EVENTS = int(_env("RECTIFICATION_PRO_MULTI_CARD_MAX_EVENTS", "4") or "4")
RECTIFICATION_PRO_MULTI_CARD_COMPLEXITY_LIMIT = int(
    _env("RECTIFICATION_PRO_MULTI_CARD_COMPLEXITY_LIMIT", "12") or "12"
)
RECTIFICATION_PRO_ASYNC_MULTI_CARD_MAX_EVENTS = int(
    _env("RECTIFICATION_PRO_ASYNC_MULTI_CARD_MAX_EVENTS", "8") or "8"
)
RECTIFICATION_PRO_ASYNC_MULTI_CARD_COMPLEXITY_LIMIT = int(
    _env("RECTIFICATION_PRO_ASYNC_MULTI_CARD_COMPLEXITY_LIMIT", "24") or "24"
)
RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS = int(
    _env("RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS", "24") or "24"
)
RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS = int(
    _env("RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS", "36") or "36"
)
RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK = int(
    _env("RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK", "4") or "4"
)
RECTIFICATION_PRO_ACTIVE_JOB_STATUSES = {"queued", "pending", "running", "chunk_running", "partial_completed"}
RECTIFICATION_PRO_TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
_RECTIFICATION_PRO_JOBS: dict[str, dict[str, Any]] = {}
_RECTIFICATION_PRO_JOBS_LOCK = threading.Lock()

RECTIFICATION_PRO_CHUNK_CARD_EVENT_TYPES: dict[str, set[str]] = {
    "RECT_CHILD_BIRTH_002_DRAFT": {"child_birth", "children_birth"},
    "RECT_MARRIAGE_UNION_002_DRAFT": {"marriage_start", "marriage_union"},
    "RECT_PROFESSION_CHANGE_002_DRAFT": {"profession_change"},
    "RECT_DIVORCE_SEPARATION_002_DRAFT": {"divorce_separation", "divorce_breakup"},
    "RECT_FATHER_DEATH_002_DRAFT": {"death_father"},
    "RECT_MOTHER_DEATH_002_DRAFT": {"death_mother"},
    "RECT_SIBLING_DEATH_002_DRAFT": {"death_sibling"},
    "RECT_GRANDPARENT_DEATH_002_DRAFT": {"death_grandparent"},
}
RECTIFICATION_PRO_CHUNK_LABELS: dict[str, str] = {
    "child_birth": "деторождение",
    "marriage_union": "брак / союз",
    "marriage_start": "брак / союз",
    "profession_change": "смена профессии",
    "divorce_separation": "развод / прекращение союза",
    "divorce_breakup": "развод / прекращение союза",
    "death_father": "смерть отца",
    "death_mother": "смерть матери",
    "death_sibling": "смерть брата / сестры",
    "death_grandparent": "смерть бабушки / дедушки",
}

QUESTION_BANK: list[dict[str, Any]] = [
    {
        "question_id": "q_element_energy_01",
        "question_text": "Какой тип энергии вам ближе?",
        "options": [
            {"id": "A", "text": "быстрая, яркая, активная, пробивная"},
            {"id": "B", "text": "спокойная, практичная, устойчивая, результативная"},
            {"id": "C", "text": "лёгкая, подвижная, контактная, интеллектуальная"},
            {"id": "D", "text": "мягкая, глубокая, эмоциональная, чувствующая"},
            {"id": "X", "text": "смешано / сложно выбрать"},
        ],
    },
    {
        "question_id": "q_element_first_impression_02",
        "question_text": "Какое первое впечатление вы чаще производите?",
        "options": [
            {"id": "A", "text": "яркий, уверенный, активный, заметный"},
            {"id": "B", "text": "спокойный, надёжный, собранный, устойчивый"},
            {"id": "C", "text": "лёгкий, общительный, дружелюбный, подвижный"},
            {"id": "D", "text": "мягкий, глубокий, загадочный, эмоциональный"},
            {"id": "X", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_element_stress_03",
        "question_text": "Как вы чаще реагируете на стресс?",
        "options": [
            {"id": "A", "text": "включаюсь резко, иду в действие или нападение"},
            {"id": "B", "text": "собираюсь, держусь, ищу практическую опору"},
            {"id": "C", "text": "начинаю обсуждать, искать варианты, проговаривать"},
            {"id": "D", "text": "переживаю глубоко, могу закрываться эмоционально"},
            {"id": "X", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_element_movement_04",
        "question_text": "Как вы обычно двигаетесь?",
        "options": [
            {"id": "A", "text": "быстро, уверенно, энергично"},
            {"id": "B", "text": "размеренно, основательно, устойчиво"},
            {"id": "C", "text": "легко, подвижно, с жестикуляцией"},
            {"id": "D", "text": "плавно, мягко, обтекаемо"},
            {"id": "X", "text": "не знаю"},
        ],
    },
    {
        "question_id": "q_element_lifestyle_05",
        "question_text": "Какой стиль жизни вам ближе?",
        "options": [
            {"id": "A", "text": "динамика, цель, движение, соревнование, быстрые решения"},
            {"id": "B", "text": "практичность, устойчивость, терпение, результат"},
            {"id": "C", "text": "переключение между делами, много интересов, гибкость"},
            {"id": "D", "text": "вдохновение, эмоциональный комфорт, атмосфера и смысл"},
            {"id": "X", "text": "смешанный стиль"},
        ],
    },
    {
        "question_id": "q_element_style_06",
        "question_text": "Какой образ вам ближе?",
        "options": [
            {"id": "A", "text": "яркие акценты, заметность, энергия, смелость"},
            {"id": "B", "text": "практичность, качество, минимализм, надёжность"},
            {"id": "C", "text": "удобство, движение, лёгкость, актуальность"},
            {"id": "D", "text": "мягкие ткани, уют, романтичность, обтекаемый силуэт"},
            {"id": "X", "text": "нет одного стиля"},
        ],
    },
    {
        "question_id": "q_mod_earth_01",
        "question_text": "Что вам ближе в достижении практического результата?",
        "options": [
            {"id": "A", "text": "поставить цель, выстроить систему и взять ответственность"},
            {"id": "B", "text": "сохранить, накопить, укрепить и приумножить уже имеющееся"},
            {"id": "C", "text": "улучшить, пересобрать, довести детали до качества"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_earth_02",
        "question_text": "Что вас больше всего раздражает в работе или делах?",
        "options": [
            {"id": "A", "text": "отсутствие цели, стратегии и ответственности"},
            {"id": "B", "text": "нестабильность, суета, резкие перемены и потеря опоры"},
            {"id": "C", "text": "хаос в деталях, ошибки, недоведённость и низкое качество"},
            {"id": "D", "text": "зависит от ситуации"},
        ],
    },
    {
        "question_id": "q_mod_earth_03",
        "question_text": "Какой стиль действия вам ближе?",
        "options": [
            {"id": "A", "text": "собраться, взять контроль и двигаться к вершине"},
            {"id": "B", "text": "держать устойчивый темп, терпеть и сохранять результат"},
            {"id": "C", "text": "анализировать, адаптироваться и улучшать по ходу дела"},
            {"id": "D", "text": "смешанный стиль"},
        ],
    },
    {
        "question_id": "q_mod_earth_04",
        "question_text": "Что для вас важнее в результате?",
        "options": [
            {"id": "A", "text": "достичь цели и выстроить систему вокруг результата"},
            {"id": "B", "text": "сохранить, укрепить и сделать результат устойчивым"},
            {"id": "C", "text": "улучшить, уточнить и довести результат до качества"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_fire_01",
        "question_text": "Как вы проявляете активную энергию?",
        "options": [
            {"id": "A", "text": "быстро начинаю и пробиваю препятствие"},
            {"id": "B", "text": "удерживаю центр, проявляю яркость и достоинство"},
            {"id": "C", "text": "расширяю идею, вдохновляю и веду к смыслу"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_fire_02",
        "question_text": "Что вас больше раздражает?",
        "options": [
            {"id": "A", "text": "ожидание, торможение, невозможность действовать сразу"},
            {"id": "B", "text": "неуважение, обесценивание, потеря признания"},
            {"id": "C", "text": "ограничения, узость, отсутствие смысла и горизонта"},
            {"id": "D", "text": "зависит от ситуации"},
        ],
    },
    {
        "question_id": "q_mod_fire_03",
        "question_text": "Какой стиль действия ближе?",
        "options": [
            {"id": "A", "text": "стартовать первым, действовать резко и прямо"},
            {"id": "B", "text": "держать образ, вести через харизму, быть центром"},
            {"id": "C", "text": "идти к масштабу, вдохновлять, расширять"},
            {"id": "D", "text": "смешанный стиль"},
        ],
    },
    {
        "question_id": "q_mod_fire_04",
        "question_text": "Что для вас важнее в проявлении силы?",
        "options": [
            {"id": "A", "text": "быстро начать и пробить препятствие"},
            {"id": "B", "text": "удержать яркость, достоинство и признание"},
            {"id": "C", "text": "расширить смысл, вдохновить и повести дальше"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_air_01",
        "question_text": "Как вы чаще проявляетесь в контакте?",
        "options": [
            {"id": "A", "text": "создаю баланс, договариваюсь, ищу форму общения"},
            {"id": "B", "text": "держу независимую позицию, идею, свободу взгляда"},
            {"id": "C", "text": "быстро связываю людей, идеи и информацию"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_air_02",
        "question_text": "Что вас больше раздражает?",
        "options": [
            {"id": "A", "text": "грубость, давление, отсутствие такта и баланса"},
            {"id": "B", "text": "контроль, навязанные правила, давление авторитетов"},
            {"id": "C", "text": "скука, однообразие, информационный вакуум"},
            {"id": "D", "text": "зависит от ситуации"},
        ],
    },
    {
        "question_id": "q_mod_air_03",
        "question_text": "Какой стиль мышления ближе?",
        "options": [
            {"id": "A", "text": "сравнить стороны, найти баланс и договорённость"},
            {"id": "B", "text": "удерживать принцип и нестандартный взгляд"},
            {"id": "C", "text": "быстро переключаться и передавать информацию"},
            {"id": "D", "text": "смешанный стиль"},
        ],
    },
    {
        "question_id": "q_mod_air_04",
        "question_text": "Что для вас важнее в общении и идеях?",
        "options": [
            {"id": "A", "text": "создать контакт, баланс и договорённость"},
            {"id": "B", "text": "сохранить свободу, принцип и независимый взгляд"},
            {"id": "C", "text": "быстро связать людей, идеи и информацию"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_water_01",
        "question_text": "Как вы проявляете эмоциональную энергию?",
        "options": [
            {"id": "A", "text": "создаю близость, защищаю своих, строю безопасное поле"},
            {"id": "B", "text": "удерживаю глубину, контроль и интенсивность переживания"},
            {"id": "C", "text": "мягко чувствую, адаптируюсь и растворяюсь в атмосфере"},
            {"id": "D", "text": "по-разному"},
        ],
    },
    {
        "question_id": "q_mod_water_02",
        "question_text": "Что вас больше раздражает или ранит?",
        "options": [
            {"id": "A", "text": "холодность, небезопасность, отрыв от близких и корней"},
            {"id": "B", "text": "поверхностность, потеря контроля, предательство"},
            {"id": "C", "text": "жёсткость, сухость, грубая конкретика, эмоциональное давление"},
            {"id": "D", "text": "зависит от ситуации"},
        ],
    },
    {
        "question_id": "q_mod_water_03",
        "question_text": "Какой стиль реакции ближе?",
        "options": [
            {"id": "A", "text": "заботиться, защищать, создавать эмоциональную опору"},
            {"id": "B", "text": "собираться в глубине, контролировать, проходить кризис"},
            {"id": "C", "text": "сочувствовать, чувствовать атмосферу, вдохновляться"},
            {"id": "D", "text": "смешанный стиль"},
        ],
    },
    {
        "question_id": "q_mod_water_04",
        "question_text": "Что для вас важнее в эмоциональной сфере?",
        "options": [
            {"id": "A", "text": "создать близость, защиту и чувство безопасности"},
            {"id": "B", "text": "удержать глубину, контроль и пройти трансформацию"},
            {"id": "C", "text": "почувствовать атмосферу, адаптироваться и вдохновиться"},
            {"id": "D", "text": "по-разному"},
        ],
    },
]

QUESTION_BANK_BY_ID = {item["question_id"]: item for item in QUESTION_BANK}

ELEMENT_LABELS: dict[str, str] = {
    "fire": "Огонь",
    "earth": "Земля",
    "air": "Воздух",
    "water": "Вода",
}
MODALITY_LABELS: dict[str, str] = {
    "cardinal": "кардинальный",
    "fixed": "фиксированный",
    "mutable": "мутабельный",
}
ELEMENT_TO_SIGNS: dict[str, tuple[tuple[str, str], ...]] = {
    "fire": (("Овен", "Aries"), ("Лев", "Leo"), ("Стрелец", "Sagittarius")),
    "earth": (("Козерог", "Capricorn"), ("Телец", "Taurus"), ("Дева", "Virgo")),
    "air": (("Весы", "Libra"), ("Водолей", "Aquarius"), ("Близнецы", "Gemini")),
    "water": (("Рак", "Cancer"), ("Скорпион", "Scorpio"), ("Рыбы", "Pisces")),
}
ELEMENT_MODALITY_TO_SIGN: dict[str, dict[str, tuple[str, str]]] = {
    "fire": {
        "cardinal": ("Овен", "Aries"),
        "fixed": ("Лев", "Leo"),
        "mutable": ("Стрелец", "Sagittarius"),
    },
    "earth": {
        "cardinal": ("Козерог", "Capricorn"),
        "fixed": ("Телец", "Taurus"),
        "mutable": ("Дева", "Virgo"),
    },
    "air": {
        "cardinal": ("Весы", "Libra"),
        "fixed": ("Водолей", "Aquarius"),
        "mutable": ("Близнецы", "Gemini"),
    },
    "water": {
        "cardinal": ("Рак", "Cancer"),
        "fixed": ("Скорпион", "Scorpio"),
        "mutable": ("Рыбы", "Pisces"),
    },
}

STAGE1_ELEMENT_QUESTION_IDS: tuple[str, ...] = (
    "q_element_energy_01",
    "q_element_first_impression_02",
    "q_element_stress_03",
    "q_element_movement_04",
    "q_element_lifestyle_05",
    "q_element_style_06",
)
STAGE1_MODALITY_QUESTION_IDS_BY_ELEMENT: dict[str, tuple[str, ...]] = {
    "earth": ("q_mod_earth_01", "q_mod_earth_02", "q_mod_earth_03", "q_mod_earth_04"),
    "fire": ("q_mod_fire_01", "q_mod_fire_02", "q_mod_fire_03", "q_mod_fire_04"),
    "air": ("q_mod_air_01", "q_mod_air_02", "q_mod_air_03", "q_mod_air_04"),
    "water": ("q_mod_water_01", "q_mod_water_02", "q_mod_water_03", "q_mod_water_04"),
}
STAGE1_MODALITY_QUESTION_IDS: set[str] = {
    qid for items in STAGE1_MODALITY_QUESTION_IDS_BY_ELEMENT.values() for qid in items
}

QUESTION_OPTION_ELEMENT_MAP: dict[str, dict[str, dict[str, float]]] = {
    qid: {"A": {"fire": 1.0}, "B": {"earth": 1.0}, "C": {"air": 1.0}, "D": {"water": 1.0}}
    for qid in STAGE1_ELEMENT_QUESTION_IDS
}
QUESTION_OPTION_MODALITY_MAP: dict[str, dict[str, dict[str, str]]] = {
    "q_mod_earth_01": {
        "A": {"modality": "cardinal", "sign": "Capricorn"},
        "B": {"modality": "fixed", "sign": "Taurus"},
        "C": {"modality": "mutable", "sign": "Virgo"},
    },
    "q_mod_earth_02": {
        "A": {"modality": "cardinal", "sign": "Capricorn"},
        "B": {"modality": "fixed", "sign": "Taurus"},
        "C": {"modality": "mutable", "sign": "Virgo"},
    },
    "q_mod_earth_03": {
        "A": {"modality": "cardinal", "sign": "Capricorn"},
        "B": {"modality": "fixed", "sign": "Taurus"},
        "C": {"modality": "mutable", "sign": "Virgo"},
    },
    "q_mod_earth_04": {
        "A": {"modality": "cardinal", "sign": "Capricorn"},
        "B": {"modality": "fixed", "sign": "Taurus"},
        "C": {"modality": "mutable", "sign": "Virgo"},
    },
    "q_mod_fire_01": {
        "A": {"modality": "cardinal", "sign": "Aries"},
        "B": {"modality": "fixed", "sign": "Leo"},
        "C": {"modality": "mutable", "sign": "Sagittarius"},
    },
    "q_mod_fire_02": {
        "A": {"modality": "cardinal", "sign": "Aries"},
        "B": {"modality": "fixed", "sign": "Leo"},
        "C": {"modality": "mutable", "sign": "Sagittarius"},
    },
    "q_mod_fire_03": {
        "A": {"modality": "cardinal", "sign": "Aries"},
        "B": {"modality": "fixed", "sign": "Leo"},
        "C": {"modality": "mutable", "sign": "Sagittarius"},
    },
    "q_mod_fire_04": {
        "A": {"modality": "cardinal", "sign": "Aries"},
        "B": {"modality": "fixed", "sign": "Leo"},
        "C": {"modality": "mutable", "sign": "Sagittarius"},
    },
    "q_mod_air_01": {
        "A": {"modality": "cardinal", "sign": "Libra"},
        "B": {"modality": "fixed", "sign": "Aquarius"},
        "C": {"modality": "mutable", "sign": "Gemini"},
    },
    "q_mod_air_02": {
        "A": {"modality": "cardinal", "sign": "Libra"},
        "B": {"modality": "fixed", "sign": "Aquarius"},
        "C": {"modality": "mutable", "sign": "Gemini"},
    },
    "q_mod_air_03": {
        "A": {"modality": "cardinal", "sign": "Libra"},
        "B": {"modality": "fixed", "sign": "Aquarius"},
        "C": {"modality": "mutable", "sign": "Gemini"},
    },
    "q_mod_air_04": {
        "A": {"modality": "cardinal", "sign": "Libra"},
        "B": {"modality": "fixed", "sign": "Aquarius"},
        "C": {"modality": "mutable", "sign": "Gemini"},
    },
    "q_mod_water_01": {
        "A": {"modality": "cardinal", "sign": "Cancer"},
        "B": {"modality": "fixed", "sign": "Scorpio"},
        "C": {"modality": "mutable", "sign": "Pisces"},
    },
    "q_mod_water_02": {
        "A": {"modality": "cardinal", "sign": "Cancer"},
        "B": {"modality": "fixed", "sign": "Scorpio"},
        "C": {"modality": "mutable", "sign": "Pisces"},
    },
    "q_mod_water_03": {
        "A": {"modality": "cardinal", "sign": "Cancer"},
        "B": {"modality": "fixed", "sign": "Scorpio"},
        "C": {"modality": "mutable", "sign": "Pisces"},
    },
    "q_mod_water_04": {
        "A": {"modality": "cardinal", "sign": "Cancer"},
        "B": {"modality": "fixed", "sign": "Scorpio"},
        "C": {"modality": "mutable", "sign": "Pisces"},
    },
}

STAGE1_METHOD_LIMITATIONS: list[str] = [
    "Этот этап сужает поиск времени рождения через определение восходящего знака.",
    "Обычно этот этап сужает 24 часа до окна примерно 1–3 часа. Длительность окна зависит от широты места рождения и скорости восхождения знака.",
    "Интервалы восходящих знаков не обязаны быть равны двум часам. Из-за широты места рождения и наклона земной оси существуют быстро восходящие и медленно восходящие знаки.",
    "Для уточнения до минут нужны события жизни и дирекционные формулы ректификации.",
    "Если в космограмме сильно выделен другой знак, впечатление Asc может искажаться.",
    "Возможен пограничный Asc: характеристики соседнего знака могут примешиваться.",
]


class GeocodeRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class GenerateRequest(BaseModel):
    api_base_url: str = ""
    datetime_local: str | None = None
    birth_date_local: str | None = None
    timezone_mode: Literal["auto", "manual"] = "auto"
    timezone_offset: str = ""
    timezone_name: str | None = None
    profile_timezone_name: str | None = None
    birth_city: str | None = None
    birth_country: str | None = None
    birth_region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    house_system: str = "P"
    aspect_orb_profile: Literal["avestan", "western"] = "avestan"
    zodiac_mode: str = "tropical"
    sidereal_mode: str | None = None
    prompt_text: str = "Сделай гороскоп по этим данным."

    @model_validator(mode="after")
    def _validate_generate_identity(self) -> GenerateRequest:
        if not (self.datetime_local or self.birth_date_local):
            raise ValueError("birth date is required")
        return self


class RectificationIntervalsRequest(BaseModel):
    api_base_url: str = ""
    birth_date_local: str
    latitude: float
    longitude: float
    timezone_mode: Literal["auto", "manual"] = "auto"
    timezone_offset: str = ""
    timezone_name: str | None = None
    house_system: str = "P"
    zodiac_mode: str = "tropical"
    sidereal_mode: str | None = None


class DialogUserResponse(BaseModel):
    selected_option_id: str | None = None
    selected_option_text: str | None = None
    free_text: str | None = None


class RectificationDialogStartRequest(BaseModel):
    api_base_url: str = ""
    birth_date_local: str
    latitude: float
    longitude: float
    timezone_mode: Literal["auto", "manual"] = "auto"
    timezone_offset: str = ""
    timezone_name: str | None = None
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
    api_base_url: str = ""
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)


class EventAnswerWebInput(BaseModel):
    question_id: str
    event_type: str
    title: str | None = None
    date_text: str | None = None
    impact_level: int | None = None
    reversibility: str | None = None
    life_area: str | None = None
    repeat_count: int | None = None
    sequence_number: int | None = None
    notes: str | None = None
    user_skipped: bool = False


class RectificationEventsContinueRequest(BaseModel):
    api_base_url: str = ""
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)
    last_answer: EventAnswerWebInput | None = None


class RectificationEventsFinalizeRequest(BaseModel):
    api_base_url: str = ""
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)


class RectificationProRunRequest(BaseModel):
    api_base_url: str = ""
    payload: dict[str, Any]


class RectificationProExcelSheetRequest(BaseModel):
    sheet_name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    sort_default: list[str] = Field(default_factory=list)


class RectificationProExcelExportRequest(BaseModel):
    filename: str = "astrodvish-v2-combined-report.xlsx"
    sheets: list[RectificationProExcelSheetRequest] = Field(default_factory=list)


class AskQuestionOption(BaseModel):
    id: str
    text: str


class AskQuestionLLMResponse(BaseModel):
    type: Literal["ask_question"]
    step_index: int
    should_continue: bool
    debug_probability_text: str
    phase: Literal["element_detection", "modality_detection"] | None = None
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
    time_range_local: TimeRangeLocal | None = None
    time_ranges_local: list[TimeRangeLocal] = Field(default_factory=list)
    probability: float


class SecondaryCandidate(BaseModel):
    sign_name_ru: str
    sign_name_en: str
    probability: float
    time_ranges_local: list[TimeRangeLocal] = Field(default_factory=list)


class CandidateGroup(BaseModel):
    element: str | None = None
    modality: str | None = None
    signs: list[str] = Field(default_factory=list)
    reason: str


class FinalResultLLMResponse(BaseModel):
    type: Literal["final_result"]
    should_continue: bool
    primary_candidate: PrimaryCandidate
    secondary_candidates: list[SecondaryCandidate]
    summary_text: str
    explanation_text: str | None = None
    element_scores: dict[str, float] = Field(default_factory=dict)
    modality_scores: dict[str, float] = Field(default_factory=dict)
    sign_scores: dict[str, float] = Field(default_factory=dict)
    leading_element: str | None = None
    leading_modality: str | None = None
    candidate_group: CandidateGroup | None = None
    needs_more_questions: bool = False
    method_limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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


def _default_element_scores() -> dict[str, float]:
    return {"fire": 0.0, "earth": 0.0, "air": 0.0, "water": 0.0}


def _default_modality_scores() -> dict[str, float]:
    return {"cardinal": 0.0, "fixed": 0.0, "mutable": 0.0}


def _default_sign_scores() -> dict[str, float]:
    return {
        "Aries": 0.0,
        "Leo": 0.0,
        "Sagittarius": 0.0,
        "Capricorn": 0.0,
        "Taurus": 0.0,
        "Virgo": 0.0,
        "Libra": 0.0,
        "Aquarius": 0.0,
        "Gemini": 0.0,
        "Cancer": 0.0,
        "Scorpio": 0.0,
        "Pisces": 0.0,
    }


def _extract_stage1_answers(dialog_history: list[dict[str, Any]]) -> list[tuple[str, str]]:
    answers: list[tuple[str, str]] = []
    for index, item in enumerate(dialog_history):
        if item.get("role") != "assistant" or item.get("type") != "ask_question":
            continue
        question_id = item.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            continue
        if index + 1 >= len(dialog_history):
            continue
        user_item = dialog_history[index + 1]
        if user_item.get("role") != "user":
            continue
        option_id = user_item.get("selected_option_id")
        if isinstance(option_id, str) and option_id:
            answers.append((question_id, option_id))
    return answers


def _calculate_stage1_scores(
    dialog_history: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    element_scores = _default_element_scores()
    modality_scores = _default_modality_scores()
    sign_scores = _default_sign_scores()

    for question_id, option_id in _extract_stage1_answers(dialog_history):
        weights_by_element = QUESTION_OPTION_ELEMENT_MAP.get(question_id, {}).get(option_id, {})
        for element_name, delta in weights_by_element.items():
            if element_name not in element_scores:
                continue
            element_scores[element_name] += float(delta)
        modality_payload = QUESTION_OPTION_MODALITY_MAP.get(question_id, {}).get(option_id)
        if modality_payload:
            modality_name = modality_payload.get("modality")
            sign_name = modality_payload.get("sign")
            if isinstance(modality_name, str) and modality_name in modality_scores:
                modality_scores[modality_name] += 1.0
            if isinstance(sign_name, str) and sign_name in sign_scores:
                sign_scores[sign_name] += 1.0

    return element_scores, modality_scores, sign_scores


def _calculate_element_and_sign_scores(
    dialog_history: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float]]:
    element_scores, _, sign_scores = _calculate_stage1_scores(dialog_history)
    return element_scores, sign_scores


def _count_answers_for_question_ids(
    dialog_history: list[dict[str, Any]],
    question_ids: set[str] | tuple[str, ...],
) -> int:
    ids = set(question_ids)
    return sum(1 for qid, _ in _extract_stage1_answers(dialog_history) if qid in ids)


def _get_top_scores(score_map: dict[str, float]) -> list[tuple[str, float]]:
    positive = [(key, float(value)) for key, value in score_map.items() if float(value) > 0]
    positive.sort(key=lambda item: item[1], reverse=True)
    return positive


def _build_element_probability_text(
    element_scores: dict[str, float],
    modality_scores: dict[str, float],
    sign_scores: dict[str, float],
    *,
    phase: Literal["element_detection", "modality_detection"],
) -> str:
    top_elements = _get_top_scores(element_scores)
    top_signs = _get_top_scores(sign_scores)
    top_modalities = _get_top_scores(modality_scores)
    top_element_name = top_elements[0][0] if top_elements else None
    top_sign_names = [name for name, _ in top_signs[:3]]
    top_modality = top_modalities[0][0] if top_modalities else None

    sign_labels = _sign_label_map()
    top_signs_text = ", ".join(sign_labels.get(name, name) for name in top_sign_names) or "пока не определены"
    top_element_text = ELEMENT_LABELS.get(top_element_name, top_element_name) if top_element_name else "пока не определена"
    top_modality_text = MODALITY_LABELS.get(top_modality, top_modality) if top_modality else "пока не определён"
    phase_text = "Определение стихии" if phase == "element_detection" else "Определение креста"
    return (
        f"{phase_text}. Стихия: {top_element_text}. "
        f"Крест: {top_modality_text}. Возможные знаки: {top_signs_text}."
    )


def _parse_iso_local(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


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

        time_ranges_local = primary.get("time_ranges_local")
        valid_ranges_count = 0
        if isinstance(time_ranges_local, list):
            for idx, time_range_item in enumerate(time_ranges_local):
                if not isinstance(time_range_item, dict):
                    errors.append(
                        f"final_result.primary_candidate.time_ranges_local[{idx}] must be object"
                    )
                    continue
                if not _non_empty_string(time_range_item.get("start")):
                    errors.append(
                        f"final_result.primary_candidate.time_ranges_local[{idx}].start is empty"
                    )
                    continue
                if not _non_empty_string(time_range_item.get("end")):
                    errors.append(
                        f"final_result.primary_candidate.time_ranges_local[{idx}].end is empty"
                    )
                    continue
                valid_ranges_count += 1

        if valid_ranges_count == 0:
            time_range = primary.get("time_range_local")
            if not isinstance(time_range, dict):
                errors.append(
                    "final_result.primary_candidate.time_range_local or time_ranges_local is required"
                )
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
    element_scores, modality_scores, sign_scores = _calculate_stage1_scores(dialog_history)

    phase: Literal["element_detection", "modality_detection"] = "element_detection"
    next_question_id: str | None = None

    for question_id in STAGE1_ELEMENT_QUESTION_IDS:
        if question_id not in asked_question_ids:
            next_question_id = question_id
            break

    if next_question_id is None:
        phase = "modality_detection"
        leading_element_scores = _get_top_scores(element_scores)
        leading_element = leading_element_scores[0][0] if leading_element_scores else "earth"
        modality_questions = STAGE1_MODALITY_QUESTION_IDS_BY_ELEMENT.get(
            leading_element, STAGE1_MODALITY_QUESTION_IDS_BY_ELEMENT["earth"]
        )
        for question_id in modality_questions:
            if question_id not in asked_question_ids:
                next_question_id = question_id
                break

    if next_question_id is None:
        return None

    fallback_question = QUESTION_BANK_BY_ID.get(next_question_id)
    if not fallback_question:
        return None

    return {
        "type": "ask_question",
        "step_index": step_count + 1,
        "should_continue": True,
        "phase": phase,
        "debug_probability_text": _build_element_probability_text(
            element_scores,
            modality_scores,
            sign_scores,
            phase=phase,
        ),
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

    normalized.sort(key=lambda x: (_parse_iso_local(x["start_local"]), x["interval_index"]))
    return normalized


def _group_intervals_by_sign(
    rectification_document: dict[str, Any],
) -> list[dict[str, Any]]:
    intervals = _sorted_intervals(rectification_document)
    by_sign: dict[str, dict[str, Any]] = {}
    for item in intervals:
        sign_en = item["sign_name_en"]
        if sign_en not in by_sign:
            by_sign[sign_en] = {
                "sign_name_ru": item["sign_name_ru"],
                "sign_name_en": sign_en,
                "intervals": [],
                "duration_total_minutes": 0,
            }
        by_sign[sign_en]["intervals"].append(
            {
                "start": item["start_local"],
                "end": item["end_local"],
            }
        )
        by_sign[sign_en]["duration_total_minutes"] += max(int(item["duration_minutes"]), 0)

    grouped = list(by_sign.values())
    grouped.sort(
        key=lambda x: (
            -x["duration_total_minutes"],
            _parse_iso_local(x["intervals"][0]["start"]) if x["intervals"] else datetime.max,
        )
    )
    return grouped


def _sign_label_map() -> dict[str, str]:
    return {
        "Aries": "Овен",
        "Taurus": "Телец",
        "Gemini": "Близнецы",
        "Cancer": "Рак",
        "Leo": "Лев",
        "Virgo": "Дева",
        "Libra": "Весы",
        "Scorpio": "Скорпион",
        "Sagittarius": "Стрелец",
        "Capricorn": "Козерог",
        "Aquarius": "Водолей",
        "Pisces": "Рыбы",
    }


def _element_label_map() -> dict[str, str]:
    return dict(ELEMENT_LABELS)


def _sign_to_element_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for element_name, signs in ELEMENT_TO_SIGNS.items():
        for _, sign_en in signs:
            mapping[sign_en] = element_name
    return mapping


def _score_ties(score_map: dict[str, float]) -> list[str]:
    positive_scores = {key: float(value) for key, value in score_map.items() if float(value) > 0}
    if not positive_scores:
        return []
    top_score = max(positive_scores.values())
    epsilon = 1e-9
    return [key for key, value in positive_scores.items() if abs(value - top_score) <= epsilon]


def _is_close_leader(score_map: dict[str, float], *, threshold: float = STAGE1_CLOSE_SCORE_GAP) -> bool:
    top_scores = _get_top_scores(score_map)
    if len(top_scores) < 2:
        return False
    return (top_scores[0][1] - top_scores[1][1]) <= threshold


def _top_score_key(score_map: dict[str, float]) -> str | None:
    top_scores = _get_top_scores(score_map)
    if not top_scores:
        return None
    return top_scores[0][0]


def _has_strong_stage1_leader(dialog_history: list[dict[str, Any]]) -> bool:
    element_scores, modality_scores, sign_scores = _calculate_stage1_scores(dialog_history)
    answered_element_questions = _count_answers_for_question_ids(
        dialog_history, set(STAGE1_ELEMENT_QUESTION_IDS)
    )
    if answered_element_questions < 5:
        return False
    total_element_score = sum(element_scores.values())
    if total_element_score <= 0:
        return False
    top_elements = _score_ties(element_scores)
    if len(top_elements) != 1:
        return False
    top_element_score = element_scores[top_elements[0]]
    if (top_element_score / total_element_score) < STAGE1_EARLY_FINAL_THRESHOLD:
        return False

    if sum(modality_scores.values()) > 0 and _is_close_leader(modality_scores):
        return False
    top_signs = _score_ties(sign_scores)
    return len(top_signs) == 1


def _should_allow_stage1_finalization(
    *,
    dialog_history: list[dict[str, Any]],
    mode: Literal["choose_next_question", "finalize_now"],
) -> bool:
    answered_questions = len(_extract_stage1_answers(dialog_history))
    modality_answers = _count_answers_for_question_ids(dialog_history, STAGE1_MODALITY_QUESTION_IDS)
    if answered_questions >= STAGE1_MAX_QUESTIONS:
        return True
    if answered_questions >= STAGE1_MIN_QUESTIONS and modality_answers >= 4:
        return True
    if mode == "finalize_now":
        return modality_answers >= 4 and _has_strong_stage1_leader(dialog_history)
    return False


def _build_secondary_candidates_from_signs(
    signs: list[str],
    grouped_by_sign: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sign_labels = _sign_label_map()
    if not signs:
        return []
    probability = round(1 / len(signs), 2)
    secondary: list[dict[str, Any]] = []
    for sign_name_en in signs:
        candidate = grouped_by_sign.get(sign_name_en)
        if not candidate:
            continue
        secondary.append(
            {
                "sign_name_ru": candidate["sign_name_ru"] or sign_labels.get(sign_name_en, sign_name_en),
                "sign_name_en": sign_name_en,
                "time_ranges_local": candidate["intervals"],
                "probability": probability,
            }
        )
    return secondary


def _build_scored_safe_final_result(
    *,
    rectification_document: dict[str, Any],
    element_scores: dict[str, float],
    modality_scores: dict[str, float],
    sign_scores: dict[str, float],
    reason: str,
) -> dict[str, Any] | None:
    candidates = _group_intervals_by_sign(rectification_document)
    grouped_by_sign = {item["sign_name_en"]: item for item in candidates}
    sign_labels = _sign_label_map()
    leading_element = _top_score_key(element_scores)
    leading_modality = _top_score_key(modality_scores)

    warnings_local: list[str] = []
    if _is_close_leader(element_scores):
        warnings_local.append("element_scores_are_close")
    if _is_close_leader(modality_scores):
        warnings_local.append("modality_scores_are_close")
    if _is_close_leader(sign_scores):
        warnings_local.append("sign_scores_are_close")

    ranked_signs = [sign_name for sign_name, _ in _get_top_scores(sign_scores) if sign_name in grouped_by_sign]
    if leading_element and leading_modality:
        matrix_sign = ELEMENT_MODALITY_TO_SIGN.get(leading_element, {}).get(leading_modality, (None, None))[1]
        if isinstance(matrix_sign, str) and matrix_sign in grouped_by_sign and matrix_sign not in ranked_signs:
            ranked_signs.insert(0, matrix_sign)
        elif isinstance(matrix_sign, str) and matrix_sign in grouped_by_sign:
            ranked_signs = [matrix_sign, *[item for item in ranked_signs if item != matrix_sign]]

    if not ranked_signs and leading_element:
        ranked_signs = [
            sign_en for _, sign_en in ELEMENT_TO_SIGNS.get(leading_element, ()) if sign_en in grouped_by_sign
        ]
    if not ranked_signs:
        ranked_signs = [item["sign_name_en"] for item in candidates]
    if not ranked_signs:
        return None

    primary_sign = ranked_signs[0]
    primary_candidate = grouped_by_sign.get(primary_sign)
    if not primary_candidate:
        return None

    total_sign_score = sum(value for value in sign_scores.values() if value > 0)
    primary_score = float(sign_scores.get(primary_sign, 0.0))
    probability = round((primary_score / total_sign_score), 2) if total_sign_score > 0 else 0.34
    if probability <= 0:
        probability = 0.34

    secondary_candidates = _build_secondary_candidates_from_signs(ranked_signs[1:4], grouped_by_sign)
    needs_more_questions = bool(warnings_local)
    candidate_group: dict[str, Any] | None = None
    if needs_more_questions:
        close_signs = ranked_signs[:3] if len(ranked_signs) >= 2 else ranked_signs
        candidate_group = {
            "element": leading_element,
            "modality": leading_modality,
            "signs": close_signs,
            "reason": "close_scores",
        }

    signs_text = ", ".join(sign_labels.get(name, name) for name in ranked_signs[:3])
    leading_element_label = ELEMENT_LABELS.get(leading_element, "не определена")
    leading_modality_label = MODALITY_LABELS.get(leading_modality, "не определён")
    explanation_text = (
        f"Стихия {leading_element_label.lower()} выражена сильнее всего. "
        f"По способу проявления энергии лидирует {leading_modality_label} крест. "
        f"Поэтому основной кандидат — {primary_candidate['sign_name_ru']}."
    )
    if needs_more_questions:
        explanation_text += (
            " Вторичные кандидаты остаются для проверки через события жизни."
        )
    summary_text = (
        "Ответ модели не получен, поэтому использован резервный расчёт по вашим ответам. "
        f"Стихия: {leading_element_label}. "
        f"Крест: {leading_modality_label}. "
        f"Основной кандидат: {primary_candidate['sign_name_ru']}."
    )
    if needs_more_questions:
        summary_text += (
            f" Кандидаты близки ({signs_text}). "
            "Для уточнения переходите к Stage 2 (события жизни)."
        )

    return {
        "type": "final_result",
        "should_continue": False,
        "primary_candidate": {
            "sign_name_ru": primary_candidate["sign_name_ru"],
            "sign_name_en": primary_candidate["sign_name_en"],
            "time_ranges_local": primary_candidate["intervals"],
            "time_range_local": primary_candidate["intervals"][0],
            "probability": probability,
        },
        "secondary_candidates": secondary_candidates,
        "element_scores": element_scores,
        "modality_scores": modality_scores,
        "sign_scores": sign_scores,
        "leading_element": leading_element,
        "leading_modality": leading_modality,
        "candidate_group": candidate_group,
        "needs_more_questions": needs_more_questions,
        "warnings": warnings_local,
        "method_limitations": STAGE1_METHOD_LIMITATIONS,
        "explanation_text": explanation_text,
        "summary_text": summary_text,
    }


def _normalize_time_ranges(primary_candidate: dict[str, Any]) -> list[dict[str, str]]:
    ranges = primary_candidate.get("time_ranges_local")
    normalized: list[dict[str, str]] = []
    if isinstance(ranges, list):
        for item in ranges:
            if not isinstance(item, dict):
                continue
            start = item.get("start")
            end = item.get("end")
            if _non_empty_string(start) and _non_empty_string(end):
                normalized.append({"start": start.strip(), "end": end.strip()})
    if normalized:
        normalized.sort(key=lambda item: _parse_iso_local(item["start"]))
        return normalized

    single = primary_candidate.get("time_range_local")
    if isinstance(single, dict):
        start = single.get("start")
        end = single.get("end")
        if _non_empty_string(start) and _non_empty_string(end):
            return [{"start": start.strip(), "end": end.strip()}]
    return []


def _merge_candidate_ranges_with_document(
    *,
    candidate: dict[str, Any],
    rectification_document: dict[str, Any],
) -> list[dict[str, str]]:
    own_ranges = _normalize_time_ranges(candidate)
    sign_name_en = candidate.get("sign_name_en")
    if not isinstance(sign_name_en, str) or not sign_name_en:
        return own_ranges

    grouped = _group_intervals_by_sign(rectification_document)
    for sign_info in grouped:
        if sign_info["sign_name_en"] == sign_name_en and sign_info["intervals"]:
            return sign_info["intervals"]
    return own_ranges


def _build_safe_final_result(
    *,
    rectification_document: dict[str, Any],
    dialog_history: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    element_scores, modality_scores, sign_scores = _calculate_stage1_scores(dialog_history)
    scored_result = _build_scored_safe_final_result(
        rectification_document=rectification_document,
        element_scores=element_scores,
        modality_scores=modality_scores,
        sign_scores=sign_scores,
        reason=reason,
    )
    if scored_result is not None:
        return scored_result

    candidates = _group_intervals_by_sign(rectification_document)
    if candidates:
        primary = candidates[0]
        secondary_source = candidates[1:4]
        secondary_probabilities = [0.22, 0.17, 0.11]
        secondary = []
        for index, item in enumerate(secondary_source):
            secondary.append(
                {
                    "sign_name_ru": item["sign_name_ru"],
                    "sign_name_en": item["sign_name_en"],
                    "time_ranges_local": item["intervals"],
                    "probability": secondary_probabilities[index],
                }
            )
        return {
            "type": "final_result",
            "should_continue": False,
            "primary_candidate": {
                "sign_name_ru": primary["sign_name_ru"],
                "sign_name_en": primary["sign_name_en"],
                "time_ranges_local": primary["intervals"],
                "time_range_local": primary["intervals"][0],
                "probability": 0.34,
            },
            "secondary_candidates": secondary,
            "element_scores": element_scores,
            "modality_scores": modality_scores,
            "sign_scores": sign_scores,
            "leading_element": None,
            "leading_modality": None,
            "candidate_group": None,
            "needs_more_questions": True,
            "warnings": ["technical_fallback_used"],
            "method_limitations": STAGE1_METHOD_LIMITATIONS,
            "summary_text": (
                "Ответы пользователя не дали пригодного лидера, поэтому использован резервный расчёт. "
                "Уверенность намеренно снижена."
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
            "time_ranges_local": [{"start": start_local, "end": end_local}],
            "time_range_local": {"start": start_local, "end": end_local},
            "probability": 0.05,
        },
        "secondary_candidates": [],
        "element_scores": element_scores,
        "modality_scores": modality_scores,
        "sign_scores": sign_scores,
        "leading_element": None,
        "leading_modality": None,
        "candidate_group": None,
        "needs_more_questions": True,
        "warnings": ["technical_fallback_used"],
        "method_limitations": STAGE1_METHOD_LIMITATIONS,
        "summary_text": (
            "Ответы пользователя не дали пригодного лидера, поэтому использован резервный расчёт. "
            "Не найдено пригодных интервалов."
        ),
    }


def _apply_free_text_policy(llm_json: dict[str, Any]) -> dict[str, Any]:
    if llm_json.get("type") == "ask_question":
        llm_json = dict(llm_json)
        llm_json["allow_free_text"] = False
    return llm_json


def _normalize_stage1_final_result_payload(
    *,
    llm_json: dict[str, Any],
    rectification_document: dict[str, Any],
    dialog_history: list[dict[str, Any]],
) -> dict[str, Any]:
    if llm_json.get("type") != "final_result":
        return llm_json

    result = dict(llm_json)
    primary = dict(result.get("primary_candidate") or {})
    primary_ranges = _merge_candidate_ranges_with_document(
        candidate=primary,
        rectification_document=rectification_document,
    )
    if primary_ranges:
        primary["time_ranges_local"] = primary_ranges
        primary["time_range_local"] = primary_ranges[0]
    result["primary_candidate"] = primary

    secondary_out: list[dict[str, Any]] = []
    for item in result.get("secondary_candidates") or []:
        if not isinstance(item, dict):
            continue
        secondary_item = dict(item)
        secondary_ranges = _merge_candidate_ranges_with_document(
            candidate=secondary_item,
            rectification_document=rectification_document,
        )
        if secondary_ranges:
            secondary_item["time_ranges_local"] = secondary_ranges
        secondary_out.append(secondary_item)
    result["secondary_candidates"] = secondary_out

    element_scores, modality_scores, sign_scores = _calculate_stage1_scores(dialog_history)
    result["element_scores"] = element_scores
    result["modality_scores"] = modality_scores
    result["sign_scores"] = sign_scores
    result["leading_element"] = result.get("leading_element") or _top_score_key(element_scores)
    result["leading_modality"] = result.get("leading_modality") or _top_score_key(modality_scores)
    result["candidate_group"] = result.get("candidate_group")
    result["needs_more_questions"] = bool(result.get("needs_more_questions", False))
    result["method_limitations"] = result.get("method_limitations") or STAGE1_METHOD_LIMITATIONS
    result["warnings"] = list(result.get("warnings") or [])

    return result


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
    can_finalize_now = _should_allow_stage1_finalization(dialog_history=dialog_history, mode=mode)

    if mode == "choose_next_question" and step_count >= RECT_MAX_STEPS:
        warnings.append("max_steps_reached_safe_finalization")
        return {
            "llm_json": _build_safe_final_result(
                rectification_document=rectification_document,
                dialog_history=dialog_history,
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
        if mode == "finalize_now" and not can_finalize_now:
            warnings.append("min_questions_not_reached")
            fallback_llm_json = _build_safe_question(
                dialog_history=dialog_history,
                step_count=step_count,
            )
            if fallback_llm_json is None:
                fallback_llm_json = _build_safe_final_result(
                    rectification_document=rectification_document,
                    dialog_history=dialog_history,
                    reason="no_safe_question_available",
                )
        elif mode == "finalize_now" or can_finalize_now:
            fallback_llm_json = _build_safe_final_result(
                rectification_document=rectification_document,
                dialog_history=dialog_history,
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
                    dialog_history=dialog_history,
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

        if mode == "finalize_now" and not can_finalize_now:
            warnings.append("min_questions_not_reached")
            fallback_llm_json = _build_safe_question(
                dialog_history=dialog_history,
                step_count=step_count,
            )
            if fallback_llm_json is None:
                fallback_llm_json = _build_safe_final_result(
                    rectification_document=rectification_document,
                    dialog_history=dialog_history,
                    reason="no_safe_question_available",
                )
        elif mode == "finalize_now" or can_finalize_now:
            fallback_llm_json = _build_safe_final_result(
                rectification_document=rectification_document,
                dialog_history=dialog_history,
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
                    dialog_history=dialog_history,
                    reason="no_safe_question_available",
                )

        llm_result["llm_json"] = fallback_llm_json
    elif llm_result["llm_json"].get("type") == "final_result" and not can_finalize_now:
        warnings.append("min_questions_not_reached")
        fallback_question = _build_safe_question(
            dialog_history=dialog_history,
            step_count=step_count,
        )
        if fallback_question is None:
            fallback_question = _build_safe_final_result(
                rectification_document=rectification_document,
                dialog_history=dialog_history,
                reason="no_safe_question_available",
            )
        llm_result["llm_json"] = fallback_question

    llm_result["llm_json"] = _normalize_stage1_final_result_payload(
        llm_json=llm_result["llm_json"],
        rectification_document=rectification_document,
        dialog_history=dialog_history,
    )
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


def _load_llm_provider() -> str:
    provider = _env("LLM_PROVIDER", "openai").strip().lower()
    if provider not in {"openai", "openrouter"}:
        raise HTTPException(status_code=500, detail="LLM_PROVIDER must be openai or openrouter")
    return provider


def _load_openai_settings() -> dict[str, Any]:
    api_key = _env("OPENAI_API_KEY", "").strip()
    base_url = _env("OPENAI_BASE_URL", OPENAI_DEFAULT_BASE_URL).strip().rstrip("/")
    timeout_raw = _env("OPENAI_TIMEOUT_SECONDS", "120").strip()
    hard_limit_raw = _env("OPENAI_MAX_TOKENS_HARD_LIMIT", "20000").strip()
    default_max_raw = _env("OPENAI_MAX_TOKENS_DEFAULT", "6000").strip()
    stage1_max_raw = _env("OPENAI_MAX_TOKENS_STAGE1", "3000").strip()
    generate_max_raw = _env("OPENAI_MAX_TOKENS_GENERATE", "8000").strip()
    pro_max_raw = _env("OPENAI_MAX_TOKENS_PRO", "12000").strip()

    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    try:
        timeout_seconds = int(timeout_raw)
        hard_limit = int(hard_limit_raw)
        max_default = int(default_max_raw)
        max_stage1 = int(stage1_max_raw)
        max_generate = int(generate_max_raw)
        max_pro = int(pro_max_raw)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="OpenAI token/timeouts must be integers") from exc

    if timeout_seconds <= 0:
        raise HTTPException(status_code=500, detail="OPENAI_TIMEOUT_SECONDS must be > 0")
    if hard_limit <= 0:
        raise HTTPException(status_code=500, detail="OPENAI_MAX_TOKENS_HARD_LIMIT must be > 0")
    for name, value in {
        "OPENAI_MAX_TOKENS_DEFAULT": max_default,
        "OPENAI_MAX_TOKENS_STAGE1": max_stage1,
        "OPENAI_MAX_TOKENS_GENERATE": max_generate,
        "OPENAI_MAX_TOKENS_PRO": max_pro,
    }.items():
        if value <= 0:
            raise HTTPException(status_code=500, detail=f"{name} must be > 0")

    models_by_scenario = {
        OPENROUTER_REQUEST_KIND_DEFAULT: _env("OPENAI_MODEL_DEFAULT", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        OPENROUTER_REQUEST_KIND_GENERATE: _env("OPENAI_MODEL_GENERATE", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        OPENROUTER_REQUEST_KIND_STAGE1: _env("OPENAI_MODEL_STAGE1", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
        OPENROUTER_REQUEST_KIND_PRO: _env("OPENAI_MODEL_PRO", "gpt-5.4-mini").strip() or "gpt-5.4-mini",
    }
    fallback_models_by_scenario = {
        OPENROUTER_REQUEST_KIND_DEFAULT: _env("OPENAI_MODEL_DEFAULT_FALLBACK", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        OPENROUTER_REQUEST_KIND_GENERATE: _env("OPENAI_MODEL_GENERATE_FALLBACK", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        OPENROUTER_REQUEST_KIND_STAGE1: _env("OPENAI_MODEL_STAGE1_FALLBACK", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        OPENROUTER_REQUEST_KIND_PRO: _env("OPENAI_MODEL_PRO_FALLBACK", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
    }

    return {
        "api_key": api_key,
        "base_url": base_url or OPENAI_DEFAULT_BASE_URL,
        "timeout_seconds": timeout_seconds,
        "max_tokens_default": max_default,
        "max_tokens_stage1": max_stage1,
        "max_tokens_generate": max_generate,
        "max_tokens_pro": max_pro,
        "max_tokens_hard_limit": hard_limit,
        "models_by_scenario": models_by_scenario,
        "fallback_models_by_scenario": fallback_models_by_scenario,
    }


def _resolve_openai_max_tokens(
    *,
    settings: dict[str, Any],
    request_kind: str = OPENROUTER_REQUEST_KIND_DEFAULT,
    requested_max_tokens: int | None = None,
) -> tuple[int, int]:
    configured_by_kind = {
        OPENROUTER_REQUEST_KIND_DEFAULT: settings["max_tokens_default"],
        OPENROUTER_REQUEST_KIND_STAGE1: settings["max_tokens_stage1"],
        OPENROUTER_REQUEST_KIND_GENERATE: settings["max_tokens_generate"],
        OPENROUTER_REQUEST_KIND_PRO: settings["max_tokens_pro"],
    }
    requested = requested_max_tokens
    if requested is None:
        requested = configured_by_kind.get(request_kind, settings["max_tokens_default"])
    applied = min(int(requested), int(settings["max_tokens_hard_limit"]))
    return int(requested), applied


def _load_openrouter_settings() -> dict[str, Any]:
    api_key = _env("OPENROUTER_API_KEY", "").strip()
    api_key_backup_1 = _env("OPENROUTER_API_KEY_BACKUP_1", "").strip()
    api_key_backup_2 = _env("OPENROUTER_API_KEY_BACKUP_2", "").strip()
    base_url = _env("OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_BASE_URL).strip().rstrip("/")
    model = _env("OPENROUTER_MODEL", "openai/gpt-5.4-mini").strip()
    llm_model_generate_primary = _env("LLM_MODEL_GENERATE_PRIMARY", "").strip()
    llm_model_generate_fallback = _env("LLM_MODEL_GENERATE_FALLBACK", "").strip()
    llm_model_stage1_primary = _env("LLM_MODEL_STAGE1_PRIMARY", "").strip()
    llm_model_stage1_fallback = _env("LLM_MODEL_STAGE1_FALLBACK", "").strip()
    llm_model_pro_primary = _env("LLM_MODEL_PRO_PRIMARY", "").strip()
    llm_model_pro_fallback = _env("LLM_MODEL_PRO_FALLBACK", "").strip()
    max_llm_attempts_raw = _env("MAX_LLM_ATTEMPTS", "4").strip()
    site_url = _env("OPENROUTER_SITE_URL", "").strip()
    app_name = _env("OPENROUTER_APP_NAME", "AstroDvish").strip() or "AstroDvish"
    timeout_raw = _env("OPENROUTER_TIMEOUT_SECONDS", "120").strip()
    max_tokens_default_raw = _env("OPENROUTER_MAX_TOKENS_DEFAULT", "6000").strip()
    max_tokens_stage1_raw = _env("OPENROUTER_MAX_TOKENS_STAGE1", "2000").strip()
    max_tokens_generate_raw = _env("OPENROUTER_MAX_TOKENS_GENERATE", "8000").strip()
    max_tokens_pro_raw = _env("OPENROUTER_MAX_TOKENS_PRO", "12000").strip()
    max_tokens_hard_limit_raw = _env("OPENROUTER_MAX_TOKENS_HARD_LIMIT", "20000").strip()

    try:
        max_llm_attempts = int(max_llm_attempts_raw)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="MAX_LLM_ATTEMPTS must be integer") from exc
    if max_llm_attempts <= 0:
        raise HTTPException(status_code=500, detail="MAX_LLM_ATTEMPTS must be > 0")

    api_key_slots: list[dict[str, str]] = []
    if api_key:
        api_key_slots.append({"name": "primary", "value": api_key})
    if api_key_backup_1:
        api_key_slots.append({"name": "backup_1", "value": api_key_backup_1})
    if api_key_backup_2:
        api_key_slots.append({"name": "backup_2", "value": api_key_backup_2})

    if not api_key_slots:
        raise HTTPException(
            status_code=500,
            detail=(
                "OPENROUTER_API_KEY is not set. Configure primary or backup keys in environment "
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

    try:
        max_tokens_default = int(max_tokens_default_raw)
        max_tokens_stage1 = int(max_tokens_stage1_raw)
        max_tokens_generate = int(max_tokens_generate_raw)
        max_tokens_pro = int(max_tokens_pro_raw)
        max_tokens_hard_limit = int(max_tokens_hard_limit_raw)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="OPENROUTER max tokens settings must be integers") from exc

    token_settings = {
        OPENROUTER_REQUEST_KIND_DEFAULT: max_tokens_default,
        OPENROUTER_REQUEST_KIND_STAGE1: max_tokens_stage1,
        OPENROUTER_REQUEST_KIND_GENERATE: max_tokens_generate,
        OPENROUTER_REQUEST_KIND_PRO: max_tokens_pro,
    }
    for request_kind, token_value in token_settings.items():
        if token_value <= 0:
            raise HTTPException(
                status_code=500,
                detail=f"OPENROUTER max tokens for {request_kind} must be > 0",
            )
    if max_tokens_hard_limit <= 0:
        raise HTTPException(status_code=500, detail="OPENROUTER_MAX_TOKENS_HARD_LIMIT must be > 0")

    # Backward compatibility: OPENROUTER_MODEL_* can still define defaults,
    # but scenario-specific LLM_MODEL_* has priority.
    generate_primary_model = (
        llm_model_generate_primary
        or _env("OPENROUTER_MODEL_HOROSCOPE", "").strip()
        or model
    )
    generate_fallback_model = llm_model_generate_fallback or "openai/gpt-4.1-mini"
    stage1_primary_model = (
        llm_model_stage1_primary
        or _env("OPENROUTER_MODEL_RECTIFICATION", "").strip()
        or model
    )
    stage1_fallback_model = llm_model_stage1_fallback or "openai/gpt-4.1-mini"
    pro_primary_model = llm_model_pro_primary or model
    pro_fallback_model = llm_model_pro_fallback or "openai/gpt-4.1-mini"

    return {
        "api_key_slots": api_key_slots,
        "max_llm_attempts": max_llm_attempts,
        "base_url": base_url or OPENROUTER_DEFAULT_BASE_URL,
        "model": model,
        "models_by_scenario": {
            OPENROUTER_REQUEST_KIND_DEFAULT: {
                "primary": model,
                "fallback": generate_fallback_model or model,
            },
            OPENROUTER_REQUEST_KIND_GENERATE: {
                "primary": generate_primary_model,
                "fallback": generate_fallback_model or generate_primary_model,
            },
            OPENROUTER_REQUEST_KIND_STAGE1: {
                "primary": stage1_primary_model,
                "fallback": stage1_fallback_model or stage1_primary_model,
            },
            OPENROUTER_REQUEST_KIND_PRO: {
                "primary": pro_primary_model,
                "fallback": pro_fallback_model or pro_primary_model,
            },
        },
        "site_url": site_url,
        "app_name": app_name,
        "timeout_seconds": timeout_seconds,
        "max_tokens_default": max_tokens_default,
        "max_tokens_stage1": max_tokens_stage1,
        "max_tokens_generate": max_tokens_generate,
        "max_tokens_pro": max_tokens_pro,
        "max_tokens_hard_limit": max_tokens_hard_limit,
    }


def _resolve_openrouter_max_tokens(
    *,
    settings: dict[str, Any],
    request_kind: str = OPENROUTER_REQUEST_KIND_DEFAULT,
    requested_max_tokens: int | None = None,
) -> tuple[int, int]:
    configured_by_kind = {
        OPENROUTER_REQUEST_KIND_DEFAULT: settings["max_tokens_default"],
        OPENROUTER_REQUEST_KIND_STAGE1: settings["max_tokens_stage1"],
        OPENROUTER_REQUEST_KIND_GENERATE: settings["max_tokens_generate"],
        OPENROUTER_REQUEST_KIND_PRO: settings["max_tokens_pro"],
    }
    requested = requested_max_tokens
    if requested is None:
        requested = configured_by_kind.get(request_kind, settings["max_tokens_default"])
    applied = min(int(requested), int(settings["max_tokens_hard_limit"]))
    return int(requested), applied


def _extract_openrouter_affordable_max_tokens(raw_error: str) -> int | None:
    if not raw_error:
        return None
    match = re.search(r"can only afford\s+(\d+)", raw_error, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        affordable_tokens = int(match.group(1))
    except ValueError:
        return None
    return affordable_tokens if affordable_tokens > 0 else None


def _classify_openrouter_error(status_code: int, raw_error: str) -> str:
    lowered = raw_error.lower()
    if status_code in {401, 403}:
        return "unauthorized_or_forbidden"
    if status_code == 429:
        return "rate_limited"
    if status_code in {500, 502, 503, 504}:
        return "provider_unavailable"
    if status_code == 402:
        if "prompt tokens limit exceeded" in lowered:
            return "insufficient_credits_or_max_tokens"
        if "requires more credits" in lowered or "can only afford" in lowered:
            return "insufficient_credits_or_max_tokens"
        return "insufficient_credits_or_max_tokens"
    return "upstream_error"


def _classify_openai_error(status_code: int, raw_error: str) -> str:
    lowered = raw_error.lower()
    if status_code in {401, 403}:
        return "unauthorized_or_forbidden"
    if status_code == 429:
        return "rate_limited"
    if status_code in {500, 502, 503, 504}:
        return "provider_unavailable"
    if status_code == 400 and "max_tokens" in lowered:
        return "invalid_max_tokens"
    if status_code == 408:
        return "timeout"
    return "upstream_error"


def _is_openai_retryable_reason(reason: str) -> bool:
    return reason in {"rate_limited", "provider_unavailable", "timeout", "network_or_timeout"}


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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_birth_date_local(value: str | None) -> date:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail="birth date is required")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid birth_date_local format") from exc


def _safe_coordinates_or_placeholder(
    latitude: float | None,
    longitude: float | None,
) -> tuple[float, float, str]:
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return float(latitude), float(longitude), "provided_coordinates"
    return NO_TIME_PLACEHOLDER_LATITUDE, NO_TIME_PLACEHOLDER_LONGITUDE, "placeholder_for_planets_only"


def _guess_timezone_name_from_region(*, region: str | None) -> str | None:
    if not isinstance(region, str) or not region.strip():
        return None
    normalized_region = region.strip().lower().replace("-", " ").replace("_", " ")
    matches = {
        tz_name
        for tz_name in available_timezones()
        if tz_name.split("/")[-1].replace("_", " ").lower() == normalized_region
    }
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _resolve_no_time_timezone_context(payload: GenerateRequest) -> tuple[dict[str, Any], list[str]]:
    birth_date = _parse_birth_date_local(payload.birth_date_local)
    local_noon = datetime.combine(birth_date, datetime.min.time()).replace(hour=12)
    datetime_local = f"{birth_date.isoformat()}T{NO_TIME_FALLBACK_LOCAL_CLOCK}:00"
    warnings: list[str] = []

    if payload.timezone_mode == "manual":
        if not TZ_OFFSET_PATTERN.match(payload.timezone_offset):
            raise HTTPException(status_code=422, detail="Invalid timezone_offset format. Use +03:00")
        sign = 1 if payload.timezone_offset[0] == "+" else -1
        hours = int(payload.timezone_offset[1:3])
        minutes = int(payload.timezone_offset[4:6])
        offset = timedelta(hours=hours, minutes=minutes) * sign
        local_aware = local_noon.replace(tzinfo=timezone(offset))
        warnings.append("manual_timezone_offset_used")
        return (
            {
                "mode": "manual",
                "timezone_name": payload.timezone_name or payload.profile_timezone_name,
                "timezone_offset": payload.timezone_offset,
                "timezone_source": "manual_offset",
                "datetime_local": datetime_local,
                "datetime_utc": local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "clarification_needed": False,
            },
            warnings,
        )

    timezone_name = (payload.timezone_name or "").strip()
    timezone_source = "provided_timezone_name"
    clarification_needed = False

    if not timezone_name and payload.profile_timezone_name:
        timezone_name = payload.profile_timezone_name.strip()
        timezone_source = "profile_timezone_name"

    if not timezone_name and isinstance(payload.latitude, (int, float)) and isinstance(payload.longitude, (int, float)):
        try:
            timezone_name = resolve_timezone_name(latitude=float(payload.latitude), longitude=float(payload.longitude))
            timezone_source = "auto_by_coordinates"
        except Exception:
            timezone_name = ""

    if not timezone_name:
        timezone_name = _guess_timezone_name_from_region(region=payload.birth_region or payload.birth_city)
        if timezone_name:
            timezone_source = "region_unique_match"

    if not timezone_name:
        clarification_needed = True
        warnings.append("timezone_clarification_needed_no_time_fallback_utc")
        local_aware = local_noon.replace(tzinfo=timezone.utc)
        return (
            {
                "mode": "auto",
                "timezone_name": "UTC",
                "timezone_offset": "+00:00",
                "timezone_source": "fallback_utc_due_timezone_ambiguity",
                "datetime_local": datetime_local,
                "datetime_utc": local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "clarification_needed": clarification_needed,
            },
            warnings,
        )

    try:
        timezone_info = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Invalid timezone_name") from exc

    local_aware = local_noon.replace(tzinfo=timezone_info)
    auto_offset = _format_offset(local_aware)
    if payload.timezone_offset and payload.timezone_offset != auto_offset:
        warnings.append("manual_offset_ignored_in_auto_timezone_mode")

    return (
        {
            "mode": "auto",
            "timezone_name": timezone_name,
            "timezone_offset": auto_offset,
            "timezone_source": timezone_source,
            "datetime_local": datetime_local,
            "datetime_utc": local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "clarification_needed": clarification_needed,
        },
        warnings,
    )


def _resolve_timezone_context(payload: GenerateRequest) -> tuple[dict[str, Any], list[str]]:
    if not payload.datetime_local:
        return _resolve_no_time_timezone_context(payload)

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
            if not isinstance(payload.latitude, (int, float)) or not isinstance(payload.longitude, (int, float)):
                raise HTTPException(status_code=422, detail="latitude and longitude are required for full forecast auto timezone")
            try:
                timezone_name = resolve_timezone_name(latitude=float(payload.latitude), longitude=float(payload.longitude))
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


def _compact_llm_chart_context(chart: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(chart, dict):
        return {}

    objects_raw = chart.get("objects")
    compact_objects: dict[str, dict[str, Any]] = {}
    if isinstance(objects_raw, dict):
        for name, obj in objects_raw.items():
            if not isinstance(obj, dict):
                continue
            compact_objects[str(name)] = {
                "sign_name_en": obj.get("sign_name_en"),
                "sign_name_ru": obj.get("sign_name_ru"),
                "sign_degree": obj.get("sign_degree"),
                "absolute_degree_0_360": obj.get("absolute_degree_0_360"),
                "house": obj.get("house"),
                "retrograde": obj.get("retrograde"),
                "speed": obj.get("speed"),
            }

    houses_raw = chart.get("houses")
    compact_houses: dict[str, Any] = {}
    if isinstance(houses_raw, dict):
        compact_houses["house_system"] = houses_raw.get("house_system")
        cusp_details = houses_raw.get("cusp_details")
        if isinstance(cusp_details, dict):
            compact_houses["cusp_details"] = {
                str(index): {
                    "sign_name_en": cusp.get("sign_name_en"),
                    "sign_name_ru": cusp.get("sign_name_ru"),
                    "sign_degree": cusp.get("sign_degree"),
                    "absolute_degree_0_360": cusp.get("absolute_degree_0_360"),
                }
                for index, cusp in cusp_details.items()
                if isinstance(cusp, dict)
            }

    angles_raw = chart.get("angles")
    compact_angles: dict[str, Any] = {}
    if isinstance(angles_raw, dict):
        for key in ("asc", "mc", "desc", "ic"):
            value = angles_raw.get(key)
            if isinstance(value, (int, float)):
                compact_angles[key] = value

    compact_aspects: list[dict[str, Any]] = []
    aspects_raw = chart.get("aspects")
    if isinstance(aspects_raw, list):
        for aspect in aspects_raw[:80]:
            if not isinstance(aspect, dict):
                continue
            compact_aspects.append(
                {
                    "object_a": aspect.get("object_a"),
                    "object_b": aspect.get("object_b"),
                    "aspect_type": aspect.get("aspect_type"),
                    "exact_angle": aspect.get("exact_angle"),
                    "actual_angle": aspect.get("actual_angle"),
                    "orb": aspect.get("orb"),
                    "applying": aspect.get("applying"),
                }
            )

    return {
        "objects": compact_objects,
        "angles": compact_angles,
        "houses": compact_houses,
        "aspects": compact_aspects,
        "meta": chart.get("meta"),
    }


def _sanitize_chart_for_no_time(chart: dict[str, Any]) -> dict[str, Any]:
    objects_raw = chart.get("objects") if isinstance(chart, dict) else {}
    sanitized_objects: dict[str, dict[str, Any]] = {}
    if isinstance(objects_raw, dict):
        for name, obj in objects_raw.items():
            if not isinstance(obj, dict):
                continue
            sanitized_objects[str(name)] = {
                **obj,
                "house": None,
            }

    houses_raw = chart.get("houses") if isinstance(chart, dict) else {}
    meta = dict(chart.get("meta") or {}) if isinstance(chart, dict) else {}
    meta["forecast_precision"] = "birth_date_no_time"
    meta["houses_available"] = False
    meta["asc_mc_available"] = False

    return {
        "input": dict(chart.get("input") or {}) if isinstance(chart, dict) else {},
        "normalized": dict(chart.get("normalized") or {}) if isinstance(chart, dict) else {},
        "objects": sanitized_objects,
        "aspects": [],
        "houses": {
            "system": houses_raw.get("system", "P") if isinstance(houses_raw, dict) else "P",
            "cusps": {},
            "cusp_details": {},
        },
        "angles": {},
        "meta": meta,
    }


def _fetch_chart_response(
    *,
    resolved_api_base_url: str,
    chart_payload: dict[str, Any],
    timeout: int = 120,
) -> dict[str, Any]:
    path = "/api/v1/chart"
    try:
        response = _post_to_api_with_fallback(
            base_url=resolved_api_base_url,
            path=path,
            payload=chart_payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        logger.warning("Chart upstream unavailable: path=%s base_url=%s error=%s", path, resolved_api_base_url, exc)
        raise HTTPException(
            status_code=502,
            detail=_build_upstream_unavailable_detail(
                base_url=resolved_api_base_url,
                path=path,
                timeout=timeout,
                exc=exc,
            ),
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code if response.status_code in {502, 504} else 502,
            detail=_build_upstream_http_status_detail(
                status_code=response.status_code,
                path=path,
                body_text=response.text,
            ),
        )
    return response.json()


def _body_display_name(name: str) -> str:
    return OBJECT_DISPLAY_NAMES.get(name, name.replace("_", " ").title())


def _motion_phase_from_speed(speed: float | None) -> str:
    if speed is None or not isinstance(speed, (int, float)):
        return "direct"
    if abs(float(speed)) <= NO_TIME_STATIONARY_THRESHOLD:
        return "stationary"
    return "retrograde" if float(speed) < 0 else "direct"


def _signed_delta_to_aspect(*, transit_degree: float, natal_degree: float, exact_angle: float) -> float:
    return ((transit_degree - natal_degree - exact_angle + 540.0) % 360.0) - 180.0


def _minimal_angular_distance(left: float, right: float) -> float:
    delta = abs(left - right) % 360.0
    return delta if delta <= 180.0 else 360.0 - delta


def _to_local_iso(dt_utc: datetime, timezone_name: str) -> str:
    return dt_utc.astimezone(ZoneInfo(timezone_name)).isoformat(timespec="seconds")


def _collect_no_time_transit_aspects(
    *,
    natal_chart: dict[str, Any],
    transit_chart: dict[str, Any],
    timezone_name: str,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    natal_objects = natal_chart.get("objects") if isinstance(natal_chart, dict) else {}
    transit_objects = transit_chart.get("objects") if isinstance(transit_chart, dict) else {}
    if not isinstance(natal_objects, dict) or not isinstance(transit_objects, dict):
        return []

    all_aspects = [*NO_TIME_MAJOR_ASPECTS, *NO_TIME_MINOR_ASPECTS]
    ranked: list[dict[str, Any]] = []
    for transit_body in NO_TIME_TRANSIT_BODIES:
        transit_obj = transit_objects.get(transit_body)
        if not isinstance(transit_obj, dict):
            continue
        transit_degree = transit_obj.get("absolute_degree_0_360")
        speed = transit_obj.get("speed_longitude_deg_per_day")
        if not isinstance(transit_degree, (int, float)):
            continue

        for natal_body in NO_TIME_NATAL_TARGET_BODIES:
            natal_obj = natal_objects.get(natal_body)
            if not isinstance(natal_obj, dict):
                continue
            natal_degree = natal_obj.get("absolute_degree_0_360")
            if not isinstance(natal_degree, (int, float)):
                continue

            for aspect_name, exact_angle, orb_limit in all_aspects:
                actual_angle = _minimal_angular_distance(float(transit_degree), float(natal_degree))
                orb = abs(actual_angle - exact_angle)
                if orb > orb_limit:
                    continue
                if aspect_name in {"semi-sextile", "quincunx"} and orb > 0.25:
                    continue

                delta_signed = _signed_delta_to_aspect(
                    transit_degree=float(transit_degree),
                    natal_degree=float(natal_degree),
                    exact_angle=exact_angle,
                )
                exact_at_local: str | None = None
                active_from_local: str | None = None
                active_to_local: str | None = None
                phase = "exact" if abs(delta_signed) <= NO_TIME_PHASE_EXACT_EPSILON else "separating"
                if isinstance(speed, (int, float)) and abs(float(speed)) > NO_TIME_STATIONARY_THRESHOLD:
                    days_to_exact = -delta_signed / float(speed)
                    exact_at_utc = now_utc + timedelta(days=days_to_exact)
                    active_span_days = orb_limit / abs(float(speed))
                    exact_at_local = _to_local_iso(exact_at_utc, timezone_name)
                    active_from_local = _to_local_iso(exact_at_utc - timedelta(days=active_span_days), timezone_name)
                    active_to_local = _to_local_iso(exact_at_utc + timedelta(days=active_span_days), timezone_name)
                    if abs(delta_signed) <= NO_TIME_PHASE_EXACT_EPSILON:
                        phase = "exact"
                    else:
                        phase = "applying" if days_to_exact > 0 else "separating"

                transit_label = _body_display_name(transit_body)
                entry = {
                    "transit_body": transit_label,
                    "natal_body": _body_display_name(natal_body),
                    "aspect": aspect_name,
                    "orb": round(float(orb), 4),
                    "phase": phase,
                    "motion": _motion_phase_from_speed(float(speed) if isinstance(speed, (int, float)) else None),
                    "active_from": active_from_local,
                    "exact_at": exact_at_local,
                    "active_to": active_to_local,
                    "transit_sign": transit_obj.get("sign_name_en"),
                    "natal_sign": natal_obj.get("sign_name_en"),
                    "reference_duration": NO_TIME_SLOW_TRANSIT_REFERENCE_DURATIONS.get(transit_label),
                    "_score": (
                        300 if transit_body == "moon" else
                        250 if transit_body == "sun" else
                        220 if transit_body == "mercury" else
                        210 if transit_body == "venus" else
                        200 if transit_body == "mars" else
                        140 if transit_body == "jupiter" else
                        120 if transit_body == "saturn" else
                        80 if transit_body == "uranus" else
                        70 if transit_body == "neptune" else
                        60
                    ) - (20 if aspect_name in {"semi-sextile", "quincunx"} else 0) - float(orb) * 10.0,
                }
                ranked.append(entry)

    ranked.sort(key=lambda item: (-item["_score"], item["orb"]))
    for item in ranked:
        item.pop("_score", None)
    return ranked[:20]


def _build_no_time_moon_daily_windows(
    *,
    transit_chart: dict[str, Any],
    timezone_context: dict[str, Any],
    now_utc: datetime,
) -> list[dict[str, Any]]:
    moon = (transit_chart.get("objects") or {}).get("moon") if isinstance(transit_chart, dict) else None
    if not isinstance(moon, dict):
        return []
    timezone_name = timezone_context.get("timezone_name") or "UTC"
    current_local = now_utc.astimezone(ZoneInfo(timezone_name))
    day_start = current_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return [
        {
            "moon_sign": moon.get("sign_name_en"),
            "from": day_start.isoformat(timespec="seconds"),
            "to": day_end.isoformat(timespec="seconds"),
            "meaning": NO_TIME_MOON_SIGN_MEANINGS.get(moon.get("sign_name_en") or "", "эмоциональный фон дня"),
        }
    ]


def _build_no_time_calculation_facts(
    *,
    natal_chart: dict[str, Any],
    transit_chart: dict[str, Any],
    timezone_context: dict[str, Any],
    warnings: list[str],
    coordinates_source: str,
    now_utc: datetime,
) -> dict[str, Any]:
    transit_aspects = _collect_no_time_transit_aspects(
        natal_chart=natal_chart,
        transit_chart=transit_chart,
        timezone_name=timezone_context.get("timezone_name") or "UTC",
        now_utc=now_utc,
    )
    moon_daily_windows = _build_no_time_moon_daily_windows(
        transit_chart=transit_chart,
        timezone_context=timezone_context,
        now_utc=now_utc,
    )
    return {
        "precision": "birth_date_no_time",
        "forecast_mode": "transit_to_natal_no_houses",
        "birth_time_used": NO_TIME_FALLBACK_LOCAL_CLOCK,
        "birth_time_assumption": "date_midpoint",
        "houses_available": False,
        "asc_mc_available": False,
        "event_specificity": "low",
        "forecast_character": "psychological_mental_energy",
        "coordinates_source": coordinates_source,
        "timezone_clarification_needed": bool(timezone_context.get("clarification_needed")),
        "limitations": [
            "No houses, ASC, MC or cusps without birth time",
            "Forecast is less event-specific",
            "Focus is psychological, energetic and mental",
        ],
        "transit_aspects": transit_aspects,
        "moon_daily_windows": moon_daily_windows,
        "warnings": warnings,
    }


def _compact_no_time_forecast_context(
    *,
    natal_chart: dict[str, Any],
    transit_chart: dict[str, Any],
    calculation_facts: dict[str, Any],
    timezone_context: dict[str, Any],
) -> dict[str, Any]:
    natal_objects = natal_chart.get("objects") if isinstance(natal_chart, dict) else {}
    transit_objects = transit_chart.get("objects") if isinstance(transit_chart, dict) else {}
    compact_natal: dict[str, Any] = {}
    compact_transits: dict[str, Any] = {}
    if isinstance(natal_objects, dict):
        for name in [*NO_TIME_NATAL_TARGET_BODIES, "moon"]:
            obj = natal_objects.get(name)
            if not isinstance(obj, dict):
                continue
            compact_natal[name] = {
                "sign_name_en": obj.get("sign_name_en"),
                "sign_degree": obj.get("sign_degree"),
                "absolute_degree_0_360": obj.get("absolute_degree_0_360"),
            }
    if isinstance(transit_objects, dict):
        for name in NO_TIME_TRANSIT_BODIES:
            obj = transit_objects.get(name)
            if not isinstance(obj, dict):
                continue
            compact_transits[name] = {
                "sign_name_en": obj.get("sign_name_en"),
                "sign_degree": obj.get("sign_degree"),
                "absolute_degree_0_360": obj.get("absolute_degree_0_360"),
                "speed_longitude_deg_per_day": obj.get("speed_longitude_deg_per_day"),
                "retrograde": obj.get("retrograde"),
            }
    return {
        "natal_positions": compact_natal,
        "transit_positions": compact_transits,
        "calculation_facts": calculation_facts,
        "timezone": timezone_context,
    }


def _truncate_prompt_text(prompt_text: str, max_chars: int = 2000) -> str:
    text = (prompt_text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[Промт сокращён из-за лимита контекста.]"


def _is_localhost_base_url(base_url: str) -> bool:
    try:
        parsed = urlparse(base_url)
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "localhost"}


def _should_use_docker_compose_fallback(base_url: str) -> bool:
    return DOCKER_COMPOSE_API_FALLBACK_ENABLED and _is_localhost_base_url(base_url)


def _build_upstream_unavailable_detail(
    *,
    base_url: str,
    path: str,
    timeout: int,
    exc: Exception,
) -> dict[str, Any]:
    try:
        upstream_host = urlparse(base_url).hostname
    except ValueError:
        upstream_host = None

    if path == "/api/v1/chart":
        user_message = "Сервис расчёта карты временно недоступен. Попробуйте повторить позже."
    elif path.startswith("/api/v1/rectification/"):
        user_message = "Сервис Pro-ректификации временно недоступен. Попробуйте повторить позже."
    else:
        user_message = "Внутренний сервис временно недоступен. Попробуйте повторить позже."

    detail: dict[str, Any] = {
        "message": "Upstream service unavailable",
        "user_message": user_message,
        "reason": "upstream_unavailable",
        "path": path,
        "timeout_seconds": timeout,
        "upstream_host": upstream_host,
        "fallback_enabled": _should_use_docker_compose_fallback(base_url),
        "error_type": type(exc).__name__,
    }
    if _should_use_docker_compose_fallback(base_url):
        try:
            detail["fallback_host"] = urlparse(DOCKER_COMPOSE_API_BASE_URL).hostname
        except ValueError:
            detail["fallback_host"] = None
    return detail


def _build_upstream_http_status_detail(
    *,
    status_code: int,
    path: str,
    body_text: str,
) -> dict[str, Any]:
    safe_body = (body_text or "")[:2000]
    normalized = safe_body.lower()
    is_timeout = status_code == 504 or "gateway time-out" in normalized or "gateway timeout" in normalized

    if path.startswith("/api/v1/rectification/"):
        user_message = (
            "Расчёт занял слишком много времени. "
            "Попробуйте V1, меньше событий или повторите позже."
            if is_timeout
            else "Сервис Pro-ректификации временно недоступен. Попробуйте повторить позже."
        )
    elif path == "/api/v1/chart":
        user_message = (
            "Расчёт карты занял слишком много времени. Попробуйте повторить позже."
            if is_timeout
            else "Сервис расчёта карты временно недоступен. Попробуйте повторить позже."
        )
    else:
        user_message = (
            "Внутренний сервис занял слишком много времени. Попробуйте повторить позже."
            if is_timeout
            else "Внутренний сервис временно недоступен. Попробуйте повторить позже."
        )

    return {
        "message": "Upstream returned non-200 status",
        "user_message": user_message,
        "technical_message": f"upstream_status={status_code}",
        "reason": "upstream_timeout" if is_timeout else "upstream_unavailable",
        "path": path,
        "status_code": status_code,
        "body": safe_body,
    }


def _load_geocode_cache() -> dict[str, dict[str, Any]]:
    if not GEOCODE_CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("version") != GEOCODE_CACHE_VERSION:
        return {}
    data = raw.get("data")
    if not isinstance(data, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            normalized[key] = value
    return normalized


def _save_geocode_cache(cache: dict[str, dict[str, Any]]) -> None:
    GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": GEOCODE_CACHE_VERSION, "data": cache}
    GEOCODE_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _cache_geocode_result(query: str, results: list[dict[str, Any]]) -> None:
    if not query or not results:
        return
    normalized_query = query.strip().lower()
    if not normalized_query:
        return
    cache = _load_geocode_cache()
    cache[normalized_query] = {
        "query": query,
        "results": results,
        "cached_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if len(cache) > GEOCODE_CACHE_MAX_ITEMS:
        sorted_keys = sorted(
            cache.keys(),
            key=lambda key: cache.get(key, {}).get("cached_at", ""),
            reverse=True,
        )
        keep_keys = set(sorted_keys[:GEOCODE_CACHE_MAX_ITEMS])
        cache = {key: value for key, value in cache.items() if key in keep_keys}
    _save_geocode_cache(cache)


def _get_cached_geocode_result(query: str) -> list[dict[str, Any]] | None:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return None
    cache = _load_geocode_cache()
    record = cache.get(normalized_query)
    if not isinstance(record, dict):
        return None
    results = record.get("results")
    if not isinstance(results, list):
        return None
    cleaned: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            cleaned.append(item)
    return cleaned or None


def _post_to_api_with_fallback(*, base_url: str, path: str, payload: dict[str, Any], timeout: int) -> httpx.Response:
    primary_url = base_url.rstrip("/") + path
    try:
        return httpx.post(primary_url, json=payload, timeout=timeout)
    except httpx.TimeoutException:
        raise
    except httpx.HTTPError as primary_error:
        if not _should_use_docker_compose_fallback(base_url):
            raise primary_error
        if not isinstance(primary_error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError)):
            raise primary_error

        fallback_url = DOCKER_COMPOSE_API_BASE_URL.rstrip("/") + path
        logger.warning(
            "Primary API base URL failed; retrying via docker-compose service name: %s -> %s",
            primary_url,
            fallback_url,
        )
        return httpx.post(fallback_url, json=payload, timeout=timeout)


def _resolve_api_base_url(base_url: str | None) -> str:
    normalized = (base_url or "").strip()
    if normalized:
        return normalized
    return WEB_UI_INTERNAL_API_BASE_URL


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


def _call_openai_chat(
    *,
    system_prompt: str,
    user_prompt: str,
    model_override_env: str | None = None,
    request_kind: str = OPENROUTER_REQUEST_KIND_DEFAULT,
    requested_max_tokens: int | None = None,
    route_label: str = "unknown",
    _retry_on_affordable_402: bool = False,
) -> dict[str, Any]:
    settings = _load_openai_settings()
    resolved_requested_max_tokens, applied_max_tokens = _resolve_openai_max_tokens(
        settings=settings,
        request_kind=request_kind,
        requested_max_tokens=requested_max_tokens,
    )

    scenario_model = settings["models_by_scenario"].get(
        request_kind,
        settings["models_by_scenario"][OPENROUTER_REQUEST_KIND_DEFAULT],
    )
    fallback_model = settings["fallback_models_by_scenario"].get(
        request_kind,
        settings["fallback_models_by_scenario"][OPENROUTER_REQUEST_KIND_DEFAULT],
    )
    if model_override_env:
        model_override = _env(model_override_env, "").strip()
        if model_override:
            scenario_model = model_override

    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    model_slots: list[tuple[str, str]] = [("primary", scenario_model)]
    if fallback_model and fallback_model != scenario_model:
        model_slots.append(("fallback", fallback_model))

    attempts: list[dict[str, Any]] = []
    last_error_detail: dict[str, Any] | None = None

    for attempt_index, (key_name, model_name) in enumerate(model_slots, start=1):
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        if model_name.startswith("gpt-5"):
            body["max_completion_tokens"] = applied_max_tokens
        else:
            body["max_tokens"] = applied_max_tokens
        try:
            response = httpx.post(
                f"{settings['base_url']}/chat/completions",
                headers=headers,
                json=body,
                timeout=settings["timeout_seconds"],
            )
        except httpx.TimeoutException as exc:
            reason = "timeout"
            error_detail = {
                "message": "LLM request timeout",
                "provider": "openai",
                "status_code": 502,
                "reason": reason,
                "route": route_label,
                "model": model_name,
                "key_name": key_name,
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
                "raw_error": str(exc)[:4000],
            }
            attempts.append(
                {
                    "attempt": attempt_index,
                    "key_name": key_name,
                    "model": model_name,
                    "status_code": 502,
                    "reason": reason,
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": applied_max_tokens,
                    "raw_error": str(exc)[:4000],
                }
            )
            last_error_detail = error_detail
            if attempt_index < len(model_slots) and _is_openai_retryable_reason(reason):
                continue
            raise HTTPException(status_code=502, detail={**error_detail, "attempts": attempts, "fallback_used": attempt_index > 1, "final_source": "llm_unavailable"}) from exc
        except httpx.HTTPError as exc:
            reason = "network_or_timeout"
            error_detail = {
                "message": "LLM request failed",
                "provider": "openai",
                "status_code": 502,
                "reason": reason,
                "route": route_label,
                "model": model_name,
                "key_name": key_name,
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
                "raw_error": str(exc)[:4000],
            }
            attempts.append(
                {
                    "attempt": attempt_index,
                    "key_name": key_name,
                    "model": model_name,
                    "status_code": 502,
                    "reason": reason,
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": applied_max_tokens,
                    "raw_error": str(exc)[:4000],
                }
            )
            last_error_detail = error_detail
            if attempt_index < len(model_slots) and _is_openai_retryable_reason(reason):
                continue
            raise HTTPException(status_code=502, detail={**error_detail, "attempts": attempts, "fallback_used": attempt_index > 1, "final_source": "llm_unavailable"}) from exc

        if response.status_code != 200:
            raw_error = response.text[:4000]
            reason = _classify_openai_error(response.status_code, raw_error)
            attempts.append(
                {
                    "attempt": attempt_index,
                    "key_name": key_name,
                    "model": model_name,
                    "status_code": response.status_code,
                    "reason": reason,
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": applied_max_tokens,
                    "raw_error": raw_error,
                }
            )
            last_error_detail = {
                "message": "LLM provider returned non-200 status",
                "provider": "openai",
                "status_code": response.status_code,
                "reason": reason,
                "route": route_label,
                "model": model_name,
                "key_name": key_name,
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
                "raw_error": raw_error,
            }
            if attempt_index < len(model_slots) and _is_openai_retryable_reason(reason):
                continue
            raise HTTPException(
                status_code=502,
                detail={
                    **last_error_detail,
                    "attempts": attempts,
                    "fallback_used": attempt_index > 1,
                    "final_source": "llm_unavailable",
                },
            )

        payload = response.json()
        text = _extract_chat_completion_text(payload)
        if not text:
            reason = "empty_response"
            attempts.append(
                {
                    "attempt": attempt_index,
                    "key_name": key_name,
                    "model": model_name,
                    "status_code": 502,
                    "reason": reason,
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": applied_max_tokens,
                }
            )
            last_error_detail = {
                "message": "LLM provider returned empty response",
                "provider": "openai",
                "status_code": 502,
                "reason": reason,
                "route": route_label,
                "model": model_name,
                "key_name": key_name,
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
            }
            if attempt_index < len(model_slots):
                continue
            raise HTTPException(
                status_code=502,
                detail={
                    **last_error_detail,
                    "attempts": attempts,
                    "fallback_used": attempt_index > 1,
                    "final_source": "llm_unavailable",
                },
            )

        attempts.append(
            {
                "attempt": attempt_index,
                "key_name": key_name,
                "model": model_name,
                "status_code": 200,
                "reason": "ok",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
            }
        )
        return {
            "text": text,
            "raw": payload,
            "provider": "openai",
            "model": model_name,
            "key_name": key_name,
            "route": route_label,
            "scenario": request_kind,
            "request_kind": request_kind,
            "requested_max_tokens": resolved_requested_max_tokens,
            "applied_max_tokens": applied_max_tokens,
            "first_applied_max_tokens": applied_max_tokens,
            "retried_with_lower_max_tokens": False,
            "attempts": attempts,
            "fallback_used": key_name != "primary",
            "final_source": "llm_fallback" if key_name != "primary" else "llm_primary",
        }

    raise HTTPException(
        status_code=502,
        detail={
            **(last_error_detail or {
                "message": "LLM provider unavailable",
                "provider": "openai",
                "status_code": 502,
                "reason": "provider_unavailable",
                "route": route_label,
                "model": scenario_model,
                "key_name": "primary",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
            }),
            "attempts": attempts,
            "fallback_used": any(item.get("key_name") == "fallback" for item in attempts),
            "final_source": "llm_unavailable",
        },
    )


def _call_llm_chat(
    *,
    system_prompt: str,
    user_prompt: str,
    model_override_env: str | None = None,
    request_kind: str = OPENROUTER_REQUEST_KIND_DEFAULT,
    requested_max_tokens: int | None = None,
    route_label: str = "unknown",
    retry_on_affordable_402: bool = False,
) -> dict[str, Any]:
    provider = _load_llm_provider()
    if provider == "openai":
        return _call_openai_chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_override_env=model_override_env,
            request_kind=request_kind,
            requested_max_tokens=requested_max_tokens,
            route_label=route_label,
            _retry_on_affordable_402=retry_on_affordable_402,
        )
    return _call_openrouter_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_override_env=model_override_env,
        request_kind=request_kind,
        requested_max_tokens=requested_max_tokens,
        route_label=route_label,
        retry_on_affordable_402=retry_on_affordable_402,
    )


def _call_openrouter_chat(
    *,
    system_prompt: str,
    user_prompt: str,
    model_override_env: str | None = None,
    request_kind: str = OPENROUTER_REQUEST_KIND_DEFAULT,
    requested_max_tokens: int | None = None,
    route_label: str = "unknown",
    retry_on_affordable_402: bool = False,
) -> dict[str, Any]:
    settings = _load_openrouter_settings()
    resolved_requested_max_tokens, applied_max_tokens = _resolve_openrouter_max_tokens(
        settings=settings,
        request_kind=request_kind,
        requested_max_tokens=requested_max_tokens,
    )

    scenario_models = settings["models_by_scenario"].get(
        request_kind, settings["models_by_scenario"][OPENROUTER_REQUEST_KIND_DEFAULT]
    )
    scenario_primary_model = scenario_models.get("primary") or settings["model"]
    scenario_fallback_model = scenario_models.get("fallback") or scenario_primary_model
    if model_override_env:
        model_override = _env(model_override_env, "").strip()
        if model_override:
            scenario_primary_model = model_override

    # Recommended attempt order:
    # 1) primary key + primary model
    # 2) primary key + fallback model
    # 3) backup_1 key + fallback model
    # 4) backup_2 key + fallback model
    all_keys = settings["api_key_slots"]
    primary_key = next((slot for slot in all_keys if slot["name"] == "primary"), all_keys[0])
    backup_1_key = next((slot for slot in all_keys if slot["name"] == "backup_1"), None)
    backup_2_key = next((slot for slot in all_keys if slot["name"] == "backup_2"), None)

    planned_attempts: list[tuple[dict[str, str], str]] = [
        (primary_key, scenario_primary_model),
        (primary_key, scenario_fallback_model),
    ]
    if backup_1_key is not None:
        planned_attempts.append((backup_1_key, scenario_fallback_model))
    if backup_2_key is not None:
        planned_attempts.append((backup_2_key, scenario_fallback_model))

    deduped_attempts: list[tuple[dict[str, str], str]] = []
    seen_attempt_signatures: set[tuple[str, str]] = set()
    for key_slot, model_name in planned_attempts:
        signature = (key_slot["name"], model_name)
        if signature in seen_attempt_signatures:
            continue
        seen_attempt_signatures.add(signature)
        deduped_attempts.append((key_slot, model_name))

    attempts_limit = min(max(1, int(settings["max_llm_attempts"])), len(deduped_attempts))
    attempts_plan = deduped_attempts[:attempts_limit]

    def _request_openrouter(
        *,
        api_key_slot: dict[str, str],
        model_name: str,
        max_tokens: int,
    ) -> httpx.Response:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key_slot['value']}",
            "Content-Type": "application/json",
            "X-Title": settings["app_name"],
        }
        if settings["site_url"]:
            headers["HTTP-Referer"] = settings["site_url"]
        body = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        try:
            return httpx.post(
                f"{settings['base_url']}/chat/completions",
                headers=headers,
                json=body,
                timeout=settings["timeout_seconds"],
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=502, detail=f"OpenRouter timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"OpenRouter request failed: {exc}") from exc

    initial_applied_max_tokens = applied_max_tokens
    attempt_max_tokens = applied_max_tokens
    retried_with_lower_max_tokens = False
    all_attempt_debug: list[dict[str, Any]] = []
    last_http_status = 502

    for attempt_index, (key_slot, model_name) in enumerate(attempts_plan, start=1):
        current_applied_tokens = attempt_max_tokens
        try:
            response = _request_openrouter(
                api_key_slot=key_slot,
                model_name=model_name,
                max_tokens=current_applied_tokens,
            )
        except HTTPException as exc:
            all_attempt_debug.append(
                {
                    "attempt": attempt_index,
                    "key_name": key_slot["name"],
                    "model": model_name,
                    "status_code": 502,
                    "reason": "network_or_timeout",
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": current_applied_tokens,
                    "raw_error": str(exc.detail)[:4000],
                }
            )
            last_http_status = 502
            continue

        if response.status_code == 200:
            payload = response.json()
            text = _extract_chat_completion_text(payload)
            if text:
                all_attempt_debug.append(
                    {
                        "attempt": attempt_index,
                        "key_name": key_slot["name"],
                        "model": model_name,
                        "status_code": 200,
                        "reason": "ok",
                        "requested_max_tokens": resolved_requested_max_tokens,
                        "applied_max_tokens": current_applied_tokens,
                    }
                )
                return {
                    "text": text,
                    "raw": payload,
                    "provider": "openrouter",
                    "model": model_name,
                    "key_name": key_slot["name"],
                    "route": route_label,
                    "scenario": request_kind,
                    "request_kind": request_kind,
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": current_applied_tokens,
                    "first_applied_max_tokens": initial_applied_max_tokens,
                    "retried_with_lower_max_tokens": retried_with_lower_max_tokens,
                    "attempts": all_attempt_debug,
                    "fallback_used": attempt_index > 1,
                    "final_source": "llm_primary" if attempt_index == 1 else "llm_fallback",
                }
            all_attempt_debug.append(
                {
                    "attempt": attempt_index,
                    "key_name": key_slot["name"],
                    "model": model_name,
                    "status_code": 502,
                    "reason": "empty_response",
                    "requested_max_tokens": resolved_requested_max_tokens,
                    "applied_max_tokens": current_applied_tokens,
                }
            )
            last_http_status = 502
            continue

        raw_error = response.text[:4000]
        reason = _classify_openrouter_error(response.status_code, raw_error)
        all_attempt_debug.append(
            {
                "attempt": attempt_index,
                "key_name": key_slot["name"],
                "model": model_name,
                "status_code": response.status_code,
                "reason": reason,
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": current_applied_tokens,
                "raw_error": raw_error,
            }
        )
        last_http_status = response.status_code

        if response.status_code not in OPENROUTER_CASCADE_FALLBACK_STATUSES:
            break

        # If credits are tight, try smaller token cap on next attempts.
        if request_kind == OPENROUTER_REQUEST_KIND_GENERATE and response.status_code == 402:
            new_tokens = min(attempt_max_tokens, 4000)
            if new_tokens < attempt_max_tokens:
                retried_with_lower_max_tokens = True
            attempt_max_tokens = new_tokens
        affordable_from_error = _extract_openrouter_affordable_max_tokens(raw_error)
        if affordable_from_error is not None:
            new_tokens = min(
                attempt_max_tokens,
                affordable_from_error,
                int(settings["max_tokens_hard_limit"]),
            )
            if new_tokens < attempt_max_tokens:
                retried_with_lower_max_tokens = True
            attempt_max_tokens = new_tokens
        if attempt_max_tokens <= 0:
            attempt_max_tokens = 1

    raise HTTPException(
        status_code=502,
        detail={
            "message": "LLM provider returned non-200 status",
            "provider": "openrouter",
            "status_code": last_http_status,
            "reason": (
                all_attempt_debug[-1]["reason"]
                if all_attempt_debug
                else "upstream_error"
            ),
            "route": route_label,
            "scenario": request_kind,
            "request_kind": request_kind,
            "requested_max_tokens": resolved_requested_max_tokens,
            "applied_max_tokens": (
                all_attempt_debug[-1]["applied_max_tokens"]
                if all_attempt_debug
                else applied_max_tokens
            ),
            "first_applied_max_tokens": initial_applied_max_tokens,
            "retried_with_lower_max_tokens": retried_with_lower_max_tokens,
            "attempts": all_attempt_debug,
            "fallback_used": bool(all_attempt_debug and len(all_attempt_debug) > 1),
            "final_source": "template_fallback",
            "model": all_attempt_debug[-1]["model"] if all_attempt_debug else scenario_primary_model,
            "key_name": all_attempt_debug[-1]["key_name"] if all_attempt_debug else "primary",
            "raw_error": all_attempt_debug[-1].get("raw_error") if all_attempt_debug else None,
        },
    )


def _render_horoscope_via_openai(
    prompt_text: str,
    chart: dict[str, Any],
    core_identity: dict[str, Any],
) -> dict[str, Any]:
    compact_chart = _compact_llm_chart_context(chart)
    safe_prompt_text = _truncate_prompt_text(prompt_text)
    system_prompt = (
        "Ты астрологический ассистент. Пиши по-русски. "
        "Дай структурированный и понятный разбор без мистификации, "
        "используя только переданные расчётные данные. "
        "Первый блок трактовки всегда обязан включать в явном виде: Солнце, Луну и Asc. "
        "Нельзя заменять Луну или Asc на узлы. Узлы допустимы только после базового блока."
    )
    user_prompt = (
        f"{safe_prompt_text}\n\n"
        "Обязательный базовый блок (используй как основу для первого раздела):\n"
        f"{json.dumps(core_identity, ensure_ascii=False)}\n\n"
        "Ниже сокращённый JSON с расчётом натальной карты. "
        "Сделай связный текстовый гороскоп: личность, эмоции, "
        "отношения, работа/реализация, сильные стороны и риски.\n\n"
        f"{json.dumps(compact_chart, ensure_ascii=False)}"
    )
    chat_result = _call_llm_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        request_kind=OPENROUTER_REQUEST_KIND_GENERATE,
        route_label="/api/generate",
        retry_on_affordable_402=True,
    )
    llm_debug = {
        "provider": chat_result.get("provider", _load_llm_provider()),
        "scenario": OPENROUTER_REQUEST_KIND_GENERATE,
        "final_source": chat_result.get("final_source", "llm_primary"),
        "fallback_used": bool(chat_result.get("fallback_used")),
        "attempts": chat_result.get("attempts", []),
    }
    return {"text": chat_result["text"], "llm_debug": llm_debug}


def _render_no_time_forecast_via_openai(
    prompt_text: str,
    forecast_context: dict[str, Any],
) -> dict[str, Any]:
    safe_prompt_text = _truncate_prompt_text(prompt_text)
    system_prompt = (
        "Ты астрологический ассистент. Пиши по-русски. "
        "Перед тобой персональный прогноз без точного времени рождения. "
        "Нельзя использовать дома, ASC, MC, куспиды, управителей домов и событийную house-логику. "
        "Опирайся только на натальные положения планет, транзитные положения, транзитные аспекты к натальным планетам, "
        "фазу аспекта (applying/exact/separating), фазу движения планеты (direct/retrograde/stationary) "
        "и фон Луны по знаку/дневным окнам. "
        "Прямо и честно объясни ограничение: без точного времени прогноз лучше описывает психологические, ментальные "
        "и энергетические тренды, а не точные бытовые сценарии. "
        "Не показывай пользователю внутренние технические имена режимов."
    )
    user_prompt = (
        f"{safe_prompt_text}\n\n"
        "Обязательная вводная формулировка для пользователя:\n"
        "Этот прогноз построен без точного времени рождения, поэтому мы не используем дома, ASC и MC. "
        "Он не показывает конкретные бытовые сценарии, зато хорошо описывает ваши психологические тренды, "
        "уровень энергии, фоновые мысли и эмоциональные триггеры на ближайшие дни.\n\n"
        "Ниже расчётный контекст no-time прогноза. Сначала дай краткий общий фон, "
        "потом выдели 3-6 самых важных транзитных тем, затем заверши короткими практическими рекомендациями.\n\n"
        f"{json.dumps(forecast_context, ensure_ascii=False)}"
    )
    chat_result = _call_llm_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        request_kind=OPENROUTER_REQUEST_KIND_GENERATE,
        route_label="/api/generate",
        retry_on_affordable_402=True,
    )
    llm_debug = {
        "provider": chat_result.get("provider", _load_llm_provider()),
        "scenario": OPENROUTER_REQUEST_KIND_GENERATE,
        "final_source": chat_result.get("final_source", "llm_primary"),
        "fallback_used": bool(chat_result.get("fallback_used")),
        "attempts": chat_result.get("attempts", []),
    }
    return {"text": chat_result["text"], "llm_debug": llm_debug}


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
    chat_result = _call_llm_chat(
        system_prompt=prompt_text,
        user_prompt=json.dumps(runtime_payload, ensure_ascii=False),
        request_kind=OPENROUTER_REQUEST_KIND_STAGE1,
        route_label="/api/rectification/dialog",
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
    resolved_api_base_url = _resolve_api_base_url(payload.api_base_url)
    api_payload = {
        "birth_date_local": payload.birth_date_local,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "timezone_mode": payload.timezone_mode,
        "timezone_offset": payload.timezone_offset or None,
        "timezone_name": payload.timezone_name,
        "house_system": payload.house_system,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }
    try:
        response = _post_to_api_with_fallback(
            base_url=resolved_api_base_url,
            path=path,
            payload=api_payload,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        logger.warning("Rectification upstream unavailable: path=%s base_url=%s error=%s", path, resolved_api_base_url, exc)
        raise HTTPException(
            status_code=502,
            detail=_build_upstream_unavailable_detail(
                base_url=resolved_api_base_url,
                path=path,
                timeout=120,
                exc=exc,
            ),
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code if response.status_code in {502, 504} else 502,
            detail=_build_upstream_http_status_detail(
                status_code=response.status_code,
                path=path,
                body_text=response.text,
            ),
        )

    return response.json()


def _post_rectification_events(
    *,
    base_url: str,
    path: str,
    payload: dict[str, Any],
    timeout: int = 120,
) -> dict[str, Any]:
    resolved_api_base_url = _resolve_api_base_url(base_url)
    try:
        response = _post_to_api_with_fallback(
            base_url=resolved_api_base_url,
            path=path,
            payload=payload,
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "message": "Rectification request timed out",
                "user_message": (
                    "Pro-расчёт занял слишком много времени. "
                    "Попробуйте повторить запуск позже или временно уменьшить объём сравнения."
                ),
                "reason": "upstream_timeout",
                "path": path,
                "timeout_seconds": timeout,
            },
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Rectification upstream unavailable: path=%s base_url=%s error=%s", path, resolved_api_base_url, exc)
        raise HTTPException(
            status_code=502,
            detail=_build_upstream_unavailable_detail(
                base_url=resolved_api_base_url,
                path=path,
                timeout=timeout,
                exc=exc,
            ),
        ) from exc

    if response.status_code != 200:
        if 400 <= response.status_code < 500:
            try:
                detail: Any = response.json().get("detail")
            except ValueError:
                detail = response.text[:2000]
            raise HTTPException(status_code=response.status_code, detail=detail)
        raise HTTPException(
            status_code=response.status_code if response.status_code in {502, 504} else 502,
            detail=_build_upstream_http_status_detail(
                status_code=response.status_code,
                path=path,
                body_text=response.text,
            ),
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Rectification events API returned invalid JSON",
        ) from exc


def _guard_rectification_pro_payload(
    payload: dict[str, Any],
    *,
    max_events: int = RECTIFICATION_PRO_MULTI_CARD_MAX_EVENTS,
    complexity_limit: int = RECTIFICATION_PRO_MULTI_CARD_COMPLEXITY_LIMIT,
    user_message: str | None = None,
) -> None:
    if not isinstance(payload, dict):
        return

    raw_events = payload.get("events")
    events_count = len(raw_events) if isinstance(raw_events, list) else 0
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    raw_card_ids = settings.get("formula_card_ids")
    selected_card_ids = [
        str(card_id).strip()
        for card_id in raw_card_ids
        if str(card_id).strip()
    ] if isinstance(raw_card_ids, list) else []

    if len(selected_card_ids) <= 1:
        return

    complexity = events_count * len(selected_card_ids)
    if (
        events_count > max_events
        or complexity > complexity_limit
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Rectification Pro payload too heavy for live multi-card run",
                "user_message": (
                    user_message
                    or "Этот multi-card V2 запуск сейчас слишком тяжёлый для live-режима. "
                    "Попробуйте до 4 событий, один V2 card или V1."
                ),
                "technical_message": (
                    f"events={events_count} cards={len(selected_card_ids)} "
                    f"complexity={complexity} limit={complexity_limit}"
                ),
                "reason": "payload_too_heavy",
                "events_count": events_count,
                "max_events": max_events,
                "complexity": complexity,
                "complexity_limit": complexity_limit,
                "selected_cards_count": len(selected_card_ids),
                "selected_card_ids": selected_card_ids,
            },
        )


def _extract_rectification_pro_selected_card_ids(payload: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    raw_card_ids = settings.get("formula_card_ids")
    if not isinstance(raw_card_ids, list):
        return []
    seen: set[str] = set()
    selected_card_ids: list[str] = []
    for raw_card_id in raw_card_ids:
        card_id = str(raw_card_id or "").strip()
        if not card_id or card_id in seen:
            continue
        seen.add(card_id)
        selected_card_ids.append(card_id)
    return selected_card_ids


def _build_rectification_pro_chunk_payload_too_heavy_detail(
    *,
    job_id: str | None = None,
    events_count: int,
    selected_card_ids: list[str],
    complexity: int,
    complexity_limit: int,
    user_message: str,
    chunk_size: int | None = None,
    candidate_count: int | None = None,
    formula_count: int | None = None,
    planned_chunks: int | None = None,
    max_chunks: int | None = None,
    max_events: int | None = None,
    max_events_per_chunk: int | None = None,
    estimated_weight: int | None = None,
    guard_reason: str | None = None,
    guard_stage: str | None = None,
    current_limit: dict[str, Any] | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    detail = {
        "message": "Rectification Pro payload too heavy for live multi-card run",
        "user_message": user_message,
        "technical_message": (
            f"events={events_count} cards={len(selected_card_ids)} "
            f"complexity={complexity} limit={complexity_limit}"
        ),
        "reason": "payload_too_heavy",
        "events_count": events_count,
        "complexity": complexity,
        "complexity_limit": complexity_limit,
        "selected_cards_count": len(selected_card_ids),
        "selected_card_ids": selected_card_ids,
        "candidate_count": candidate_count,
        "formula_count": formula_count,
    }
    if job_id is not None:
        detail["job_id"] = job_id
    if chunk_size is not None:
        detail["chunk_size"] = chunk_size
    if planned_chunks is not None:
        detail["planned_chunks"] = planned_chunks
    if max_chunks is not None:
        detail["max_chunks"] = max_chunks
    if max_events is not None:
        detail["max_events"] = max_events
    if max_events_per_chunk is not None:
        detail["max_events_per_chunk"] = max_events_per_chunk
    if estimated_weight is not None:
        detail["estimated_weight"] = estimated_weight
    if guard_reason:
        detail["guard_reason"] = guard_reason
    if guard_stage:
        detail["guard_stage"] = guard_stage
    if current_limit:
        detail["current_limit"] = current_limit
    if runtime_snapshot:
        detail["runtime_snapshot"] = runtime_snapshot
    if recommendation:
        detail["recommendation"] = recommendation
    return detail


def _split_rectification_pro_chunk_events(
    events: list[dict[str, Any]],
    *,
    max_events_per_chunk: int,
) -> list[list[dict[str, Any]]]:
    if max_events_per_chunk <= 0:
        return [list(events)] if events else []
    return [
        events[idx:idx + max_events_per_chunk]
        for idx in range(0, len(events), max_events_per_chunk)
        if events[idx:idx + max_events_per_chunk]
    ]


def _build_rectification_pro_chunk_plan(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    selected_card_ids = _extract_rectification_pro_selected_card_ids(payload)
    if len(selected_card_ids) <= 1:
        return None

    raw_events = payload.get("events")
    events = [item for item in raw_events if isinstance(item, dict)] if isinstance(raw_events, list) else []
    events_count = len(events)
    complexity = events_count * len(selected_card_ids)
    if (
        events_count <= RECTIFICATION_PRO_ASYNC_MULTI_CARD_MAX_EVENTS
        and complexity <= RECTIFICATION_PRO_ASYNC_MULTI_CARD_COMPLEXITY_LIMIT
    ):
        return None

    chunk_items: list[dict[str, Any]] = []
    skipped_card_ids: list[str] = []
    max_events_per_chunk = 0
    chunk_size = 0
    relevant_events_count = 0

    for card_id in selected_card_ids:
        accepted_event_types = RECTIFICATION_PRO_CHUNK_CARD_EVENT_TYPES.get(card_id)
        if not accepted_event_types:
            skipped_card_ids.append(card_id)
            continue
        chunk_events = [
            item
            for item in events
            if str(item.get("event_type") or "").strip() in accepted_event_types
        ]
        if not chunk_events:
            skipped_card_ids.append(card_id)
            continue

        relevant_events_count += len(chunk_events)
        chunk_label = sorted(accepted_event_types)[0]
        chunk_batch_size = _resolve_rectification_pro_chunk_batch_size(
            relevant_events_count=len(chunk_events),
            selected_cards_count=len(selected_card_ids),
            complexity=complexity,
        )
        chunk_size = max(chunk_size, chunk_batch_size)
        event_batches = _split_rectification_pro_chunk_events(
            chunk_events,
            max_events_per_chunk=chunk_batch_size,
        )
        max_events_per_chunk = max(
            max_events_per_chunk,
            max((len(batch) for batch in event_batches), default=0),
        )
        for batch_idx, batch_events in enumerate(event_batches, start=1):
            chunk_payload = json.loads(json.dumps(payload))
            chunk_payload["events"] = batch_events
            settings = chunk_payload.setdefault("settings", {})
            settings["formula_card_id"] = card_id
            settings["formula_card_ids"] = []
            settings["compare_formula_card_ids"] = []
            chunk_items.append(
                {
                    "card_id": card_id,
                    "chunk_label": chunk_label,
                    "event_types": sorted(
                        {
                            str(item.get("event_type") or "").strip()
                            for item in batch_events
                            if item.get("event_type")
                        }
                    ),
                    "subchunk_index": batch_idx,
                    "subchunk_count": len(event_batches),
                    "payload": chunk_payload,
                }
            )

    if len(chunk_items) <= 1:
        return None

    planned_chunks = len(chunk_items)
    estimated_weight = complexity
    guard_reason = None
    diagnostic_job_id = f"guard-{uuid4()}"
    current_limit = _current_rectification_pro_chunk_limits()
    runtime_snapshot = _collect_rectification_pro_runtime_snapshot()
    if events_count > RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS:
        guard_reason = "events_limit_exceeded"
    elif planned_chunks > RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS:
        guard_reason = "planned_chunks_exceeded"
    elif max_events_per_chunk > RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK:
        guard_reason = "chunk_batch_too_large"

    if guard_reason:
        _log_rectification_pro_chunk_guard(
            level=logging.WARNING,
            message="Rectification Pro chunk plan rejected",
            job_id=diagnostic_job_id,
            guard_stage="pre_job_chunk_plan",
            events_count=events_count,
            selected_cards_count=len(selected_card_ids),
            planned_chunks=planned_chunks,
            chunk_size=chunk_size or max_events_per_chunk,
            candidate_count=None,
            formula_count=None,
            estimated_weight=estimated_weight,
            guard_reason=guard_reason,
            current_limit=current_limit,
            runtime_snapshot=runtime_snapshot,
        )
        raise HTTPException(
            status_code=422,
            detail=_build_rectification_pro_chunk_payload_too_heavy_detail(
                job_id=diagnostic_job_id,
                events_count=events_count,
                selected_card_ids=selected_card_ids,
                complexity=complexity,
                complexity_limit=RECTIFICATION_PRO_ASYNC_MULTI_CARD_COMPLEXITY_LIMIT,
                chunk_size=chunk_size or max_events_per_chunk,
                candidate_count=None,
                formula_count=None,
                planned_chunks=planned_chunks,
                max_chunks=RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_CHUNKS,
                max_events=RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS,
                max_events_per_chunk=RECTIFICATION_PRO_CHUNKED_MULTI_CARD_MAX_EVENTS_PER_CHUNK,
                estimated_weight=estimated_weight,
                guard_reason=guard_reason,
                guard_stage="pre_job_chunk_plan",
                current_limit=current_limit,
                runtime_snapshot=runtime_snapshot,
                recommendation=(
                    "Сократите общее число событий, уменьшите события в одном типе "
                    "или проверьте часть карточек отдельно."
                ),
                user_message=(
                    "Этот multi-card V2 запуск слишком большой даже для поэтапного live-режима. "
                    "Сократите события в одном блоке или проверьте карты по частям."
                ),
            ),
        )

    return {
        "mode": "chunked_async_multi_card",
        "selected_card_ids": selected_card_ids,
        "skipped_card_ids": skipped_card_ids,
        "total_chunks": len(chunk_items),
        "planned_chunks": planned_chunks,
        "relevant_events_count": relevant_events_count,
        "max_events_per_chunk": max_events_per_chunk,
        "chunk_size": chunk_size or max_events_per_chunk,
        "estimated_weight": estimated_weight,
        "chunks": chunk_items,
    }


def _rectification_pro_chunk_label_text(chunk_label: str) -> str:
    return RECTIFICATION_PRO_CHUNK_LABELS.get(chunk_label, chunk_label or "блок")


def _rectification_pro_chunk_user_message(
    *,
    completed_chunks: int,
    total_chunks: int,
    current_chunk_label: str | None,
    status: str,
) -> str:
    if status == "completed":
        return "Большой V2-отчёт по блокам завершён."
    if status == "partial_completed":
        return f"Готово {completed_chunks} из {total_chunks} блоков."
    if current_chunk_label:
        label = _rectification_pro_chunk_label_text(current_chunk_label)
        return f"Считаем {completed_chunks + 1} из {total_chunks} блоков: {label}."
    return "Большой V2-отчёт считается по блокам."


def _merge_rectification_pro_chunk_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    merged = {"golden": 0, "supporting": 0, "context": 0, "ambiguity_risk": 0}
    for item in items:
        for tier in merged:
            merged[tier] += int((item.get("priority_counts") or {}).get(tier) or 0)
    return merged


def _parse_rectification_local_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _merge_rectification_pro_working_ranges(chunk_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for item in chunk_results:
        chunk = item["chunk"]
        result = item["result"]
        refinement = result.get("formula_refinement_results") or {}
        ranges = refinement.get("working_time_ranges") or []
        if not ranges and refinement.get("working_time_range"):
            ranges = [refinement.get("working_time_range")]
        best = refinement.get("best_candidate") or {}
        for range_item in ranges:
            if not isinstance(range_item, dict):
                continue
            start_dt = _parse_rectification_local_dt(range_item.get("start_local"))
            end_dt = _parse_rectification_local_dt(range_item.get("end_local"))
            if start_dt is None or end_dt is None:
                continue
            flattened.append(
                {
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "start_local": range_item.get("start_local"),
                    "end_local": range_item.get("end_local"),
                    "candidate_count": int(range_item.get("candidate_count") or 0),
                    "best_candidate": range_item.get("best_candidate") or best.get("candidate_time_local"),
                    "golden_matched_count": int(range_item.get("golden_matched_count") or 0),
                    "score": float(range_item.get("score") or best.get("score") or 0.0),
                    "supporting_card_ids": [chunk.get("card_id")],
                }
            )

    if not flattened:
        return []

    flattened.sort(key=lambda item: item["start_dt"])
    merged: list[dict[str, Any]] = []
    for item in flattened:
        if not merged or item["start_dt"] > merged[-1]["end_dt"]:
            merged.append(dict(item))
            continue
        current = merged[-1]
        if item["end_dt"] > current["end_dt"]:
            current["end_dt"] = item["end_dt"]
            current["end_local"] = item["end_local"]
        current["candidate_count"] += int(item.get("candidate_count") or 0)
        current["golden_matched_count"] += int(item.get("golden_matched_count") or 0)
        current["score"] = round(float(current.get("score") or 0.0) + float(item.get("score") or 0.0), 4)
        for card_id in item.get("supporting_card_ids") or []:
            if card_id not in current["supporting_card_ids"]:
                current["supporting_card_ids"].append(card_id)
        if float(item.get("score") or 0.0) >= float(current.get("score") or 0.0):
            current["best_candidate"] = item.get("best_candidate")

    for item in merged:
        item.pop("start_dt", None)
        item.pop("end_dt", None)
    return merged


def _summarize_rectification_pro_chunk_result(chunk: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    refinement = result.get("formula_refinement_results") or {}
    best = refinement.get("best_candidate") or {}
    return {
        "chunk_label": _rectification_pro_chunk_label_text(str(chunk.get("chunk_label") or "")),
        "card_id": chunk.get("card_id"),
        "event_types": list(chunk.get("event_types") or []),
        "event_count": len((chunk.get("payload") or {}).get("events") or []),
        "subchunk_index": chunk.get("subchunk_index"),
        "subchunk_count": chunk.get("subchunk_count"),
        "best_candidate": best.get("candidate_time_local"),
        "score": best.get("score"),
        "working_time_range": refinement.get("working_time_range"),
        "performance_debug": result.get("performance_debug") or {},
    }


def _aggregate_rectification_pro_ranked_reasons(items: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for group in items:
        for item in group:
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or "unknown")
            counts[reason] = counts.get(reason, 0) + int(item.get("count") or 0)
    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
    ]


def _aggregate_rectification_pro_event_audit(chunk_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    total_score = 0.0
    for item in chunk_results:
        best = ((item["result"].get("formula_refinement_results") or {}).get("best_candidate") or {})
        for event_item in best.get("event_contribution_audit") or []:
            if not isinstance(event_item, dict):
                continue
            copied = dict(event_item)
            copied.setdefault("best_orb", None)
            copied.setdefault("avg_orb", None)
            copied.setdefault("affected_best_candidate", bool(float(copied.get("score") or 0.0)))
            copied.setdefault(
                "tier_summary",
                {
                    "golden": int(copied.get("golden_matched_count") or 0),
                    "supporting": int(copied.get("supporting_matched_count") or 0),
                    "context": int(copied.get("context_matched_count") or 0),
                },
            )
            audit.append(copied)
            total_score += float(copied.get("score") or 0.0)
    for item in audit:
        if total_score <= 0:
            item["contribution_to_final_candidate"] = 0.0
        else:
            item["contribution_to_final_candidate"] = round((float(item.get("score") or 0.0) / total_score) * 100.0, 2)
        item["score_contribution"] = round(float(item.get("score") or 0.0), 4)
    return audit


def _aggregate_rectification_pro_card_audit(chunk_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    total_score = 0.0
    for item in chunk_results:
        best = ((item["result"].get("formula_refinement_results") or {}).get("best_candidate") or {})
        chunk = item["chunk"]
        audit_items = best.get("card_contribution_audit") or []
        card_item = dict(audit_items[0]) if audit_items else {
            "card_id": chunk.get("card_id"),
            "score": float(best.get("score") or 0.0),
            "matched_count": int(best.get("matched_count") or 0),
            "rejected_count": int(best.get("rejected_count") or 0),
            "missed_count": int(best.get("missing_count") or 0),
            "golden_matched_count": int(best.get("golden_matched_count") or 0),
            "supporting_matched_count": int(best.get("supporting_matched_count") or 0),
            "context_matched_count": int(best.get("context_matched_count") or 0),
            "context_score": float(best.get("context_score") or 0.0),
            "top_rejected_reasons": best.get("top_rejected_reasons") or [],
        }
        card_id = str(card_item.get("card_id") or chunk.get("card_id") or "unknown")
        merged_item = merged.setdefault(
            card_id,
            {
                "card_id": card_id,
                "score": 0.0,
                "matched_count": 0,
                "rejected_count": 0,
                "missed_count": 0,
                "golden_matched_count": 0,
                "supporting_matched_count": 0,
                "context_matched_count": 0,
                "context_score": 0.0,
                "top_rejected_reasons": [],
            },
        )
        merged_item["score"] = round(float(merged_item["score"]) + float(card_item.get("score") or 0.0), 4)
        merged_item["matched_count"] += int(card_item.get("matched_count") or 0)
        merged_item["rejected_count"] += int(card_item.get("rejected_count") or 0)
        merged_item["missed_count"] += int(card_item.get("missed_count") or 0)
        merged_item["golden_matched_count"] += int(card_item.get("golden_matched_count") or 0)
        merged_item["supporting_matched_count"] += int(card_item.get("supporting_matched_count") or 0)
        merged_item["context_matched_count"] += int(card_item.get("context_matched_count") or 0)
        merged_item["context_score"] = round(
            float(merged_item["context_score"]) + float(card_item.get("context_score") or 0.0),
            4,
        )
        merged_item["top_rejected_reasons"] = _aggregate_rectification_pro_ranked_reasons(
            [
                merged_item.get("top_rejected_reasons") or [],
                card_item.get("top_rejected_reasons") or [],
            ]
        )
        total_score += float(card_item.get("score") or 0.0)
    card_items = list(merged.values())
    for item in card_items:
        if total_score <= 0:
            item["contribution_to_final_candidate"] = 0.0
        else:
            item["contribution_to_final_candidate"] = round((float(item.get("score") or 0.0) / total_score) * 100.0, 2)
    return card_items


def _aggregate_rectification_pro_event_type_contribution(chunk_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    total_score = 0.0
    for item in chunk_results:
        best = ((item["result"].get("formula_refinement_results") or {}).get("best_candidate") or {})
        for event_item in best.get("event_type_contribution") or []:
            if not isinstance(event_item, dict):
                continue
            event_type = str(event_item.get("event_type") or "unknown")
            merged_item = merged.setdefault(
                event_type,
                {
                    "event_type": event_type,
                    "card_ids": [],
                    "score": 0.0,
                    "matched_count": 0,
                    "rejected_count": 0,
                    "missed_count": 0,
                    "golden_matched_count": 0,
                    "supporting_matched_count": 0,
                    "context_matched_count": 0,
                    "context_score": 0.0,
                },
            )
            merged_item["score"] = round(float(merged_item["score"]) + float(event_item.get("score") or 0.0), 4)
            merged_item["matched_count"] += int(event_item.get("matched_count") or 0)
            merged_item["rejected_count"] += int(event_item.get("rejected_count") or 0)
            merged_item["missed_count"] += int(event_item.get("missed_count") or 0)
            merged_item["golden_matched_count"] += int(event_item.get("golden_matched_count") or 0)
            merged_item["supporting_matched_count"] += int(event_item.get("supporting_matched_count") or 0)
            merged_item["context_matched_count"] += int(event_item.get("context_matched_count") or 0)
            merged_item["context_score"] = round(float(merged_item["context_score"]) + float(event_item.get("context_score") or 0.0), 4)
            for card_id in event_item.get("card_ids") or []:
                if card_id not in merged_item["card_ids"]:
                    merged_item["card_ids"].append(card_id)
            total_score += float(event_item.get("score") or 0.0)
    result = list(merged.values())
    for item in result:
        if total_score <= 0:
            item["contribution_to_final_candidate"] = 0.0
        else:
            item["contribution_to_final_candidate"] = round((float(item.get("score") or 0.0) / total_score) * 100.0, 2)
    return result


def _build_rectification_pro_question_efficiency_recommendation(item: dict[str, Any]) -> dict[str, str]:
    matched_count = int(item.get("matched_count") or 0)
    rejected_count = int(item.get("rejected_count") or 0)
    missed_count = int(item.get("missed_count") or 0)
    contribution_percent = float(item.get("contribution_to_final_candidate") or 0.0)
    if matched_count >= 3 or contribution_percent >= 15.0:
        return {
            "recommendation_code": "keep",
            "recommendation": "Оставить как сильный вопрос/событие.",
        }
    if matched_count <= 1 and contribution_percent < 5.0 and rejected_count >= matched_count:
        return {
            "recommendation_code": "merge",
            "recommendation": "Кандидат на объединение с соседним вопросом или блоком.",
        }
    if missed_count > matched_count and contribution_percent < 10.0:
        return {
            "recommendation_code": "supplemental_block",
            "recommendation": "Скорее дополнительный блок: сигнал слабый, но не нулевой.",
        }
    return {
        "recommendation_code": "review_weak",
        "recommendation": "Нужна экспертная проверка: польза пограничная, автоматом не удалять.",
    }


def _build_rectification_pro_question_efficiency_audit(
    event_contribution_audit: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    audit: list[dict[str, Any]] = []
    for item in event_contribution_audit:
        recommendation = _build_rectification_pro_question_efficiency_recommendation(item)
        audit.append(
            {
                "event_id": item.get("event_id"),
                "event_type": item.get("event_type"),
                "event_date": item.get("event_date"),
                "card_id": item.get("card_id"),
                "matched_count": int(item.get("matched_count") or 0),
                "rejected_count": int(item.get("rejected_count") or 0),
                "missed_count": int(item.get("missed_count") or 0),
                "best_orb": item.get("best_orb"),
                "avg_orb": item.get("avg_orb"),
                "score_contribution": round(float(item.get("score_contribution") or item.get("score") or 0.0), 4),
                "contribution_to_final_candidate": round(float(item.get("contribution_to_final_candidate") or 0.0), 2),
                "affected_best_candidate": bool(item.get("affected_best_candidate")),
                "tier_summary": {
                    "golden": int((item.get("tier_summary") or {}).get("golden") or item.get("golden_matched_count") or 0),
                    "supporting": int((item.get("tier_summary") or {}).get("supporting") or item.get("supporting_matched_count") or 0),
                    "context": int((item.get("tier_summary") or {}).get("context") or item.get("context_matched_count") or 0),
                },
                "recommendation_code": recommendation["recommendation_code"],
                "recommendation": recommendation["recommendation"],
                "action_policy": "advisory_only",
            }
        )
    return sorted(
        audit,
        key=lambda row: (
            -float(row.get("contribution_to_final_candidate") or 0.0),
            -int(row.get("matched_count") or 0),
            float(row.get("best_orb") if row.get("best_orb") is not None else 999.0),
            str(row.get("event_date") or ""),
        ),
    )


def _build_rectification_pro_question_efficiency_excel_sheet(
    question_efficiency_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in question_efficiency_audit:
        tier_summary = item.get("tier_summary") or {}
        rows.append(
            {
                "Тип события": item.get("event_type"),
                "Дата события": item.get("event_date"),
                "ID карточки": item.get("card_id"),
                "Совпало формул": item.get("matched_count"),
                "Отклонено формул": item.get("rejected_count"),
                "Не найдено формул": item.get("missed_count"),
                "Лучший орбис": item.get("best_orb"),
                "Средний орбис": item.get("avg_orb"),
                "Вклад в score": item.get("score_contribution"),
                "Вклад в итог %": item.get("contribution_to_final_candidate"),
                "Повлиял на best candidate": item.get("affected_best_candidate"),
                "Golden": tier_summary.get("golden"),
                "Supporting": tier_summary.get("supporting"),
                "Context": tier_summary.get("context"),
                "Рекомендация": item.get("recommendation"),
            }
        )
    return {
        "sheet_name": "Эффективность вопросов",
        "columns": list(rows[0].keys()) if rows else [
            "Тип события",
            "Дата события",
            "ID карточки",
            "Совпало формул",
            "Отклонено формул",
            "Не найдено формул",
            "Лучший орбис",
            "Средний орбис",
            "Вклад в score",
            "Вклад в итог %",
            "Повлиял на best candidate",
            "Golden",
            "Supporting",
            "Context",
            "Рекомендация",
        ],
        "rows": rows,
        "sort_default": ["ID карточки", "Дата события", "Вклад в итог %", "Лучший орбис"],
    }


def _rectification_pro_excel_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rectification_pro_excel_sort_value(row: dict[str, Any], key: str) -> tuple[int, Any]:
    value = row.get(key)
    number = _rectification_pro_excel_number(value)
    if number is not None:
        return (0, number)
    if value is None:
        return (2, "")
    return (1, str(value))


def _sort_rectification_pro_excel_rows(rows: list[dict[str, Any]], sort_default: list[str]) -> list[dict[str, Any]]:
    if not sort_default:
        return list(rows)
    return sorted(rows, key=lambda row: tuple(_rectification_pro_excel_sort_value(row, key) for key in sort_default))


def _rectification_pro_excel_sheet(
    sheet_name: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    sort_default: list[str],
) -> dict[str, Any]:
    sorted_rows = _sort_rectification_pro_excel_rows(rows, sort_default)
    return {
        "sheet_name": sheet_name,
        "columns": columns,
        "rows": sorted_rows,
        "sort_default": sort_default,
    }


def _build_rectification_pro_formula_rule_indexes(
    validation_report: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    expected_rules = ((validation_report.get("expected_by_card") or {}).get("direction_rules") or [])
    expected_by_id = {
        str(rule.get("id") or ""): rule
        for rule in expected_rules
        if isinstance(rule, dict) and str(rule.get("id") or "").strip()
    }
    debug_by_id = {
        str(rule.get("rule_id") or ""): rule
        for rule in (validation_report.get("rule_debug") or [])
        if isinstance(rule, dict) and str(rule.get("rule_id") or "").strip()
    }
    return expected_by_id, debug_by_id


def _build_rectification_pro_formula_event_lookup(
    chunk: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    events = list((chunk.get("payload") or {}).get("events") or [])
    event_by_id: dict[str, dict[str, Any]] = {}
    events_by_type: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or "").strip()
        event_type = str(event.get("event_type") or "").strip()
        if event_id:
            event_by_id[event_id] = event
        events_by_type.setdefault(event_type, []).append(event)
    return event_by_id, events_by_type, events


def _resolve_rectification_pro_formula_event_meta(
    *,
    formula_result: dict[str, Any],
    fallback_event: dict[str, Any] | None,
) -> dict[str, Any]:
    event_type = (
        formula_result.get("source_event_type")
        or formula_result.get("event_type")
        or (fallback_event or {}).get("event_type")
        or ""
    )
    return {
        "event_type": str(event_type or ""),
        "event_date": (
            formula_result.get("source_event_date")
            or formula_result.get("event_date")
            or (fallback_event or {}).get("start_date")
            or (fallback_event or {}).get("date_text")
            or ""
        ),
        "event_id": formula_result.get("event_id") or (fallback_event or {}).get("event_id"),
        "event_title": formula_result.get("source_event_title") or formula_result.get("event_title") or (fallback_event or {}).get("title"),
    }


def _build_rectification_pro_formula_status_row(
    *,
    card_id: str,
    event_meta: dict[str, Any],
    candidate_time: str | None,
    rule_id: str,
    expected_rule: dict[str, Any],
    debug_rule: dict[str, Any],
    item: dict[str, Any],
    status_label: str,
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    checked_pairs = list(debug_rule.get("checked_pairs") or [])
    matched_pairs = list(debug_rule.get("matched_pairs") or [])
    rejected_pairs = list(debug_rule.get("rejected_pairs") or [])
    pair = matched_pairs[0] if matched_pairs else rejected_pairs[0] if rejected_pairs else checked_pairs[0] if checked_pairs else {}
    actual_angle = item.get("actual_angle", pair.get("actual_angle"))
    exact_angle = item.get("exact_angle", pair.get("exact_angle"))
    orb = item.get("orb", pair.get("orb"))
    orb_limit = item.get("orb_limit", pair.get("orb_limit"))
    return {
        "ID карточки": card_id,
        "Тип события": event_meta.get("event_type"),
        "Дата события": event_meta.get("event_date"),
        "Кандидат времени": candidate_time,
        "ID формулы": rule_id,
        "Уровень": expected_rule.get("priority") or debug_rule.get("priority"),
        "Направленный объект": item.get("directed_point") or pair.get("directed_point"),
        "Натальный объект": item.get("natal_target") or pair.get("natal_target"),
        "Аспект": item.get("aspect_type") or expected_rule.get("aspect") or pair.get("aspect_type"),
        "Точный угол": exact_angle,
        "Фактический угол": actual_angle,
        "Орбис": orb,
        "Лимит орбиса": orb_limit,
        "Статус": status_label,
        "Вес / балл": item.get("score"),
        "Причина отклонения": rejection_reason or item.get("reason"),
    }


def _collect_rectification_pro_formula_sheet_rows(
    chunk_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    matched_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []

    for item in chunk_results:
        chunk = item["chunk"]
        result = item["result"]
        refinement = result.get("formula_refinement_results") or {}
        candidate_time = (refinement.get("best_candidate") or {}).get("candidate_time_local")
        event_by_id, events_by_type, fallback_events = _build_rectification_pro_formula_event_lookup(chunk)
        formula_results = list(result.get("formula_test_mode_results") or [])
        for index, formula_result in enumerate(formula_results):
            if not isinstance(formula_result, dict):
                continue
            validation_report = formula_result.get("validation_report") or {}
            expected_by_id, debug_by_id = _build_rectification_pro_formula_rule_indexes(validation_report)
            fallback_event = None
            event_id = str(formula_result.get("event_id") or "").strip()
            event_type = str(
                formula_result.get("source_event_type")
                or formula_result.get("event_type")
                or validation_report.get("event_type")
                or ""
            ).strip()
            if event_id:
                fallback_event = event_by_id.get(event_id)
            if fallback_event is None and event_type and events_by_type.get(event_type):
                fallback_event = events_by_type[event_type][0]
            if fallback_event is None and index < len(fallback_events):
                fallback_event = fallback_events[index]
            event_meta = _resolve_rectification_pro_formula_event_meta(
                formula_result=formula_result,
                fallback_event=fallback_event,
            )
            card_id = str(formula_result.get("card_id") or chunk.get("card_id") or refinement.get("card_id") or "unknown")

            matched_items = formula_result.get("matched_formula_aspects") or validation_report.get("found_by_engine") or []
            for matched in matched_items:
                if not isinstance(matched, dict):
                    continue
                rule_id = str(matched.get("formula_rule_matched") or matched.get("rule_id") or "").strip()
                matched_rows.append(
                    _build_rectification_pro_formula_status_row(
                        card_id=card_id,
                        event_meta=event_meta,
                        candidate_time=candidate_time,
                        rule_id=rule_id,
                        expected_rule=expected_by_id.get(rule_id, {}),
                        debug_rule=debug_by_id.get(rule_id, {}),
                        item=matched,
                        status_label="совпало",
                    )
                )

            rejected_items = formula_result.get("rejected_aspects") or validation_report.get("rejected_aspects") or []
            for rejected in rejected_items:
                if not isinstance(rejected, dict):
                    continue
                rule_id = str(rejected.get("formula_rule_matched") or rejected.get("rule_id") or "").strip()
                rejected_rows.append(
                    _build_rectification_pro_formula_status_row(
                        card_id=card_id,
                        event_meta=event_meta,
                        candidate_time=candidate_time,
                        rule_id=rule_id,
                        expected_rule=expected_by_id.get(rule_id, {}),
                        debug_rule=debug_by_id.get(rule_id, {}),
                        item=rejected,
                        status_label="отклонено",
                        rejection_reason=str(rejected.get("reason") or ""),
                    )
                )

            missing_items = formula_result.get("missing_formula_links") or validation_report.get("missed_by_engine") or []
            for missing in missing_items:
                if not isinstance(missing, dict):
                    continue
                rule_id = str(missing.get("rule_id") or missing.get("formula_rule_matched") or "").strip()
                expected_rule = expected_by_id.get(rule_id, {})
                missing_rows.append(
                    {
                        "ID карточки": card_id,
                        "Тип события": event_meta.get("event_type"),
                        "Дата события": event_meta.get("event_date"),
                        "Кандидат времени": candidate_time,
                        "ID формулы": rule_id,
                        "Уровень": expected_rule.get("priority"),
                        "Направленный объект": None,
                        "Натальный объект": None,
                        "Аспект": expected_rule.get("aspect"),
                        "Точный угол": None,
                        "Фактический угол": None,
                        "Орбис": None,
                        "Лимит орбиса": None,
                        "Статус": "не найдено",
                        "Вес / балл": None,
                        "Причина отклонения": missing.get("reason"),
                    }
                )

    orb_rows = [
        dict(row)
        for row in matched_rows + rejected_rows
        if _rectification_pro_excel_number(row.get("Орбис")) is not None
        and float(_rectification_pro_excel_number(row.get("Орбис")) or 0.0) <= 2.0
    ]
    return matched_rows, rejected_rows, missing_rows, orb_rows


def _build_rectification_pro_multi_card_sheet_specs(
    *,
    payload: dict[str, Any],
    formula_multi_card_report: dict[str, Any],
    formula_refinement_results: dict[str, Any],
    chunk_results: list[dict[str, Any]],
    question_efficiency_audit: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overall_best = formula_multi_card_report.get("overall_best_candidate") or {}
    top_candidates = list(formula_refinement_results.get("top_candidates") or [])
    working_ranges = list(formula_multi_card_report.get("overall_working_ranges") or [])
    matched_rows, rejected_rows, missing_rows, orb_rows = _collect_rectification_pro_formula_sheet_rows(chunk_results)

    summary_rows = [
        {
            "ID карточки": ", ".join(formula_multi_card_report.get("selected_card_ids") or []),
            "Тип события": ", ".join(sorted({str(item.get("event_type") or "") for item in formula_multi_card_report.get("event_type_contribution") or [] if str(item.get("event_type") or "").strip()})),
            "Дата события": ", ".join(sorted({str(item.get("event_date") or "") for item in formula_multi_card_report.get("event_contribution_audit") or [] if str(item.get("event_date") or "").strip()})),
            "Кандидат времени": overall_best.get("candidate_time_local"),
            "Статус": "combined_report_ready",
            "Вес / балл": overall_best.get("score"),
        }
    ]

    candidate_rows: list[dict[str, Any]] = []
    for candidate in top_candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_rows.append(
            {
                "Кандидат времени": candidate.get("candidate_time_local"),
                "Вес / балл": candidate.get("score"),
                "Статус": "candidate",
                "Совпало формул": candidate.get("matched_count"),
                "Отклонено формул": candidate.get("rejected_count"),
                "Не найдено формул": candidate.get("missing_count"),
                "Golden": candidate.get("golden_matched_count"),
                "Supporting": candidate.get("supporting_matched_count"),
                "Context": candidate.get("context_matched_count"),
            }
        )
    if not candidate_rows:
        for item in working_ranges:
            candidate_rows.append(
                {
                    "Кандидат времени": item.get("best_candidate"),
                    "Вес / балл": item.get("score"),
                    "Статус": "working_range",
                    "Совпало формул": item.get("golden_matched_count"),
                    "Отклонено формул": None,
                    "Не найдено формул": None,
                    "Golden": item.get("golden_matched_count"),
                    "Supporting": None,
                    "Context": None,
                }
            )

    per_card_rows: list[dict[str, Any]] = []
    cards_by_id = {
        str(item.get("card_id") or ""): item
        for item in formula_multi_card_report.get("cards") or []
        if isinstance(item, dict)
    }
    for item in formula_multi_card_report.get("card_contribution_audit") or []:
        if not isinstance(item, dict):
            continue
        card_meta = cards_by_id.get(str(item.get("card_id") or ""), {})
        priority_counts = card_meta.get("priority_counts") or {}
        per_card_rows.append(
            {
                "ID карточки": item.get("card_id"),
                "Тип события": ", ".join(card_meta.get("event_types") or []) if isinstance(card_meta.get("event_types"), list) else None,
                "Дата события": None,
                "Кандидат времени": overall_best.get("candidate_time_local"),
                "Статус": "card_summary",
                "Вес / балл": item.get("score"),
                "Совпало формул": item.get("matched_count"),
                "Отклонено формул": item.get("rejected_count"),
                "Не найдено формул": item.get("missed_count"),
                "Golden": priority_counts.get("golden", item.get("golden_matched_count")),
                "Supporting": priority_counts.get("supporting", item.get("supporting_matched_count")),
                "Context": priority_counts.get("context", item.get("context_matched_count")),
            }
        )

    chunk_rows: list[dict[str, Any]] = []
    for chunk in formula_multi_card_report.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        perf = chunk.get("performance_debug") or {}
        chunk_rows.append(
            {
                "ID карточки": chunk.get("card_id"),
                "Тип события": ", ".join(chunk.get("event_types") or []),
                "Дата события": None,
                "Кандидат времени": chunk.get("best_candidate"),
                "Статус": f"chunk {chunk.get('subchunk_index') or 1}/{chunk.get('subchunk_count') or 1}",
                "Вес / балл": chunk.get("score"),
                "Блок": chunk.get("chunk_label"),
                "Событий в блоке": chunk.get("event_count"),
                "Время блока, мс": perf.get("total_runtime_ms"),
            }
        )

    disputed_rows: list[dict[str, Any]] = []
    for reason in formula_multi_card_report.get("top_rejected_reasons") or []:
        if not isinstance(reason, dict):
            continue
        disputed_rows.append(
            {
                "ID карточки": None,
                "Тип события": None,
                "Дата события": None,
                "Кандидат времени": overall_best.get("candidate_time_local"),
                "Статус": "rejected_reason",
                "Вес / балл": reason.get("count"),
                "Причина отклонения": reason.get("reason"),
            }
        )
    for reason in formula_multi_card_report.get("unresolved_source_summary") or []:
        if not isinstance(reason, dict):
            continue
        disputed_rows.append(
            {
                "ID карточки": None,
                "Тип события": None,
                "Дата события": None,
                "Кандидат времени": overall_best.get("candidate_time_local"),
                "Статус": "unresolved_source",
                "Вес / балл": reason.get("count"),
                "Причина отклонения": reason.get("reason"),
            }
        )

    sheets = [
        _build_rectification_pro_question_efficiency_excel_sheet(question_efficiency_audit),
        _rectification_pro_excel_sheet(
            "Итог",
            summary_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "Статус", "Вес / балл"],
            ["Кандидат времени"],
        ),
        _rectification_pro_excel_sheet(
            "Кандидаты времени",
            candidate_rows,
            ["Кандидат времени", "Вес / балл", "Статус", "Совпало формул", "Отклонено формул", "Не найдено формул", "Golden", "Supporting", "Context"],
            ["Кандидат времени", "Вес / балл"],
        ),
        _rectification_pro_excel_sheet(
            "Совпавшие формулы",
            matched_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "ID формулы", "Уровень", "Направленный объект", "Натальный объект", "Аспект", "Точный угол", "Фактический угол", "Орбис", "Лимит орбиса", "Статус", "Вес / балл", "Причина отклонения"],
            ["ID карточки", "Тип события", "Статус", "Орбис"],
        ),
        _rectification_pro_excel_sheet(
            "Отклонённые формулы",
            rejected_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "ID формулы", "Уровень", "Направленный объект", "Натальный объект", "Аспект", "Точный угол", "Фактический угол", "Орбис", "Лимит орбиса", "Статус", "Вес / балл", "Причина отклонения"],
            ["ID карточки", "Тип события", "Статус", "Орбис"],
        ),
        _rectification_pro_excel_sheet(
            "Не найденные формулы",
            missing_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "ID формулы", "Уровень", "Направленный объект", "Натальный объект", "Аспект", "Точный угол", "Фактический угол", "Орбис", "Лимит орбиса", "Статус", "Вес / балл", "Причина отклонения"],
            ["ID карточки", "Тип события", "Статус", "ID формулы"],
        ),
        _rectification_pro_excel_sheet(
            "Орбис до 2°",
            orb_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "ID формулы", "Уровень", "Направленный объект", "Натальный объект", "Аспект", "Точный угол", "Фактический угол", "Орбис", "Лимит орбиса", "Статус", "Вес / балл", "Причина отклонения"],
            ["ID карточки", "Тип события", "Статус", "Орбис"],
        ),
        _rectification_pro_excel_sheet(
            "По карточкам",
            per_card_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "Статус", "Вес / балл", "Совпало формул", "Отклонено формул", "Не найдено формул", "Golden", "Supporting", "Context"],
            ["ID карточки", "Статус"],
        ),
        _rectification_pro_excel_sheet(
            "Блоки расчёта",
            chunk_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "Статус", "Вес / балл", "Блок", "Событий в блоке", "Время блока, мс"],
            ["ID карточки", "Блок", "Статус"],
        ),
        _rectification_pro_excel_sheet(
            "Спорные зоны",
            disputed_rows,
            ["ID карточки", "Тип события", "Дата события", "Кандидат времени", "Статус", "Вес / балл", "Причина отклонения"],
            ["Статус", "Причина отклонения"],
        ),
    ]
    return sheets


def _build_rectification_pro_multi_card_expert_artifacts(
    *,
    payload: dict[str, Any],
    formula_multi_card_report: dict[str, Any],
    formula_refinement_results: dict[str, Any],
    chunk_results: list[dict[str, Any]],
    question_efficiency_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    sheets = _build_rectification_pro_multi_card_sheet_specs(
        payload=payload,
        formula_multi_card_report=formula_multi_card_report,
        formula_refinement_results=formula_refinement_results,
        chunk_results=chunk_results,
        question_efficiency_audit=question_efficiency_audit,
    )
    return {
        "expert_tables": [
            {
                "title": sheet["sheet_name"],
                "columns": list(sheet.get("columns") or []),
                "rows": list(sheet.get("rows") or []),
            }
            for sheet in sheets
        ],
        "expert_excel_export": {
            "action_policy": "advisory_only",
            "filename": "astrodvish-v2-combined-report.xlsx",
            "sheets": sheets,
        },
    }


def _sanitize_rectification_pro_excel_filename(filename: str | None) -> str:
    value = str(filename or "").strip() or "astrodvish-v2-combined-report.xlsx"
    if not value.lower().endswith(".xlsx"):
        value = f"{value}.xlsx"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return safe or "astrodvish-v2-combined-report.xlsx"


def _sanitize_rectification_pro_sheet_name(sheet_name: str, used: set[str]) -> str:
    value = re.sub(r"[\[\]:*?/\\]+", " ", str(sheet_name or "").strip())
    value = re.sub(r"\s+", " ", value).strip() or "Лист"
    value = value[:31]
    candidate = value
    suffix = 2
    while candidate in used:
        trimmed = value[: max(0, 31 - len(str(suffix)) - 1)].rstrip()
        candidate = f"{trimmed}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _rectification_pro_xlsx_column_name(index: int) -> str:
    value = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        value = chr(65 + remainder) + value
    return value or "A"


def _rectification_pro_xlsx_cell_xml(cell_ref: str, value: Any, style_id: int = 0) -> str:
    if value is None or value == "":
        return f'<c r="{cell_ref}" s="{style_id}"/>'
    number = _rectification_pro_excel_number(value)
    if number is not None:
        return f'<c r="{cell_ref}" s="{style_id}"><v>{number}</v></c>'
    if isinstance(value, bool):
        bool_value = "да" if value else "нет"
        return f'<c r="{cell_ref}" s="{style_id}" t="inlineStr"><is><t>{escape(bool_value)}</t></is></c>'
    return f'<c r="{cell_ref}" s="{style_id}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def _build_rectification_pro_xlsx_sheet_xml(sheet: dict[str, Any]) -> str:
    columns = list(sheet.get("columns") or [])
    rows = list(sheet.get("rows") or [])
    last_column_name = _rectification_pro_xlsx_column_name(max(len(columns), 1))
    last_row_number = max(len(rows) + 1, 1)
    header_cells = "".join(
        _rectification_pro_xlsx_cell_xml(f"{_rectification_pro_xlsx_column_name(index + 1)}1", header, style_id=1)
        for index, header in enumerate(columns)
    )
    body_rows_xml: list[str] = [f'<row r="1">{header_cells}</row>']
    for row_index, row in enumerate(rows, start=2):
        cells = []
        for col_index, header in enumerate(columns, start=1):
            cell_ref = f"{_rectification_pro_xlsx_column_name(col_index)}{row_index}"
            cells.append(_rectification_pro_xlsx_cell_xml(cell_ref, row.get(header)))
        body_rows_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    cols_xml: list[str] = []
    for index, header in enumerate(columns, start=1):
        max_len = len(str(header))
        for row in rows:
            value = row.get(header)
            rendered = "" if value is None else ("да" if value is True else "нет" if value is False else str(value))
            max_len = max(max_len, len(rendered))
        width = min(max(max_len + 2, 12), 60)
        cols_xml.append(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>')

    auto_filter_ref = f"A1:{last_column_name}{last_row_number}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/>'
        "</sheetView></sheetViews>"
        f"<cols>{''.join(cols_xml)}</cols>"
        f'<sheetData>{"".join(body_rows_xml)}</sheetData>'
        f'<autoFilter ref="{auto_filter_ref}"/>'
        "</worksheet>"
    )


def _build_rectification_pro_excel_bytes(export_payload: RectificationProExcelExportRequest) -> bytes:
    used_sheet_names: set[str] = set()
    normalized_sheets: list[tuple[str, dict[str, Any]]] = []
    for sheet in export_payload.sheets:
        normalized_name = _sanitize_rectification_pro_sheet_name(sheet.sheet_name, used_sheet_names)
        normalized_sheets.append(
            (
                normalized_name,
                {
                    "columns": list(sheet.columns or []),
                    "rows": _sort_rectification_pro_excel_rows(list(sheet.rows or []), list(sheet.sort_default or [])),
                },
            )
        )

    workbook_sheets_xml = []
    workbook_rels_xml = []
    worksheets_xml: list[tuple[str, str]] = []
    for index, (sheet_name, sheet) in enumerate(normalized_sheets, start=1):
        workbook_sheets_xml.append(
            f'<sheet name="{escape(sheet_name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        workbook_rels_xml.append(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        )
        worksheets_xml.append((f"xl/worksheets/sheet{index}.xml", _build_rectification_pro_xlsx_sheet_xml(sheet)))

    workbook_rels_xml.append(
        f'<Relationship Id="rId{len(normalized_sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(workbook_sheets_xml)}</sheets>"
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(workbook_rels_xml)}"
        "</Relationships>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="2">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF4E3B2"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '</cellXfs>'
        '</styleSheet>'
    )
    worksheet_content_overrides = "".join(
        (
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        for index in range(1, len(normalized_sheets) + 1)
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{worksheet_content_overrides}"
        '</Types>'
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>AstroDvish V2 combined report</dc:title>'
        '<dc:creator>Codex</dc:creator>'
        '<cp:lastModifiedBy>Codex</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).isoformat()}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).isoformat()}</dcterms:modified>'
        '</cp:coreProperties>'
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>AstroDvish</Application>'
        '</Properties>'
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles_xml)
        for path, xml_content in worksheets_xml:
            archive.writestr(path, xml_content)
    return buffer.getvalue()


def _aggregate_rectification_pro_chunk_results(
    *,
    payload: dict[str, Any],
    chunk_plan: dict[str, Any],
    chunk_results: list[dict[str, Any]],
    total_runtime_ms: float,
) -> dict[str, Any]:
    selected_card_ids = list(chunk_plan.get("selected_card_ids") or [])
    if not selected_card_ids:
        selected_card_ids = [
            str(item["chunk"].get("card_id") or "").strip()
            for item in chunk_results
            if str(item["chunk"].get("card_id") or "").strip()
        ]
    card_items_by_id: dict[str, dict[str, Any]] = {}
    warnings: set[str] = set()
    limitations: list[str] = []
    formula_counts_by_card: dict[str, int] = {}
    total_candidate_count = 0
    score_breakdown = {
        "matched_formula_score": 0.0,
        "orb_strength_score": 0.0,
        "participant_bonus_score": 0.0,
        "golden_formula_score": 0.0,
        "golden_orb_quality_score": 0.0,
        "supporting_formula_score": 0.0,
        "context_formula_score": 0.0,
        "supporting_bonus": 0.0,
        "ambiguity_penalty": 0.0,
        "event_confirmation_score": 0.0,
        "time_refinement_score": 0.0,
        "rejected_penalty": 0.0,
        "missing_penalty": 0.0,
    }
    top_formulas: list[str] = []
    best_candidates: list[dict[str, Any]] = []
    top_rejected_reasons_input: list[list[dict[str, Any]]] = []
    unresolved_summary_input: list[list[dict[str, Any]]] = []

    for item in chunk_results:
        chunk = item["chunk"]
        result = item["result"]
        refinement = result.get("formula_refinement_results") or {}
        best = refinement.get("best_candidate") or {}
        warnings.update(result.get("warnings") or [])
        for limitation in result.get("limitations") or []:
            if limitation not in limitations:
                limitations.append(limitation)
        card_id = str(refinement.get("card_id") or chunk.get("card_id") or "").strip()
        formula_counts_by_card[card_id] = max(
            formula_counts_by_card.get(card_id, 0),
            int((result.get("performance_debug") or {}).get("formula_count") or refinement.get("formulas_count") or 0),
        )
        total_candidate_count += int((result.get("performance_debug") or {}).get("candidate_count") or 0)
        card_item = card_items_by_id.setdefault(
            card_id,
            {
                "card_id": refinement.get("card_id") or chunk.get("card_id"),
                "card_version": refinement.get("card_version"),
                "formulas_count": int(refinement.get("formulas_count") or 0),
                "priority_counts": dict(refinement.get("priority_counts") or {}),
                "event_types": [],
                "chunk_labels": [],
                "chunk_count": 0,
                "event_count": 0,
            },
        )
        card_item["chunk_count"] += 1
        card_item["event_count"] += len((chunk.get("payload") or {}).get("events") or [])
        card_item["formulas_count"] = max(
            int(card_item.get("formulas_count") or 0),
            int(refinement.get("formulas_count") or 0),
        )
        for event_type in chunk.get("event_types") or []:
            if event_type not in card_item["event_types"]:
                card_item["event_types"].append(event_type)
        chunk_label = chunk.get("chunk_label")
        if chunk_label and chunk_label not in card_item["chunk_labels"]:
            card_item["chunk_labels"].append(chunk_label)
        best_candidates.append(dict(best))
        for field in score_breakdown:
            score_breakdown[field] = round(
                float(score_breakdown[field]) + float((best.get("score_breakdown") or {}).get(field) or 0.0),
                4,
            )
        top_formulas.extend([str(value) for value in (best.get("best_formulas") or []) if str(value).strip()])
        top_rejected_reasons_input.append(best.get("top_rejected_reasons") or [])
        unresolved_summary_input.append(best.get("unresolved_source_summary") or [])

    card_audit = _aggregate_rectification_pro_card_audit(chunk_results)
    event_type_contribution = _aggregate_rectification_pro_event_type_contribution(chunk_results)
    event_contribution_audit = _aggregate_rectification_pro_event_audit(chunk_results)
    question_efficiency_audit = _build_rectification_pro_question_efficiency_audit(event_contribution_audit)
    working_ranges = _merge_rectification_pro_working_ranges(chunk_results)
    total_score = round(sum(float(item.get("score") or 0.0) for item in card_audit), 4)
    card_items = list(card_items_by_id.values())
    total_formula_count = sum(formula_counts_by_card.values())
    merged_priority_counts = _merge_rectification_pro_chunk_counts(card_items)
    primary_range = None
    if working_ranges:
        primary_range = max(working_ranges, key=lambda item: float(item.get("score") or 0.0))

    selected_candidate_time = None
    if primary_range:
        selected_candidate_time = primary_range.get("best_candidate")
    if not selected_candidate_time and best_candidates:
        selected_candidate_time = max(best_candidates, key=lambda item: float(item.get("score") or 0.0)).get("candidate_time_local")

    overall_best_candidate = {
        "candidate_time_local": selected_candidate_time,
        "candidate_time_utc": None,
        "score": total_score,
        "matched_count": sum(int(item.get("matched_count") or 0) for item in card_audit),
        "rejected_count": sum(int(item.get("rejected_count") or 0) for item in card_audit),
        "missing_count": sum(int(item.get("missed_count") or 0) for item in card_audit),
        "golden_matched_count": sum(int(item.get("golden_matched_count") or 0) for item in card_audit),
        "golden_orb_sum": round(sum(float((candidate.get("golden_orb_sum") or 0.0)) for candidate in best_candidates), 4),
        "supporting_matched_count": sum(int(item.get("supporting_matched_count") or 0) for item in card_audit),
        "context_matched_count": sum(int(item.get("context_matched_count") or 0) for item in card_audit),
        "context_score": round(sum(float(item.get("context_score") or 0.0) for item in card_audit), 4),
        "supporting_bonus": round(sum(float(candidate.get("supporting_bonus") or 0.0) for candidate in best_candidates), 4),
        "event_confirmation_score": round(sum(float(candidate.get("event_confirmation_score") or 0.0) for candidate in best_candidates), 4),
        "time_refinement_score": round(sum(float(candidate.get("time_refinement_score") or 0.0) for candidate in best_candidates), 4),
        "score_breakdown": score_breakdown,
        "best_formulas": list(dict.fromkeys(top_formulas))[:10],
        "top_rejected_reasons": _aggregate_rectification_pro_ranked_reasons(top_rejected_reasons_input),
        "unresolved_source_summary": _aggregate_rectification_pro_ranked_reasons(unresolved_summary_input),
        "event_contribution_audit": event_contribution_audit,
        "card_contribution_audit": card_audit,
        "event_type_contribution": event_type_contribution,
        "selection_reason": (
            f"chunked_async_multi_card aggregation across {len(chunk_results)} blocks; "
            "best live-safe combined range selected from completed chunk summaries."
        ),
        "selected_card_ids": selected_card_ids,
        "multi_card_enabled": True,
        "selected_candidate_time": selected_candidate_time,
        "chart_build_time": selected_candidate_time,
        "natal_houses_time": selected_candidate_time,
        "rulers_resolved_time": selected_candidate_time,
        "house_elements_resolved_time": selected_candidate_time,
        "directed_points_time": selected_candidate_time,
        "timezone_used": next((candidate.get("timezone_used") for candidate in best_candidates if candidate.get("timezone_used")), payload.get("timezone_name")),
        "timezone_offset_used": next((candidate.get("timezone_offset_used") for candidate in best_candidates if candidate.get("timezone_offset_used")), None),
    }

    formula_refinement_results = {
        "enabled": True,
        "step_seconds": None,
        "supported_step_seconds": [],
        "direction_method": "symbolic_1deg_per_year",
        "timezone_used": overall_best_candidate.get("timezone_used"),
        "timezone_offset_used": overall_best_candidate.get("timezone_offset_used"),
        "timezone_source": "chunked_async_multi_card",
        "timezone_name": overall_best_candidate.get("timezone_used"),
        "utc_offset": overall_best_candidate.get("timezone_offset_used"),
        "coordinates_used": {
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
        },
        "payload_path": "rectification_chunked_async_multi_card",
        "card_id": "MULTI_CARD_V2_CHUNKED_ASYNC",
        "card_version": "multi_card_v2_chunked_async",
        "formulas_count": total_formula_count,
        "priority_counts": merged_priority_counts,
        "selected_card_ids": selected_card_ids,
        "cards": card_items,
        "multi_card_enabled": True,
        "scanned_candidates_count": total_candidate_count,
        "top_candidates": [
            {
                "candidate_time_local": candidate.get("candidate_time_local"),
                "score": candidate.get("score"),
                "matched_count": candidate.get("matched_count"),
                "rejected_count": candidate.get("rejected_count"),
                "missing_count": candidate.get("missing_count"),
                "golden_matched_count": candidate.get("golden_matched_count"),
                "supporting_matched_count": candidate.get("supporting_matched_count"),
                "context_matched_count": candidate.get("context_matched_count"),
                "context_score": candidate.get("context_score"),
            }
            for candidate in sorted(best_candidates, key=lambda item: float(item.get("score") or 0.0), reverse=True)
        ],
        "best_candidate": overall_best_candidate,
        "coarse_candidate": None,
        "working_time_ranges": working_ranges,
        "working_time_range": primary_range,
        "reference_time": {
            "provided": ((payload.get("settings") or {}).get("formula_reference_time_local") if isinstance(payload.get("settings"), dict) else None),
            "inside_working_time_range": False,
            "evaluation": None,
        },
        "legacy_mode": False,
        "aggregation_mode": "chunked_async_multi_card",
        "chunks": [_summarize_rectification_pro_chunk_result(item["chunk"], item["result"]) for item in chunk_results],
    }

    formula_multi_card_report = {
        "enabled": True,
        "multi_card_enabled": True,
        "aggregation_mode": "chunked_async_multi_card",
        "selected_card_ids": selected_card_ids,
        "cards": card_items,
        "overall_best_candidate": overall_best_candidate,
        "overall_working_ranges": working_ranges,
        "overall_working_time_range": primary_range,
        "score_summary": {
            "event_confirmation_score": overall_best_candidate.get("event_confirmation_score"),
            "time_refinement_score": overall_best_candidate.get("time_refinement_score"),
            "score_breakdown": score_breakdown,
        },
        "event_contribution_audit": event_contribution_audit,
        "question_efficiency_audit": question_efficiency_audit,
        "event_type_contribution": event_type_contribution,
        "card_contribution_audit": card_audit,
        "top_matched_rules": overall_best_candidate.get("best_formulas") or [],
        "top_rejected_reasons": overall_best_candidate.get("top_rejected_reasons") or [],
        "unresolved_source_summary": overall_best_candidate.get("unresolved_source_summary") or [],
        "expert_notes": [
            "Combined report was calculated sequentially by explicit V2 card/event blocks.",
            "This live-safe mode keeps single-card scoring unchanged and aggregates only completed chunk summaries.",
        ],
        "chunks": [_summarize_rectification_pro_chunk_result(item["chunk"], item["result"]) for item in chunk_results],
        "debug": {
            "direction_method": "symbolic_1deg_per_year",
            "timezone_used": overall_best_candidate.get("timezone_used"),
            "timezone_offset_used": overall_best_candidate.get("timezone_offset_used"),
            "payload_path": "rectification_chunked_async_multi_card",
        },
    }
    formula_multi_card_report.update(
        _build_rectification_pro_multi_card_expert_artifacts(
            payload=payload,
            formula_multi_card_report=formula_multi_card_report,
            formula_refinement_results=formula_refinement_results,
            chunk_results=chunk_results,
            question_efficiency_audit=question_efficiency_audit,
        )
    )

    return {
        "candidate_windows": [],
        "best_candidates": [],
        "method_results": {"directions": [], "solars": [], "lunars": [], "transits": [], "totems": []},
        "formula_test_mode_results": [],
        "formula_refinement_results": formula_refinement_results,
        "formula_card_comparison": {},
        "formula_multi_card_report": formula_multi_card_report,
        "performance_debug": {
            "card_id": "MULTI_CARD_V2_CHUNKED_ASYNC",
            "formula_count": total_formula_count,
            "event_count": len(payload.get("events") or []),
            "candidate_count": total_candidate_count,
            "total_runtime_ms": round(total_runtime_ms, 2),
            "slowest_stage": "chunked_async_multi_card",
            "stage_timings_ms": {
                (
                    f"{str(item['chunk'].get('card_id'))}#"
                    f"{int(item['chunk'].get('subchunk_index') or 1)}/"
                    f"{int(item['chunk'].get('subchunk_count') or 1)}"
                ): float(((item["result"].get("performance_debug") or {}).get("total_runtime_ms") or 0.0))
                for item in chunk_results
            },
        },
        "confidence": {
            "level": "high" if total_score > 0 else "low",
            "time_window_minutes": None,
            "explanation": "Combined V2 expert report aggregated from sequential chunk execution.",
        },
        "warnings": sorted(warnings.union({"chunked_multi_card_async_aggregation"})),
        "limitations": limitations + [
            "Combined expert report is aggregated from sequential per-card chunks to keep the live server stable.",
        ],
    }


def _cleanup_rectification_pro_jobs(now_ts: float | None = None) -> None:
    cutoff = (now_ts or time.time()) - RECTIFICATION_PRO_JOB_TTL_SECONDS
    expired_ids: list[str] = []
    for job_id, payload in _RECTIFICATION_PRO_JOBS.items():
        updated_at = float(payload.get("updated_at") or payload.get("created_at") or 0.0)
        if updated_at < cutoff:
            expired_ids.append(job_id)
    for job_id in expired_ids:
        _RECTIFICATION_PRO_JOBS.pop(job_id, None)


def _get_rectification_pro_job(job_id: str) -> dict[str, Any] | None:
    with _RECTIFICATION_PRO_JOBS_LOCK:
        _cleanup_rectification_pro_jobs()
        job = _RECTIFICATION_PRO_JOBS.get(job_id)
        if job is None:
            return None
        return dict(job)


def _get_active_rectification_pro_job() -> dict[str, Any] | None:
    with _RECTIFICATION_PRO_JOBS_LOCK:
        _cleanup_rectification_pro_jobs()
        for job in _RECTIFICATION_PRO_JOBS.values():
            if job.get("status") in RECTIFICATION_PRO_ACTIVE_JOB_STATUSES:
                return dict(job)
    return None


def _run_rectification_pro_job(
    *,
    job_id: str,
    base_url: str,
    payload: dict[str, Any],
    timeout: int,
    chunk_plan: dict[str, Any] | None = None,
) -> None:
    with _RECTIFICATION_PRO_JOBS_LOCK:
        job = _RECTIFICATION_PRO_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["mode"] = str(chunk_plan.get("mode")) if isinstance(chunk_plan, dict) else "single_async"
        job["updated_at"] = time.time()

    if chunk_plan:
        started_at = perf_counter()
        chunk_results: list[dict[str, Any]] = []
        partial_results: list[dict[str, Any]] = []
        total_chunks = int(chunk_plan.get("total_chunks") or 0)
        chunks = list(chunk_plan.get("chunks") or [])
        for index, chunk in enumerate(chunks):
            chunk_label = str(chunk.get("chunk_label") or "")
            _log_rectification_pro_chunk_guard(
                level=logging.INFO,
                message="Rectification Pro chunk started",
                job_id=job_id,
                guard_stage="chunk_execution",
                events_count=len((chunk.get("payload") or {}).get("events") or []),
                selected_cards_count=1,
                planned_chunks=total_chunks,
                chunk_size=len((chunk.get("payload") or {}).get("events") or []),
                candidate_count=None,
                formula_count=None,
                estimated_weight=int(chunk_plan.get("estimated_weight") or 0),
                guard_reason=f"chunk_{index + 1}_started",
                current_limit=_current_rectification_pro_chunk_limits(),
                runtime_snapshot=_collect_rectification_pro_runtime_snapshot(),
            )
            with _RECTIFICATION_PRO_JOBS_LOCK:
                job = _RECTIFICATION_PRO_JOBS.get(job_id)
                if job is None:
                    return
                job["status"] = "chunk_running"
                job["total_chunks"] = total_chunks
                job["completed_chunks"] = len(partial_results)
                job["failed_chunks"] = 0
                job["current_chunk_label"] = chunk_label
                job["progress_percent"] = int((len(partial_results) / max(total_chunks, 1)) * 100)
                job["user_message"] = _rectification_pro_chunk_user_message(
                    completed_chunks=len(partial_results),
                    total_chunks=total_chunks,
                    current_chunk_label=chunk_label,
                    status="chunk_running",
                )
                job["partial_results"] = list(partial_results)
                job["updated_at"] = time.time()
            try:
                result = _post_rectification_events(
                    base_url=base_url,
                    path="/api/v1/rectification/pro/run",
                    payload=chunk.get("payload") or {},
                    timeout=timeout,
                )
            except HTTPException as exc:
                detail_dict = exc.detail if isinstance(exc.detail, dict) else {}
                _log_rectification_pro_chunk_guard(
                    level=logging.WARNING,
                    message="Rectification Pro chunk failed",
                    job_id=job_id,
                    guard_stage="chunk_execution",
                    events_count=len((chunk.get("payload") or {}).get("events") or []),
                    selected_cards_count=1,
                    planned_chunks=total_chunks,
                    chunk_size=len((chunk.get("payload") or {}).get("events") or []),
                    candidate_count=None,
                    formula_count=None,
                    estimated_weight=int(chunk_plan.get("estimated_weight") or 0),
                    guard_reason=str(detail_dict.get("reason") or "http_exception"),
                    current_limit=_current_rectification_pro_chunk_limits(),
                    runtime_snapshot=_collect_rectification_pro_runtime_snapshot(),
                )
                with _RECTIFICATION_PRO_JOBS_LOCK:
                    job = _RECTIFICATION_PRO_JOBS.get(job_id)
                    if job is None:
                        return
                    job["status"] = "failed"
                    job["completed_chunks"] = len(partial_results)
                    job["failed_chunks"] = 1
                    job["current_chunk_label"] = chunk_label
                    job["progress_percent"] = int((len(partial_results) / max(total_chunks, 1)) * 100)
                    job["partial_results"] = list(partial_results)
                    job["error"] = {
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                    }
                    job["updated_at"] = time.time()
                return
            except Exception as exc:  # noqa: BLE001
                _log_rectification_pro_chunk_guard(
                    level=logging.ERROR,
                    message="Rectification Pro chunk crashed",
                    job_id=job_id,
                    guard_stage="chunk_execution",
                    events_count=len((chunk.get("payload") or {}).get("events") or []),
                    selected_cards_count=1,
                    planned_chunks=total_chunks,
                    chunk_size=len((chunk.get("payload") or {}).get("events") or []),
                    candidate_count=None,
                    formula_count=None,
                    estimated_weight=int(chunk_plan.get("estimated_weight") or 0),
                    guard_reason=type(exc).__name__,
                    current_limit=_current_rectification_pro_chunk_limits(),
                    runtime_snapshot=_collect_rectification_pro_runtime_snapshot(),
                )
                with _RECTIFICATION_PRO_JOBS_LOCK:
                    job = _RECTIFICATION_PRO_JOBS.get(job_id)
                    if job is None:
                        return
                    job["status"] = "failed"
                    job["completed_chunks"] = len(partial_results)
                    job["failed_chunks"] = 1
                    job["current_chunk_label"] = chunk_label
                    job["progress_percent"] = int((len(partial_results) / max(total_chunks, 1)) * 100)
                    job["partial_results"] = list(partial_results)
                    job["error"] = {
                        "status_code": 500,
                        "detail": {
                            "message": "Unexpected async pro chunk error",
                            "user_message": "Сервис Pro-ректификации временно недоступен. Попробуйте повторить позже.",
                            "reason": "internal_async_chunk_error",
                            "error_type": type(exc).__name__,
                            "chunk_label": chunk_label,
                        },
                    }
                    job["updated_at"] = time.time()
                return

            chunk_results.append({"chunk": chunk, "result": result})
            partial_results.append(_summarize_rectification_pro_chunk_result(chunk, result))
            perf = result.get("performance_debug") or {}
            _log_rectification_pro_chunk_guard(
                level=logging.INFO,
                message="Rectification Pro chunk completed",
                job_id=job_id,
                guard_stage="chunk_execution",
                events_count=len((chunk.get("payload") or {}).get("events") or []),
                selected_cards_count=1,
                planned_chunks=total_chunks,
                chunk_size=len((chunk.get("payload") or {}).get("events") or []),
                candidate_count=int(perf.get("candidate_count") or 0),
                formula_count=int(perf.get("formula_count") or 0),
                estimated_weight=int(chunk_plan.get("estimated_weight") or 0),
                guard_reason=f"chunk_{index + 1}_completed",
                current_limit=_current_rectification_pro_chunk_limits(),
                runtime_snapshot=_collect_rectification_pro_runtime_snapshot(),
            )
            with _RECTIFICATION_PRO_JOBS_LOCK:
                job = _RECTIFICATION_PRO_JOBS.get(job_id)
                if job is None:
                    return
                job["status"] = "partial_completed" if index + 1 < total_chunks else "running"
                job["completed_chunks"] = len(partial_results)
                job["failed_chunks"] = 0
                job["current_chunk_label"] = None if index + 1 >= total_chunks else str((chunks[index + 1].get("chunk_label") or ""))
                job["progress_percent"] = int((len(partial_results) / max(total_chunks, 1)) * 100)
                job["user_message"] = _rectification_pro_chunk_user_message(
                    completed_chunks=len(partial_results),
                    total_chunks=total_chunks,
                    current_chunk_label=None,
                    status="partial_completed",
                )
                job["partial_results"] = list(partial_results)
                job["updated_at"] = time.time()

        aggregated_result = _aggregate_rectification_pro_chunk_results(
            payload=payload,
            chunk_plan=chunk_plan,
            chunk_results=chunk_results,
            total_runtime_ms=(perf_counter() - started_at) * 1000,
        )
        with _RECTIFICATION_PRO_JOBS_LOCK:
            job = _RECTIFICATION_PRO_JOBS.get(job_id)
            if job is None:
                return
            job["status"] = "completed"
            job["completed_chunks"] = len(partial_results)
            job["failed_chunks"] = 0
            job["current_chunk_label"] = None
            job["progress_percent"] = 100
            job["user_message"] = _rectification_pro_chunk_user_message(
                completed_chunks=len(partial_results),
                total_chunks=total_chunks,
                current_chunk_label=None,
                status="completed",
            )
            job["partial_results"] = list(partial_results)
            job["result"] = aggregated_result
            job["updated_at"] = time.time()
        return

    try:
        result = _post_rectification_events(
            base_url=base_url,
            path="/api/v1/rectification/pro/run",
            payload=payload,
            timeout=timeout,
        )
    except HTTPException as exc:
        with _RECTIFICATION_PRO_JOBS_LOCK:
            job = _RECTIFICATION_PRO_JOBS.get(job_id)
            if job is None:
                return
            job["status"] = "failed"
            job["error"] = {"status_code": exc.status_code, "detail": exc.detail}
            job["updated_at"] = time.time()
        return
    except Exception as exc:  # noqa: BLE001
        with _RECTIFICATION_PRO_JOBS_LOCK:
            job = _RECTIFICATION_PRO_JOBS.get(job_id)
            if job is None:
                return
            job["status"] = "failed"
            job["error"] = {
                "status_code": 500,
                "detail": {
                    "message": "Unexpected async pro job error",
                    "user_message": "Сервис Pro-ректификации временно недоступен. Попробуйте повторить позже.",
                    "reason": "internal_async_job_error",
                    "error_type": type(exc).__name__,
                },
            }
            job["updated_at"] = time.time()
        return

    with _RECTIFICATION_PRO_JOBS_LOCK:
        job = _RECTIFICATION_PRO_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "completed"
        job["progress_percent"] = 100
        job["result"] = result
        job["updated_at"] = time.time()


def _create_rectification_pro_job(
    *,
    base_url: str,
    payload: dict[str, Any],
    timeout: int,
    chunk_plan: dict[str, Any] | None = None,
) -> str:
    job_id = str(uuid4())
    now_ts = time.time()
    with _RECTIFICATION_PRO_JOBS_LOCK:
        _cleanup_rectification_pro_jobs(now_ts)
        _RECTIFICATION_PRO_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "mode": str(chunk_plan.get("mode")) if isinstance(chunk_plan, dict) else "single_async",
            "result": None,
            "error": None,
            "total_chunks": int(chunk_plan.get("total_chunks") or 1) if isinstance(chunk_plan, dict) else 1,
            "completed_chunks": 0,
            "failed_chunks": 0,
            "current_chunk_label": None,
            "progress_percent": 0,
            "user_message": (
                "Большой V2-отчёт считается по блокам."
                if isinstance(chunk_plan, dict)
                else "Тяжёлый Pro-расчёт поставлен в очередь."
            ),
            "partial_results": [],
            "created_at": now_ts,
            "updated_at": now_ts,
        }
    worker = threading.Thread(
        target=_run_rectification_pro_job,
        kwargs={
            "job_id": job_id,
            "base_url": base_url,
            "payload": payload,
            "timeout": timeout,
            "chunk_plan": chunk_plan,
        },
        daemon=True,
        name=f"rectification-pro-job-{job_id}",
    )
    worker.start()
    return job_id


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


@app.get("/api/preview/pro-result")
def get_preview_pro_result() -> JSONResponse:
    return JSONResponse(_load_preview_fixture("pro_result_preview.json"))


@app.get("/api/preview/chart-result")
def get_preview_chart_result() -> JSONResponse:
    return JSONResponse(_load_preview_fixture("chart_result_preview.json"))


def _normalize_geocode_results_from_open_meteo(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        timezone_name = item.get("timezone")
        if not timezone_name:
            try:
                timezone_name = resolve_timezone_name(latitude=float(latitude), longitude=float(longitude))
            except Exception:
                timezone_name = None
        normalized.append(
            {
                "name": item.get("name"),
                "country": item.get("country"),
                "admin1": item.get("admin1"),
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone_name,
                "timezone_name": timezone_name,
                "timezone_source": "open_meteo",
            }
        )
    return normalized


def _normalize_geocode_results_from_nominatim(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            latitude = float(item.get("lat"))
            longitude = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        display_name = item.get("display_name")
        name = item.get("name") or (display_name.split(",")[0].strip() if isinstance(display_name, str) else None)
        address = item.get("address") if isinstance(item.get("address"), dict) else {}
        country = address.get("country")
        admin1 = (
            address.get("state")
            or address.get("region")
            or address.get("county")
            or address.get("city")
            or address.get("town")
        )
        try:
            timezone_name = resolve_timezone_name(latitude=latitude, longitude=longitude)
        except Exception:
            timezone_name = None
        normalized.append(
            {
                "name": name,
                "country": country,
                "admin1": admin1,
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone_name,
                "timezone_name": timezone_name,
                "timezone_source": "nominatim",
            }
        )
    return normalized


def _fetch_geocode_open_meteo(query: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": query, "count": 8, "language": "ru", "format": "json"}
    try:
        response = httpx.get(url, params=params, timeout=20)
    except httpx.TimeoutException as exc:
        return [], {
            "provider": "open_meteo",
            "status_code": 504,
            "reason": "timeout",
            "raw_error": str(exc),
        }
    except httpx.HTTPError as exc:
        return [], {
            "provider": "open_meteo",
            "status_code": 502,
            "reason": "network_error",
            "raw_error": str(exc),
        }
    if response.status_code >= 400:
        return [], {
            "provider": "open_meteo",
            "status_code": response.status_code,
            "reason": "provider_error",
            "raw_error": response.text[:2000],
        }
    payload = response.json()
    results = payload.get("results", []) or []
    normalized = _normalize_geocode_results_from_open_meteo(results)
    return normalized, None


def _fetch_geocode_nominatim(query: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 8,
        "accept-language": "ru",
    }
    headers = {
        "User-Agent": "AstroDvish/1.0 (+https://astrodvish.local)",
    }
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=20)
    except httpx.TimeoutException as exc:
        return [], {
            "provider": "nominatim",
            "status_code": 504,
            "reason": "timeout",
            "raw_error": str(exc),
        }
    except httpx.HTTPError as exc:
        return [], {
            "provider": "nominatim",
            "status_code": 502,
            "reason": "network_error",
            "raw_error": str(exc),
        }
    if response.status_code >= 400:
        return [], {
            "provider": "nominatim",
            "status_code": response.status_code,
            "reason": "provider_error",
            "raw_error": response.text[:2000],
        }
    payload = response.json()
    if not isinstance(payload, list):
        payload = []
    normalized = _normalize_geocode_results_from_nominatim(payload)
    return normalized, None


@app.post("/api/geocode")
def geocode_city(payload: GeocodeRequest) -> JSONResponse:
    query = payload.query.strip()
    open_meteo_results, open_meteo_error = _fetch_geocode_open_meteo(query)
    if open_meteo_results:
        _cache_geocode_result(query, open_meteo_results)
        return JSONResponse(
            {
                "results": open_meteo_results,
                "provider": "open_meteo",
                "fallback_provider_used": False,
                "cached_result_used": False,
            }
        )

    fallback_error: dict[str, Any] | None = None
    fallback_results: list[dict[str, Any]] = []
    # Fallback provider is used only for provider/network failures.
    if open_meteo_error and open_meteo_error.get("status_code") in {500, 502, 503, 504}:
        fallback_results, fallback_error = _fetch_geocode_nominatim(query)
        if fallback_results:
            _cache_geocode_result(query, fallback_results)
            return JSONResponse(
                {
                    "results": fallback_results,
                    "provider": "nominatim",
                    "fallback_provider_used": True,
                    "cached_result_used": False,
                    "debug": {
                        "provider": "open_meteo",
                        "status_code": open_meteo_error.get("status_code"),
                        "raw_error": open_meteo_error.get("raw_error"),
                    },
                }
            )

    cached_results = _get_cached_geocode_result(query)
    if cached_results:
        return JSONResponse(
            {
                "results": cached_results,
                "provider": "cache",
                "fallback_provider_used": bool(fallback_results),
                "cached_result_used": True,
                "debug": {
                    "provider": "open_meteo",
                    "status_code": open_meteo_error.get("status_code") if open_meteo_error else None,
                    "raw_error": open_meteo_error.get("raw_error") if open_meteo_error else None,
                    "fallback_provider_used": bool(fallback_results or fallback_error),
                    "fallback_provider": "nominatim" if (fallback_results or fallback_error) else None,
                },
            }
        )

    detail = {
        "message": "Geocoding temporarily unavailable",
        "user_message": (
            "Сервис поиска города временно недоступен. "
            "Попробуйте ещё раз или введите координаты вручную."
        ),
        "provider": "open_meteo",
        "status_code": open_meteo_error.get("status_code") if open_meteo_error else 502,
        "fallback_provider_used": bool(fallback_results or fallback_error),
        "cached_result_used": False,
        "raw_error": open_meteo_error.get("raw_error") if open_meteo_error else None,
        "fallback_provider": "nominatim" if (fallback_results or fallback_error) else None,
        "fallback_error": fallback_error,
    }
    raise HTTPException(status_code=502, detail=detail)


@app.post("/api/generate")
def generate(payload: GenerateRequest) -> JSONResponse:
    resolved_api_base_url = _resolve_api_base_url(payload.api_base_url)
    timezone_context, timezone_warnings = _resolve_timezone_context(payload)
    datetime_utc = timezone_context["datetime_utc"]
    is_no_time_mode = not bool(payload.datetime_local) and bool(payload.birth_date_local)
    llm_debug: dict[str, Any] | None = None
    llm_status = "ok"
    llm_message: str | None = None
    warnings = list(timezone_warnings)

    if is_no_time_mode:
        latitude, longitude, coordinates_source = _safe_coordinates_or_placeholder(payload.latitude, payload.longitude)
        natal_chart_response = _fetch_chart_response(
            resolved_api_base_url=resolved_api_base_url,
            chart_payload={
                "datetime_utc": datetime_utc,
                "latitude": latitude,
                "longitude": longitude,
                "house_system": payload.house_system,
                "aspect_orb_profile": payload.aspect_orb_profile,
                "zodiac_mode": payload.zodiac_mode,
                "sidereal_mode": payload.sidereal_mode,
            },
        )
        current_now_utc = _now_utc()
        transit_chart_response = _fetch_chart_response(
            resolved_api_base_url=resolved_api_base_url,
            chart_payload={
                "datetime_utc": current_now_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "latitude": latitude,
                "longitude": longitude,
                "house_system": payload.house_system,
                "aspect_orb_profile": payload.aspect_orb_profile,
                "zodiac_mode": payload.zodiac_mode,
                "sidereal_mode": payload.sidereal_mode,
            },
        )
        calculation_facts = _build_no_time_calculation_facts(
            natal_chart=natal_chart_response,
            transit_chart=transit_chart_response,
            timezone_context=timezone_context,
            warnings=warnings,
            coordinates_source=coordinates_source,
            now_utc=current_now_utc,
        )
        chart_response = _sanitize_chart_for_no_time(natal_chart_response)
        core_identity = {
            "sun": (chart_response.get("objects") or {}).get("sun"),
            "moon": (chart_response.get("objects") or {}).get("moon"),
            "asc": None,
        }
        core_identity_warnings = ["core_identity_missing_asc_no_time_mode"]
        try:
            llm_result = _render_no_time_forecast_via_openai(
                payload.prompt_text,
                _compact_no_time_forecast_context(
                    natal_chart=chart_response,
                    transit_chart=transit_chart_response,
                    calculation_facts=calculation_facts,
                    timezone_context=timezone_context,
                ),
            )
            horoscope_text = llm_result.get("text", "") if isinstance(llm_result, dict) else str(llm_result)
            if isinstance(llm_result, dict):
                llm_debug = llm_result.get("llm_debug")
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            if exc.status_code != 502:
                raise
            llm_debug = {
                "provider": detail.get("provider", _load_llm_provider()),
                "scenario": OPENROUTER_REQUEST_KIND_GENERATE,
                "final_source": "llm_unavailable",
                "fallback_used": True,
                "attempts": detail.get("attempts", []),
                "status_code": detail.get("status_code"),
                "reason": detail.get("reason"),
                "model": detail.get("model"),
                "key_name": detail.get("key_name"),
                "requested_max_tokens": detail.get("requested_max_tokens"),
                "applied_max_tokens": detail.get("applied_max_tokens"),
                "route": detail.get("route", "/api/generate"),
                "raw_error": detail.get("raw_error"),
            }
            horoscope_text = None
            llm_status = "unavailable"
            llm_message = LLM_UNAVAILABLE_MESSAGE
            core_identity_warnings.append("llm_unavailable")

        warnings.extend(core_identity_warnings)
        return JSONResponse(
            {
                "chart_status": "ok",
                "llm_status": llm_status,
                "llm_message": llm_message,
                "datetime_utc": datetime_utc,
                "timezone": timezone_context,
                "warnings": warnings,
                "core_identity": core_identity,
                "horoscope_text": horoscope_text,
                "chart_response": chart_response,
                "calculation_facts": calculation_facts,
                "llm_debug": llm_debug,
            }
        )

    if not isinstance(payload.latitude, (int, float)) or not isinstance(payload.longitude, (int, float)):
        raise HTTPException(status_code=422, detail="latitude and longitude are required for full forecast mode")

    chart_payload = {
        "datetime_utc": datetime_utc,
        "latitude": float(payload.latitude),
        "longitude": float(payload.longitude),
        "house_system": payload.house_system,
        "aspect_orb_profile": payload.aspect_orb_profile,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }

    chart_response = _fetch_chart_response(
        resolved_api_base_url=resolved_api_base_url,
        chart_payload=chart_payload,
    )
    core_identity, core_identity_warnings = _build_core_identity_block(chart_response)
    llm_debug: dict[str, Any] | None = None
    llm_status = "ok"
    llm_message: str | None = None
    try:
        llm_result = _render_horoscope_via_openai(payload.prompt_text, chart_response, core_identity)
        if isinstance(llm_result, dict):
            horoscope_text = llm_result.get("text", "")
            llm_debug = llm_result.get("llm_debug")
        else:
            # Backward compatibility for tests and older mocks returning plain text.
            horoscope_text = str(llm_result)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        if exc.status_code != 502:
            raise
        llm_debug = {
            "provider": detail.get("provider", _load_llm_provider()),
            "scenario": OPENROUTER_REQUEST_KIND_GENERATE,
            "final_source": "llm_unavailable",
            "fallback_used": True,
            "attempts": detail.get("attempts", []),
            "status_code": detail.get("status_code"),
            "reason": detail.get("reason"),
            "model": detail.get("model"),
            "key_name": detail.get("key_name"),
            "requested_max_tokens": detail.get("requested_max_tokens"),
            "applied_max_tokens": detail.get("applied_max_tokens"),
            "route": detail.get("route", "/api/generate"),
            "raw_error": detail.get("raw_error"),
        }
        horoscope_text = None
        llm_status = "unavailable"
        llm_message = LLM_UNAVAILABLE_MESSAGE
        core_identity_warnings.append("llm_unavailable")

    warnings = timezone_warnings + core_identity_warnings
    return JSONResponse(
        {
            "chart_status": "ok",
            "llm_status": llm_status,
            "llm_message": llm_message,
            "datetime_utc": datetime_utc,
            "timezone": timezone_context,
            "warnings": warnings,
            "core_identity": core_identity,
            "horoscope_text": horoscope_text,
            "chart_response": chart_response,
            "llm_debug": llm_debug,
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
            timezone_mode=payload.timezone_mode,
            timezone_offset=payload.timezone_offset,
            timezone_name=payload.timezone_name,
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


@app.post("/api/rectification/pro/run")
def rectification_pro_run(payload: RectificationProRunRequest) -> JSONResponse:
    _guard_rectification_pro_payload(payload.payload)
    response_json = _post_rectification_events(
        base_url=payload.api_base_url,
        path="/api/v1/rectification/pro/run",
        payload=payload.payload,
        timeout=RECTIFICATION_PRO_TIMEOUT_SECONDS,
    )
    return JSONResponse(response_json)


@app.post("/api/rectification/pro/run-async")
def rectification_pro_run_async(payload: RectificationProRunRequest) -> JSONResponse:
    active_job = _get_active_rectification_pro_job()
    if active_job is not None:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Rectification Pro async job already running",
                "user_message": (
                    "Сейчас уже выполняется другой тяжёлый Pro-расчёт. "
                    "Дождитесь завершения и запустите снова."
                ),
                "reason": "job_already_running",
                "active_job_id": active_job.get("job_id"),
                "active_status": active_job.get("status"),
            },
        )
    chunk_plan = _build_rectification_pro_chunk_plan(payload.payload)
    if chunk_plan is not None:
        job_id = _create_rectification_pro_job(
            base_url=payload.api_base_url,
            payload=payload.payload,
            timeout=RECTIFICATION_PRO_TIMEOUT_SECONDS,
            chunk_plan=chunk_plan,
        )
        _log_rectification_pro_chunk_guard(
            level=logging.INFO,
            message="Rectification Pro chunk plan accepted",
            job_id=job_id,
            guard_stage="pre_job_chunk_plan",
            events_count=len(payload.payload.get("events") or []) if isinstance(payload.payload, dict) else 0,
            selected_cards_count=len(chunk_plan.get("selected_card_ids") or []),
            planned_chunks=int(chunk_plan.get("planned_chunks") or 0),
            chunk_size=int(chunk_plan.get("chunk_size") or 0),
            candidate_count=None,
            formula_count=None,
            estimated_weight=int(chunk_plan.get("estimated_weight") or 0),
            guard_reason="accepted",
            current_limit=_current_rectification_pro_chunk_limits(),
            runtime_snapshot=_collect_rectification_pro_runtime_snapshot(),
        )
        return JSONResponse(
            {
                "job_id": job_id,
                "status": "queued",
                "mode": chunk_plan["mode"],
                "total_chunks": chunk_plan["total_chunks"],
                "planned_chunks": chunk_plan["planned_chunks"],
                "chunk_size": chunk_plan["chunk_size"],
                "estimated_weight": chunk_plan["estimated_weight"],
                "user_message": "Большой V2-отчёт считается по блокам. Это может занять больше времени.",
                "poll_url": f"/api/rectification/pro/jobs/{job_id}",
            },
            status_code=202,
        )
    _guard_rectification_pro_payload(
        payload.payload,
        max_events=RECTIFICATION_PRO_ASYNC_MULTI_CARD_MAX_EVENTS,
        complexity_limit=RECTIFICATION_PRO_ASYNC_MULTI_CARD_COMPLEXITY_LIMIT,
        user_message=(
            "Этот multi-card V2 запуск слишком большой для текущего live-сервера. "
            "Запустите по группам событий или выберите один V2 card, чтобы расчёт не упал."
        ),
    )
    job_id = _create_rectification_pro_job(
        base_url=payload.api_base_url,
        payload=payload.payload,
        timeout=RECTIFICATION_PRO_TIMEOUT_SECONDS,
    )
    return JSONResponse(
        {
            "job_id": job_id,
            "status": "pending",
            "poll_url": f"/api/rectification/pro/jobs/{job_id}",
        },
        status_code=202,
    )


@app.get("/api/rectification/pro/jobs/{job_id}")
def rectification_pro_job_status(job_id: str) -> JSONResponse:
    job = _get_rectification_pro_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Rectification Pro job not found")
    return JSONResponse(job)


@app.post("/api/rectification/pro/export-excel")
def rectification_pro_export_excel(payload: RectificationProExcelExportRequest) -> Response:
    if not payload.sheets:
        raise HTTPException(
            status_code=422,
            detail={
                "reason": "missing_excel_sheets",
                "user_message": "Нет данных для Excel-экспорта combined report.",
            },
        )
    content = _build_rectification_pro_excel_bytes(payload)
    filename = _sanitize_rectification_pro_excel_filename(payload.filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Явные MIME-типы: на Windows стандартный mimetypes часто отдаёт .js как
# text/plain, из-за чего браузер отказывается грузить ES6-модули
# ("Failed to load module script: ... MIME type 'text/plain'").
_STATIC_MEDIA_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".map": "application/json",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ico": "image/x-icon",
    ".html": "text/html",
}


@app.get("/static/{filename:path}")
def static_files(filename: str) -> FileResponse:
    # Защита от выхода за пределы каталога static (path traversal).
    file_path = (STATIC_DIR / filename).resolve()
    if STATIC_DIR.resolve() not in file_path.parents and file_path != STATIC_DIR.resolve():
        raise HTTPException(status_code=404, detail="Not found")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media_type = _STATIC_MEDIA_TYPES.get(file_path.suffix.lower())
    # no-cache: браузер всегда ревалидирует — иначе старые styles.css/js залипают в кэше.
    return FileResponse(file_path, media_type=media_type, headers={"Cache-Control": "no-cache"})
