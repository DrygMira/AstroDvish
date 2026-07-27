# Деплой AstroDvish

Инструмент: `scripts/deploy.py` (Python, запуск из корня проекта в `.venv`).

## Установка (один раз)
```
.venv\Scripts\python.exe -m pip install -r scripts/requirements-deploy.txt
```

## Команды
- Сухой прогон: `.venv\Scripts\python.exe scripts/deploy.py --plan`
- Проверить, совпадает ли прод с кодом: `.venv\Scripts\python.exe scripts/deploy.py --status`
- Выложить: `.venv\Scripts\python.exe scripts/deploy.py` (спросит подтверждение)
- Откат: `.venv\Scripts\python.exe scripts/deploy.py --rollback /opt/astrodvish_backups/<файл>.tgz`

## Что происходит при выкладке
1. Сборка артефакта из текущего дерева (трекнутые + новые файлы; `.env`/`ephe`/секреты исключены).
2. Бэкап текущего live в `/opt/astrodvish_backups/`.
3. Запись «бирки» `DEPLOYED.json` (+ `DEPLOYED_uncommitted.patch`, если дерево грязное).
4. Распаковка, подчистка хвостов, `docker compose up -d --build`.
5. Health-gate; при провале — авто-откат.

## Настройки через окружение
`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`, `DEPLOY_REMOTE`.

Боевой сервер: `root@194.87.0.137:/opt/astrodvish`, ключ `~/.ssh/astrodvish_deploy`, remote `dryg`.
В коде дефолты пока указывают на прежний сервер `45.133.18.90` с ключом `~/.ssh/auron_deploy`,
поэтому выкладка идёт с явным указанием:

```
set DEPLOY_HOST=194.87.0.137
set DEPLOY_SSH_KEY=%USERPROFILE%\.sshstrodvish_deploy
```

## Ручки производительности

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `API_WORKERS` | `2` (задаётся в `docker-compose.yml`) | Число процессов uvicorn у API. Один тяжёлый расчёт занимает примерно одно ядро, поэтому два воркера = два пользователя считают параллельно. На слабом сервере ставь `1`. |
| `RECTIFICATION_PRO_MAX_CONCURRENT_JOBS` | `2` | Сколько тяжёлых Pro-расчётов web_ui пускает одновременно. Сверх лимита — `429` с понятным текстом. Держи не больше, чем `API_WORKERS`, иначе задачи начнут толкаться на одном ядре. |

**Нельзя** запускать `web_ui` больше чем в одном процессе: реестр Pro-задач живёт в памяти
процесса, и опрос статуса начнёт попадать в чужой воркер. На это есть тест
`test_web_ui_container_stays_single_process`.
