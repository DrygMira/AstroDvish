from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_bundle import get_main_ui_bundle
import web_ui.main as web_ui_main


def test_expert_table_uses_motion_phase_column_instead_of_retrograde() -> None:
    with TestClient(web_ui_main.app) as client:
        response, html = get_main_ui_bundle(client)

    assert response.status_code == 200
    assert "Фазы движения" in html
    assert "Ретроградность" not in html
    assert "resolveMotionPhase(" in html
    assert "S = стационарное" in html
