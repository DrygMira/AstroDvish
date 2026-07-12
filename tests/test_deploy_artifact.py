import subprocess
from pathlib import Path

import pytest

from scripts.deploylib import artifact


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n*.log\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "junk.txt").write_text("junk", encoding="utf-8")
    (tmp_path / "trace.log").write_text("log", encoding="utf-8")
    _git(tmp_path, "add", "keep.py", ".gitignore")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_list_includes_tracked_and_new_but_not_ignored(repo: Path) -> None:
    # новый, ещё не добавленный в git файл — должен попасть
    (repo / "new_card.json").write_text("{}", encoding="utf-8")
    files = artifact.list_deploy_files(repo)
    assert "keep.py" in files
    assert ".gitignore" in files
    assert "new_card.json" in files
    assert "ignored/junk.txt" not in files
    assert "trace.log" not in files
    assert files == sorted(files)  # отсортировано и без дублей


def test_is_dirty_reflects_working_tree(repo: Path) -> None:
    assert artifact.is_dirty(repo) is False
    (repo / "keep.py").write_text("x = 2\n", encoding="utf-8")
    assert artifact.is_dirty(repo) is True


def test_commit_info_has_sha_short_branch(repo: Path) -> None:
    info = artifact.commit_info(repo)
    assert len(info["commit"]) == 40
    assert info["commit"].startswith(info["short"])
    assert info["branch"]  # непустая ветка
