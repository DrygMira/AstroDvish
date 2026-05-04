# AstroBot Integration Notes

Документ описывает как основной бот GlobaAstro должен использовать AstroDvish как внешнее расчётное ядро.

## Роли систем

- AstroDvish:
  - считает `calculation_json`, `rectification_json`, `events_json`;
  - не хранит пользовательские сессии;
  - не генерирует GPT-интерпретации;
  - не придумывает пользовательские ответы.
- AstroBot:
  - управляет сессией пользователя;
  - хранит контекст диалога, history и выборы пользователя;
  - вызывает AstroDvish API;
  - передаёт расчётные JSON в LLM-слой для текстовой подачи.

## Рекомендуемый flow вызовов

1. Health check:
  - `GET /api/v1/health` перед рабочими вызовами.
2. Базовый расчёт:
  - `POST /api/v1/chart` -> сохранить как `calculation_json`.
3. Stage 1 rectification (опционально):
  - `POST /api/v1/rectification/asc-sign-intervals` -> `rectification_json`.
4. Stage 2 events (опционально):
  - `POST /api/v1/rectification/events/start`
  - `POST /api/v1/rectification/events/continue` (loop)
  - `POST /api/v1/rectification/events/finalize` -> `events_json`.

## Recommended adapter usage

- Основной бот должен использовать централизованный adapter:
  - `app/clients/astrobot_client.py`
- Не размазывать HTTP-вызовы по хендлерам Telegram-бота.
- Весь transport/retry/timeout/error mapping держать в adapter-слое.
- Bot-код должен работать с типизированными response-моделями adapter-а.

Минимальный рекомендуемый набор вызовов adapter-а:

- `get_health(...)`
- `get_chart(...)`
- `get_asc_sign_intervals(...)`
- `start_events_collection(...)`
- `continue_events_collection(...)`
- `finalize_events_collection(...)`
- `run_rectification_pro(...)`

Пример: `docs/examples/astrobot_client_usage.py`.

## Что хранит бот у себя

- User profile и технический session id.
- `calculation_json`, `rectification_json`, `events_json`.
- `dialog_history` Stage 2.
- `warnings`, `confidence_preliminary`.
- Связь между bot message id и `X-Request-ID`.

## Что AstroDvish не хранит

- Не ведёт персистентную историю пользователя.
- Не хранит Telegram chat state.
- Не хранит ключи/настройки внешних LLM клиента.

## Передача JSON в GPT-слой

- Бот передаёт в GPT только результаты AstroDvish как входные факты.
- В prompt GPT явно указывать:
  - использовать только переданные degrees/houses/aspects;
  - не выдумывать дополнительные астроданные;
  - не подменять `confidence_preliminary`.

## Жёсткие правила для GPT

- GPT не должен придумывать:
  - градусы;
  - дома;
  - аспекты;
  - орбисы;
  - timezone/UTC преобразования.
- Все точные данные берутся только из AstroDvish JSON.

## Работа с warnings и confidence

- Если `warnings` не пустой:
  - показать пользователю мягкое техническое предупреждение;
  - при необходимости предложить повтор шага.
- Если `confidence_preliminary = low`:
  - не подавать результат как точную ректификацию;
  - предложить собрать больше событий Stage 2 (если лимиты не достигнуты);
  - явно маркировать как предварительный результат.
- Если `confidence_preliminary = medium/high`:
  - можно продолжать следующий pipeline шаг,
  - но всё равно хранить warning-коды для аудита.

## Request ID tracing

- Для каждого запроса к AstroDvish бот должен отправлять `X-Request-ID`.
- Этот же id логировать на стороне бота и связывать с user session.
- При ошибках из AstroDvish читать `error.request_id` и включать в bot logs/support traces.

## Anti-patterns

- Не смешивать `calculation_json` с GPT-ответом в один source of truth.
- Не переписывать AstroDvish числа в боте.
- Не делать fallback-расчёты в боте, если AstroDvish вернул ошибку.
