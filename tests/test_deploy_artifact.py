import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.deploylib import artifact, remote


def test_split_remote_path_is_posix() -> None:
    # Удалённый путь Linux-сервера должен разбираться POSIX-style
    # даже когда инструмент запущен на Windows (Path().parent там дал бы '\\opt').
    assert remote.split_remote_path("/opt/astrodvish") == ("/opt", "astrodvish")
    assert remote.split_remote_path("/opt/app/sub") == ("/opt/app", "sub")


def test_validate_backup_listing() -> None:
    ok = "astrodvish/\nastrodvish/docker-compose.yml\nastrodvish/app/main.py\n"
    assert remote.validate_backup_listing(ok, "astrodvish") is True
    # пустой архив (20-байтный gzip после упавшего tar) — невалиден
    assert remote.validate_backup_listing("", "astrodvish") is False
    assert remote.validate_backup_listing("\n\n", "astrodvish") is False
    # архив с чужим корнем — откат в /opt/astrodvish им делать нельзя
    assert remote.validate_backup_listing("other/file.py\n", "astrodvish") is False


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


def test_is_pushed_to_remote(tmp_path: Path) -> None:
    bare = tmp_path / "bare.git"
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(bare), str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "a.txt").write_text("a", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-qm", "c1")
    branch = artifact.commit_info(work)["branch"]

    # ещё не запушено
    assert artifact.is_pushed_to_remote(work, "origin", branch) is False
    _git(work, "push", "-q", "origin", branch)
    _git(work, "fetch", "-q", "origin")
    # после пуша — да
    assert artifact.is_pushed_to_remote(work, "origin", branch) is True


def test_build_artifact_is_deterministic_and_correct(repo: Path, tmp_path: Path) -> None:
    (repo / "sub").mkdir()
    (repo / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")
    files = ["keep.py", "sub/b.py"]

    out1 = tmp_path / "a1.tgz"
    out2 = tmp_path / "a2.tgz"
    sha1 = artifact.build_artifact(repo, files, out1)
    sha2 = artifact.build_artifact(repo, files, out2)

    # content-sha не зависит от gzip-mtime → детерминирован
    assert sha1 == sha2
    assert len(sha1) == 64

    with tarfile.open(out1) as tar:
        names = sorted(tar.getnames())
    assert names == ["keep.py", "sub/b.py"]  # posix-пути, вложенность сохранена


def test_build_artifact_skips_missing_files(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "a.tgz"
    sha = artifact.build_artifact(repo, ["keep.py", "deleted.py"], out)
    assert len(sha) == 64
    with tarfile.open(out) as tar:
        assert tar.getnames() == ["keep.py"]


def test_build_stamp_shape(repo: Path) -> None:
    stamp = artifact.build_stamp(
        repo_root=repo,
        artifact_sha="deadbeef",
        remote="dryg",
        deployed_at="2026-07-12T00:00:00Z",
    )
    assert stamp["artifact_sha256"] == "deadbeef"
    assert stamp["deployed_at"] == "2026-07-12T00:00:00Z"
    assert stamp["dirty"] in (True, False)
    assert "commit" in stamp and "short" in stamp and "branch" in stamp
    assert "pushed_to_dryg" in stamp
