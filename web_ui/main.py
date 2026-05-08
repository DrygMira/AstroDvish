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
    api_base_url: str = "http://127.0.0.1:8013"
    datetime_local: str
    timezone_mode: Literal["auto", "manual"] = "auto"
    timezone_offset: str = ""
    timezone_name: str | None = None
    latitude: float
    longitude: float
    house_system: str = "P"
    aspect_orb_profile: Literal["avestan", "western"] = "avestan"
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
    repeat_count: int | None = None
    sequence_number: int | None = None
    notes: str | None = None
    user_skipped: bool = False


class RectificationEventsContinueRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)
    last_answer: EventAnswerWebInput | None = None


class RectificationEventsFinalizeRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    dialog_history: list[dict[str, Any]] = Field(default_factory=list)


class RectificationProRunRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    payload: dict[str, Any]


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
        OPENROUTER_REQUEST_KIND_DEFAULT: _env("OPENAI_MODEL_DEFAULT", "gpt-4.1").strip() or "gpt-4.1",
        OPENROUTER_REQUEST_KIND_GENERATE: _env("OPENAI_MODEL_GENERATE", "gpt-4.1").strip() or "gpt-4.1",
        OPENROUTER_REQUEST_KIND_STAGE1: _env("OPENAI_MODEL_STAGE1", "gpt-4.1").strip() or "gpt-4.1",
        OPENROUTER_REQUEST_KIND_PRO: _env("OPENAI_MODEL_PRO", "gpt-4.1").strip() or "gpt-4.1",
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
    model = _env("OPENROUTER_MODEL", "openai/gpt-4.1").strip()
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
    if model_override_env:
        model_override = _env(model_override_env, "").strip()
        if model_override:
            scenario_model = model_override

    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": scenario_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": applied_max_tokens,
    }
    try:
        response = httpx.post(
            f"{settings['base_url']}/chat/completions",
            headers=headers,
            json=body,
            timeout=settings["timeout_seconds"],
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM request timeout",
                "provider": "openai",
                "status_code": 502,
                "reason": "timeout",
                "route": route_label,
                "model": scenario_model,
                "key_name": "primary",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
                "raw_error": str(exc)[:4000],
            },
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM request failed",
                "provider": "openai",
                "status_code": 502,
                "reason": "network_or_timeout",
                "route": route_label,
                "model": scenario_model,
                "key_name": "primary",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
                "raw_error": str(exc)[:4000],
            },
        ) from exc

    if response.status_code != 200:
        raw_error = response.text[:4000]
        reason = _classify_openai_error(response.status_code, raw_error)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM provider returned non-200 status",
                "provider": "openai",
                "status_code": response.status_code,
                "reason": reason,
                "route": route_label,
                "model": scenario_model,
                "key_name": "primary",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
                "attempts": [
                    {
                        "attempt": 1,
                        "key_name": "primary",
                        "model": scenario_model,
                        "status_code": response.status_code,
                        "reason": reason,
                        "requested_max_tokens": resolved_requested_max_tokens,
                        "applied_max_tokens": applied_max_tokens,
                        "raw_error": raw_error,
                    }
                ],
                "fallback_used": False,
                "final_source": "llm_unavailable",
                "raw_error": raw_error,
            },
        )

    payload = response.json()
    text = _extract_chat_completion_text(payload)
    if not text:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM provider returned empty response",
                "provider": "openai",
                "status_code": 502,
                "reason": "empty_response",
                "route": route_label,
                "model": scenario_model,
                "key_name": "primary",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
            },
        )

    return {
        "text": text,
        "raw": payload,
        "provider": "openai",
        "model": scenario_model,
        "key_name": "primary",
        "route": route_label,
        "scenario": request_kind,
        "request_kind": request_kind,
        "requested_max_tokens": resolved_requested_max_tokens,
        "applied_max_tokens": applied_max_tokens,
        "first_applied_max_tokens": applied_max_tokens,
        "retried_with_lower_max_tokens": False,
        "attempts": [
            {
                "attempt": 1,
                "key_name": "primary",
                "model": scenario_model,
                "status_code": 200,
                "reason": "ok",
                "requested_max_tokens": resolved_requested_max_tokens,
                "applied_max_tokens": applied_max_tokens,
            }
        ],
        "fallback_used": False,
        "final_source": "llm_primary",
    }


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
        if 400 <= response.status_code < 500:
            try:
                detail: Any = response.json().get("detail")
            except ValueError:
                detail = response.text[:2000]
            raise HTTPException(status_code=response.status_code, detail=detail)
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
    timezone_context, timezone_warnings = _resolve_timezone_context(payload)
    datetime_utc = timezone_context["datetime_utc"]

    chart_payload = {
        "datetime_utc": datetime_utc,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "house_system": payload.house_system,
        "aspect_orb_profile": payload.aspect_orb_profile,
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
    response_json = _post_rectification_events(
        base_url=payload.api_base_url,
        path="/api/v1/rectification/pro/run",
        payload=payload.payload,
    )
    return JSONResponse(response_json)


@app.get("/static/{filename}")
def static_files(filename: str) -> FileResponse:
    file_path = STATIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path)
