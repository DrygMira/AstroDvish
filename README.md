# AstroDvish (Astra Engine)

AstroDvish — расчётное ядро для проекта GlobaAstro.

Проект считает астрологические факты и возвращает стабильный JSON. Он **не** должен придумывать градусы/дома/аспекты и **не** должен смешивать расчётные данные с GPT-интерпретациями.
Текущий фокус — подготовка AstroDvish как стабильного service API для подключения основного AstroBot.

## Что сейчас умеет

- Расчёт натальной карты через Swiss Ephemeris:
  - координаты объектов;
  - знаки, градусы, ретроградность;
  - ASC/MC и дома;
  - мажорные аспекты и орбисы;
  - служебные метаданные расчёта.
- Stage 1 ректификации:
  - `asc-sign-intervals` (интервалы восходящих знаков);
  - диалог Stage 1 с guard/fallback слоем для LLM.
- Stage 2 ректификации (events API):
  - сбор событий жизни;
  - structured event cards JSON;
  - preliminary confidence по числу/силе событий.
- Локальный web UI для тестирования API, Stage 1 и Stage 2.
- Timezone lookup по координатам.
- Health endpoint-ы для API и web UI.
- Request tracing через `X-Request-ID` и структурные request-логи.

## Структура проекта

```text
app/                      # FastAPI расчётный API
web_ui/                   # FastAPI web UI backend + static UI
tests/                    # pytest тесты
scripts/                  # локальный запуск/смоук
Dockerfile
docker-compose.yml
CURRENT_STATE.md
```

## Документация контракта

- API contract: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)
- AstroBot integration notes: [docs/ASTROBOT_INTEGRATION.md](docs/ASTROBOT_INTEGRATION.md)
- JSON examples: `docs/examples/*.json`
- AstroBot adapter usage example: [docs/examples/astrobot_client_usage.py](docs/examples/astrobot_client_usage.py)

## Требования

- Python 3.12+
- `pip`
- (опционально) Docker + Docker Compose

## Env-переменные

Основные (API):

- `APP_NAME=astro-ephemeris-service`
- `APP_HOST=0.0.0.0`
- `APP_PORT=8013`
- `APP_LOG_LEVEL=INFO`
- `SWEPH_EPHE_PATH=/opt/ephe`
- `SWEPH_AUTO_DOWNLOAD=true`
- `SWEPH_DOWNLOAD_TIMEOUT=120`
- `SWEPH_DOWNLOAD_RETRIES=2`
- `SWEPH_DOWNLOAD_BASE_URLS=https://www.astro.com/ftp/swisseph/ephe,https://github.com/aloistr/swisseph/raw/master/ephe`

Для web UI:

- `WEB_UI_HOST=0.0.0.0`
- `WEB_UI_PORT=8014`
- `DOCKER_COMPOSE_API_BASE_URL=http://astrodvish-api:8013` (в docker-compose)

Для OpenRouter в web UI:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (например `openai/gpt-4.1-mini`)
- `OPENROUTER_BASE_URL` (обычно `https://openrouter.ai/api/v1`)
- `OPENROUTER_SITE_URL` (опционально, для OpenRouter headers)
- `OPENROUTER_APP_NAME` (опционально, по умолчанию `AstroDvish`)
- `OPENROUTER_TIMEOUT_SECONDS` (по умолчанию `120`)

## Локальный запуск API

```bash
./scripts/start_api_local.sh
```

API по умолчанию: `http://127.0.0.1:8013`

## Локальный запуск web UI

```bash
./scripts/start_web_ui.sh
```

UI по умолчанию: `http://127.0.0.1:8014`

## Docker / docker-compose

```bash
cp .env.example .env
docker compose up -d --build
```

Поднимаются 2 сервиса:

- `astrodvish-api` (`8013`)
- `astrodvish-web-ui` (`8014`)

Оба сервиса имеют healthcheck.

## Endpoint-ы

### API (`app`)

- `GET /health`
- `GET /api/v1/health`
- `POST /api/v1/chart`
- `POST /api/v1/rectification/asc-sign-intervals`
- `POST /api/v1/rectification/events/start`
- `POST /api/v1/rectification/events/continue`
- `POST /api/v1/rectification/events/finalize`

### Web UI backend (`web_ui`)

- `GET /`
- `GET /health`
- `GET /api/prompt`
- `GET /api/rectification/prompt`
- `POST /api/geocode`
- `POST /api/generate`
- `POST /api/rectification/asc-sign-intervals`
- `POST /api/rectification/dialog/start`
- `POST /api/rectification/dialog/continue`
- `POST /api/rectification/events/start`
- `POST /api/rectification/events/continue`
- `POST /api/rectification/events/finalize`
- `GET /static/{filename}`

## Примеры запросов

### Health

```bash
curl http://127.0.0.1:8013/health
```

Пример ответа:

```json
{
  "status": "ok",
  "service": "astrodvish-api",
  "version": "0.5.0",
  "request_id": "..."
}
```

### Натальная карта

```bash
curl -X POST "http://127.0.0.1:8013/api/v1/chart" \
  -H "Content-Type: application/json" \
  -d '{
    "datetime_utc": "1984-11-13T11:35:00Z",
    "latitude": 53.9006,
    "longitude": 27.5590,
    "house_system": "P",
    "zodiac_mode": "tropical",
    "sidereal_mode": null
  }'
```

Примечание: `POST /api/v1/chart` возвращает только расчётные данные (`objects`, `houses`, `angles`, `aspects`, `meta`) и не содержит `horoscope_text`/`interpretation_text`.

### Аспекты и орбисы (в `chart` output)

Считаются аспекты:

- `conjunction` (`0°`, orb `8°`)
- `opposition` (`180°`, orb `8°`)
- `trine` (`120°`, orb `7°`)
- `square` (`90°`, orb `6°`)
- `sextile` (`60°`, orb `5°`)

Формат элемента массива `aspects`:

```json
{
  "object_a": "Sun",
  "object_b": "Moon",
  "aspect_type": "trine",
  "exact_angle": 120.0,
  "actual_angle": 118.4,
  "orb": 1.6,
  "applying": null
}
```

### Интервалы Stage 1

```bash
curl -X POST "http://127.0.0.1:8013/api/v1/rectification/asc-sign-intervals" \
  -H "Content-Type: application/json" \
  -d '{
    "birth_date_local": "2000-04-16",
    "latitude": 53.9,
    "longitude": 27.56667,
    "house_system": "P",
    "zodiac_mode": "tropical",
    "sidereal_mode": null
  }'
```

### Stage 1 dialog start (через web_ui backend)

```bash
curl -X POST "http://127.0.0.1:8014/api/rectification/dialog/start" \
  -H "Content-Type: application/json" \
  -d '{
    "api_base_url": "http://127.0.0.1:8013",
    "birth_date_local": "2000-04-16",
    "latitude": 53.9,
    "longitude": 27.56667,
    "house_system": "P",
    "zodiac_mode": "tropical",
    "sidereal_mode": null,
    "prompt_text": "stage1 prompt"
  }'
```

Пример ответа (сокращённо):

```json
{
  "rectification_document": {"mode": "asc_sign_intervals"},
  "llm_json": {
    "type": "ask_question",
    "question_id": "q_first_impression_01",
    "options": [{"id": "A", "text": "..."}],
    "allow_free_text": false
  },
  "warnings": [],
  "step_count": 1
}
```

### Stage 2 events finalize (через web_ui backend)

```bash
curl -X POST "http://127.0.0.1:8014/api/rectification/events/finalize" \
  -H "Content-Type: application/json" \
  -d '{
    "api_base_url": "http://127.0.0.1:8013",
    "dialog_history": []
  }'
```

Пример ответа (сокращённо):

```json
{
  "status": "finalized",
  "events": [],
  "events_count": 0,
  "strong_events_count": 0,
  "confidence_preliminary": "low",
  "warnings": ["insufficient_events_minimum_not_reached"]
}
```

## Stage 2 в web UI

1. Откройте вкладку `Уточнить время по событиям жизни`.
2. Нажмите `Начать сбор событий`.
3. На каждый вопрос заполните поля события и нажмите `Ответить`, либо `Пропустить`.
4. Нажмите `Завершить` в любой момент для принудительного finalize.
5. После finalize UI показывает:
   - `events_count`;
   - `strong_events_count`;
   - `confidence_preliminary`;
   - список `event cards`;
   - `warnings` (если есть).
6. Кнопка `Показать технический JSON` раскрывает raw ответ Stage 2.

## Запуск тестов

```bash
python -m pytest -q
```

Если проект запускается через виртуальное окружение:

```bash
.venv/bin/python -m pytest -q
```

## Release smoke check

- Release checklist: [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)

Windows:

```powershell
.\scripts\smoke_release.ps1
```

Linux/macOS:

```bash
./scripts/smoke_release.sh
```

## Стабилизация Stage 1: guard/fallback

Для `dialog/start` и `dialog/continue` добавлен guard-слой:

- валидирует структуру и семантику `ask_question`;
- валидирует структуру и семантику `final_result`;
- проверяет повтор `question_id`;
- проверяет диапазон `probability` (`0..1`);
- принудительно ставит `allow_free_text=false` (стабилизационная политика B).

Если LLM вернул плохой JSON/ошибку/невалидную схему:

- пользователю не отдаётся сломанный результат;
- возвращается deterministic fallback:
  - безопасный следующий вопрос из Question Bank, или
  - safe finalization при `finalize_now`/достаточном шаге/`max_steps`;
- в ответе заполняется `warnings`, в лог пишется причина fallback.

## Логи и request_id

- В API middleware генерирует/принимает `X-Request-ID`.
- `X-Request-ID` добавляется в response headers.
- Ошибки включают `error.request_id`.
- Логируются события `request_start`, `request_end`, `request_exception` в структурном формате.

## Известные ограничения

- Stage 2 пока только собирает события жизни и возвращает structured JSON; сужение времени рождения на этом этапе не выполняется.
- Аспекты/orbs Stage 2 в этой задаче не расширялись.
- Free text в Stage 1 отключён (политика B): `allow_free_text=false`, `free_text` не используется.
- `POST /api/generate` и dialog LLM-вызовы требуют `OPENROUTER_API_KEY`.

## Не входит в текущий scope

- дирекции/соляры/лунары/транзиты
- тотемы/антитотемы
- интеграция с основным AstroBot
- редизайн UI
#   A s t r o D v i s h  
 