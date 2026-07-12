# Deploy Source-of-Truth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Один Python-инструмент `scripts/deploy.py`, который воспроизводимо выкладывает текущее рабочее дерево на боевой сервер, фиксирует на сервере что именно выкачено, проверяет health с авто-откатом и в одну команду показывает расхождение git-vs-live.

**Architecture:** Чистая логика сборки артефакта (список файлов, детект «грязного» дерева, детерминированный tar, метаданные-«бирка») вынесена в `scripts/deploylib/artifact.py` и покрыта юнит-тестами без сети. Работа с сервером (бэкап, заливка, распаковка, пересборка, health, откат) — в `scripts/deploylib/remote.py` через `paramiko`. CLI и оркестрация — в `scripts/deploy.py`. `paramiko` ставится только локально (`scripts/requirements-deploy.txt`) и НЕ попадает в серверный Docker-образ.

**Tech Stack:** Python 3.11 (`.venv`), `git` CLI, стандартный `tarfile`/`hashlib`, `paramiko` (локально), Docker Compose на сервере.

**Целевой сервер (значения по умолчанию, переопределяются env):** `root@45.133.18.90`, путь `/opt/astrodvish`, ключ `~/.ssh/auron_deploy`, remote `dryg`, контейнеры `astrodvish-api` / `astrodvish-web-ui`.

---

## File Structure

- Create: `scripts/deploylib/__init__.py` — пометка пакета.
- Create: `scripts/deploylib/artifact.py` — чистая логика (список файлов, dirty, commit-инфо, pushed, tar+sha, stamp). Без сети → юнит-тестируется.
- Create: `scripts/deploylib/remote.py` — SSH/SFTP-операции над сервером (paramiko).
- Create: `scripts/deploy.py` — CLI (`argparse`) + оркестрация режимов `--plan` / деплой / `--status` / `--rollback`.
- Create: `scripts/requirements-deploy.txt` — `paramiko` (локальная зависимость).
- Create: `tests/test_deploy_artifact.py` — юнит-тесты чистой логики `artifact.py`.
- Create: `docs/DEPLOY.md` — короткая инструкция по использованию.
- Modify: `.gitignore` — игнор временной папки артефактов `scripts/.deploy_tmp/`.

---

## Task 1: Скелет пакета и зависимость

**Files:**
- Create: `scripts/requirements-deploy.txt`
- Create: `scripts/deploylib/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Создать локальную зависимость деплоя**

`scripts/requirements-deploy.txt`:

```text
# Локальные зависимости инструмента деплоя (scripts/deploy.py).
# НЕ входят в серверный Docker-образ (Dockerfile ставит только requirements.txt).
paramiko==3.5.0
```

- [ ] **Step 2: Создать пакет deploylib**

`scripts/deploylib/__init__.py`:

```python
"""Библиотека инструмента деплоя AstroDvish (scripts/deploy.py)."""
```

- [ ] **Step 3: Игнорировать временную папку артефактов**

Добавить в конец `.gitignore`:

```text

# Временные артефакты инструмента деплоя
scripts/.deploy_tmp/
```

- [ ] **Step 4: Установить paramiko в .venv**

Run: `.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-deploy.txt`
Expected: `Successfully installed paramiko-3.5.0 ...` (или «already satisfied»).

- [ ] **Step 5: Commit**

```bash
git add scripts/requirements-deploy.txt scripts/deploylib/__init__.py .gitignore
git commit -m "Add deploy tool scaffold: deploylib package and local paramiko dep"
```

---

## Task 2: `artifact.py` — список файлов для деплоя

**Files:**
- Create: `scripts/deploylib/artifact.py`
- Test: `tests/test_deploy_artifact.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_deploy_artifact.py`:

```python
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
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError: module ... has no attribute 'list_deploy_files'`.

- [ ] **Step 3: Реализовать минимум**

`scripts/deploylib/artifact.py`:

```python
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
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/deploylib/artifact.py tests/test_deploy_artifact.py
git commit -m "Add deploy artifact file listing (tracked + new, ignore-aware)"
```

---

## Task 3: `artifact.py` — dirty-детект и commit-инфо

**Files:**
- Modify: `scripts/deploylib/artifact.py`
- Test: `tests/test_deploy_artifact.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_deploy_artifact.py`:

```python
def test_is_dirty_reflects_working_tree(repo: Path) -> None:
    assert artifact.is_dirty(repo) is False
    (repo / "keep.py").write_text("x = 2\n", encoding="utf-8")
    assert artifact.is_dirty(repo) is True


def test_commit_info_has_sha_short_branch(repo: Path) -> None:
    info = artifact.commit_info(repo)
    assert len(info["commit"]) == 40
    assert info["commit"].startswith(info["short"])
    assert info["branch"]  # непустая ветка
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: FAIL — `AttributeError: ... 'is_dirty'`.

- [ ] **Step 3: Реализовать**

Добавить в `scripts/deploylib/artifact.py`:

```python
def is_dirty(repo_root: Path) -> bool:
    """True, если в рабочем дереве есть незакоммиченные изменения."""
    return bool(_git(repo_root, "status", "--porcelain").strip())


def commit_info(repo_root: Path) -> dict[str, str]:
    """Текущий коммит: полный sha, короткий, имя ветки."""
    commit = _git(repo_root, "rev-parse", "HEAD").strip()
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return {"commit": commit, "short": commit[:7], "branch": branch}
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/deploylib/artifact.py tests/test_deploy_artifact.py
git commit -m "Add deploy dirty detection and commit info"
```

---

## Task 4: `artifact.py` — проверка «коммит запушен в remote»

**Files:**
- Modify: `scripts/deploylib/artifact.py`
- Test: `tests/test_deploy_artifact.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_deploy_artifact.py`:

```python
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py::test_is_pushed_to_remote -q`
Expected: FAIL — `AttributeError: ... 'is_pushed_to_remote'`.

- [ ] **Step 3: Реализовать**

Добавить в `scripts/deploylib/artifact.py`:

```python
def is_pushed_to_remote(repo_root: Path, remote: str, branch: str) -> bool:
    """True, если текущий HEAD содержится в <remote>/<branch> (уже запушен)."""
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    try:
        contains = _git(repo_root, "branch", "-r", "--contains", head).splitlines()
    except subprocess.CalledProcessError:
        return False
    target = f"{remote}/{branch}"
    return any(line.strip() == target for line in contains)
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/deploylib/artifact.py tests/test_deploy_artifact.py
git commit -m "Add deploy check: is HEAD pushed to remote branch"
```

---

## Task 5: `artifact.py` — детерминированный tar + content-sha

**Files:**
- Modify: `scripts/deploylib/artifact.py`
- Test: `tests/test_deploy_artifact.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_deploy_artifact.py`:

```python
import tarfile


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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: FAIL — `AttributeError: ... 'build_artifact'`.

- [ ] **Step 3: Реализовать**

Добавить в `scripts/deploylib/artifact.py` (импорты вверх файла):

```python
import hashlib
import io
import tarfile
```

и функцию:

```python
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
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/deploylib/artifact.py tests/test_deploy_artifact.py
git commit -m "Add deterministic deploy artifact tar with content sha256"
```

---

## Task 6: `artifact.py` — сборка «бирки» (stamp)

**Files:**
- Modify: `scripts/deploylib/artifact.py`
- Test: `tests/test_deploy_artifact.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/test_deploy_artifact.py`:

```python
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py::test_build_stamp_shape -q`
Expected: FAIL — `AttributeError: ... 'build_stamp'`.

- [ ] **Step 3: Реализовать**

Добавить в `scripts/deploylib/artifact.py`:

```python
def build_stamp(
    repo_root: Path,
    artifact_sha: str,
    remote: str,
    deployed_at: str,
) -> dict:
    """Метаданные для DEPLOYED.json (deployed_at передаётся снаружи — детерминизм в тестах)."""
    info = commit_info(repo_root)
    dirty = is_dirty(repo_root)
    pushed = is_pushed_to_remote(repo_root, remote, info["branch"])
    return {
        "commit": info["commit"],
        "short": info["short"],
        "branch": info["branch"],
        "dirty": dirty,
        f"pushed_to_{remote}": pushed,
        "artifact_sha256": artifact_sha,
        "deployed_at": deployed_at,
    }
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deploy_artifact.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/deploylib/artifact.py tests/test_deploy_artifact.py
git commit -m "Add deploy stamp (DEPLOYED.json metadata) builder"
```

---

## Task 7: `remote.py` — SSH-подключение и примитивы

**Files:**
- Create: `scripts/deploylib/remote.py`

Примечание: сетевые операции юнит-тестами не покрываем (нужен реальный сервер); модуль пишется аккуратно и проверяется на живом безопасном no-op деплое в Task 11.

- [ ] **Step 1: Реализовать подключение и примитивы**

`scripts/deploylib/remote.py`:

```python
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
```

- [ ] **Step 2: Проверить импорт**

Run: `.\.venv\Scripts\python.exe -c "from scripts.deploylib import remote; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add scripts/deploylib/remote.py
git commit -m "Add remote SSH primitives for deploy tool"
```

---

## Task 8: `remote.py` — бэкап, заливка, распаковка, подчистка, stamp

**Files:**
- Modify: `scripts/deploylib/remote.py`

- [ ] **Step 1: Реализовать операции деплоя**

Добавить в `scripts/deploylib/remote.py`:

```python
LEFTOVER_FILES = ["main.py", "api.js"]  # хвосты в корне от прежних ручных копирований


def backup(client, remote_path: str, backups_dir: str, tag: str, ts: str) -> str:
    """Снять tar-бэкап текущего live (без ephe и без каталога бэкапов). Вернуть путь бэкапа."""
    run(client, f"mkdir -p {q(backups_dir)}")
    backup_path = f"{backups_dir}/predeploy_{ts}_{tag}.tgz"
    base = Path(remote_path).name
    parent = str(Path(remote_path).parent)
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
```

- [ ] **Step 2: Проверить импорт**

Run: `.\.venv\Scripts\python.exe -c "from scripts.deploylib import remote; print(remote.LEFTOVER_FILES)"`
Expected: `['main.py', 'api.js']`.

- [ ] **Step 3: Commit**

```bash
git add scripts/deploylib/remote.py
git commit -m "Add remote deploy ops: backup, extract, leftovers cleanup, stamp"
```

---

## Task 9: `remote.py` — пересборка, health-gate, откат

**Files:**
- Modify: `scripts/deploylib/remote.py`

- [ ] **Step 1: Реализовать пересборку/health/откат**

Добавить в `scripts/deploylib/remote.py` (импорт `time` вверх файла):

```python
import time

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
    base = Path(remote_path).name
    parent = str(Path(remote_path).parent)
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
```

- [ ] **Step 2: Проверить импорт**

Run: `.\.venv\Scripts\python.exe -c "from scripts.deploylib import remote; print(remote.CONTAINERS)"`
Expected: `['astrodvish-api', 'astrodvish-web-ui']`.

- [ ] **Step 3: Commit**

```bash
git add scripts/deploylib/remote.py
git commit -m "Add remote compose rebuild, health gate and rollback"
```

---

## Task 10: `deploy.py` — CLI и оркестрация

**Files:**
- Create: `scripts/deploy.py`

- [ ] **Step 1: Реализовать CLI**

`scripts/deploy.py`:

```python
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
```

- [ ] **Step 2: Проверить `--plan` вживую (безопасно, без сети)**

Run: `.\.venv\Scripts\python.exe scripts/deploy.py --plan`
Expected: печатает коммит/ветку, «грязное дерево», «запушено в dryg», число файлов, цель, «сухой прогон — ничего не изменено». Кода выхода 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/deploy.py
git commit -m "Add deploy CLI: plan, deploy, status, rollback orchestration"
```

---

## Task 11: Документация и полный прогон тестов

**Files:**
- Create: `docs/DEPLOY.md`

- [ ] **Step 1: Написать короткую инструкцию**

`docs/DEPLOY.md`:

```markdown
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
```

- [ ] **Step 2: Полный прогон тестов**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: `375 passed, 1 xfailed` (374 прежних + новый файл `test_deploy_artifact.py` с 7 тестами; итог — все зелёные, 1 xfailed прежний).

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOY.md
git commit -m "Add deploy tool usage doc"
```

---

## Task 12: Живая проверка инструмента (ГЕЙТ — требует подтверждения пользователя)

Эта задача трогает боевой сервер. Выполнять только после явного «ок» пользователя. Безопасность: деплоим коммит, идентичный серверу по содержимому → по поведению это no-op, но проходит весь путь.

- [ ] **Step 1: Проверить статус ДО**

Run: `.\.venv\Scripts\python.exe scripts/deploy.py --status`
Expected: печатает live-версию (или «DEPLOYED.json отсутствует», т.к. первый раз). Ошибок соединения нет.

- [ ] **Step 2: Сухой прогон**

Run: `.\.venv\Scripts\python.exe scripts/deploy.py --plan`
Expected: адекватный список (коммит, ~N файлов, цель).

- [ ] **Step 3: Реальный no-op деплой текущего коммита**

Run: `.\.venv\Scripts\python.exe scripts/deploy.py --yes`
Expected: печатает путь бэкапа, «пересборка», «проверка health», `УСПЕХ`. Код выхода 0.

- [ ] **Step 4: Проверить статус ПОСЛЕ**

Run: `.\.venv\Scripts\python.exe scripts/deploy.py --status`
Expected: `СТАТУС: совпадает (git == live)`; short-хэш = локальный HEAD.

- [ ] **Step 5: Прогон боевого функционала (регресс не сломан)**

Повторить лёгкий live-check из этой сессии (8 событий × 8 карточек внутри web-ui контейнера) — combined report `completed`, все 8 карточек, Excel 200; default `child_birth` = `RECT_CHILD_BIRTH_001`; контейнеры healthy, 0 рестартов.

- [ ] **Step 6: Финальный статус-репорт пользователю** (что задеплоено, `DEPLOYED.json`, что бэкап на сервере). Коммитов на этом шаге нет.

---

## Self-Review

**1. Покрытие спеки:**
- §3 четыре режима (`--plan`/deploy/`--status`/`--rollback`) → Task 10. ✓
- §4.1 сборка артефакта (трекнутые+новые, исключения через .gitignore) → Task 2 + Task 5. ✓
- §4.2 гибкий guard (предупреждать, не блокировать) → Task 10 `cmd_deploy`. ✓
- §4.3 бэкап predeploy_*.tgz → Task 8 `backup`. ✓
- §4.4 stamp DEPLOYED.json + patch при dirty → Task 6 + Task 8 `write_stamp` + Task 10. ✓
- §4.5 распаковка + подчистка хвостов + поведение удаления → Task 8 `upload_and_extract`/`remove_leftovers`. ✓
- §4.6 пересборка + health-gate → Task 9 `compose_up`/`wait_healthy`. ✓
- §4.7 авто-откат при провале health → Task 9 `rollback` + Task 10. ✓
- §6 тесты (юнит artifact + безопасный e2e) → Tasks 2-6 (юнит) + Task 12 (e2e). ✓
- §7 критерии готовности (.env/ephe не тронуты) → артефакт исключает .env (gitignore), бэкап/rollback сохраняют ephe. ✓

**2. Плейсхолдеры:** нет TBD/TODO; код в каждом шаге полный.

**3. Согласованность типов/имён:** `list_deploy_files`, `is_dirty`, `commit_info`, `is_pushed_to_remote`, `build_artifact`, `build_stamp` — имена совпадают между определением (Tasks 2-6) и вызовами в `deploy.py` (Task 10). `remote.connect/run/put/read_text/write_text/backup/upload_and_extract/remove_leftovers/write_stamp/compose_up/wait_healthy/rollback` — совпадают между Tasks 7-9 и вызовами в Task 10. `build_stamp` кладёт ключ `pushed_to_dryg` (remote="dryg"), `cmd_status` его напрямую не читает — консистентно. ✓

Замечание по среде: тесты используют `git`; на машине он есть. Импорт `from scripts.deploylib import ...` требует запуск pytest из корня проекта (conftest/rootdir корень) — pytest уже так и запускается.
