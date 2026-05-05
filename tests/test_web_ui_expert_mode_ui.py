from __future__ import annotations

from fastapi.testclient import TestClient

import web_ui.main as web_ui_main


def test_expert_mode_block_contains_degree_format_toggle() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="expertObjects"' in html
    assert 'id="expertNodes"' in html
    assert 'id="expertAngles"' in html
    assert 'id="expertCusps"' in html
    assert 'id="expertAspects"' in html
    assert 'id="expertTimezone"' in html
    assert 'id="expertDegreesExpandedToggle"' in html
    assert "Расширенный формат градусов" in html

    tail = html.split('id="expertDegreesExpandedToggle"', 1)[1][:120]
    assert "checked" not in tail


def test_expert_mode_script_default_uses_short_dms_without_seconds() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "let expertDegreesExpanded = false;" in html
    assert "if (!includeSeconds)" in html
    assert "return degreeToDms(value, expertDegreesExpanded);" in html


def test_expert_mode_script_supports_expanded_dms_and_hides_decimal_by_default() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "expertDegreesExpanded = !!expertDegreesExpandedToggleEl.checked;" in html
    assert "formatDegreeForExpert(" in html
    assert "formatDegreePair(" not in html
    assert "toFixed(3)}°)" not in html


def test_stage1_final_ui_supports_multiple_time_ranges_and_pro_forwarding() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "time_ranges_local" in html
    assert "buildProAscWindowsFromStage1" in html
    assert "secondary_candidates" in html
    assert "Екатерина, благодарим вас за участие!" in html


def test_expert_mode_main_ui_shows_true_south_node_and_hides_mean_node_from_primary_tables() -> None:
    with TestClient(web_ui_main.app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '"true_south_node"' in html
    assert '"Истинный Южный узел"' in html
    assert '"Истинный Северный узел"' in html
    assert "Средний Северный узел (mean_node, debug)" not in html
