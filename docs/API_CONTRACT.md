# AstroDvish API Contract (Core Service)

Этот документ фиксирует стабильный контракт AstroDvish как расчётного API для внешнего клиента (в т.ч. будущего AstroBot).

## Scope

- AstroDvish возвращает только расчётные данные и структурированные JSON-документы.
- AstroDvish не возвращает `interpretation_text` и не генерирует GPT-трактовки.
- Контракт покрывает только core API endpoints:
1. `GET /health`
2. `GET /api/v1/health`
3. `POST /api/v1/chart`
4. `POST /api/v1/rectification/asc-sign-intervals`
5. `POST /api/v1/rectification/events/start`
6. `POST /api/v1/rectification/events/continue`
7. `POST /api/v1/rectification/events/finalize`

## Data Layer Separation

- `calculation_json`:
  - источник: `POST /api/v1/chart`
  - содержит: `objects`, `aspects`, `houses`, `angles`, `meta`
- `rectification_json`:
  - источник: `POST /api/v1/rectification/asc-sign-intervals`
  - содержит интервалы Asc, timezone-блок, day window и summary
- `events_json`:
  - источник: `POST /api/v1/rectification/events/*`
  - содержит event cards и confidence/warnings
- `interpretation_text`:
  - отсутствует в core API AstroDvish

## Request ID Behavior

- API принимает входящий header `X-Request-ID`.
- Если header не передан, API генерирует UUID.
- API возвращает `X-Request-ID` в response headers для всех endpoint-ов.
- Для `GET /health` и `GET /api/v1/health` `request_id` также включён в JSON body.
- Для error-response `request_id` включён в поле `error.request_id`.
- В логах присутствуют `request_start`, `request_end`, `request_exception` с `request_id`.

## Error Model (общий)

- Validation: HTTP `422`
```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": [],
    "request_id": "..."
  }
}
```

- Domain errors (например timezone lookup): HTTP `4xx/5xx` с `error.code`, `error.message`, `error.details`, `error.request_id`.
- Unhandled errors: HTTP `500`, `error.code = "internal_error"`.

## Endpoint Contract

### 1) GET /health

- Purpose: базовый healthcheck сервиса.
- Input JSON: отсутствует.
- Output JSON:
```json
{
  "status": "ok",
  "service": "astrodvish-api",
  "version": "0.5.0",
  "request_id": "..."
}
```
- Required fields: `status`, `service`, `version`.
- Optional fields: нет.
- Errors: стандартный error model.
- Warnings: нет.
- Request ID: в header и body.

### 2) GET /api/v1/health

- Purpose: versioned healthcheck для клиентов `/api/v1/*`.
- Input JSON: отсутствует.
- Output JSON: как у `GET /health`.
- Required fields: `status`, `service`, `version`.
- Optional fields: нет.
- Errors: стандартный error model.
- Warnings: нет.
- Request ID: в header и body.

### 3) POST /api/v1/chart

- Purpose: расчёт натальной карты и аспектов (computation-only).
- Input JSON:
```json
{
  "datetime_utc": "1984-11-13T11:35:00Z",
  "latitude": 53.9006,
  "longitude": 27.559,
  "house_system": "P",
  "zodiac_mode": "tropical",
  "sidereal_mode": null
}
```
- Required fields:
  - `datetime_utc` (UTC ISO8601 string),
  - `latitude`,
  - `longitude`.
- Optional fields:
  - `house_system` (default `P`),
  - `zodiac_mode` (default `tropical`),
  - `sidereal_mode` (required только при `zodiac_mode = sidereal`).
- Output JSON (top-level):
```json
{
  "input": {},
  "normalized": {},
  "objects": {},
  "aspects": [],
  "houses": {},
  "angles": {},
  "meta": {}
}
```
- Required output fields: `input`, `normalized`, `objects`, `aspects`, `houses`, `angles`, `meta`.
- Optional output fields: нет.
- Errors:
  - `422 validation_error` для невалидных входных данных.
  - `500 internal_error` или domain error для сбоев расчёта.
- Warnings: нет.
- Request ID: в response header; в body только в error-response.

### 4) POST /api/v1/rectification/asc-sign-intervals

- Purpose: Stage 1 расчёт intervals-документа по Asc без LLM-интерпретации.
- Input JSON:
```json
{
  "birth_date_local": "2000-04-16",
  "latitude": 53.9,
  "longitude": 27.56667,
  "house_system": "P",
  "zodiac_mode": "tropical",
  "sidereal_mode": null
}
```
- Required fields:
  - `birth_date_local`,
  - `latitude`,
  - `longitude`.
- Optional fields:
  - `house_system` (default `P`),
  - `zodiac_mode` (default `tropical`),
  - `sidereal_mode` (required только при `zodiac_mode = sidereal`).
- Output JSON (top-level):
```json
{
  "mode": "asc_sign_intervals",
  "version": "1.0",
  "generated_at_utc": "...Z",
  "birth_context": {
    "timezone": "Europe/...",
    "timezone_source": "coordinates"
  },
  "day_window": {},
  "day_window_utc": {},
  "shared_day_summary": {},
  "asc_sign_intervals": []
}
```
- Required output fields:
  - `mode`, `version`, `generated_at_utc`,
  - `birth_context` (включая `timezone`, `timezone_source`),
  - `day_window`, `day_window_utc`,
  - `shared_day_summary`,
  - `asc_sign_intervals`.
- Optional output fields: нет.
- Errors:
  - `422 validation_error`,
  - `422 timezone_lookup_error` (например не определён timezone по координатам),
  - другие domain/internal ошибки.
- Warnings: нет (в этом endpoint-е поле `warnings` не возвращается).
- Request ID: в response header; в body только в error-response.

### 5) POST /api/v1/rectification/events/start

- Purpose: начать Stage 2 flow сбора событий жизни.
- Input JSON:
```json
{
  "dialog_history": []
}
```
- Required fields: нет (пустое тело допустимо).
- Optional fields:
  - `dialog_history` (default `[]`).
- Output JSON:
  - либо `ask_question`,
  - либо `finalized` (safe finalize).
- `ask_question` форма (top-level):
```json
{
  "status": "ask_question",
  "step_index": 1,
  "events_collected_count": 0,
  "warnings": [],
  "question": {
    "question_id": "ev_children_birth_01",
    "event_type": "children_birth",
    "question_text": "...",
    "options": [{"id": "yes", "text": "Да"}]
  },
  "dialog_history": []
}
```
- Errors: стандартный error model.
- Warnings:
  - массив `warnings` может быть пустым или содержать service flags.
- Request ID: в response header; в body только в error-response.

### 6) POST /api/v1/rectification/events/continue

- Purpose: продолжить Stage 2 flow по ответу пользователя.
- Input JSON:
```json
{
  "dialog_history": [],
  "last_answer": {
    "question_id": "ev_children_birth_01",
    "event_type": "children_birth",
    "title": "Рождение ребёнка",
    "date_text": "2018-09",
    "impact_level": 5,
    "reversibility": null,
    "life_area": null,
    "notes": "Сильный перелом",
    "user_skipped": false
  }
}
```
- Required fields:
  - `dialog_history`.
- Optional fields:
  - `last_answer` (если null/пусто, service может вернуть retry/safe behavior).
- Output JSON:
  - `status: "ask_question"` или `status: "finalized"`.
- Errors: стандартный error model.
- Warnings:
  - возможны `empty_answer_retry`, `question_mismatch_retry`, `max_steps_reached_safe_finalize` и т.д.
- Request ID: в response header; в body только в error-response.

### 7) POST /api/v1/rectification/events/finalize

- Purpose: завершить Stage 2 и получить events summary JSON.
- Input JSON:
```json
{
  "dialog_history": []
}
```
- Required fields:
  - `dialog_history`.
- Optional fields: нет.
- Output JSON:
```json
{
  "status": "finalized",
  "step_index": 0,
  "events_collected_count": 0,
  "warnings": ["insufficient_events_minimum_not_reached"],
  "events": [],
  "events_count": 0,
  "strong_events_count": 0,
  "confidence_preliminary": "low",
  "dialog_history": []
}
```
- Required output fields:
  - `status`, `step_index`, `events_collected_count`, `warnings`,
  - `events`, `events_count`, `strong_events_count`, `confidence_preliminary`, `dialog_history`.
- Optional output fields: нет.
- Errors: стандартный error model.
- Warnings:
  - например `insufficient_events_minimum_not_reached`.
- Request ID: в response header; в body только в error-response.

## References

- Примеры payload: `docs/examples/*.json`
- Интеграция с ботом: `docs/ASTROBOT_INTEGRATION.md`
