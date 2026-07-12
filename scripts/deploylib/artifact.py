"""Чистая логика сборки артефакта деплоя (без сети)."""
from __future__ import annotations

import hashlib
import io
import subprocess
import tarfile
from pathlib import Path


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def list_deploy_files(repo_root: Path) -> list[str]:
    """Пути (posix, относительно корня) для деплоя: трекнутые + новые не-игнорируемые.

    Мусор и секреты отсекаются автоматически через .gitignore.
    """
    tracked = _git(repo_root, "ls-files").splitlines()
    untracked = _git(repo_root, "ls-files", "--others", "--exclude-standard").splitlines()
    files = {p.strip() for p in (*tracked, *untracked) if p.strip()}
    return sorted(files)


def is_dirty(repo_root: Path) -> bool:
    """True, если в рабочем дереве есть незакоммиченные изменения."""
    return bool(_git(repo_root, "status", "--porcelain").strip())


def commit_info(repo_root: Path) -> dict[str, str]:
    """Текущий коммит: полный sha, короткий, имя ветки."""
    commit = _git(repo_root, "rev-parse", "HEAD").strip()
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return {"commit": commit, "short": commit[:7], "branch": branch}


def is_pushed_to_remote(repo_root: Path, remote: str, branch: str) -> bool:
    """True, если текущий HEAD содержится в <remote>/<branch> (уже запушен)."""
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    try:
        contains = _git(repo_root, "branch", "-r", "--contains", head).splitlines()
    except subprocess.CalledProcessError:
        return False
    target = f"{remote}/{branch}"
    return any(line.strip() == target for line in contains)


def build_artifact(repo_root: Path, files: list[str], out_path: Path) -> str:
    """Собрать .tar.gz из файлов (posix-имена, фикс. mtime) и вернуть sha256 по содержимому.

    content-sha считается по (path, bytes) и не зависит от gzip-заголовка,
    поэтому одинаковое дерево → одинаковый sha (детерминированно).
    Несуществующие пути (удалённые в рабочем дереве) пропускаются.
    """
    hasher = hashlib.sha256()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tar:
        for rel in files:
            local = repo_root.joinpath(*rel.split("/"))
            if not local.is_file():
                continue
            data = local.read_bytes()
            hasher.update(rel.encode("utf-8") + b"\x00")
            hasher.update(data)
            info = tarfile.TarInfo(name=rel)  # posix-путь как есть
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return hasher.hexdigest()
