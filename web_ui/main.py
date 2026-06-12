from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.utils.timezone_lookup import resolve_timezone_name

PROMPT_PATH = Path(__file__).resolve().parent.parent / "PROMPT.md"
PROMPT_RECTIFICATION_STAGE1_PATH = (
    Path(__file__).resolve().parent.parent / "PROMPT_RECTIFICATION_STAGE1.md"
)
STATIC_DIR = Path(__file__).resolve().parent / "static"
SECRETS_PATH = Path(__file__).resolve().parent.parent / "secrets.txt"

TZ_OFFSET_PATTERN = re.compile(r"^[+-](?:0\d|1[0-4]):[0-5]\d$")

RECT_MIN_STEPS = 3
RECT_MAX_STEPS = 10
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
BODY_DISPLAY_NAMES: dict[str, str] = {
    "sun": "Sun",
    "moon": "Moon",
    "mercury": "Mercury",
    "venus": "Venus",
    "mars": "Mars",
    "jupiter": "Jupiter",
    "saturn": "Saturn",
    "uranus": "Uranus",
    "neptune": "Neptune",
    "pluto": "Pluto",
    "true_node": "True Node",
    "mean_node": "Mean Node",
}
NO_TIME_MOON_SIGN_MEANINGS: dict[str, str] = {
    "Aries": "initiative / impulse / fast emotional response",
    "Taurus": "stability / embodiment / need for grounding",
    "Gemini": "communication / mental activity / switching",
    "Cancer": "sensitivity / home / emotional memory",
    "Leo": "self-expression / visibility / heart energy",
    "Virgo": "analysis / order / attention to detail",
    "Libra": "contact / balance / relationship themes",
    "Scorpio": "intensity / triggers / depth",
    "Sagittarius": "meaning / perspective / movement forward",
    "Capricorn": "structure / discipline / practicality",
    "Aquarius": "distance / ideas / updated perspective",
    "Pisces": "intuition / blur / emotional background",
}
NO_TIME_SLOW_TRANSIT_REFERENCE_DURATIONS: dict[str, str] = {
    "Saturn": "1-1.5 months",
    "Jupiter": "2-3 months",
    "Uranus": "1-1.5 years",
    "Neptune": "1.5-2 years",
    "Pluto": "2-3 years",
}

app = FastAPI(title="astro-web-ui", docs_url=None, redoc_url=None, openapi_url=None)


class GeocodeRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class GenerateRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    datetime_local: str | None = None
    birth_date_local: str | None = None
    timezone_mode: Literal["auto", "manual"] = "manual"
    timezone_offset: str = ""
    timezone_name: str | None = None
    profile_timezone_name: str | None = None
    birth_city: str | None = None
    birth_country: str | None = None
    birth_region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    house_system: str = "P"
    zodiac_mode: str = "tropical"
    sidereal_mode: str | None = None
    prompt_text: str = "Сделай гороскоп по этим данным."

    @model_validator(mode="after")
    def _validate_generate_identity(self) -> GenerateRequest:
        if not (self.datetime_local or self.birth_date_local):
            raise ValueError("birth date is required")
        return self


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


def _load_openai_api_key() -> str:
    if not SECRETS_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing secrets file. Create ./secrets.txt (see secrets.txt.example) "
                "and set OPENAI_API_KEY."
            ),
        )

    for raw_line in SECRETS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("OPENAI_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
        elif line.startswith("sk-"):
            return line

    raise HTTPException(
        status_code=500,
        detail="OPENAI_API_KEY not found in ./secrets.txt file",
    )


def _to_utc_iso(local_dt_str: str, tz_offset: str) -> str:
    if not TZ_OFFSET_PATTERN.match(tz_offset):
        raise HTTPException(status_code=422, detail="Invalid timezone_offset format. Use +03:00")

    try:
        local_naive = datetime.fromisoformat(local_dt_str)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid datetime_local format") from exc

    sign = 1 if tz_offset[0] == "+" else -1
    hours = int(tz_offset[1:3])
    minutes = int(tz_offset[4:6])
    offset = timedelta(hours=hours, minutes=minutes) * sign
    dt_with_tz = local_naive.replace(tzinfo=timezone(offset))
    return dt_with_tz.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_openai_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    texts: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
            elif content.get("type") == "text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    return "\n\n".join(texts).strip()


def _call_openai_text(*, system_prompt: str, user_prompt: str) -> str:
    api_key = _load_openai_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gpt-5.4-nano",
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=body,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "OpenAI returned non-200 status",
                "status_code": response.status_code,
                "body": response.text[:2000],
            },
        )

    data = response.json()
    text = _extract_openai_text(data)
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI response did not contain text")
    return text


def _render_horoscope_via_openai(prompt_text: str, chart: dict[str, Any]) -> str:
    system_prompt = (
        "Ты астрологический ассистент. Пиши по-русски. "
        "Дай структурированный и понятный разбор без мистификации, "
        "используя только переданные расчётные данные."
    )
    user_prompt = (
        f"{prompt_text.strip()}\n\n"
        "Ниже JSON с расчётом натальной карты. "
        "Сделай связный текстовый гороскоп: личность, эмоции, "
        "отношения, работа/реализация, сильные стороны и риски.\n\n"
        f"{json.dumps(chart, ensure_ascii=False)}"
    )
    return _call_openai_text(system_prompt=system_prompt, user_prompt=user_prompt)


def _extract_usage_stats(openai_response: dict[str, Any]) -> dict[str, int | None]:
    usage = openai_response.get("usage", {}) or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
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
    api_key = _load_openai_api_key()

    runtime_payload = {
        "mode": mode,
        "rectification_document": rectification_document,
        "dialog_history": dialog_history,
        "step_count": step_count,
        "min_steps": RECT_MIN_STEPS,
        "max_steps": RECT_MAX_STEPS,
        "user_profile_note": user_profile_note or "",
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gpt-5-nano",
        "input": [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": json.dumps(runtime_payload, ensure_ascii=False)},
        ],
    }

    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=body,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {exc}") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "OpenAI returned non-200 status",
                "status_code": response.status_code,
                "body": response.text[:4000],
            },
        )

    openai_json = response.json()
    llm_text = _extract_openai_text(openai_json)
    if not llm_text:
        raise HTTPException(status_code=502, detail="OpenAI response did not contain text")

    parsed_llm = _parse_llm_json_text(llm_text)
    validated_llm = _validate_llm_response_shape(parsed_llm)
    usage = _extract_usage_stats(openai_json)

    return {
        "llm_json": validated_llm,
        "llm_text": llm_text,
        "usage": usage,
        "openai_raw_response": openai_json,
    }


def _fetch_rectification_document(payload: RectificationIntervalsRequest) -> dict[str, Any]:
    api_url = payload.api_base_url.rstrip("/") + "/api/v1/rectification/asc-sign-intervals"
    api_payload = {
        "birth_date_local": payload.birth_date_local,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "house_system": payload.house_system,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }
    try:
        response = httpx.post(api_url, json=api_payload, timeout=120)
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


def _fetch_chart_response(*, api_base_url: str, chart_payload: dict[str, Any]) -> dict[str, Any]:
    api_url = api_base_url.rstrip("/") + "/api/v1/chart"
    try:
        response = httpx.post(api_url, json=chart_payload, timeout=120)
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

    return response.json()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_birth_date_local(value: str | None) -> date:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail="birth date is required")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid birth_date_local format") from exc


def _format_offset(dt_with_tz: datetime) -> str:
    offset = dt_with_tz.utcoffset()
    if offset is None:
        return "+00:00"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


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


def _resolve_manual_offset_context(*, local_dt: datetime, payload: GenerateRequest) -> dict[str, Any]:
    if not TZ_OFFSET_PATTERN.match(payload.timezone_offset):
        raise HTTPException(status_code=422, detail="Invalid timezone_offset format. Use +03:00")
    sign = 1 if payload.timezone_offset[0] == "+" else -1
    hours = int(payload.timezone_offset[1:3])
    minutes = int(payload.timezone_offset[4:6])
    offset = timedelta(hours=hours, minutes=minutes) * sign
    local_aware = local_dt.replace(tzinfo=timezone(offset))
    return {
        "mode": "manual",
        "timezone_name": payload.timezone_name or payload.profile_timezone_name,
        "timezone_offset": payload.timezone_offset,
        "timezone_source": "manual_offset",
        "datetime_local": local_dt.isoformat(timespec="seconds"),
        "datetime_utc": local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "clarification_needed": False,
    }


def _resolve_named_timezone_context(
    *,
    local_dt: datetime,
    payload: GenerateRequest,
    allow_fallback_utc: bool,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    timezone_name = (payload.timezone_name or "").strip()
    timezone_source = "provided_timezone_name"
    clarification_needed = False

    if not timezone_name and payload.profile_timezone_name:
        timezone_name = payload.profile_timezone_name.strip()
        timezone_source = "profile_timezone_name"

    if not timezone_name and isinstance(payload.latitude, (int, float)) and isinstance(payload.longitude, (int, float)):
        timezone_name = resolve_timezone_name(latitude=float(payload.latitude), longitude=float(payload.longitude))
        timezone_source = "auto_by_coordinates"

    if not timezone_name:
        timezone_name = _guess_timezone_name_from_region(region=payload.birth_region or payload.birth_city)
        if timezone_name:
            timezone_source = "region_unique_match"

    if not timezone_name:
        if not allow_fallback_utc:
            raise HTTPException(status_code=422, detail="timezone information is required for full forecast mode")
        clarification_needed = True
        warnings.append("timezone_clarification_needed_no_time_fallback_utc")
        timezone_name = "UTC"
        timezone_source = "fallback_utc_due_timezone_ambiguity"

    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Invalid timezone_name") from exc

    local_aware = local_dt.replace(tzinfo=zone)
    return (
        {
            "mode": "auto",
            "timezone_name": timezone_name,
            "timezone_offset": _format_offset(local_aware),
            "timezone_source": timezone_source,
            "datetime_local": local_dt.isoformat(timespec="seconds"),
            "datetime_utc": local_aware.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "clarification_needed": clarification_needed,
        },
        warnings,
    )


def _resolve_timezone_context(payload: GenerateRequest) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    if payload.datetime_local:
        try:
            local_dt = datetime.fromisoformat(payload.datetime_local)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid datetime_local format") from exc

        if payload.timezone_mode == "manual" or payload.timezone_offset:
            return _resolve_manual_offset_context(local_dt=local_dt, payload=payload), warnings

        auto_context, auto_warnings = _resolve_named_timezone_context(
            local_dt=local_dt,
            payload=payload,
            allow_fallback_utc=False,
        )
        return auto_context, auto_warnings

    birth_date = _parse_birth_date_local(payload.birth_date_local)
    local_noon = datetime.combine(birth_date, time(hour=12))
    datetime_local = f"{birth_date.isoformat()}T{NO_TIME_FALLBACK_LOCAL_CLOCK}:00"

    if payload.timezone_mode == "manual" and payload.timezone_offset:
        context = _resolve_manual_offset_context(local_dt=local_noon, payload=payload)
        context["datetime_local"] = datetime_local
        return context, ["manual_timezone_offset_used"]

    auto_context, auto_warnings = _resolve_named_timezone_context(
        local_dt=local_noon,
        payload=payload,
        allow_fallback_utc=True,
    )
    auto_context["datetime_local"] = datetime_local
    return auto_context, auto_warnings


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


def _body_display_name(name: str) -> str:
    return BODY_DISPLAY_NAMES.get(name, name.replace("_", " ").title())


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

    ranked: list[dict[str, Any]] = []
    all_aspects = [*NO_TIME_MAJOR_ASPECTS, *NO_TIME_MINOR_ASPECTS]

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

                delta_signed = _signed_delta_to_aspect(
                    transit_degree=float(transit_degree),
                    natal_degree=float(natal_degree),
                    exact_angle=exact_angle,
                )
                phase = "exact" if abs(delta_signed) <= NO_TIME_PHASE_EXACT_EPSILON else "separating"
                active_from_local: str | None = None
                exact_at_local: str | None = None
                active_to_local: str | None = None

                if isinstance(speed, (int, float)) and abs(float(speed)) > NO_TIME_STATIONARY_THRESHOLD:
                    days_to_exact = -delta_signed / float(speed)
                    exact_at_utc = now_utc + timedelta(days=days_to_exact)
                    active_span_days = orb_limit / abs(float(speed))
                    active_from_local = _to_local_iso(exact_at_utc - timedelta(days=active_span_days), timezone_name)
                    exact_at_local = _to_local_iso(exact_at_utc, timezone_name)
                    active_to_local = _to_local_iso(exact_at_utc + timedelta(days=active_span_days), timezone_name)
                    if abs(delta_signed) <= NO_TIME_PHASE_EXACT_EPSILON:
                        phase = "exact"
                    else:
                        phase = "applying" if days_to_exact > 0 else "separating"

                transit_label = _body_display_name(transit_body)
                natal_label = _body_display_name(natal_body)
                entry = {
                    "transit_body": transit_label,
                    "natal_body": natal_label,
                    "aspect": aspect_name,
                    "orb": round(float(orb), 4),
                    "phase": phase,
                    "motion": _motion_phase_from_speed(float(speed) if isinstance(speed, (int, float)) else None),
                    "active_from": active_from_local,
                    "exact_at": exact_at_local,
                    "active_to": active_to_local,
                    "transit_sign": transit_obj.get("sign_name_en"),
                    "natal_sign": natal_obj.get("sign_name_en"),
                }
                if transit_label in NO_TIME_SLOW_TRANSIT_REFERENCE_DURATIONS:
                    entry["reference_duration"] = NO_TIME_SLOW_TRANSIT_REFERENCE_DURATIONS[transit_label]
                ranked.append(entry)

    priority_order = {
        "moon": 0,
        "sun": 1,
        "mercury": 2,
        "venus": 3,
        "mars": 4,
        "jupiter": 5,
        "saturn": 6,
        "uranus": 7,
        "neptune": 8,
        "pluto": 9,
    }
    inverse_display_map = {value: key for key, value in BODY_DISPLAY_NAMES.items()}
    ranked.sort(
        key=lambda item: (
            priority_order.get(inverse_display_map.get(item["transit_body"], ""), 99),
            item["orb"],
        )
    )
    return ranked[:12]


def _collect_moon_daily_windows(
    *,
    transit_chart: dict[str, Any],
    timezone_name: str,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    transit_objects = transit_chart.get("objects") if isinstance(transit_chart, dict) else {}
    if not isinstance(transit_objects, dict):
        return []
    moon = transit_objects.get("moon")
    if not isinstance(moon, dict):
        return []

    local_now = now_utc.astimezone(ZoneInfo(timezone_name))
    start_of_day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = local_now.replace(hour=23, minute=59, second=59, microsecond=0)
    sign_name = moon.get("sign_name_en") or "Unknown"
    return [
        {
            "moon_sign": sign_name,
            "from": start_of_day.isoformat(timespec="seconds"),
            "to": end_of_day.isoformat(timespec="seconds"),
            "meaning": NO_TIME_MOON_SIGN_MEANINGS.get(str(sign_name), "daily emotional background"),
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
    timezone_name = str(timezone_context.get("timezone_name") or "UTC")
    transit_aspects = _collect_no_time_transit_aspects(
        natal_chart=natal_chart,
        transit_chart=transit_chart,
        timezone_name=timezone_name,
        now_utc=now_utc,
    )
    moon_daily_windows = _collect_moon_daily_windows(
        transit_chart=transit_chart,
        timezone_name=timezone_name,
        now_utc=now_utc,
    )
    return {
        "precision": "birth_date_no_time",
        "forecast_mode": "transit_to_natal_no_houses",
        "birth_time_used": "12:00",
        "birth_time_assumption": "date_midpoint",
        "houses_available": False,
        "asc_mc_available": False,
        "event_specificity": "low",
        "forecast_character": "psychological_mental_energy",
        "timezone_source": timezone_context.get("timezone_source"),
        "timezone_name": timezone_name,
        "utc_offset": timezone_context.get("timezone_offset"),
        "coordinates_used": coordinates_source,
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


def _render_no_time_forecast_via_openai(
    prompt_text: str,
    forecast_context: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        "Ты астрологический ассистент. Пиши по-русски. "
        "Перед тобой персональный прогноз без точного времени рождения. "
        "Нельзя использовать дома, ASC, MC, куспиды, управителей домов и house-based event logic. "
        "Опирайся только на натальные положения планет, транзитные положения, транзитные аспекты к натальным планетам, "
        "фазу аспекта, фазу движения планеты и фон Луны по знаку."
    )
    user_prompt = (
        f"{prompt_text.strip()}\n\n"
        "Этот прогноз построен без точного времени рождения, поэтому мы не используем дома, ASC и MC. "
        "Он не показывает конкретные бытовые сценарии, зато хорошо описывает ваши психологические тренды, "
        "уровень энергии, фоновые мысли и эмоциональные триггеры на ближайшие дни.\n\n"
        "Сначала дай краткий общий фон, затем выдели несколько ключевых транзитных тем, "
        "после этого заверши практическими рекомендациями.\n\n"
        f"{json.dumps(forecast_context, ensure_ascii=False)}"
    )
    text = _call_openai_text(system_prompt=system_prompt, user_prompt=user_prompt)
    return {"text": text}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
        }
        for item in results
    ]
    return JSONResponse({"results": normalized})


@app.post("/api/generate")
def generate(payload: GenerateRequest) -> JSONResponse:
    timezone_context, timezone_warnings = _resolve_timezone_context(payload)
    datetime_utc = timezone_context["datetime_utc"]
    is_no_time_mode = not bool(payload.datetime_local) and bool(payload.birth_date_local)

    if is_no_time_mode:
        latitude, longitude, coordinates_source = _safe_coordinates_or_placeholder(
            payload.latitude,
            payload.longitude,
        )
        natal_chart_response = _fetch_chart_response(
            api_base_url=payload.api_base_url,
            chart_payload={
                "datetime_utc": datetime_utc,
                "latitude": latitude,
                "longitude": longitude,
                "house_system": payload.house_system,
                "zodiac_mode": payload.zodiac_mode,
                "sidereal_mode": payload.sidereal_mode,
            },
        )
        current_now_utc = _now_utc()
        transit_chart_response = _fetch_chart_response(
            api_base_url=payload.api_base_url,
            chart_payload={
                "datetime_utc": current_now_utc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "latitude": latitude,
                "longitude": longitude,
                "house_system": payload.house_system,
                "zodiac_mode": payload.zodiac_mode,
                "sidereal_mode": payload.sidereal_mode,
            },
        )
        calculation_facts = _build_no_time_calculation_facts(
            natal_chart=natal_chart_response,
            transit_chart=transit_chart_response,
            timezone_context=timezone_context,
            warnings=list(timezone_warnings),
            coordinates_source=coordinates_source,
            now_utc=current_now_utc,
        )
        chart_response = _sanitize_chart_for_no_time(natal_chart_response)
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
        return JSONResponse(
            {
                "datetime_utc": datetime_utc,
                "horoscope_text": horoscope_text,
                "chart_response": chart_response,
                "calculation_facts": calculation_facts,
                "timezone": timezone_context,
                "warnings": timezone_warnings,
            }
        )

    if not payload.datetime_local:
        raise HTTPException(status_code=422, detail="birth date is required")
    if not isinstance(payload.latitude, (int, float)) or not isinstance(payload.longitude, (int, float)):
        raise HTTPException(status_code=422, detail="latitude and longitude are required for full forecast mode")

    chart_payload = {
        "datetime_utc": datetime_utc,
        "latitude": float(payload.latitude),
        "longitude": float(payload.longitude),
        "house_system": payload.house_system,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }
    chart_response = _fetch_chart_response(api_base_url=payload.api_base_url, chart_payload=chart_payload)
    horoscope_text = _render_horoscope_via_openai(payload.prompt_text, chart_response)
    return JSONResponse(
        {
            "datetime_utc": datetime_utc,
            "horoscope_text": horoscope_text,
            "chart_response": chart_response,
            "timezone": timezone_context,
            "warnings": timezone_warnings,
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

    llm_result = _call_rectification_llm(
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
                "free_text": payload.user_response.free_text,
            }
        )

    mode = "finalize_now" if payload.mode == "finalize_now" else "choose_next_question"
    llm_result = _call_rectification_llm(
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
            "step_count": next_step_count,
        }
    )


@app.get("/static/{filename}")
def static_files(filename: str) -> FileResponse:
    file_path = STATIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path)
