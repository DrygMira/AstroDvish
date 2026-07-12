"""Операции над боевым сервером через SSH/SFTP (paramiko)."""
from __future__ import annotations

import shlex
from pathlib import Path

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
