from __future__ import annotations

from pathlib import Path


def test_project_state_mentions_confirmed_methodology_and_multiple_ranges() -> None:
    text = Path("docs/PROJECT_STATE.md").read_text(encoding="utf-8")
    assert "confirmed" in text.lower()
    assert "symbolic_1deg_per_year" in text
    assert "Directed source -> Natal target" in text
    assert "working_time_ranges" in text or "working ranges" in text.lower()
