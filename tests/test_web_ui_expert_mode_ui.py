from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_expert_mode_block_present_in_web_ui_html() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "Экспертная проверка карты" in html
    assert "Показать экспертную таблицу" in html
    assert 'id="expertObjects"' in html
    assert 'id="expertNodes"' in html
    assert 'id="expertAngles"' in html
    assert 'id="expertCusps"' in html
    assert 'id="expertAspects"' in html
    assert 'id="expertTimezone"' in html


def test_expert_mode_script_uses_required_chart_fields() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "obj.house" in html
    assert "houses.cusp_details" in html
    assert "true_node" in html
    assert "mean_node" in html
    assert "aspect.orb" in html
