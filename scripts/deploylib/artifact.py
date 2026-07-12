"""Чистая логика сборки артефакта деплоя (без сети)."""
from __future__ import annotations

import subprocess
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
