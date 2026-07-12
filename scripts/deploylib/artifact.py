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
