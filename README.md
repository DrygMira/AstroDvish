# Astro Ephemeris Service

Локальный REST-микросервис на `FastAPI` + `pyswisseph` для расчёта:
- положений планет и узлов;
- домов (cusp 1..12);
- углов (`ASC`, `MC`, `ARMC`, `Vertex` и дополнительные стандартные точки `ascmc`).

Сервис принимает только:
- `datetime_utc` (уже в UTC, ISO 8601),
- `latitude`,
- `longitude`,

и опциональные параметры режима зодиака/домов.

Только один публичный рабочий endpoint: `POST /api/v1/chart`.

## Архитектурные решения

- Сервис без БД, Redis, очередей и авторизации: рассчитан на локальную доверенную сеть.
- Глобальные обработчики ошибок возвращают структурированный JSON.
- Логика расчёта вынесена в сервисный слой (`app/services`), endpoint тонкий.
- Автозагрузка эфемерид вынесена в отдельный модуль (`ephemeris_downloader`).
- Для потокобезопасности при работе с глобальным состоянием Swiss Ephemeris используется lock в расчётном сервисе.
- Если `SWEPH_AUTO_DOWNLOAD=false` и файлы отсутствуют, сервис стартует в fallback-режиме (Moshier), но логирует отсутствие файлов.

## Стек

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic v2
- pyswisseph
- pytest
- httpx / TestClient
- Docker / docker compose

## Структура проекта

```text
astro-bot-API/
  api_service/                # API-часть (документация запуска)
  app/                        # Реализация API
  web_ui/                     # Веб-морда для тестов (порт 8014)
    main.py
    static/index.html
  tests/                      # Тесты API
  PROMPT.md
  scripts/start_api_local.sh
  scripts/start_web_ui.sh
  scripts/test_api_local.sh
  requirements.txt
  Dockerfile
  docker-compose.yml
  .env.example
  README.md
```

## Входные данные

### POST `/api/v1/chart`

Обязательные поля:
- `datetime_utc`: ISO 8601 UTC (например, `1984-11-13T11:35:00Z`)
- `latitude`: `-90..90`
- `longitude`: `-180..180`

Необязательные:
- `house_system`: `P`/`K`/`O`, по умолчанию `P`
- `zodiac_mode`: `tropical` или `sidereal`, по умолчанию `tropical`
- `sidereal_mode`: `null` или `lahiri` / `fagan_bradley` / `krishnamurti`

Правила:
- `tropical` -> `sidereal_mode` должен быть `null`
- `sidereal` -> `sidereal_mode` обязателен

## Таблица объектов Swiss Ephemeris

| Имя | Константа |
|---|---|
| sun | `swe.SUN` |
| moon | `swe.MOON` |
| mercury | `swe.MERCURY` |
| venus | `swe.VENUS` |
| mars | `swe.MARS` |
| jupiter | `swe.JUPITER` |
| saturn | `swe.SATURN` |
| uranus | `swe.URANUS` |
| neptune | `swe.NEPTUNE` |
| pluto | `swe.PLUTO` |
| true_node | `swe.TRUE_NODE` |
| mean_node | `swe.MEAN_NODE` |
| chiron | `swe.CHIRON` (опционально; пропускается при недоступности данных) |

## Формат ответа

Ответ строго JSON, пригоден для машинной обработки.
Для каждого объекта возвращаются:
- координаты, скорость, ретроградность;
- знак (`sign_index`, `sign_name_en`, `sign_degree`, `sign_degree_dms`);
- `absolute_degree_0_360`.

Также возвращаются:
- `normalized.julian_day_ut`;
- `houses.cusps` (12 домов);
- `angles` из стандартного массива `ascmc`: `asc`, `mc`, `armc`, `vertex`, `equatorial_ascendant`, `co_ascendant_koch`, `co_ascendant_munkasey`, `polar_ascendant`.

## Автозагрузка эфемерид

При старте сервис:
1. проверяет наличие обязательных файлов в `SWEPH_EPHE_PATH`;
2. скачивает недостающие файлы (если `SWEPH_AUTO_DOWNLOAD=true`);
3. не скачивает повторно уже существующие файлы (идемпотентно);
4. логирует найденные/скачанные/отсутствующие файлы.

Куда складываются файлы:
- по умолчанию: `/opt/ephe`
- в Docker: том `./ephe:/opt/ephe`

Как предзагрузить вручную:
- положите файлы `sepl_18.se1`, `sepl_24.se1`, `semo_18.se1`, `semo_24.se1`, `seas_18.se1`, `seas_24.se1` в каталог `SWEPH_EPHE_PATH`.

Источники загрузки:
- задаются через `SWEPH_DOWNLOAD_BASE_URLS` (comma-separated URL).

Поддержаны:
- timeout (`SWEPH_DOWNLOAD_TIMEOUT`);
- ограниченное число retry (`SWEPH_DOWNLOAD_RETRIES`);
- аккуратная ошибка bootstrap при неудачной загрузке.

## Переменные окружения

Смотрите `.env.example`.

Основные:
- `APP_NAME=astro-ephemeris-service`
- `APP_HOST=0.0.0.0`
- `APP_PORT=8013`
- `APP_LOG_LEVEL=INFO`
- `SWEPH_EPHE_PATH=/opt/ephe`
- `SWEPH_AUTO_DOWNLOAD=true`
- `SWEPH_DOWNLOAD_TIMEOUT=120`
- `SWEPH_DOWNLOAD_RETRIES=2`
- `SWEPH_DOWNLOAD_BASE_URLS=https://www.astro.com/ftp/swisseph/ephe,https://github.com/aloistr/swisseph/raw/master/ephe`

## Локальный запуск

```bash
./scripts/start_api_local.sh
```

Сервис будет доступен на `0.0.0.0:8013`.

## Запуск веб-морды (локально)

```bash
./scripts/start_web_ui.sh
```

Веб-морда доступна на `0.0.0.0:8014`.

Она умеет:
- ввод локального времени + выбор `UTC offset` и превью UTC;
- выбор `house_system`, `zodiac_mode`, `sidereal_mode`;
- поиск города через geocoding и автоподстановку координат;
- ручной ввод координат;
- редактирование промта из `PROMPT.md`;
- генерацию текста гороскопа через OpenAI API (модель `gpt-5.4-nano`) с ключом из файла `./secrets.txt` (см. `secrets.txt.example`);
- вызов API и показ результата во всплывающем окне:
  - верхнее поле: текст "гороскопа";
  - нижнее поле: полный JSON-ответ API (скрыт по умолчанию, показывается кнопкой).

## Тестовый запуск API без веб-морды

```bash
./scripts/test_api_local.sh
```

Скрипт поднимает API на отдельном порту `18013` (можно переопределить через `TEST_API_PORT`)
и прогоняет HTTP smoke-тесты по endpoint-ам `/api/v1/chart` и
`/api/v1/rectification/asc-sign-intervals`.

## Запуск через Docker

```bash
cp .env.example .env
docker compose up -d --build
```

## Тесты

```bash
.venv/bin/python -m pytest -q
```

Покрыты сценарии:
- успешный `POST /api/v1/chart`;
- реальные API-вызовы с проверкой структуры/диапазонов;
- все указанные ошибки валидации;
- bootstrap эфемерид;
- идемпотентность загрузчика.

## Пример запроса

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

## Пример ответа

```json
{
  "input": {
    "datetime_utc": "1984-11-13T11:35:00Z",
    "latitude": 53.9006,
    "longitude": 27.559,
    "house_system": "P",
    "zodiac_mode": "tropical",
    "sidereal_mode": null
  },
  "normalized": {
    "julian_day_ut": 2446017.982638889
  },
  "objects": {
    "sun": {
      "name": "sun",
      "longitude_deg": 231.0,
      "latitude_deg": 0.0,
      "distance_au": 0.99,
      "speed_longitude_deg_per_day": 1.0,
      "retrograde": false,
      "sign_index": 7,
      "sign_name_en": "Scorpio",
      "sign_degree": 21.0,
      "sign_degree_dms": "21°00'00.00\"",
      "absolute_degree_0_360": 231.0
    }
  },
  "houses": {
    "system": "P",
    "cusps": {
      "1": 145.0,
      "2": 172.0,
      "3": 201.0,
      "4": 238.0,
      "5": 271.0,
      "6": 300.0,
      "7": 325.0,
      "8": 352.0,
      "9": 21.0,
      "10": 58.0,
      "11": 91.0,
      "12": 120.0
    }
  },
  "angles": {
    "asc": 145.0,
    "mc": 58.0,
    "armc": 57.8,
    "vertex": 289.4
  },
  "meta": {
    "ephemeris_source": "swisseph",
    "zodiac_mode": "tropical",
    "sidereal_mode": null,
    "object_constants": {
      "sun": 0
    }
  }
}
```

## Важно про безопасность и лицензию

- Сервис предназначен для внутренней доверенной сети и не содержит авторизации.
- Перед публичным/коммерческим использованием обязательно проверьте условия лицензии Swiss Ephemeris.
