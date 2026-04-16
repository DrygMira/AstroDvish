from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

PROMPT_PATH = Path(__file__).resolve().parent.parent / "PROMPT.md"
STATIC_DIR = Path(__file__).resolve().parent / "static"
SECRETS_PATH = Path(__file__).resolve().parent.parent / "secrets.txt"

TZ_OFFSET_PATTERN = re.compile(r"^[+-](?:0\d|1[0-4]):[0-5]\d$")

app = FastAPI(title="astro-web-ui", docs_url=None, redoc_url=None, openapi_url=None)


class GeocodeRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)


class GenerateRequest(BaseModel):
    api_base_url: str = "http://127.0.0.1:8013"
    datetime_local: str
    timezone_offset: str
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


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        return "Сделай гороскоп по этим данным."
    return PROMPT_PATH.read_text(encoding="utf-8").strip() or "Сделай гороскоп по этим данным."


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


def _extract_openai_text(payload: dict) -> str:
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


def _render_horoscope_via_openai(prompt_text: str, chart: dict) -> str:
    api_key = _load_openai_api_key()
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/prompt")
def get_prompt() -> JSONResponse:
    return JSONResponse({"prompt_text": _load_prompt()})


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
    datetime_utc = _to_utc_iso(payload.datetime_local, payload.timezone_offset)

    chart_payload = {
        "datetime_utc": datetime_utc,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "house_system": payload.house_system,
        "zodiac_mode": payload.zodiac_mode,
        "sidereal_mode": payload.sidereal_mode,
    }

    api_url = payload.api_base_url.rstrip("/") + "/api/v1/chart"
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

    chart_response = response.json()
    horoscope_text = _render_horoscope_via_openai(payload.prompt_text, chart_response)
    return JSONResponse(
        {
            "datetime_utc": datetime_utc,
            "horoscope_text": horoscope_text,
            "chart_response": chart_response,
        }
    )


@app.post("/api/rectification/asc-sign-intervals")
def rectification_asc_sign_intervals(payload: RectificationIntervalsRequest) -> JSONResponse:
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

    return JSONResponse(response.json())


@app.get("/static/{filename}")
def static_files(filename: str) -> FileResponse:
    file_path = STATIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path)
