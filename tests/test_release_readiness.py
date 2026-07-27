from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_version_file_exists_and_is_050() -> None:
    version_path = PROJECT_ROOT / "VERSION"
    assert version_path.exists()
    assert version_path.read_text(encoding="utf-8").strip() == "0.5.0"


def test_smoke_scripts_exist() -> None:
    assert (PROJECT_ROOT / "scripts" / "smoke_release.ps1").exists()
    assert (PROJECT_ROOT / "scripts" / "smoke_release.sh").exists()


def test_readme_contains_release_checklist_link() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/RELEASE_CHECKLIST.md" in readme


def test_dockerfile_includes_runtime_formula_cards_and_data_dirs() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY product /app/product" in dockerfile
    assert "COPY data /app/data" in dockerfile


def test_dockerfile_prebuilds_project_venv_for_container_startup() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python -m venv /app/.venv" in dockerfile
    assert "/app/.venv/bin/pip install --no-cache-dir -r /app/requirements.txt" in dockerfile


def test_server_compose_exposes_only_http_entrypoint() -> None:
    compose = (PROJECT_ROOT / "scripts" / "docker-compose.server.yml").read_text(encoding="utf-8")
    assert '"80:8014"' in compose
    assert '"8013:8013"' not in compose
    assert '"8014:8014"' not in compose


def test_api_container_runs_several_uvicorn_workers() -> None:
    """Два тестера считают параллельно только если API -- несколько процессов.

    Один процесс Python держит GIL, поэтому вторая задача не получит своё ядро,
    сколько бы их ни было у сервера.
    """
    start_script = (PROJECT_ROOT / "scripts" / "start_api_local.sh").read_text(encoding="utf-8")
    assert '--workers "${API_WORKERS:-1}"' in start_script

    for relative in ("docker-compose.yml", "scripts/docker-compose.server.yml"):
        compose = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert 'API_WORKERS: "2"' in compose, f"{relative}: не задано число воркеров API"


def test_web_ui_container_stays_single_process() -> None:
    """web_ui обязан остаться одним процессом.

    Реестр Pro-задач (_RECTIFICATION_PRO_JOBS) живёт в памяти процесса: с
    несколькими воркерами опрос статуса попадал бы в чужой процесс и задачи
    "терялись" бы через раз.
    """
    start_script = (PROJECT_ROOT / "scripts" / "start_web_ui.sh").read_text(encoding="utf-8")
    launch_lines = [line for line in start_script.splitlines() if "uvicorn web_ui.main:app" in line]
    assert launch_lines, "не нашёл строку запуска web_ui"
    assert all("--workers" not in line for line in launch_lines), launch_lines
    for relative in ("docker-compose.yml", "scripts/docker-compose.server.yml"):
        compose = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "WEB_UI_WORKERS" not in compose, f"{relative}: у web_ui не должно быть воркеров"
