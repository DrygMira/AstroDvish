#!/usr/bin/env python3
"""Инструмент воспроизводимого деплоя AstroDvish.

Режимы:
  python scripts/deploy.py            — выложить текущее рабочее дерево
  python scripts/deploy.py --plan     — сухой прогон (ничего не менять)
  python scripts/deploy.py --status   — сравнить live vs локальный HEAD vs remote
  python scripts/deploy.py --rollback <backup.tgz>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.deploylib import artifact, remote

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST = os.environ.get("DEPLOY_HOST", "45.133.18.90")
USER = os.environ.get("DEPLOY_USER", "root")
KEY = os.environ.get("DEPLOY_SSH_KEY", str(Path("~/.ssh/auron_deploy").expanduser()))
REMOTE_PATH = os.environ.get("DEPLOY_PATH", "/opt/astrodvish")
BACKUPS_DIR = os.environ.get("DEPLOY_BACKUPS", "/opt/astrodvish_backups")
REMOTE_NAME = os.environ.get("DEPLOY_REMOTE", "dryg")


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_diff() -> str:
    return subprocess.run(
        ["git", "diff", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout


def cmd_plan(files: list[str], dirty: bool, info: dict, pushed: bool) -> None:
    print(f"[plan] коммит: {info['short']} ({info['branch']})")
    print(f"[plan] грязное дерево: {'ДА' if dirty else 'нет'}")
    print(f"[plan] запушено в {REMOTE_NAME}: {'да' if pushed else 'НЕТ'}")
    print(f"[plan] файлов в артефакте: {len(files)}")
    print(f"[plan] цель: {USER}@{HOST}:{REMOTE_PATH}")
    print("[plan] сухой прогон — ничего не изменено.")


def cmd_status() -> int:
    info = artifact.commit_info(REPO_ROOT)
    client = remote.connect(HOST, USER, KEY)
    try:
        raw = remote.read_text(client, f"{REMOTE_PATH}/DEPLOYED.json")
    finally:
        client.close()
    print(f"локальный HEAD : {info['short']} ({info['branch']})")
    if raw is None:
        print("на сервере     : DEPLOYED.json отсутствует (деплой инструментом ещё не делался)")
        return 1
    live = json.loads(raw)
    print(f"на сервере     : {live.get('short')} (dirty={live.get('dirty')}, {live.get('deployed_at')})")
    same = live.get("commit") == info["commit"] and not live.get("dirty")
    print("СТАТУС         :", "совпадает (git == live)" if same else "РАСХОЖДЕНИЕ git != live")
    return 0 if same else 2


def cmd_rollback(backup_path: str) -> int:
    client = remote.connect(HOST, USER, KEY)
    try:
        print(f"[rollback] восстанавливаю из {backup_path} ...")
        remote.rollback(client, REMOTE_PATH, backup_path)
        ok = remote.wait_healthy(client)
    finally:
        client.close()
    print("[rollback] health:", "OK" if ok else "НЕ поднялся")
    return 0 if ok else 1


def cmd_deploy(files: list[str], dirty: bool, info: dict, pushed: bool, assume_yes: bool) -> int:
    if dirty:
        print("[warn] рабочее дерево ГРЯЗНОЕ — деплоятся незакоммиченные правки.")
    if not pushed:
        print(f"[warn] коммит НЕ запушен в {REMOTE_NAME} — live будет труднее восстановить из git.")
    print(f"[deploy] {info['short']} ({info['branch']}), файлов: {len(files)} -> {USER}@{HOST}:{REMOTE_PATH}")
    if not assume_yes:
        if input("Продолжить деплой? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Отменено.")
            return 1

    ts = _now_utc().replace(":", "").replace("-", "")
    tag = f"{info['short']}{'_dirty' if dirty else ''}"
    with tempfile.TemporaryDirectory() as td:
        tar_path = Path(td) / f"astrodvish_{tag}.tgz"
        sha = artifact.build_artifact(REPO_ROOT, files, tar_path)
        stamp = artifact.build_stamp(REPO_ROOT, sha, REMOTE_NAME, _now_utc())
        patch = _local_diff() if dirty else None

        client = remote.connect(HOST, USER, KEY)
        try:
            backup_path = remote.backup(client, REMOTE_PATH, BACKUPS_DIR, tag, ts)
            print(f"[deploy] бэкап: {backup_path}")
            remote.write_stamp(client, REMOTE_PATH, json.dumps(stamp, ensure_ascii=False, indent=2), patch)
            remote.upload_and_extract(client, tar_path, REMOTE_PATH)
            removed = remote.remove_leftovers(client, REMOTE_PATH)
            if removed:
                print(f"[deploy] удалены хвосты: {removed}")
            print("[deploy] пересборка контейнеров ...")
            remote.compose_up(client, REMOTE_PATH)
            print("[deploy] проверка health ...")
            if remote.wait_healthy(client):
                print(f"[deploy] УСПЕХ. live = {info['short']} (sha {sha[:12]})")
                return 0
            print("[deploy] health НЕ поднялся — авто-откат ...")
            remote.rollback(client, REMOTE_PATH, backup_path)
            print("[deploy] откат выполнен. Проверь логи сервера.")
            return 1
        finally:
            client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Деплой AstroDvish (source-of-truth)")
    parser.add_argument("--plan", action="store_true", help="сухой прогон")
    parser.add_argument("--status", action="store_true", help="сравнить live vs git")
    parser.add_argument("--rollback", metavar="BACKUP", help="откат из бэкапа .tgz")
    parser.add_argument("-y", "--yes", action="store_true", help="без подтверждения")
    args = parser.parse_args()

    if args.status:
        return cmd_status()
    if args.rollback:
        return cmd_rollback(args.rollback)

    files = artifact.list_deploy_files(REPO_ROOT)
    dirty = artifact.is_dirty(REPO_ROOT)
    info = artifact.commit_info(REPO_ROOT)
    pushed = artifact.is_pushed_to_remote(REPO_ROOT, REMOTE_NAME, info["branch"])

    if args.plan:
        cmd_plan(files, dirty, info, pushed)
        return 0
    return cmd_deploy(files, dirty, info, pushed, args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
