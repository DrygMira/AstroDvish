"""Операции над боевым сервером через SSH/SFTP (paramiko)."""
from __future__ import annotations

import shlex
import time
from pathlib import Path, PurePosixPath

try:
    import paramiko
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Не найден paramiko. Установи локальные зависимости деплоя:\n"
        "  .venv\\Scripts\\python.exe -m pip install -r scripts/requirements-deploy.txt"
    ) from exc


class RemoteError(RuntimeError):
    pass


def connect(host: str, user: str, key_path: str, timeout: int = 25) -> "paramiko.SSHClient":
    key = paramiko.Ed25519Key.from_private_key_file(str(Path(key_path).expanduser()))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host, port=22, username=user, pkey=key, timeout=timeout,
        look_for_keys=False, allow_agent=False, auth_timeout=timeout, banner_timeout=timeout,
    )
    return client


def run(client: "paramiko.SSHClient", cmd: str, timeout: int = 300, check: bool = True) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    if check and rc != 0:
        raise RemoteError(f"cmd failed (rc={rc}): {cmd}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    return out


def put(client: "paramiko.SSHClient", local: Path, remote: str) -> None:
    sftp = client.open_sftp()
    try:
        sftp.put(str(local), remote)
    finally:
        sftp.close()


def read_text(client: "paramiko.SSHClient", remote: str) -> str | None:
    sftp = client.open_sftp()
    try:
        with sftp.open(remote, "r") as f:
            return f.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return None
    finally:
        sftp.close()


def write_text(client: "paramiko.SSHClient", remote: str, content: str) -> None:
    sftp = client.open_sftp()
    try:
        with sftp.open(remote, "w") as f:
            f.write(content)
    finally:
        sftp.close()


def q(path: str) -> str:
    """Безопасное экранирование пути для удалённого bash."""
    return shlex.quote(path)


LEFTOVER_FILES = ["main.py", "api.js"]  # хвосты в корне от прежних ручных копирований


def split_remote_path(remote_path: str) -> tuple[str, str]:
    """(parent, base) для POSIX-пути сервера.

    Через PurePosixPath, а не Path: инструмент запускается на Windows, где
    Path("/opt/astrodvish").parent дал бы '\\opt' и сломал удалённые команды.
    """
    p = PurePosixPath(remote_path)
    return str(p.parent), p.name


def backup(client, remote_path: str, backups_dir: str, tag: str, ts: str) -> str:
    """Снять tar-бэкап текущего live (без ephe и без каталога бэкапов). Вернуть путь бэкапа."""
    run(client, f"mkdir -p {q(backups_dir)}")
    backup_path = f"{backups_dir}/predeploy_{ts}_{tag}.tgz"
    parent, base = split_remote_path(remote_path)
    run(
        client,
        f"tar czf {q(backup_path)} -C {q(parent)} "
        f"--exclude={q(base + '/ephe')} {q(base)}",
        timeout=600,
    )
    return backup_path


def upload_and_extract(client, local_tar: Path, remote_path: str) -> None:
    remote_tar = f"/tmp/{local_tar.name}"
    put(client, local_tar, remote_tar)
    run(client, f"mkdir -p {q(remote_path)}")
    run(client, f"tar xzf {q(remote_tar)} -C {q(remote_path)}", timeout=600)
    run(client, f"rm -f {q(remote_tar)}", check=False)


def remove_leftovers(client, remote_path: str, names: list[str] = LEFTOVER_FILES) -> list[str]:
    removed = []
    for name in names:
        target = f"{remote_path}/{name}"
        rc = run(client, f"test -f {q(target)} && rm -f {q(target)} && echo removed || echo absent")
        if "removed" in rc:
            removed.append(name)
    return removed


def write_stamp(client, remote_path: str, stamp_json: str, patch_text: str | None) -> None:
    write_text(client, f"{remote_path}/DEPLOYED.json", stamp_json)
    patch_path = f"{remote_path}/DEPLOYED_uncommitted.patch"
    if patch_text:
        write_text(client, patch_path, patch_text)
    else:
        run(client, f"rm -f {q(patch_path)}", check=False)


CONTAINERS = ["astrodvish-api", "astrodvish-web-ui"]


def compose_up(client, remote_path: str) -> None:
    run(client, f"cd {q(remote_path)} && docker compose up -d --build", timeout=900)


def wait_healthy(client, containers: list[str] = CONTAINERS, timeout: int = 180) -> bool:
    """Ждать, пока все контейнеры в состоянии healthy. True/False по факту."""
    deadline = time.time() + timeout
    fmt = "{{.State.Health.Status}}"
    while time.time() < deadline:
        statuses = {}
        for name in containers:
            out = run(client, f"docker inspect -f '{fmt}' {q(name)}", check=False).strip()
            statuses[name] = out
        if all(s == "healthy" for s in statuses.values()):
            return True
        time.sleep(5)
    return False


def rollback(client, remote_path: str, backup_path: str) -> None:
    """Восстановить live из бэкапа и пересобрать."""
    parent, _ = split_remote_path(remote_path)
    run(client, f"rm -rf {q(remote_path + '.broken')}", check=False)
    run(client, f"mv {q(remote_path)} {q(remote_path + '.broken')}")
    run(client, f"mkdir -p {q(remote_path)}")
    run(client, f"tar xzf {q(backup_path)} -C {q(parent)}", timeout=600)
    # ephe в бэкап не входит → перенести из .broken, если там был
    run(
        client,
        f"[ -d {q(remote_path + '.broken/ephe')} ] && cp -a {q(remote_path + '.broken/ephe')} {q(remote_path + '/ephe')} || true",
        check=False,
    )
    compose_up(client, remote_path)
    run(client, f"rm -rf {q(remote_path + '.broken')}", check=False)
