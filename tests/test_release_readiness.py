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

