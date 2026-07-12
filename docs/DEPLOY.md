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
По умолчанию: `root@45.133.18.90:/opt/astrodvish`, ключ `~/.ssh/auron_deploy`, remote `dryg`.
