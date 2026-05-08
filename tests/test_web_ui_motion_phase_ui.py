from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_expert_table_uses_motion_phase_column_instead_of_retrograde() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Фазы движения" in html
    assert "Ретроградность" not in html
    assert "resolveMotionPhase(" in html
    assert "S = стационарное" in html
