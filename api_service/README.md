# API Service

Эта часть проекта отвечает только за расчёт астрологических данных через Swiss Ephemeris.

Основной API endpoint:
- `POST /api/v1/chart`

Запуск API локально:
```bash
../scripts/start_api_local.sh
```

Тестовый запуск API (без веб-морды, с отключённой автозагрузкой эфемерид):
```bash
../scripts/start_api_test_mode.sh
```

