# Release Checklist (Cluster 5.1)

Этот чеклист нужен перед передачей AstroDvish и перед подключением к основному боту.

## 1) Поднять API

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8013
```

Linux/macOS:

```bash
./scripts/start_api_local.sh
```

## 2) Поднять web UI

Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m uvicorn web_ui.main:app --host 0.0.0.0 --port 8014
```

Linux/macOS:

```bash
./scripts/start_web_ui.sh
```

## 3) Прогнать тесты

Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS:

```bash
python -m pytest -q
```

## 4) Проверить health

```bash
curl http://127.0.0.1:8013/health
curl http://127.0.0.1:8013/api/v1/health
```

Ожидается:

- `status = ok`
- `service = astrodvish-api`
- `version = 0.5.0`
- есть `request_id`

## 5) Проверить chart

```bash
curl -X POST "http://127.0.0.1:8013/api/v1/chart" \
  -H "Content-Type: application/json" \
  -d @docs/examples/chart_request.json
```

Проверить:

- есть top-level поля: `input`, `normalized`, `objects`, `aspects`, `houses`, `angles`, `meta`
- нет `interpretation_text`

## 6) Проверить Stage 1

```bash
curl -X POST "http://127.0.0.1:8013/api/v1/rectification/asc-sign-intervals" \
  -H "Content-Type: application/json" \
  -d @docs/examples/asc_intervals_request.json
```

Проверить:

- есть `birth_context.timezone`
- есть `birth_context.timezone_source` (`coordinates`)
- есть `asc_sign_intervals` (не пустой массив)

## 7) Проверить Stage 2

```bash
curl -X POST "http://127.0.0.1:8013/api/v1/rectification/events/start" \
  -H "Content-Type: application/json" \
  -d '{"dialog_history":[]}'
```

Проверить:

- `status = ask_question` или `status = finalized`
- есть `warnings` и `dialog_history`

Опционально:

- прогнать полный flow `start -> continue -> finalize` через web UI вкладку Stage 2.

## 8) Проверить adapter

- Запустить тесты adapter:

```bash
python -m pytest -q tests/test_astrobot_client.py
```

- Открыть пример:
  - `docs/examples/astrobot_client_usage.py`

Проверить:

- bot использует adapter, а не прямые HTTP вызовы по всему коду.

## 9) Автоматический smoke pack

Windows:

```powershell
.\scripts\smoke_release.ps1
```

Linux/macOS:

```bash
./scripts/smoke_release.sh
```

Оба скрипта проверяют:

- `/health`
- `/api/v1/health`
- `/api/v1/chart`
- `/api/v1/rectification/asc-sign-intervals`
- `/api/v1/rectification/events/start`

## 10) Что считать успешной проверкой

Проверка считается успешной, если одновременно выполнено всё:

- `pytest -q` проходит без падений;
- manual проверки из пунктов 4-8 не дают ошибок;
- smoke script для вашей ОС завершается кодом `0`;
- smoke script показывает `OK` по каждому шагу;
- в `health` и `api/v1/health` версия равна `0.5.0`.
